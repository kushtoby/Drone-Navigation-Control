#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from cv_bridge import CvBridge
import cv2
import mediapipe as mp
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, Int32, String

try:
    from ai_edge_litert.interpreter import Interpreter as LiteRTInterpreter  # type: ignore
except Exception:  # pragma: no cover
    LiteRTInterpreter = None

try:
    from tflite_runtime.interpreter import Interpreter as TFLiteRuntimeInterpreter  # type: ignore
except Exception:  # pragma: no cover
    TFLiteRuntimeInterpreter = None

try:
    from tensorflow import lite as tflite  # type: ignore
except Exception:  # pragma: no cover
    tflite = None


class LiteKeyPointClassifier:
    def __init__(self, model_path: str, num_threads: int = 1) -> None:
        if LiteRTInterpreter is not None:
            self.interpreter = LiteRTInterpreter(model_path=model_path)
        elif TFLiteRuntimeInterpreter is not None:
            self.interpreter = TFLiteRuntimeInterpreter(model_path=model_path, num_threads=num_threads)
        elif tflite is not None:
            self.interpreter = tflite.Interpreter(model_path=model_path, num_threads=num_threads)
        else:
            raise RuntimeError('No LiteRT/TFLite interpreter is available. Install ai-edge-litert, tflite-runtime, or tensorflow.')

        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()

    def infer(self, landmark_list: List[float]) -> int:
        input_index = self.input_details[0]['index']
        self.interpreter.set_tensor(input_index, np.array([landmark_list], dtype=np.float32))
        self.interpreter.invoke()
        output_index = self.output_details[0]['index']
        result = self.interpreter.get_tensor(output_index)
        return int(np.argmax(np.squeeze(result)))


class GestureRecognizer(Node):
    def __init__(self) -> None:
        super().__init__('gesture_recognizer')

        self.declare_parameter('show_debug', False)
        self.declare_parameter('min_detection_confidence', 0.6)
        self.declare_parameter('min_tracking_confidence', 0.5)
        self.declare_parameter('max_num_hands', 1)
        self.declare_parameter('model_path', '')
        self.declare_parameter('labels_path', '')

        self.show_debug = bool(self.get_parameter('show_debug').value)
        min_det = float(self.get_parameter('min_detection_confidence').value)
        min_track = float(self.get_parameter('min_tracking_confidence').value)
        max_num_hands = int(self.get_parameter('max_num_hands').value)

        pkg_dir = Path(__file__).resolve().parent
        default_model = pkg_dir / 'model' / 'keypoint_classifier' / 'keypoint_classifier.tflite'
        default_labels = pkg_dir / 'model' / 'keypoint_classifier' / 'keypoint_classifier_label.csv'

        model_path = str(self.get_parameter('model_path').value).strip() or str(default_model)
        labels_path = str(self.get_parameter('labels_path').value).strip() or str(default_labels)

        self.bridge = CvBridge()
        self.valid_pub = self.create_publisher(Bool, '/tello/gesture_valid', 10)
        self.label_pub = self.create_publisher(String, '/tello/gesture_label', 10)
        self.id_pub = self.create_publisher(Int32, '/tello/gesture_id', 10)
        self.debug_pub = self.create_publisher(Image, '/tello/gesture_debug', 10)
        self.create_subscription(Image, '/tello/image_raw', self.image_callback, 10)

        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_num_hands,
            min_detection_confidence=min_det,
            min_tracking_confidence=min_track,
        )

        self.labels = self.load_labels(labels_path)
        self.classifier: Optional[LiteKeyPointClassifier] = None
        self.classifier_ready = False

        try:
            if not Path(model_path).exists():
                raise FileNotFoundError(f'Model file not found: {model_path}')
            self.classifier = LiteKeyPointClassifier(model_path)
            self.classifier_ready = True
            self.get_logger().info(f'Gesture classifier loaded from {model_path}')
        except Exception as exc:
            self.classifier_ready = False
            self.get_logger().error(
                'Gesture classifier could not be initialized. '
                f'Place the kinivi TFLite model at {model_path}. Error: {exc}'
            )

        self.window_name = 'Gesture Recognizer'
        self.get_logger().info('gesture_recognizer started.')

    def load_labels(self, labels_path: str) -> List[str]:
        path = Path(labels_path)
        if not path.exists():
            self.get_logger().warn(f'Label file not found: {labels_path}')
            return []
        text = path.read_text(encoding='utf-8-sig').strip()
        if ',' in text:
            return [line.strip() for line in text.splitlines() if line.strip()]
        return [token.strip() for token in text.split() if token.strip()]

    def calc_landmark_list(self, image: np.ndarray, landmarks) -> List[List[int]]:
        image_width, image_height = image.shape[1], image.shape[0]
        landmark_points: List[List[int]] = []
        for landmark in landmarks.landmark:
            x = min(int(landmark.x * image_width), image_width - 1)
            y = min(int(landmark.y * image_height), image_height - 1)
            landmark_points.append([x, y])
        return landmark_points

    def pre_process_landmark(self, landmark_list: List[List[int]]) -> List[float]:
        temp_landmarks = [[x, y] for x, y in landmark_list]
        base_x, base_y = temp_landmarks[0]
        for i, point in enumerate(temp_landmarks):
            temp_landmarks[i][0] = point[0] - base_x
            temp_landmarks[i][1] = point[1] - base_y

        flattened = [coord for point in temp_landmarks for coord in point]
        max_value = max([abs(value) for value in flattened]) if flattened else 1.0
        if max_value == 0.0:
            max_value = 1.0
        return [value / max_value for value in flattened]

    def publish_invalid(self) -> None:
        self.valid_pub.publish(Bool(data=False))
        self.label_pub.publish(String(data=''))
        self.id_pub.publish(Int32(data=-1))

    def image_callback(self, msg: Image) -> None:
        if not self.classifier_ready or self.classifier is None:
            self.publish_invalid()
            return

        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb)

            if not results.multi_hand_landmarks:
                self.publish_invalid()
                if self.show_debug:
                    self.debug_pub.publish(self.bridge.cv2_to_imgmsg(frame, encoding='bgr8'))
                return

            hand_landmarks = results.multi_hand_landmarks[0]
            landmark_list = self.calc_landmark_list(frame, hand_landmarks)
            processed = self.pre_process_landmark(landmark_list)
            gesture_id = self.classifier.infer(processed)
            gesture_label = self.labels[gesture_id] if 0 <= gesture_id < len(self.labels) else str(gesture_id)

            self.valid_pub.publish(Bool(data=True))
            self.label_pub.publish(String(data=gesture_label))
            self.id_pub.publish(Int32(data=gesture_id))

            if self.show_debug:
                self.mp_drawing.draw_landmarks(frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS)
                cv2.putText(
                    frame,
                    f'Gesture: {gesture_label}',
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )
                self.debug_pub.publish(self.bridge.cv2_to_imgmsg(frame, encoding='bgr8'))
                cv2.imshow(self.window_name, frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    cv2.destroyWindow(self.window_name)
                    self.show_debug = False
        except Exception as exc:
            self.publish_invalid()
            self.get_logger().error(f'Gesture recognition failed: {exc}')

    def destroy_node(self) -> None:
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = GestureRecognizer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down gesture_recognizer.')
    finally:
        node.destroy_node()
        rclpy.shutdown()
