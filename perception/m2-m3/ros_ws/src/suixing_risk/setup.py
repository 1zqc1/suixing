from setuptools import setup

setup(
    name="suixing_risk",
    version="0.7.0",
    packages=["suixing_risk"],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/suixing_risk"]),
        ("share/suixing_risk", ["package.xml"]),
        ("share/suixing_risk/launch", ["launch/navigation.launch.py", "launch/vehicle.launch.py", "launch/perception_risk.launch.py"]),
    ],
    install_requires=["setuptools", "numpy"],
    maintainer="Suixing team",
    license="UNLICENSED",
    entry_points={"console_scripts": [
        "risk_node = suixing_risk.ros_node:main",
        "rpmsg_risk = suixing_risk.rpmsg_risk:main",
        "sensor_sync = suixing_risk.sensor_sync:main",
        "chassis_bridge = suixing_risk.chassis_ros:main",
        "replay_m1 = suixing_risk.replay:main",
        "simulate_m1 = suixing_risk.simulate:main",
        "semantic_node = suixing_risk.semantic_ros:main",
        "detect_image = suixing_risk.semantic:main",
        "simulate_avoidance = suixing_risk.simulate_avoidance:main",
    ]},
)
