#!/usr/bin/env python3
from __future__ import annotations

from collections import deque

import cv2
from cv_bridge import CvBridge
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, Int32


class PinkBalloonDetector(Node):
    def __init__(self) -> None:
        super().__init__('pink_balloon_detector')

        self.bridge = CvBridge()

        self.detected_pub = self.create_publisher(Bool, '/tello/pink_balloon_detected', 10)
        self.cx_pub = self.create_publisher(Int32, '/tello/pink_balloon_center_x', 10)
        self.cy_pub = self.create_publisher(Int32, '/tello/pink_balloon_center_y', 10)
        self.area_pub = self.create_publisher(Int32, '/tello/pink_balloon_area', 10)

        self.create_subscription(Image, '/tello/image_raw', self.image_callback, 10)

        self.declare_parameter('show_debug', True)
        self.declare_parameter('pink_hsv_lower', [140, 80, 80])
        self.declare_parameter('pink_hsv_upper', [179, 255, 255])
        self.declare_parameter('min_pixel_count', 320)
        self.declare_parameter('min_blob_area', 120)
        self.declare_parameter('roi_top_frac', 0.0)
        self.declare_parameter('roi_bottom_frac', 0.9)
        self.declare_parameter('history_len', 5)
        self.declare_parameter('required_hits', 3)

        self.window_name = 'Pink Balloon Detector'
        self.show_debug = bool(self.get_parameter('show_debug').value)

        self.lower_pink = np.array(self.get_parameter('pink_hsv_lower').value, dtype=np.uint8)
        self.upper_pink = np.array(self.get_parameter('pink_hsv_upper').value, dtype=np.uint8)
        self.min_pixel_count = int(self.get_parameter('min_pixel_count').value)
        self.min_blob_area = int(self.get_parameter('min_blob_area').value)
        self.roi_top_frac = float(self.get_parameter('roi_top_frac').value)
        self.roi_bottom_frac = float(self.get_parameter('roi_bottom_frac').value)
        history_len = max(1, int(self.get_parameter('history_len').value))
        self.required_hits = int(self.get_parameter('required_hits').value)
        self.history = deque(maxlen=history_len)

        self.get_logger().info('Pink balloon detector started.')

    def image_callback(self, msg: Image) -> None:
        detected_msg = Bool()
        cx_msg = Int32()
        cy_msg = Int32()
        area_msg = Int32()

        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            h_img, w_img = frame.shape[:2]

            y0 = int(self.roi_top_frac * h_img)
            y1 = int(self.roi_bottom_frac * h_img)

            roi = frame[y0:y1, :]
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

            mask = cv2.inRange(hsv, self.lower_pink, self.upper_pink)

            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            pixel_count = int(cv2.countNonZero(mask))
            raw_detected = pixel_count >= self.min_pixel_count

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            best_area = 0
            best_bbox = None
            best_center = None
            best_score = -1e18

            img_cx = w_img // 2
            img_cy = h_img // 2

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < self.min_blob_area:
                    continue

                x, y, w, h = cv2.boundingRect(cnt)
                if w < 12 or h < 12:
                    continue

                full_x = x
                full_y = y + y0
                cx = full_x + w // 2
                cy = full_y + h // 2

                dist = ((cx - img_cx) ** 2 + (cy - img_cy) ** 2) ** 0.5
                score = area - 1.5 * dist

                if score > best_score:
                    best_score = score
                    best_area = int(area)
                    best_bbox = (full_x, full_y, w, h)
                    best_center = (cx, cy)

            self.history.append(1 if raw_detected else 0)
            confirmed = sum(self.history) >= self.required_hits

            detected_msg.data = confirmed
            self.detected_pub.publish(detected_msg)

            if confirmed and best_bbox is not None and best_center is not None:
                cx_msg.data = int(best_center[0])
                cy_msg.data = int(best_center[1])
                area_msg.data = int(best_area)

                self.cx_pub.publish(cx_msg)
                self.cy_pub.publish(cy_msg)
                self.area_pub.publish(area_msg)

                self.get_logger().info(
                    f'Pink balloon detected: center=({cx_msg.data}, {cy_msg.data}), '
                    f'blob_area={area_msg.data}, pixel_count={pixel_count}, history={list(self.history)}'
                )

                if self.show_debug:
                    x, y, w, h = best_bbox
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    cv2.circle(frame, best_center, 5, (0, 0, 255), -1)
                    cv2.putText(
                        frame,
                        f'DET pixels={pixel_count} area={best_area}',
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.75,
                        (0, 255, 0),
                        2,
                        cv2.LINE_AA,
                    )
            else:
                self.get_logger().info(
                    f'Pink balloon not confirmed. pixel_count={pixel_count}, history={list(self.history)}'
                )

                if self.show_debug:
                    cv2.putText(
                        frame,
                        f'NOT DETECTED pixels={pixel_count} hist={list(self.history)}',
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.75,
                        (0, 0, 255),
                        2,
                        cv2.LINE_AA,
                    )

            if self.show_debug:
                cv2.line(frame, (0, y1), (w_img, y1), (255, 0, 0), 2)
                cv2.imshow(self.window_name, frame)
                cv2.imshow('Pink Mask', mask)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    cv2.destroyWindow(self.window_name)
                    cv2.destroyWindow('Pink Mask')
                    self.show_debug = False

        except Exception as exc:
            detected_msg.data = False
            self.detected_pub.publish(detected_msg)
            self.get_logger().error(f'Pink balloon detection failed: {exc}')

    def destroy_node(self) -> None:
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = PinkBalloonDetector()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down pink_balloon_detector.')
    finally:
        node.destroy_node()
        rclpy.shutdown()
