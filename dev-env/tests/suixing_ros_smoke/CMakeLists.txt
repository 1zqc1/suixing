cmake_minimum_required(VERSION 3.16)
project(suixing_ros_smoke)

find_package(ament_cmake REQUIRED)
find_package(rclcpp REQUIRED)
find_package(std_msgs REQUIRED)
find_package(OpenCV REQUIRED COMPONENTS core)

add_executable(message_node message_node.cpp)
target_compile_features(message_node PRIVATE cxx_std_17)
target_include_directories(message_node PRIVATE ${OpenCV_INCLUDE_DIRS})
target_link_libraries(message_node ${OpenCV_LIBS})
ament_target_dependencies(message_node rclcpp std_msgs)

install(TARGETS message_node DESTINATION lib/${PROJECT_NAME})
ament_package()
