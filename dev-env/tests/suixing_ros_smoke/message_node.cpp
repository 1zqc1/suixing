#include <chrono>
#include <iostream>
#include <string>

#include <opencv2/core.hpp>
#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>

int main(int argc, char **argv)
{
    if (argc != 2 || (std::string(argv[1]) != "publish" && std::string(argv[1]) != "subscribe")) {
        std::cerr << "Usage: message_node publish|subscribe\n";
        return 2;
    }

    const cv::Mat pixel(1, 1, CV_8UC1, cv::Scalar(42));
    const auto payload = "SUIXING_HUMBLE_SMOKE_" + std::to_string(pixel.at<unsigned char>(0, 0));
    const std::string topic = "/suixing_smoke";
    using Message = std_msgs::msg::String;

    rclcpp::init(argc, argv);
    if (std::string(argv[1]) == "publish") {
        auto node = rclcpp::Node::make_shared("suixing_smoke_publisher");
        auto publisher = node->create_publisher<Message>(topic, 10);
        auto timer = node->create_wall_timer(std::chrono::milliseconds(200), [&]() {
            Message message;
            message.data = payload;
            publisher->publish(message);
        });
        rclcpp::spin(node);
        rclcpp::shutdown();
        return 0;
    }

    auto node = rclcpp::Node::make_shared("suixing_smoke_subscriber");
    bool received = false;
    auto subscriber = node->create_subscription<Message>(topic, 10, [&](const Message &message) {
        if (message.data == payload) {
            std::cout << "RECEIVED " << message.data << std::endl;
            received = true;
            rclcpp::shutdown();
        }
    });
    rclcpp::spin(node);
    rclcpp::shutdown();
    return received ? 0 : 1;
}
