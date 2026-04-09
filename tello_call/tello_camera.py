import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Int32
from djitellopy import Tello


class TelloCamera(Node):
    def __init__(self) -> None:
        super().__init__('tello_camera')

        self.frame_alive_pub = self.create_publisher(Bool, '/tello/frame_alive', 10)
        self.frame_width_pub = self.create_publisher(Int32, '/tello/frame_width', 10)
        self.frame_height_pub = self.create_publisher(Int32, '/tello/frame_height', 10)

        self.tello = None
        self.frame_read = None
        self.connected = False
        self.stream_enabled = False

        self.connect_and_setup()

        self.frame_timer = self.create_timer(0.1, self.check_frame)  # 10 Hz
        self.get_logger().info('Tello camera node started.')

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
            self.get_logger().error(f'Failed to connect/setup camera: {e}')

    def check_frame(self) -> None:
        alive_msg = Bool()
        width_msg = Int32()
        height_msg = Int32()

        if not self.connected or not self.stream_enabled or self.frame_read is None:
            alive_msg.data = False
            self.frame_alive_pub.publish(alive_msg)
            self.get_logger().warn('Camera not ready.')
            return

        try:
            frame = self.frame_read.frame

            if frame is None:
                alive_msg.data = False
                self.frame_alive_pub.publish(alive_msg)
                self.get_logger().warn('No frame received.')
                return

            height, width = frame.shape[:2]

            alive_msg.data = True
            width_msg.data = int(width)
            height_msg.data = int(height)

            self.frame_alive_pub.publish(alive_msg)
            self.frame_width_pub.publish(width_msg)
            self.frame_height_pub.publish(height_msg)

            self.get_logger().info(
                f'Frame received: width={width}, height={height}'
            )

        except Exception as e:
            alive_msg.data = False
            self.frame_alive_pub.publish(alive_msg)
            self.get_logger().error(f'Failed to read frame: {e}')

    def destroy_node(self) -> None:
        try:
            if self.tello is not None and self.stream_enabled:
                self.tello.streamoff()
        except Exception as e:
            self.get_logger().warn(f'Failed to stop stream cleanly: {e}')

        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TelloCamera()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down Tello camera.')
    finally:
        node.destroy_node()
        rclpy.shutdown()