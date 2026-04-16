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

        self.blob_count_pub = self.create_publisher(Int32, '/tello/pink_balloon_blob_count', 10)
        self.mode_code_pub = self.create_publisher(Int32, '/tello/pink_balloon_mode_code', 10)

        self.create_subscription(Image, '/tello/image_raw', self.image_callback, 10)

        self.declare_parameter('show_debug', True)
        self.declare_parameter('pink_hsv_lower', [140, 80, 80])
        self.declare_parameter('pink_hsv_upper', [179, 255, 255])

        # Main detection is pixel-count based
        self.declare_parameter('min_pixel_count', 320)

        # Per-blob validity filters
        self.declare_parameter('min_blob_area', 120)
        self.declare_parameter('min_blob_pixels', 180)
        self.declare_parameter('min_blob_w', 12)
        self.declare_parameter('min_blob_h', 12)

        self.declare_parameter('roi_top_frac', 0.0)
        self.declare_parameter('roi_bottom_frac', 0.9)

        # Boolean detection debounce
        self.declare_parameter('history_len', 5)
        self.declare_parameter('required_hits', 3)

        # Blob-count debounce
        self.declare_parameter('blob_history_len', 5)
        self.declare_parameter('required_blob_count_hits', 3)

        self.window_name = 'Pink Balloon Detector'
        self.show_debug = bool(self.get_parameter('show_debug').value)

        self.lower_pink = np.array(self.get_parameter('pink_hsv_lower').value, dtype=np.uint8)
        self.upper_pink = np.array(self.get_parameter('pink_hsv_upper').value, dtype=np.uint8)

        self.min_pixel_count = int(self.get_parameter('min_pixel_count').value)
        self.min_blob_area = int(self.get_parameter('min_blob_area').value)
        self.min_blob_pixels = int(self.get_parameter('min_blob_pixels').value)
        self.min_blob_w = int(self.get_parameter('min_blob_w').value)
        self.min_blob_h = int(self.get_parameter('min_blob_h').value)

        self.roi_top_frac = float(self.get_parameter('roi_top_frac').value)
        self.roi_bottom_frac = float(self.get_parameter('roi_bottom_frac').value)

        history_len = max(1, int(self.get_parameter('history_len').value))
        self.required_hits = int(self.get_parameter('required_hits').value)
        self.history = deque(maxlen=history_len)

        blob_history_len = max(1, int(self.get_parameter('blob_history_len').value))
        self.required_blob_count_hits = int(self.get_parameter('required_blob_count_hits').value)
        self.blob_count_history = deque(maxlen=blob_history_len)

        self.get_logger().info('Pink balloon detector started.')

    def image_callback(self, msg: Image) -> None:
        detected_msg = Bool()
        cx_msg = Int32()
        cy_msg = Int32()
        area_msg = Int32()
        blob_count_msg = Int32()
        mode_code_msg = Int32()

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

            valid_blobs = []

            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < self.min_blob_area:
                    continue

                x, y, w, h = cv2.boundingRect(cnt)
                if w < self.min_blob_w or h < self.min_blob_h:
                    continue

                single_blob_mask = np.zeros_like(mask)
                cv2.drawContours(single_blob_mask, [cnt], -1, 255, thickness=cv2.FILLED)
                blob_pixels = int(cv2.countNonZero(single_blob_mask))

                if blob_pixels < self.min_blob_pixels:
                    continue

                valid_blobs.append((cnt, int(area), x, y, w, h, blob_pixels))

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

            # Debounce boolean detection
            self.history.append(1 if raw_detected else 0)
            confirmed = sum(self.history) >= self.required_hits

            # Debounce blob count
            raw_blob_count = min(len(valid_blobs), 2)
            self.blob_count_history.append(raw_blob_count)

            stable_blob_count = 0
            for candidate in [2, 1, 0]:
                hits = sum(1 for v in self.blob_count_history if v == candidate)
                if hits >= self.required_blob_count_hits:
                    stable_blob_count = candidate
                    break

            detected_msg.data = confirmed
            self.detected_pub.publish(detected_msg)

            blob_count_msg.data = int(stable_blob_count)
            self.blob_count_pub.publish(blob_count_msg)

            # mode_code mirrors blob count for now:
            # 0 = no valid cue
            # 1 = single balloon region
            # 2 = split balloon / two valid regions
            mode_code_msg.data = int(stable_blob_count)
            self.mode_code_pub.publish(mode_code_msg)

            if confirmed and best_bbox is not None and best_center is not None:
                cx_msg.data = int(best_center[0])
                cy_msg.data = int(best_center[1])
                area_msg.data = int(best_area)

                self.cx_pub.publish(cx_msg)
                self.cy_pub.publish(cy_msg)
                self.area_pub.publish(area_msg)

                self.get_logger().info(
                    f'Pink balloon detected: center=({cx_msg.data}, {cy_msg.data}), '
                    f'blob_area={area_msg.data}, pixel_count={pixel_count}, '
                    f'raw_blob_count={raw_blob_count}, stable_blob_count={stable_blob_count}, '
                    f'det_hist={list(self.history)}, blob_hist={list(self.blob_count_history)}'
                )

                if self.show_debug:
                    x, y, w, h = best_bbox
                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    cv2.circle(frame, best_center, 5, (0, 0, 255), -1)
                    cv2.putText(
                        frame,
                        f'DET pixels={pixel_count} area={best_area} blobs={stable_blob_count}',
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 0),
                        2,
                        cv2.LINE_AA,
                    )
            else:
                self.get_logger().info(
                    f'Pink balloon not confirmed. pixel_count={pixel_count}, '
                    f'raw_blob_count={raw_blob_count}, stable_blob_count={stable_blob_count}, '
                    f'det_hist={list(self.history)}, blob_hist={list(self.blob_count_history)}'
                )

                if self.show_debug:
                    cv2.putText(
                        frame,
                        f'NOT DET pixels={pixel_count} blobs={stable_blob_count}',
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 0, 255),
                        2,
                        cv2.LINE_AA,
                    )

            if self.show_debug:
                # draw all valid blobs in yellow
                for _, area, x, y, w, h, blob_pixels in valid_blobs:
                    cv2.rectangle(frame, (x, y + y0), (x + w, y + y0 + h), (0, 255, 255), 1)
                    cv2.putText(
                        frame,
                        f'a={area} p={blob_pixels}',
                        (x, max(15, y + y0 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.4,
                        (0, 255, 255),
                        1,
                        cv2.LINE_AA,
                    )

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

            blob_count_msg.data = 0
            self.blob_count_pub.publish(blob_count_msg)

            mode_code_msg.data = 0
            self.mode_code_pub.publish(mode_code_msg)

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