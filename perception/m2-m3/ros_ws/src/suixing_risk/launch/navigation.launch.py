"""Start YOLOv8 and the fused-risk local navigator."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, NotEqualsSubstitution

from suixing_risk.geometry import Config
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    model_path = LaunchConfiguration("model_path")
    use_sim_time = ParameterValue(LaunchConfiguration("use_sim_time"), value_type=bool)
    speed = ParameterValue(LaunchConfiguration("speed_mps"), value_type=float)
    lifetime = ParameterValue(LaunchConfiguration("lifetime_ms"), value_type=int)
    global_planning = ParameterValue(LaunchConfiguration("global_planning"), value_type=bool)
    map_yaml = LaunchConfiguration("map_yaml")
    load_static_map = IfCondition(NotEqualsSubstitution(map_yaml, ""))
    geometry = {
        "navigation_curvature_per_m": "1.15",
        "navigation_front_m": "0.30",
        "navigation_back_m": "0.55",
        "navigation_half_width_m": "0.30",
    }
    risk_defaults = Config()
    risk_geometry = {name.replace("navigation_", "risk_"): str(
        getattr(risk_defaults, name.removeprefix("navigation_"))) for name in geometry}
    return LaunchDescription([
        *(DeclareLaunchArgument(name, default_value=value)
          for name, value in {**geometry, **risk_geometry}.items()),
        DeclareLaunchArgument("model_path"),
        DeclareLaunchArgument("global_planning", default_value="true"),
        DeclareLaunchArgument("map_topic", default_value="/map"),
        DeclareLaunchArgument("map_yaml", default_value=""),
        DeclareLaunchArgument("path_lookahead_m", default_value="1.2"),
        DeclareLaunchArgument("map_frame", default_value="map"),
        DeclareLaunchArgument("use_sim_time", default_value="false"),
        DeclareLaunchArgument("speed_mps", default_value="0.25"),
        DeclareLaunchArgument("lifetime_ms", default_value="100"),
        DeclareLaunchArgument("require_semantic_navigation", default_value="false"),
        DeclareLaunchArgument("stereo_backend", default_value="sad"),
        DeclareLaunchArgument("min_depth_m", default_value="0.25"),
        DeclareLaunchArgument("max_disparity_cap", default_value="192"),
        DeclareLaunchArgument("publish_perception_diagnostics", default_value="false"),
        DeclareLaunchArgument("navigation_odom_age_ms", default_value="30"),
        DeclareLaunchArgument("risk_period_ms", default_value="50"),
        Node(package="nav2_map_server", executable="map_server", name="suixing_map_server",
             condition=load_static_map, parameters=[{
                 "yaml_filename": map_yaml, "use_sim_time": use_sim_time,
                 "topic_name": LaunchConfiguration("map_topic"),
                 "frame_id": LaunchConfiguration("map_frame"),
             }], output="screen"),
        Node(package="nav2_lifecycle_manager", executable="lifecycle_manager",
             name="suixing_map_lifecycle", condition=load_static_map, parameters=[{
                 "autostart": True, "node_names": ["suixing_map_server"],
                 "use_sim_time": use_sim_time,
             }], output="screen"),
        Node(package="suixing_risk", executable="semantic_node", parameters=[{
            "model_path": model_path, "use_sim_time": use_sim_time,
        }], output="screen"),
        Node(package="suixing_risk", executable="risk_node", parameters=[{
            "semantic_association": True, "publish_wire_frame": True, "publish_directional_ttc": True,
            "navigation_enabled": True, "use_sim_time": use_sim_time,
            "global_planning": global_planning,
            "map_frame": LaunchConfiguration("map_frame"),
            "map_topic": LaunchConfiguration("map_topic"),
            "path_lookahead_m": ParameterValue(LaunchConfiguration("path_lookahead_m"),
                                               value_type=float),
            "navigation_speed_mps": speed, "lifetime_ms": lifetime,
            "require_semantic_navigation": ParameterValue(
                LaunchConfiguration("require_semantic_navigation"), value_type=bool),
            "navigation_odom_age_ms": ParameterValue(
                LaunchConfiguration("navigation_odom_age_ms"), value_type=int),
            "risk_period_ms": ParameterValue(LaunchConfiguration("risk_period_ms"), value_type=int),
            "stereo_backend": LaunchConfiguration("stereo_backend"),
            "min_depth_m": ParameterValue(LaunchConfiguration("min_depth_m"), value_type=float),
            "max_disparity_cap": ParameterValue(LaunchConfiguration("max_disparity_cap"), value_type=int),
            "publish_perception_diagnostics": ParameterValue(
                LaunchConfiguration("publish_perception_diagnostics"), value_type=bool),
            **{name: ParameterValue(LaunchConfiguration(name), value_type=float)
               for name in (*geometry, *risk_geometry)},
        }], output="screen"),
    ])
