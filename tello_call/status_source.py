import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32, Bool


class StatusSource(Node):
    def __init__(self) -> None:
        super().__init__('status_source')

        self.battery_pub = self.create_publisher(Int32, '/tello/battery', 10)
        self.link_pub = self.create_publisher(Bool, '/tello/link_ok', 10)

        self.battery = 100
        self.link_ok = True

        self.timer = self.create_timer(1.0, self.publish_status)
        self.get_logger().info('Status source started.')

    def publish_status(self) -> None:
        battery_msg = Int32()
        battery_msg.data = self.battery

        link_msg = Bool()
        link_msg.data = self.link_ok

        self.battery_pub.publish(battery_msg)
        self.link_pub.publish(link_msg)

        self.get_logger().info(
            f'Published battery={self.battery}%, link_ok={self.link_ok}'
        )

        # simple demo pattern
        if self.battery > 15:
            self.battery -= 1


def main(args=None) -> None:
    rclpy.init(args=args)
    node = StatusSource()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()