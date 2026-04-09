import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32, Bool, String


class StatusMonitor(Node):
    def __init__(self) -> None:
        super().__init__('status_monitor')

        self.battery_percent = None
        self.link_ok = False

        self.last_battery_time = None
        self.last_link_time = None

        self.create_subscription(Int32, '/tello/battery', self.battery_callback, 10)
        self.create_subscription(Bool, '/tello/link_ok', self.link_callback, 10)

        self.summary_pub = self.create_publisher(String, '/tello/status_summary', 10)

        self.timer = self.create_timer(1.0, self.publish_summary)
        self.get_logger().info('Status monitor started.')

    def battery_callback(self, msg: Int32) -> None:
        self.battery_percent = msg.data
        self.last_battery_time = self.get_clock().now()

    def link_callback(self, msg: Bool) -> None:
        self.link_ok = msg.data
        self.last_link_time = self.get_clock().now()

    def publish_summary(self) -> None:
        now = self.get_clock().now()

        battery_fresh = False
        link_fresh = False

        if self.last_battery_time is not None:
            battery_age = (now - self.last_battery_time).nanoseconds / 1e9
            battery_fresh = battery_age < 3.0

        if self.last_link_time is not None:
            link_age = (now - self.last_link_time).nanoseconds / 1e9
            link_fresh = link_age < 3.0

        connected = self.link_ok and link_fresh
        battery_ok = self.battery_percent is not None and self.battery_percent >= 20

        summary = String()
        summary.data = (
            f'connected={connected}, '
            f'link_fresh={link_fresh}, '
            f'battery={self.battery_percent}, '
            f'battery_fresh={battery_fresh}, '
            f'battery_ok={battery_ok}'
        )

        self.summary_pub.publish(summary)
        self.get_logger().info(summary.data)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = StatusMonitor()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()