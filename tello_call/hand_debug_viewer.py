import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
import cv2
import mediapipe as mp


class HandDebugViewer(Node):
    def __init__(self) -> None:
        super().__init__('hand_debug_viewer')

        self.bridge = CvBridge()

        self.create_subscription(
            Image,
            '/tello/image_raw',
            self.image_callback,
            10
        )

        self.last_frame_time = None

        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_drawing_styles = mp.solutions.drawing_styles

        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            model_complexity=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        self.window_name = 'Tello Hand Debug Viewer'
        self.get_logger().info('Hand debug viewer started.')

    def image_callback(self, msg: Image) -> None:
        try:
            frame_bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            self.last_frame_time = self.get_clock().now()

            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            results = self.hands.process(frame_rgb)

            hand_count = 0
            if results.multi_hand_landmarks is not None:
                hand_count = len(results.multi_hand_landmarks)

                for hand_landmarks in results.multi_hand_landmarks:
                    self.mp_drawing.draw_landmarks(
                        frame_bgr,
                        hand_landmarks,
                        self.mp_hands.HAND_CONNECTIONS,
                        self.mp_drawing_styles.get_default_hand_landmarks_style(),
                        self.mp_drawing_styles.get_default_hand_connections_style(),
                    )

            detected = hand_count > 0

            status_text = f'Hand detected: {detected} | Count: {hand_count}'
            cv2.putText(
                frame_bgr,
                status_text,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0) if detected else (0, 0, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow(self.window_name, frame_bgr)
            key = cv2.waitKey(1) & 0xFF

            if key == ord('q'):
                self.get_logger().info('q pressed, closing debug viewer window.')
                cv2.destroyWindow(self.window_name)

            self.get_logger().info(
                f'Hand debug: detected={detected}, hand_count={hand_count}'
            )

        except Exception as e:
            self.get_logger().error(f'Failed in hand debug viewer: {e}')

    def destroy_node(self) -> None:
        try:
            self.hands.close()
        except Exception:
            pass

        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = HandDebugViewer()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down hand debug viewer.')
    finally:
        node.destroy_node()
        rclpy.shutdown()