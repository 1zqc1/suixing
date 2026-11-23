"""Optional ROS 2 YOLOv8 node for camera semantics and debug images."""

from array import array
import hashlib
import json
from math import isfinite
from threading import Lock
from time import perf_counter

import numpy as np
import rclpy
from rclpy.callback_groups import MutuallyExclusiveCallbackGroup
from rclpy.clock import Clock, ClockType
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import String

from .semantic import YoloV8Detector, annotate_image
from .tracker import IouTracker


def image_bgr(message):
    channels = {"mono8": 1, "rgb8": 3, "bgr8": 3}.get(message.encoding)
    if channels is None:
        raise ValueError(f"unsupported image encoding {message.encoding!r}")
    row_bytes = message.width * channels
    pixels = np.frombuffer(message.data, dtype=np.uint8)
    if (message.width <= 0 or message.height <= 0 or message.step < row_bytes
            or pixels.size != message.height * message.step):
        raise ValueError("invalid image dimensions, stride or data length")
    rows = pixels.reshape(message.height, message.step)[:, :row_bytes]
    if channels == 1:
        return np.repeat(rows[:, :, None], 3, axis=2)
    color = rows.reshape(message.height, message.width, 3)
    if message.encoding == "rgb8":
        color = color[:, :, ::-1]
    return np.ascontiguousarray(color)


class SemanticNode(Node):
    def __init__(self):
        super().__init__("suixing_semantic")
        self.declare_parameter("model_path", "")
        self.declare_parameter("image_topic", "/stereo/left/image_raw")
        self.declare_parameter("confidence", 0.25)
        self.declare_parameter("iou_threshold", 0.45)
        self.declare_parameter("inference_hz", 5.0)
        self.declare_parameter("publish_annotated", False)
        self.declare_parameter("publish_vision_msgs", True)
        self.declare_parameter("model_version", "")
        self.declare_parameter("track_iou", 0.3)
        self.declare_parameter("track_max_age", 5)
        model_path = self.get_parameter("model_path").value
        image_topic = self.get_parameter("image_topic").value
        inference_hz = self.get_parameter("inference_hz").value
        if not model_path:
            raise ValueError("set model_path to a local YOLOv8 detection ONNX model")
        if not isfinite(inference_hz) or not 0.1 <= inference_hz <= 60.0:
            raise ValueError("inference_hz must be between 0.1 and 60 Hz")
        self.detector = YoloV8Detector(
            model_path,
            confidence=self.get_parameter("confidence").value,
            iou=self.get_parameter("iou_threshold").value,
        )
        if self.get_parameter("model_version").value:
            self.model_version = self.get_parameter("model_version").value
        else:
            with open(model_path, "rb") as handle:
                self.model_version = hashlib.sha256(handle.read()).hexdigest()[:16]
        self.tracker = IouTracker(self.get_parameter("track_iou").value,
                                  self.get_parameter("track_max_age").value)

        self.latest = None
        self.lock = Lock()
        self.input_group = MutuallyExclusiveCallbackGroup()
        self.inference_group = MutuallyExclusiveCallbackGroup()
        latest_image_qos = QoSProfile(
            depth=1,
            history=qos_profile_sensor_data.history,
            reliability=qos_profile_sensor_data.reliability,
            durability=qos_profile_sensor_data.durability,
        )
        self.create_subscription(
            Image, image_topic, self.receive_image, latest_image_qos, callback_group=self.input_group,
        )
        self.publisher = self.create_publisher(String, "/suixing/detections", 10)
        self.model_publisher = self.create_publisher(
            String, "/suixing/detection_model",
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
        )
        self.model_publisher.publish(String(data=json.dumps(
            {"model_version": self.model_version}, allow_nan=False)))
        self.vision_publisher = None
        if self.get_parameter("publish_vision_msgs").value:
            try:
                from vision_msgs.msg import Detection2DArray
            except ImportError:
                self.get_logger().warning(
                    "vision_msgs not installed; publishing JSON detections only")
            else:
                self.vision_publisher = self.create_publisher(
                    Detection2DArray, "/suixing/detections_2d", latest_image_qos)
        self.annotated_publisher = None
        if self.get_parameter("publish_annotated").value:
            self.annotated_publisher = self.create_publisher(
                Image, "/suixing/detections/image", latest_image_qos,
            )
        self.create_timer(
            1.0 / inference_hz, self.process_latest,
            callback_group=self.inference_group, clock=Clock(clock_type=ClockType.STEADY_TIME),
        )
        self.get_logger().info(f"YOLOv8 inference ready on {image_topic} ({inference_hz:g} Hz limit)")

    def receive_image(self, message):
        with self.lock:
            self.latest = message

    def process_latest(self):
        with self.lock:
            message, self.latest = self.latest, None
        if message is None:
            return

        stamp = message.header.stamp
        stamp_ns = stamp.sec * 1_000_000_000 + stamp.nanosec
        started = perf_counter()
        try:
            image = image_bgr(message)
            detections = self.detector.detect(image)
            track_ids = self.tracker.update([detection.xyxy for detection in detections])
            now_ns = self.get_clock().now().nanoseconds
            payload = {
                "stamp_ns": stamp_ns,
                "frame_id": message.header.frame_id,
                "image_width": message.width,
                "image_height": message.height,
                "model_version": self.model_version,
                "inference_ms": round((perf_counter() - started) * 1e3, 2),
                "inference_age_ms": round((now_ns - stamp_ns) / 1e6, 2) if now_ns else None,
                "detections": [dict(detection.as_dict(), track_id=track_id)
                               for detection, track_id in zip(detections, track_ids)],
            }
            serialized = json.dumps(payload, allow_nan=False)
        except Exception as error:
            self.get_logger().warning(
                f"YOLOv8 could not process frame {stamp_ns}: {error}", throttle_duration_sec=5.0,
            )
            return
        self.publisher.publish(String(data=serialized))
        if self.vision_publisher is not None:
            try:
                self.vision_publisher.publish(
                    detection_array(message.header, detections, track_ids))
            except Exception as error:
                self.get_logger().warning(
                    f"Could not publish Detection2DArray for {stamp_ns}: {error}",
                    throttle_duration_sec=5.0,
                )
        if self.annotated_publisher is not None and self.annotated_publisher.get_subscription_count():
            try:
                annotated = annotate_image(image, detections)
            except Exception as error:
                self.get_logger().warning(
                    f"Could not annotate frame {stamp_ns}: {error}", throttle_duration_sec=5.0,
                )
                return
            self.annotated_publisher.publish(Image(
                header=message.header, height=message.height, width=message.width,
                encoding="bgr8", is_bigendian=0, step=3 * message.width,
                data=array("B", annotated.tobytes()),
            ))


def detection_array(header, detections, track_ids):
    """Standard 2D detection message; coordinates stay in image pixels."""
    from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose

    message = Detection2DArray()
    message.header = header
    for detection, track_id in zip(detections, track_ids):
        item = Detection2D()
        item.header = header
        item.id = str(track_id)
        x1, y1, x2, y2 = detection.xyxy
        item.bbox.center.position.x = (x1 + x2) / 2.0
        item.bbox.center.position.y = (y1 + y2) / 2.0
        item.bbox.size_x = x2 - x1
        item.bbox.size_y = y2 - y1
        hypothesis = ObjectHypothesisWithPose()
        hypothesis.hypothesis.class_id = detection.label
        hypothesis.hypothesis.score = detection.confidence
        item.results.append(hypothesis)
        message.detections.append(item)
    return message


def main(args=None):
    rclpy.init(args=args)
    node = None
    executor = MultiThreadedExecutor(num_threads=2)
    try:
        node = SemanticNode()
        executor.add_node(node)
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        executor.shutdown()
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()
