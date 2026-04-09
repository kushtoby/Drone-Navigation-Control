import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32, Bool
from djitellopy import Tello


class TelloAdapter(Node):
    def __init__(self) -> None:
        super().__init__('tello_adapter')

        self.battery_pub = self.create_publisher(Int32, '/tello/battery', 10)
        self.link_pub = self.create_publisher(Bool, '/tello/link_ok', 10)

        self.tello = None
        self.connected = False

        self.connect_and_setup()

        self.status_timer = self.create_timer(1.0, self.publish_status)

        self.get_logger().info('Tello adapter started.')

    def connect_and_setup(self) -> None:
        try:
            self.get_logger().info('Creating Tello object...')
            self.tello = Tello()

            self.get_logger().info('Connecting to Tello...')
            self.tello.connect()
            self.connected = True

            battery = int(self.tello.get_battery())
            self.get_logger().info(f'Connected to Tello. Battery: {battery}%')

        except Exception as e:
            self.connected = False
            self.get_logger().error(f'Failed to connect/setup Tello: {e}')

    def publish_status(self) -> None:
        link_msg = Bool()
        battery_msg = Int32()

        if not self.connected or self.tello is None:
            link_msg.data = False
            self.link_pub.publish(link_msg)
            self.get_logger().warn('Tello not connected.')
            return

        try:
            battery = int(self.tello.get_battery())

            link_msg.data = True
            battery_msg.data = battery

            self.link_pub.publish(link_msg)
            self.battery_pub.publish(battery_msg)

            self.get_logger().info(f'Published battery={battery}%, link_ok=True')

        except Exception as e:
            link_msg.data = False
            self.link_pub.publish(link_msg)
            self.get_logger().error(f'Failed to read battery/status: {e}')

    def destroy_node(self) -> None:
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TelloAdapter()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down Tello adapter.')
    finally:
        node.destroy_node()
        rclpy.shutdown()