import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Bool
from cv_bridge import CvBridge


class ImageListener(Node):
    def __init__(self) -> None:
        super().__init__('image_listener')

        self.bridge = CvBridge()

        self.image_received_pub = self.create_publisher(Bool, '/tello/image_received', 10)

        self.create_subscription(
            Image,
            '/tello/image_raw',
            self.image_callback,
            10
        )

        self.last_image_time = None
        self.watchdog_timer = self.create_timer(1.0, self.check_image_health)

        self.get_logger().info('Image listener started.')

    def image_callback(self, msg: Image) -> None:
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            self.last_image_time = self.get_clock().now()

            received_msg = Bool()
            received_msg.data = True
            self.image_received_pub.publish(received_msg)

            height, width = frame.shape[:2]
            self.get_logger().info(
                f'Received image: width={width}, height={height}, encoding={msg.encoding}'
            )

        except Exception as e:
            received_msg = Bool()
            received_msg.data = False
            self.image_received_pub.publish(received_msg)
            self.get_logger().error(f'Failed to convert incoming image: {e}')

    def check_image_health(self) -> None:
        msg = Bool()

        if self.last_image_time is None:
            msg.data = False
            self.image_received_pub.publish(msg)
            self.get_logger().warn('No image received yet.')
            return

        age_sec = (self.get_clock().now() - self.last_image_time).nanoseconds / 1e9

        if age_sec > 2.0:
            msg.data = False
            self.image_received_pub.publish(msg)
            self.get_logger().warn(f'Image stream stale: last image {age_sec:.2f}s ago')

    def destroy_node(self) -> None:
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ImageListener()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down image listener.')
    finally:
        node.destroy_node()
        rclpy.shutdown()