import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Bool
from cv_bridge import CvBridge
from djitellopy import Tello


class TelloImagePublisher(Node):
    def __init__(self) -> None:
        super().__init__('tello_image_publisher')

        self.image_pub = self.create_publisher(Image, '/tello/image_raw', 10)
        self.frame_alive_pub = self.create_publisher(Bool, '/tello/frame_alive', 10)

        self.bridge = CvBridge()

        self.tello = None
        self.frame_read = None
        self.connected = False
        self.stream_enabled = False

        self.connect_and_setup()

        self.timer = self.create_timer(0.1, self.publish_image)  # 10 Hz
        self.get_logger().info('Tello image publisher started.')

    def connect_and_setup(self) -> None:
        try:
            self.get_logger().info('Creating Tello object...')
            self.tello = Tello()

            self.get_logger().info('Connecting to Tello...')
            self.tello.connect()
            self.connected = True
            self.get_logger().info('Connected to Tello.')

            self.get_logger().info('Starting video stream...')
            self.tello.streamon()
            self.stream_enabled = True

            self.frame_read = self.tello.get_frame_read()
            self.get_logger().info('Video stream started.')

        except Exception as e:
            self.connected = False
            self.stream_enabled = False
            self.get_logger().error(f'Failed to connect/setup image publisher: {e}')

    def publish_image(self) -> None:
        alive_msg = Bool()

        if not self.connected or not self.stream_enabled or self.frame_read is None:
            alive_msg.data = False
            self.frame_alive_pub.publish(alive_msg)
            self.get_logger().warn('Image publisher not ready.')
            return

        try:
            frame = self.frame_read.frame

            if frame is None:
                alive_msg.data = False
                self.frame_alive_pub.publish(alive_msg)
                self.get_logger().warn('No frame received.')
                return

            image_msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')

            self.image_pub.publish(image_msg)

            alive_msg.data = True
            self.frame_alive_pub.publish(alive_msg)

            self.get_logger().info(
                f'Published image: width={frame.shape[1]}, height={frame.shape[0]}'
            )

        except Exception as e:
            alive_msg.data = False
            self.frame_alive_pub.publish(alive_msg)
            self.get_logger().error(f'Failed to publish image: {e}')

    def destroy_node(self) -> None:
        try:
            if self.tello is not None and self.stream_enabled:
                self.tello.streamoff()
        except Exception as e:
            self.get_logger().warn(f'Failed to stop stream cleanly: {e}')

        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TelloImagePublisher()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down Tello image publisher.')
    finally:
        node.destroy_node()
        rclpy.shutdown()