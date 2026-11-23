"""ROS 2 adapter for perception, risk, and optional local navigation."""

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from math import atan2, hypot, isfinite
import json
from time import perf_counter
import uuid

import numpy as np
import rclpy
from geometry_msgs.msg import PoseStamped, TwistStamped
from nav_msgs.msg import OccupancyGrid, Odometry, Path
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import CameraInfo, Image, LaserScan
from std_msgs.msg import String, UInt8MultiArray
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformException, TransformListener

from .geometry import Config, Pose, cluster, fresh, summarize, track
from .global_plan import Grid, tracking_target
from .navigation import NAV_CONFIG, Decision, LocalNavigator, relative_goal
from .perception import Transform, observe_stereo, scan_from_values
from .protocol import encode
from .semantic_geometry import scene_objects


def stamp_ns(message):
    stamp = message.header.stamp
    return stamp.sec * 1_000_000_000 + stamp.nanosec


def image_array(message):
    if message.encoding == "mono8":
        pixels = np.frombuffer(bytes(message.data), dtype=np.uint8)
        return pixels.reshape(message.height, message.step)[:, :message.width]
    if message.encoding in ("rgb8", "bgr8"):
        import cv2
        raw = np.frombuffer(bytes(message.data), dtype=np.uint8).reshape(message.height, message.step)
        rgb = raw[:, :message.width*3].reshape(message.height, message.width, 3)
        code = cv2.COLOR_RGB2GRAY if message.encoding == "rgb8" else cv2.COLOR_BGR2GRAY
        return cv2.cvtColor(rgb, code)
    raise ValueError(f"unsupported image encoding {message.encoding}")


def camera_parameters(message):
    return {name: getattr(message, name) for name in ("width", "height", "p", "k", "r", "d", "distortion_model")}


def planar_pose(position, q):
    norm = q.x*q.x + q.y*q.y + q.z*q.z + q.w*q.w
    if not all(isfinite(value) for value in (position.x, position.y, norm)) or abs(norm - 1) >= 0.01:
        raise ValueError("invalid planar pose")
    return Pose(position.x, position.y,
                atan2(2 * (q.w*q.z + q.x*q.y), 1 - 2 * (q.y*q.y + q.z*q.z)))


class RiskNode(Node):
    def __init__(self):
        super().__init__("suixing_risk")
        self.declare_parameter("lifetime_ms", 100)
        self.declare_parameter("max_disparity", 0)
        self.declare_parameter("max_disparity_cap", 192)
        self.declare_parameter("min_depth_m", 0.25)
        self.declare_parameter("stereo_enabled", True)
        self.declare_parameter("semantic_association", False)
        self.declare_parameter("require_semantic_navigation", False)
        self.declare_parameter("semantic_max_age_ms", 500)
        self.declare_parameter("navigation_odom_age_ms", 30)
        self.declare_parameter("risk_period_ms", 50)
        self.declare_parameter("publish_wire_frame", False)
        self.directional_ttc = self.declare_parameter("publish_directional_ttc", False).value
        geometry_fields = ("curvature_per_m", "front_m", "back_m", "half_width_m")
        risk_defaults = Config()
        risk_shape = {name: self.declare_parameter(f"risk_{name}", getattr(risk_defaults, name)).value
                      for name in geometry_fields}
        if any(not isfinite(value) or value <= 0 for value in risk_shape.values()):
            raise ValueError("risk footprint and curvature must be positive and finite")
        self.risk_config = replace(risk_defaults, **risk_shape)
        self.declare_parameter("navigation_enabled", False)
        self.declare_parameter("navigation_speed_mps", 0.25)
        self.declare_parameter("goal_tolerance_m", 0.15)
        self.declare_parameter("navigation_frame", "odom")
        self.declare_parameter("global_planning", False)
        self.declare_parameter("map_frame", "map")
        self.declare_parameter("map_topic", "/map")
        self.declare_parameter("map_occupied_threshold", 65)
        self.declare_parameter("path_lookahead_m", 1.2)
        self.declare_parameter("navigation_curvature_per_m", NAV_CONFIG.curvature_per_m)
        self.declare_parameter("navigation_front_m", NAV_CONFIG.front_m)
        self.declare_parameter("navigation_back_m", NAV_CONFIG.back_m)
        self.declare_parameter("navigation_half_width_m", NAV_CONFIG.half_width_m)
        self.nav = self.get_parameter("navigation_enabled").value
        self.nav_speed = self.get_parameter("navigation_speed_mps").value
        self.goal_tolerance = self.get_parameter("goal_tolerance_m").value
        self.nav_frame = self.get_parameter("navigation_frame").value
        self.global_planning = self.nav and self.get_parameter("global_planning").value
        self.map_frame = self.get_parameter("map_frame").value
        self.goal_frame = self.map_frame if self.global_planning else self.nav_frame
        self.grid = None
        self.map_key = None
        self.route = ()
        self.route_index = 1
        self.failed_plan = None
        self.plan_job = None
        self.planner = None
        self.path_publisher = None
        self.require_semantic = self.get_parameter("require_semantic_navigation").value
        self.semantic_age = self.get_parameter("semantic_max_age_ms").value
        self.odom_age = self.get_parameter("navigation_odom_age_ms").value
        period = self.get_parameter("risk_period_ms").value
        if (not 0 < self.semantic_age <= 1000 or not 0 < self.odom_age <= 100
                or not 10 <= period <= 100 or
                (self.require_semantic and not self.get_parameter("semantic_association").value)):
            raise ValueError("invalid navigation freshness configuration")
        self.lifetime = self.get_parameter("lifetime_ms").value
        self.stereo_backend = self.declare_parameter("stereo_backend", "sad").value
        if self.stereo_backend not in ("sad", "sgbm"):
            raise ValueError("stereo_backend must be sad or sgbm")
        self.max_disparity = self.get_parameter("max_disparity").value
        self.max_disparity_cap = self.get_parameter("max_disparity_cap").value
        self.min_depth_m = self.get_parameter("min_depth_m").value
        if (self.lifetime <= 0 or self.max_disparity < 0 or self.max_disparity_cap < 2
                or not 0.05 <= self.min_depth_m <= 5.0):
            raise ValueError("invalid lifetime_ms, disparity bounds or min_depth_m")
        self.tf = Buffer(node=self)
        self.tf_listener = TransformListener(self.tf, self)
        self.publisher = self.create_publisher(String, "/suixing/risk_summary", 10)
        self.perception_diagnostics = None
        if self.declare_parameter("publish_perception_diagnostics", False).value:
            self.perception_diagnostics = self.create_publisher(String, "/suixing/perception_diagnostics", 5)
        self.wire_publisher = None
        if self.get_parameter("publish_wire_frame").value:
            self.wire_publisher = self.create_publisher(
                UInt8MultiArray, "/suixing/risk_frame", 10)
        self.scene_publisher = None
        if self.get_parameter("semantic_association").value:
            self.scene_publisher = self.create_publisher(String, "/suixing/scene_objects", 5)
            self.create_subscription(String, "/suixing/detections", self.receive_detections, 5)
            try:
                from vision_msgs.msg import Detection2DArray
            except ImportError:
                self.get_logger().warning(
                    "vision_msgs not installed; semantic association uses JSON detections only")
            else:
                self.create_subscription(
                    Detection2DArray, "/suixing/detections_2d", self.receive_detections_2d,
                    qos_profile_sensor_data)
        self.nav_command = None
        self.navigator = None
        if self.nav:
            if not (0 < self.nav_speed <= 0.30 and 0 < self.goal_tolerance <= 0.5
                    and self.nav_frame):
                raise ValueError("invalid navigation speed, goal tolerance or frame")
            shape = {field: self.get_parameter(f"navigation_{field}").value
                     for field in geometry_fields}
            if any(not isfinite(value) or value <= 0 for value in shape.values()):
                raise ValueError("navigation footprint and curvature must be positive and finite")
            self.navigator = LocalNavigator(self.nav_speed, self.goal_tolerance,
                                            replace(NAV_CONFIG, **shape))
            self.nav_command = self.create_publisher(TwistStamped, "/suixing/cmd_vel_candidate", 1)
            self.nav_status = self.create_publisher(String, "/suixing/navigation_status", 1)
            self.create_subscription(PoseStamped, "/suixing/navigation_goal", self.receive_goal, 1)
            self.create_service(Trigger, "/suixing/cancel_navigation", self.cancel_navigation)
        if self.global_planning:
            self.map_threshold = self.get_parameter("map_occupied_threshold").value
            self.lookahead = self.get_parameter("path_lookahead_m").value
            if (not self.map_frame or self.map_frame == self.nav_frame
                    or not 1 <= self.map_threshold <= 100
                    or not 0.1 <= self.lookahead <= 10):
                raise ValueError("invalid global planning parameters")
            self.planner = ThreadPoolExecutor(max_workers=1)
            map_qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
            self.path_publisher = self.create_publisher(Path, "/suixing/global_path", map_qos)
            self.create_subscription(OccupancyGrid, self.get_parameter("map_topic").value,
                                     self.receive_map, map_qos)
        self.buffers = {}
        self.received = {}
        topics = {"scan": (LaserScan, "/d6/scan"), "odom": (Odometry, "/odom")}
        if self.get_parameter("stereo_enabled").value:
            for side in ("left", "right"):
                topics[side] = (Image, f"/stereo/{side}/image_raw")
                topics[f"{side}_info"] = (CameraInfo, f"/stereo/{side}/camera_info")
        for name, (kind, topic) in topics.items():
            self.buffers[name] = deque(maxlen=8)
            self.create_subscription(kind, topic, lambda message, name=name: self.receive(name, message),
                                     qos_profile_sensor_data)
        self.reset()
        self.last_now = 0
        self.timer = self.create_timer(period / 1000, self.publish_risk)

    def reset(self):
        if self.navigator is not None:
            self.navigator.reset()
        self.goal = None
        self.invalidate_route()
        self.matched_scene = None
        self.session = uuid.uuid4().hex
        self.seq = 0
        self.scan = None
        self.stereo = None
        self.tracks = None
        self.previous_cluster = None
        self.previous_pose = None
        self.stereo_stamp = None
        self.stereo_profile = None
        self.processed_scans = deque(maxlen=8)
        self.received.clear()
        if self.scene_publisher is not None:
            self.pixel_history = deque(maxlen=24)
            self.semantic_history = deque(maxlen=8)

    def receive(self, name, message):
        """Buffer a message and remember when the node actually saw it."""
        stamp = stamp_ns(message)
        self.received[(name, stamp)] = self.get_clock().now().nanoseconds
        self.buffers[name].append(message)

    def receive_detections_2d(self, message):
        try:
            payload = {
                "stamp_ns": stamp_ns(message),
                "frame_id": message.header.frame_id,
                "image_width": None,
                "image_height": None,
                "detections": [],
            }
            if payload["stamp_ns"] <= 0 or not payload["frame_id"]:
                return
            for item in message.detections:
                if item.header != message.header or not item.results:
                    continue
                best = max(item.results, key=lambda result: result.hypothesis.score)
                label, score = best.hypothesis.class_id, best.hypothesis.score
                box = item.bbox
                x1 = box.center.position.x - box.size_x / 2.0
                y1 = box.center.position.y - box.size_y / 2.0
                x2 = box.center.position.x + box.size_x / 2.0
                y2 = box.center.position.y + box.size_y / 2.0
                if (not isinstance(label, str) or not label
                        or not 0.0 <= score <= 1.0 or box.size_x <= 0 or box.size_y <= 0
                        or not all(isfinite(n) for n in (x1, y1, x2, y2))):
                    continue
                payload["detections"].append({
                    "label": label, "confidence": float(score), "xyxy": [x1, y1, x2, y2],
                    "track_id": item.id,
                })
        except (AttributeError, TypeError, ValueError):
            return
        self.semantic_history.append(payload)

    def receive_detections(self, message):
        try:
            if len(message.data) > 128_000:
                return
            payload = json.loads(message.data)
        except (ValueError, RecursionError):
            return
        if (not isinstance(payload, dict) or type(payload.get("stamp_ns")) is not int
                or payload["stamp_ns"] <= 0 or not isinstance(payload.get("frame_id"), str)
                or not payload["frame_id"] or not isinstance(payload.get("detections"), list)):
            return
        width, height = payload.get("image_width"), payload.get("image_height")
        if (width is not None or height is not None) and not (
                type(width) is int and width > 0 and type(height) is int and height > 0):
            return
        self.semantic_history.append(payload)

    def publish_scene(self, now, odom=None):
        """Associate same-frame detections, then compensate ego motion in odom."""
        if self.scene_publisher is None:
            return None
        current = self.stereo.stamp_ns if self.stereo is not None else None
        for _ in range(len(self.semantic_history)):
            message = self.semantic_history.popleft()
            stamp = message["stamp_ns"]
            if not fresh(stamp, self.semantic_age, now):
                continue
            frame = message["frame_id"]
            pixels = next((pixels for t, f, pixels in self.pixel_history if (t, f) == (stamp, frame)), None)
            if pixels is None:
                self.semantic_history.append(message)
                continue
            width, height = message.get("image_width"), message.get("image_height")
            if width is not None and (pixels.width, pixels.height) != (width, height):
                continue
            supported = scene_objects(message["detections"], pixels)
            self.scene_publisher.publish(String(data=json.dumps({
                "stamp_ns": stamp,
                "frame_id": "base_link",
                "image_frame_id": frame,
                "objects": supported,
            }, allow_nan=False)))
            if self.matched_scene is None or stamp >= self.matched_scene[0]:
                self.matched_scene = (stamp, supported)
        if self.matched_scene is None:
            return None
        stamp, supported = self.matched_scene
        if not fresh(stamp, self.semantic_age, now):
            return None
        if stamp == current:
            return supported
        if odom is None or odom.header.frame_id != self.nav_frame:
            return None
        if not supported:
            return []
        try:
            at = Time(nanoseconds=stamp, clock_type=self.get_clock().clock_type)
            tf = self.tf.lookup_transform(self.nav_frame, "base_link", at).transform
            old = planar_pose(tf.translation, tf.rotation)
            present = planar_pose(odom.pose.pose.position, odom.pose.pose.orientation)
        except (TransformException, ValueError):
            return None
        uncertainty = 1.5 * (now - stamp) / 1e9
        return [dict(obj, position_m=[*relative_goal(old.apply(*obj["position_m"][:2]), present),
                                      obj["position_m"][2]], extra_radius_m=uncertainty)
                for obj in supported]

    def transform(self, frame, stamp):
        at = Time(nanoseconds=stamp, clock_type=self.get_clock().clock_type)
        tf = self.tf.lookup_transform("base_link", frame, at).transform
        t, q = tf.translation, tf.rotation
        return Transform((t.x, t.y, t.z), (q.x, q.y, q.z, q.w))

    def find_odometry(self, stamp, *, latest_ns=None):
        limit = self.odom_age * 1_000_000
        latest = stamp if latest_ns is None else latest_ns
        nearby = []
        for msg in self.buffers["odom"]:
            sample = stamp_ns(msg)
            difference = stamp - sample
            if (0 < sample <= latest and msg.header.frame_id == self.nav_frame
                    and msg.child_frame_id == "base_link" and abs(difference) < limit
                    and isfinite(msg.twist.twist.linear.x)):
                nearby.append(msg)
        return min(nearby, key=lambda msg: abs(stamp_ns(msg) - stamp), default=None)

    def update_scan(self, now):
        for msg in sorted(self.buffers["scan"], key=stamp_ns):
            stamp = stamp_ns(msg)
            if (stamp in self.processed_scans or not fresh(stamp, self.lifetime, now)
                    or (self.scan is not None and stamp <= self.scan.stamp_ns)):
                continue
            try:
                scan = scan_from_values(stamp, self.lifetime, msg.angle_min, msg.angle_increment,
                                        msg.range_min, msg.range_max, msg.ranges,
                                        self.transform(msg.header.frame_id, stamp),
                                        self.received.get(("scan", stamp)))
            except TransformException:
                continue
            except ValueError as error:
                self.get_logger().warning(f"D6 observation rejected: {error}")
                self.processed_scans.append(stamp)
                continue
            detections = cluster(scan)
            odom = self.find_odometry(stamp, latest_ns=now)
            pose = None
            if odom is not None:
                try:
                    measured = odom.pose.pose
                    pose = (odom.header.frame_id, planar_pose(measured.position, measured.orientation))
                except ValueError:
                    pass  # Keep obstacle positions, but omit velocity from invalid ego poses.
            if pose is not None and self.previous_pose is not None and pose[0] == self.previous_pose[0]:
                elapsed = (stamp - self.scan.stamp_ns) / 1e9
                self.tracks = track(detections, self.previous_cluster, elapsed, pose[1], self.previous_pose[1])
            else:
                self.tracks = detections
            if self.scan is None:
                self.get_logger().info(f"D6 frame accepted at {stamp}")
            self.previous_pose, self.previous_cluster = pose, detections
            self.scan = scan
            self.processed_scans.append(stamp)

    def update_stereo(self, now):
        if "left" not in self.buffers:
            return
        by_stamp = {name: {stamp_ns(msg): msg for msg in self.buffers[name]}
                    for name in ("left", "right", "left_info", "right_info")}
        stamps = set.intersection(*(set(messages) for messages in by_stamp.values()))
        for stamp in sorted(stamps, reverse=True):
            if self.stereo_stamp is not None and stamp <= self.stereo_stamp:
                return
            if not fresh(stamp, self.lifetime, now):
                continue
            left, right, li, ri = (by_stamp[name][stamp] for name in ("left", "right", "left_info", "right_info"))
            started = perf_counter() if self.perception_diagnostics is not None else None
            try:
                if left.header.frame_id != li.header.frame_id or right.header.frame_id != ri.header.frame_id:
                    raise ValueError("image frame differs from CameraInfo")
                transform = self.transform(left.header.frame_id, stamp)
                self.transform(right.header.frame_id, stamp)
                evidence, metrics = observe_stereo(image_array(left), image_array(right),
                                                   camera_parameters(li), camera_parameters(ri),
                                                   transform, stamp, self.lifetime,
                                                   self.max_disparity or None, self.min_depth_m,
                                                   self.received.get(("left", stamp)),
                                                   capture_pixels=self.scene_publisher is not None,
                                                   max_disparity_cap=self.max_disparity_cap,
                                                   disparity_backend=self.stereo_backend)
                if self.stereo is None:
                    self.get_logger().info(
                        f"Stereo pair accepted at {stamp}, median disparity {metrics['median_disparity_px']} px")
                self.stereo = evidence
                if started is not None:
                    self.stereo_profile = {
                        "stamp_ns": stamp,
                        "processing_ms": round((perf_counter() - started) * 1000, 3),
                        **{key: value for key, value in metrics.items() if key != "stereo_pixels"},
                    }
                if self.scene_publisher is not None:
                    self.pixel_history.append((stamp, left.header.frame_id, metrics["stereo_pixels"]))
            except TransformException:
                return
            except (ImportError, ValueError) as error:
                self.stereo = None
                self.stereo_profile = None
                self.get_logger().warning(f"stereo observation rejected: {error}")
            self.stereo_stamp = stamp
            return

    def publish_path(self):
        if self.path_publisher is None:
            return
        path = Path()
        path.header.frame_id = self.map_frame
        path.header.stamp = self.get_clock().now().to_msg()
        for x, y in self.route:
            waypoint = PoseStamped()
            waypoint.header = path.header
            waypoint.pose.position.x = x
            waypoint.pose.position.y = y
            waypoint.pose.orientation.w = 1.0
            path.poses.append(waypoint)
        self.path_publisher.publish(path)

    def invalidate_route(self):
        if self.plan_job is not None:
            self.plan_job[0].cancel()
            # Keep a running job until it finishes, but discard its result.
            self.plan_job = self.plan_job[0], None, None
        had_route = bool(self.route)
        self.route = ()
        self.route_index = 1
        self.failed_plan = None
        if had_route:
            self.publish_path()

    def receive_map(self, message):
        if message.header.frame_id != self.map_frame:
            return
        info = message.info
        try:
            origin = planar_pose(info.origin.position, info.origin.orientation)
            key = (info.width, info.height, info.resolution, origin, message.data.tobytes())
            if key == self.map_key:
                return
            config = self.navigator.config
            radius = hypot(max(config.front_m, config.back_m), config.half_width_m) + config.margin_m
            self.grid = Grid(info.width, info.height, info.resolution, origin,
                             message.data, radius, self.map_threshold)
            self.map_key = key
        except (ImportError, ValueError) as error:
            self.grid = None
            self.map_key = None
            self.get_logger().warning(f"map rejected: {error}", throttle_duration_sec=5.0)
        self.invalidate_route()
        self.navigator.reset()

    def map_pose(self, odom_pose, stamp):
        when = Time(nanoseconds=stamp, clock_type=self.get_clock().clock_type)
        tf = self.tf.lookup_transform(self.map_frame, self.nav_frame, when).transform
        transform = planar_pose(tf.translation, tf.rotation)
        return Pose(*transform.apply(odom_pose.x, odom_pose.y), transform.yaw + odom_pose.yaw)

    def follow_map(self, pose, speed, now, objects):
        if self.grid is None:
            return Decision(reason="waiting_for_map")
        grid = self.grid
        start = pose.x, pose.y
        if self.plan_job is not None and self.plan_job[0].done():
            job, job_grid, job_goal = self.plan_job
            self.plan_job = None
            if job_grid is grid and job_goal == self.goal:
                try:
                    self.route = job.result()
                except (ValueError, RuntimeError) as error:
                    self.get_logger().error(f"global planning failed: {error}")
                    self.route = ()
                self.route_index = 1
                self.failed_plan = None if self.route else grid.cell(start)
                self.publish_path()
        if not grid.open(*grid.cell(start)):
            self.invalidate_route()
            return Decision(reason="map_pose_blocked")
        if self.route:
            self.route_index, target = tracking_target(
                grid, self.route, self.route_index, pose, self.lookahead)
            if target is not None:
                return self.navigator.choose(
                    target, pose, speed, now, self.scan, self.stereo, self.tracks, objects,
                    intermediate=self.route_index < len(self.route) - 1,
                    arc_check=lambda speed, curvature, seconds: grid.arc_clear(
                        pose, speed, curvature, seconds))
            self.invalidate_route()
            self.navigator.reset()
        if self.failed_plan == grid.cell(start):
            return Decision(reason="no_global_path")
        if self.plan_job is None:
            job = self.planner.submit(grid.plan, start, self.goal)
            self.plan_job = job, grid, self.goal
        return Decision(reason="planning")

    def receive_goal(self, message):
        self.invalidate_route()
        self.navigator.reset()
        position = message.pose.position
        stamp = stamp_ns(message)
        now = self.get_clock().now().nanoseconds
        if (message.header.frame_id != self.goal_frame or not 0 < stamp <= now
                or not fresh(stamp, 2000, now)
                or not all(isfinite(value) for value in (position.x, position.y))):
            self.goal = None
            return
        self.goal = position.x, position.y

    def cancel_navigation(self, _request, response):
        self.goal = None
        self.invalidate_route()
        self.navigator.reset()
        self.publish_navigation(None, self.get_clock().now().nanoseconds, None, None)
        response.success = True
        response.message = "Navigation goal cleared"
        return response

    def publish_navigation(self, odom, now, speed, objects):
        decision = Decision(reason="missing_goal_or_odometry")
        if (self.goal is not None and odom is not None and odom.header.frame_id == self.nav_frame
                and fresh(stamp_ns(odom), self.odom_age, now)):
            try:
                pose = planar_pose(odom.pose.pose.position, odom.pose.pose.orientation)
                if self.require_semantic and objects is None:
                    decision = Decision(reason="waiting_for_semantics")
                elif self.global_planning:
                    decision = self.follow_map(self.map_pose(pose, stamp_ns(odom)), speed, now, objects)
                else:
                    decision = self.navigator.choose(self.goal, pose, speed, now,
                                                     self.scan, self.stereo, self.tracks, objects)
            except TransformException:
                decision = Decision(reason="waiting_for_map_tf")
            except (ValueError, OverflowError):
                decision = Decision(reason="invalid_navigation_pose")
            if decision.speed:
                deadline = min(decision.valid_until_ns, stamp_ns(odom) + self.odom_age * 1_000_000)
                if self.require_semantic and self.matched_scene is not None:
                    deadline = min(deadline, self.matched_scene[0] + self.semantic_age * 1_000_000)
                decision = replace(decision, valid_until_ns=deadline)
        if decision.reason == "reached":
            self.goal = None
            self.invalidate_route()
        publish_ns = self.get_clock().now().nanoseconds
        if decision.speed and not now <= publish_ns < decision.valid_until_ns:
            decision = Decision(reason="expired_during_compute")
        command = TwistStamped()
        command.header.stamp = Time(nanoseconds=now, clock_type=self.get_clock().clock_type).to_msg()
        command.header.frame_id = "base_link"
        command.twist.linear.x = decision.speed
        command.twist.angular.z = decision.yaw_rate
        self.nav_command.publish(command)
        self.nav_status.publish(String(data=json.dumps({
            "reason": decision.reason, "valid_until_ns": decision.valid_until_ns,
            "stamp_ns": now,
        })))

    def publish_risk(self):
        now = self.get_clock().now().nanoseconds
        if now == 0:
            return
        if now < self.last_now:
            for history in self.buffers.values():
                history.clear()
            self.reset()
        self.last_now = now
        started = perf_counter() if self.perception_diagnostics is not None else None
        self.update_scan(now)
        self.update_stereo(now)
        now = self.get_clock().now().nanoseconds
        if now < self.last_now:
            return  # Reset this session on the next timer tick after the clock jump.
        odom = self.find_odometry(now)
        speed = odom.twist.twist.linear.x if odom is not None else None
        objects = self.publish_scene(now, odom)
        self.seq += 1
        summary = summarize(self.session, self.seq, now, self.scan, self.stereo, speed,
                            self.tracks, self.risk_config, semantic=objects,
                            include_directional_ttc=self.directional_ttc)
        self.publisher.publish(String(data=json.dumps(summary, allow_nan=False)))
        if self.wire_publisher is not None:
            try:
                self.wire_publisher.publish(UInt8MultiArray(data=list(encode(summary, now))))
            except ValueError as error:
                self.get_logger().warning(
                    f"Risk frame not published: {error}", throttle_duration_sec=5.0)
        if self.nav:
            self.publish_navigation(odom, now, speed, objects)
        if started is not None:
            self.publish_diagnostics(summary, now, started, odom, objects)
        for key, seen in list(self.received.items()):
            if now - seen > 2_000_000_000:
                del self.received[key]


    def publish_diagnostics(self, summary, now, started, odom, objects):
        profile = self.stereo_profile if summary["stereo_valid"] else None
        self.perception_diagnostics.publish(String(data=json.dumps({
            "stamp_ns": now,
            "session_id": summary["session_id"],
            "seq": summary["seq"],
            "pipeline_ms": round((perf_counter() - started) * 1000, 3),
            "stereo_backend": self.stereo_backend,
            "stereo": profile,
            "scan_valid": summary["scan_valid"],
            "stereo_valid": summary["stereo_valid"],
            "aligned": summary["aligned"],
            "lidar_stereo_skew_ms": (abs(self.scan.stamp_ns - self.stereo.stamp_ns) / 1e6
                                    if summary["scan_valid"] and summary["stereo_valid"] else None),
            "odom_age_ms": (now - stamp_ns(odom)) / 1e6 if odom is not None else None,
            "semantic_age_ms": (now - self.matched_scene[0]) / 1e6 if objects is not None else None,
        }, allow_nan=False)))


def main(args=None):
    rclpy.init(args=args)
    node = RiskNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node.planner is not None:
            node.planner.shutdown(wait=False, cancel_futures=True)
        node.destroy_node()
        rclpy.try_shutdown()
