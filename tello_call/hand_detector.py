import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, Int32
from cv_bridge import CvBridge
import cv2
import mediapipe as mp


class HandDetector(Node):
    def __init__(self) -> None:
        super().__init__('hand_detector')

        self.bridge = CvBridge()

        self.hand_detected_pub = self.create_publisher(Bool, '/tello/hand_detected', 10)
        self.hand_count_pub = self.create_publisher(Int32, '/tello/hand_count', 10)

        self.create_subscription(
            Image,
            '/tello/image_raw',
            self.image_callback,
            10
        )

        self.last_hand_time = None
        self.watchdog_timer = self.create_timer(1.0, self.check_hand_health)

        # MediaPipe Hands
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            model_complexity=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        self.get_logger().info('Hand detector started.')

    def image_callback(self, msg: Image) -> None:
        detected_msg = Bool()
        count_msg = Int32()

        try:
            frame_bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

            # MediaPipe expects RGB
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

            results = self.hands.process(frame_rgb)

            hand_count = 0
            if results.multi_hand_landmarks is not None:
                hand_count = len(results.multi_hand_landmarks)

            detected = hand_count > 0

            detected_msg.data = detected
            count_msg.data = int(hand_count)

            self.hand_detected_pub.publish(detected_msg)
            self.hand_count_pub.publish(count_msg)

            if detected:
                self.last_hand_time = self.get_clock().now()

            self.get_logger().info(
                f'Hand detection: detected={detected}, hand_count={hand_count}'
            )

        except Exception as e:
            detected_msg.data = False
            count_msg.data = 0
            self.hand_detected_pub.publish(detected_msg)
            self.hand_count_pub.publish(count_msg)
            self.get_logger().error(f'Failed to process image for hand detection: {e}')

    def check_hand_health(self) -> None:
        if self.last_hand_time is None:
            self.get_logger().warn('No hand detected yet.')
            return

        age_sec = (self.get_clock().now() - self.last_hand_time).nanoseconds / 1e9
        if age_sec > 2.0:
            self.get_logger().warn(f'Hand stream stale: last detection {age_sec:.2f}s ago')

    def destroy_node(self) -> None:
        try:
            self.hands.close()
        except Exception:
            pass
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = HandDetector()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down hand detector.')
    finally:
        node.destroy_node()
        rclpy.shutdown()