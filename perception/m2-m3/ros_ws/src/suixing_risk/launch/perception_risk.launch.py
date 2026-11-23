"""Start the CPU3-facing perception and risk publishers."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

from suixing_risk.geometry import Config


def generate_launch_description():
    model = LaunchConfiguration("model_path")
    clock = ParameterValue(LaunchConfiguration("use_sim_time"), value_type=bool)
    yolo = LaunchConfiguration("enable_yolo")
    defaults = Config()
    dimensions = {f"risk_{name}": getattr(defaults, name)
                  for name in ("curvature_per_m", "front_m", "back_m", "half_width_m")}
    return LaunchDescription([
        *(DeclareLaunchArgument(name, default_value=str(value))
          for name, value in dimensions.items()),
        DeclareLaunchArgument("stereo_backend", default_value="sad"),
        DeclareLaunchArgument("min_depth_m", default_value="0.25"),
        DeclareLaunchArgument("max_disparity_cap", default_value="192"),
        DeclareLaunchArgument("publish_perception_diagnostics", default_value="false"),
        DeclareLaunchArgument("navigation_odom_age_ms", default_value="30"),
        DeclareLaunchArgument("model_path", default_value=""),
        DeclareLaunchArgument("enable_yolo", default_value="true"),
        DeclareLaunchArgument("use_sim_time", default_value="false"),
        Node(package="suixing_risk", executable="semantic_node", condition=IfCondition(yolo),
             parameters=[{"model_path": model, "use_sim_time": clock}], output="screen"),
        Node(package="suixing_risk", executable="risk_node",
             parameters=[{"semantic_association": ParameterValue(yolo, value_type=bool), "publish_wire_frame": True,
                          "navigation_enabled": False, "publish_directional_ttc": True,
                          "navigation_odom_age_ms": ParameterValue(
                              LaunchConfiguration("navigation_odom_age_ms"), value_type=int),
                          "stereo_backend": LaunchConfiguration("stereo_backend"),
                          "min_depth_m": ParameterValue(LaunchConfiguration("min_depth_m"), value_type=float),
                          "max_disparity_cap": ParameterValue(LaunchConfiguration("max_disparity_cap"), value_type=int),
                          "publish_perception_diagnostics": ParameterValue(
                              LaunchConfiguration("publish_perception_diagnostics"), value_type=bool),
                          "use_sim_time": clock,
                          **{name: ParameterValue(LaunchConfiguration(name), value_type=float)
                             for name in dimensions}}], output="screen"),
    ])
