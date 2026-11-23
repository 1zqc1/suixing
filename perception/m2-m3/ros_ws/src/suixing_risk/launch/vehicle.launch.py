"""Bring up static-map localization, synchronized stereo, navigation and the chassis bridge."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    arguments = {key: LaunchConfiguration(key) for key in (
        "model_path", "map_yaml", "vehicle_params", "use_sim_time", "speed_mps",
        "navigation_curvature_per_m", "navigation_front_m", "navigation_back_m",
        "navigation_half_width_m", "lifetime_ms",
        "stereo_backend", "min_depth_m", "max_disparity_cap", "publish_perception_diagnostics",
        "navigation_odom_age_ms", "risk_period_ms",
    )}
    public_navigation = {key: value for key, value in arguments.items() if key != "vehicle_params"}
    # The vehicle launch uses the same measured geometry for M3 and the planner.
    shared_geometry = {name.replace("navigation_", "risk_"): value for name, value in arguments.items()
                       if name.startswith("navigation_")}
    sim_clock = ParameterValue(arguments["use_sim_time"], value_type=bool)
    share = get_package_share_directory("suixing_risk")
    return LaunchDescription([
        DeclareLaunchArgument("map_yaml"),
        DeclareLaunchArgument("model_path"),
        DeclareLaunchArgument("vehicle_params"),
        DeclareLaunchArgument("navigation_curvature_per_m"),
        DeclareLaunchArgument("navigation_front_m"),
        DeclareLaunchArgument("navigation_back_m"),
        DeclareLaunchArgument("navigation_half_width_m"),
        DeclareLaunchArgument("use_sim_time", default_value="false"),
        DeclareLaunchArgument("speed_mps", default_value="0.25"),
        DeclareLaunchArgument("lifetime_ms", default_value="100"),
        DeclareLaunchArgument("navigation_odom_age_ms", default_value="70"),
        DeclareLaunchArgument("risk_period_ms", default_value="25"),
        DeclareLaunchArgument("stereo_backend", default_value="sad"),
        DeclareLaunchArgument("min_depth_m", default_value="0.25"),
        DeclareLaunchArgument("max_disparity_cap", default_value="192"),
        DeclareLaunchArgument("publish_perception_diagnostics", default_value="false"),
        Node(package="suixing_risk", executable="sensor_sync", output="screen",
             parameters=[arguments["vehicle_params"], {"use_sim_time": sim_clock}]),
        Node(package="suixing_risk", executable="chassis_bridge", output="screen",
             parameters=[arguments["vehicle_params"], {
                 "use_sim_time": sim_clock,
                 "max_speed_mps": ParameterValue(arguments["speed_mps"], value_type=float),
             }]),
        Node(package="nav2_amcl", executable="amcl", name="suixing_amcl", output="screen",
             parameters=[{
                 "use_sim_time": sim_clock, "global_frame_id": "map", "odom_frame_id": "odom",
                 "base_frame_id": "base_link", "scan_topic": "/d6/scan", "map_topic": "/map",
                 "tf_broadcast": True, "set_initial_pose": False,
             }, arguments["vehicle_params"]]),
        Node(package="nav2_lifecycle_manager", executable="lifecycle_manager",
             name="suixing_amcl_lifecycle", output="screen",
             parameters=[{"autostart": True, "node_names": ["suixing_amcl"], "use_sim_time": sim_clock}]),
        IncludeLaunchDescription(PythonLaunchDescriptionSource(os.path.join(
            share, "launch", "navigation.launch.py")), launch_arguments={
                **public_navigation, **shared_geometry, "require_semantic_navigation": "true",
            }.items()),
    ])
