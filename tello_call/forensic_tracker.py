#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, Empty, Int32, String


@dataclass
class Snapshot:
    state: str = ""
    mode: str = ""
    link_ok: Optional[bool] = None
    battery_pct: int = -1
    tof_cm: int = -1
    gesture_valid: Optional[bool] = None
    gesture_label: str = ""
    cue_detected: Optional[bool] = None
    cue_center_x: int = -1
    cue_center_y: int = -1
    cue_area: int = -1
    image_width: int = -1
    image_height: int = -1
    cmd_forward: float = 0.0
    cmd_left: float = 0.0
    cmd_up: float = 0.0
    cmd_yaw: float = 0.0


class ForensicTracker(Node):
    def __init__(self) -> None:
        super().__init__('forensic_tracker')

        self.declare_parameter('summary_period_s', 0.5)
        self.declare_parameter('print_heartbeat', True)
        self.declare_parameter('print_topic_changes', False)
        self.declare_parameter('cue_center_x_target_px', 480)
        self.declare_parameter('cue_center_tolerance_px', 80)
        self.declare_parameter('cue_area_stop_threshold', 22000)
        self.declare_parameter('hover_height_m', 0.91)
        self.declare_parameter('hover_height_tolerance_m', 0.10)
        self.declare_parameter('jsonl_path', '/tmp/tello_forensic.jsonl')
        self.declare_parameter('print_to_terminal', False)

        self.summary_period_s = float(self.get_parameter('summary_period_s').value)
        self.print_heartbeat = bool(self.get_parameter('print_heartbeat').value)
        self.print_topic_changes = bool(self.get_parameter('print_topic_changes').value)
        self.cue_center_x_target_px = int(self.get_parameter('cue_center_x_target_px').value)
        self.cue_center_tolerance_px = int(self.get_parameter('cue_center_tolerance_px').value)
        self.cue_area_stop_threshold = int(self.get_parameter('cue_area_stop_threshold').value)
        self.hover_height_m = float(self.get_parameter('hover_height_m').value)
        self.hover_height_tolerance_m = float(self.get_parameter('hover_height_tolerance_m').value)
        self.jsonl_path = str(self.get_parameter('jsonl_path').value).strip()
        self.print_to_terminal = bool(self.get_parameter('print_to_terminal').value)

        self.start_time = time.time()
        self.last_summary_time = 0.0
        self.last_image_stamp = None
        self.image_dt_ema = None
        self.last_state = ''
        self.last_mode = ''
        self.last_gesture_label = ''
        self.last_cmd_nonzero = False
        self.last_cmd_time = 0.0
        self.last_gesture_valid_time = 0.0
        self.last_gesture_label_time = 0.0
        self.last_cue_detected_time = 0.0
        self.last_cue_good_time = 0.0
        self.last_takeoff_event_time = 0.0
        self.last_land_event_time = 0.0
        self.last_start_hover_event_time = 0.0
        self.last_emergency_event_time = 0.0
        self.prev_snapshot = Snapshot()
        self.s = Snapshot()
        self.event_count = 0
        self.summary_count = 0

        self.jsonl_fp = open(self.jsonl_path, 'a', encoding='utf-8') if self.jsonl_path else None

        self.create_subscription(String, '/tello/state', self.on_state, 10)
        self.create_subscription(String, '/tello/mode', self.on_mode, 10)
        self.create_subscription(Bool, '/tello/link_ok', self.on_link_ok, 10)
        self.create_subscription(Int32, '/tello/battery', self.on_battery, 10)
        self.create_subscription(Int32, '/tello/tof_cm', self.on_tof, 10)
        self.create_subscription(Bool, '/tello/gesture_valid', self.on_gesture_valid, 10)
        self.create_subscription(String, '/tello/gesture_label', self.on_gesture_label, 10)
        self.create_subscription(Bool, '/tello/pink_balloon_detected', self.on_cue_detected, 10)
        self.create_subscription(Int32, '/tello/pink_balloon_center_x', self.on_cue_center_x, 10)
        self.create_subscription(Int32, '/tello/pink_balloon_center_y', self.on_cue_center_y, 10)
        self.create_subscription(Int32, '/tello/pink_balloon_area', self.on_cue_area, 10)
        self.create_subscription(Image, '/tello/image_raw', self.on_image, 10)
        self.create_subscription(Twist, '/tello/cmd_vel', self.on_cmd_vel, 10)
        self.create_subscription(Empty, '/tello/takeoff', self.on_takeoff, 10)
        self.create_subscription(Empty, '/tello/land', self.on_land, 10)
        self.create_subscription(Empty, '/tello/start_hover', self.on_start_hover, 10)
        self.create_subscription(Empty, '/tello/emergency', self.on_emergency, 10)

        self.timer = self.create_timer(0.05, self.on_timer)
        self.emit('tracker_started', {'summary_period_s': self.summary_period_s})

    def now_rel(self) -> float:
        return time.time() - self.start_time

    def write_jsonl(self, payload: Dict[str, Any]) -> None:
        if self.jsonl_fp is not None:
            self.jsonl_fp.write(json.dumps(payload, separators=(',', ':')) + '\n')
            self.jsonl_fp.flush()

    def emit(self, kind: str, data: Dict[str, Any]) -> None:
        self.event_count += 1
        payload = {
            't': round(self.now_rel(), 3),
            'kind': kind,
            **data,
        }
        line = json.dumps(payload, separators=(',', ':'))
        if self.print_to_terminal:
            print(line, flush=True)
        self.write_jsonl(payload)

    def cue_good_for_handoff(self) -> bool:
        if not self.s.cue_detected:
            return False
        if self.s.cue_area >= self.cue_area_stop_threshold:
            return True
        if self.s.image_width <= 0:
            return False
        err = abs(self.s.cue_center_x - self.cue_center_x_target_px)
        return err <= self.cue_center_tolerance_px

    def hover_height_ok(self) -> Optional[bool]:
        if self.s.tof_cm <= 0:
            return None
        target_cm = self.hover_height_m * 100.0
        tol_cm = self.hover_height_tolerance_m * 100.0
        return abs(self.s.tof_cm - target_cm) <= tol_cm

    def cmd_nonzero(self) -> bool:
        return any(abs(v) > 1e-6 for v in (self.s.cmd_forward, self.s.cmd_left, self.s.cmd_up, self.s.cmd_yaw))

    def classify_cmd_source_guess(self) -> str:
        if self.s.mode == 'gesture':
            return 'gesture_or_failsafe'
        if abs(self.s.cmd_yaw) > 0.0 and abs(self.s.cmd_forward) < 1e-6 and abs(self.s.cmd_left) < 1e-6 and abs(self.s.cmd_up) < 1e-6:
            return 'cue_yaw_only'
        if abs(self.s.cmd_forward) > 0.0 and abs(self.s.cmd_yaw) < 1e-6:
            return 'cue_forward_only'
        if abs(self.s.cmd_up) > 0.0 and abs(self.s.cmd_forward) < 1e-6 and abs(self.s.cmd_left) < 1e-6 and abs(self.s.cmd_yaw) < 1e-6:
            return 'hover_height_control'
        return 'mixed_or_unknown'

    def maybe_emit_change(self, field: str, old: Any, new: Any) -> None:
        if self.print_topic_changes and old != new:
            self.emit('topic_change', {'field': field, 'old': old, 'new': new})

    def on_state(self, msg: String) -> None:
        old = self.s.state
        self.s.state = msg.data.strip()
        if self.s.state != old:
            self.emit('state_change', {'old': old, 'new': self.s.state})
        self.last_state = self.s.state

    def on_mode(self, msg: String) -> None:
        old = self.s.mode
        self.s.mode = msg.data.strip()
        if self.s.mode != old:
            self.emit('mode_change', {'old': old, 'new': self.s.mode})
        self.last_mode = self.s.mode

    def on_link_ok(self, msg: Bool) -> None:
        old = self.s.link_ok
        self.s.link_ok = bool(msg.data)
        self.maybe_emit_change('link_ok', old, self.s.link_ok)

    def on_battery(self, msg: Int32) -> None:
        old = self.s.battery_pct
        self.s.battery_pct = int(msg.data)
        self.maybe_emit_change('battery_pct', old, self.s.battery_pct)

    def on_tof(self, msg: Int32) -> None:
        old = self.s.tof_cm
        self.s.tof_cm = int(msg.data)
        self.maybe_emit_change('tof_cm', old, self.s.tof_cm)

    def on_gesture_valid(self, msg: Bool) -> None:
        old = self.s.gesture_valid
        self.s.gesture_valid = bool(msg.data)
        if self.s.gesture_valid:
            self.last_gesture_valid_time = time.time()
        self.maybe_emit_change('gesture_valid', old, self.s.gesture_valid)

    def on_gesture_label(self, msg: String) -> None:
        old = self.s.gesture_label
        self.s.gesture_label = msg.data.strip()
        if self.s.gesture_label:
            self.last_gesture_label_time = time.time()
        if self.s.gesture_label != old:
            self.emit('gesture_label_change', {'old': old, 'new': self.s.gesture_label})
        self.last_gesture_label = self.s.gesture_label

    def on_cue_detected(self, msg: Bool) -> None:
        old = self.s.cue_detected
        self.s.cue_detected = bool(msg.data)
        if self.s.cue_detected:
            self.last_cue_detected_time = time.time()
        self.maybe_emit_change('cue_detected', old, self.s.cue_detected)

    def on_cue_center_x(self, msg: Int32) -> None:
        self.s.cue_center_x = int(msg.data)
        if self.cue_good_for_handoff():
            self.last_cue_good_time = time.time()

    def on_cue_center_y(self, msg: Int32) -> None:
        self.s.cue_center_y = int(msg.data)

    def on_cue_area(self, msg: Int32) -> None:
        self.s.cue_area = int(msg.data)
        if self.cue_good_for_handoff():
            self.last_cue_good_time = time.time()

    def on_image(self, msg: Image) -> None:
        self.s.image_width = int(msg.width)
        self.s.image_height = int(msg.height)
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        if self.last_image_stamp is not None and stamp > self.last_image_stamp:
            dt = stamp - self.last_image_stamp
            if self.image_dt_ema is None:
                self.image_dt_ema = dt
            else:
                self.image_dt_ema = 0.9 * self.image_dt_ema + 0.1 * dt
        self.last_image_stamp = stamp

    def on_cmd_vel(self, msg: Twist) -> None:
        prev_nonzero = self.cmd_nonzero()
        self.s.cmd_forward = float(msg.linear.x)
        self.s.cmd_left = float(msg.linear.y)
        self.s.cmd_up = float(msg.linear.z)
        self.s.cmd_yaw = float(msg.angular.z)
        now_nonzero = self.cmd_nonzero()
        self.last_cmd_time = time.time()
        if now_nonzero != prev_nonzero:
            self.emit('cmd_zero_crossing', {
                'now_nonzero': now_nonzero,
                'cmd': {
                    'forward': self.s.cmd_forward,
                    'left': self.s.cmd_left,
                    'up': self.s.cmd_up,
                    'yaw': self.s.cmd_yaw,
                },
                'source_guess': self.classify_cmd_source_guess(),
            })

    def on_takeoff(self, _: Empty) -> None:
        self.last_takeoff_event_time = time.time()
        self.emit('takeoff_topic', {})

    def on_land(self, _: Empty) -> None:
        self.last_land_event_time = time.time()
        self.emit('land_topic', {})

    def on_start_hover(self, _: Empty) -> None:
        self.last_start_hover_event_time = time.time()
        self.emit('start_hover_topic', {})

    def on_emergency(self, _: Empty) -> None:
        self.last_emergency_event_time = time.time()
        self.emit('emergency_topic', {})

    def build_anomalies(self) -> list[str]:
        anomalies: list[str] = []
        now = time.time()
        if self.s.mode == 'gesture' and not self.s.gesture_valid and now - self.last_gesture_valid_time > 0.25:
            anomalies.append('gesture_mode_without_recent_valid_gesture')
        if self.s.mode == 'gesture' and self.cmd_nonzero() and not self.s.gesture_valid:
            anomalies.append('nonzero_cmd_in_gesture_mode_without_gesture_valid')
        if self.s.mode == 'gesture' and self.cmd_nonzero() and self.s.gesture_label in ('', 'Land'):
            anomalies.append('nonzero_cmd_in_gesture_mode_with_blank_or_land_label')
        if self.s.state == 'CUE_APPROACH' and self.s.cue_detected and not self.cmd_nonzero():
            anomalies.append('cue_approach_with_detection_but_zero_cmd')
        if self.s.state == 'CUE_APPROACH' and self.s.cue_detected and self.s.cue_area < self.cue_area_stop_threshold and self.s.tof_cm > 0 and self.hover_height_ok() and not self.cmd_nonzero():
            anomalies.append('stopped_short_before_area_threshold')
        if self.s.state in ('WAIT_FOR_CUE', 'CUE_APPROACH') and self.s.cue_detected and self.s.gesture_valid:
            anomalies.append('cue_and_gesture_both_live_during_handoff_window')
        if self.s.state == 'TAKEOFF_HOVER' and self.s.cue_detected:
            anomalies.append('cue_detected_during_takeoff_hover')
        if self.s.link_ok is False and self.cmd_nonzero():
            anomalies.append('nonzero_cmd_while_link_unhealthy')
        return anomalies

    def on_timer(self) -> None:
        now = time.time()
        if now - self.last_summary_time < self.summary_period_s:
            return
        self.last_summary_time = now
        self.summary_count += 1

        fps = None
        if self.image_dt_ema and self.image_dt_ema > 1e-6:
            fps = round(1.0 / self.image_dt_ema, 2)

        cue_x_error = None
        if self.s.image_width > 0 and self.s.cue_center_x >= 0:
            cue_x_error = self.s.cue_center_x - self.cue_center_x_target_px

        payload = {
            'state': self.s.state,
            'mode': self.s.mode,
            'link_ok': self.s.link_ok,
            'battery_pct': self.s.battery_pct,
            'tof_cm': self.s.tof_cm,
            'hover_height_ok': self.hover_height_ok(),
            'cue_detected': self.s.cue_detected,
            'cue_center_x': self.s.cue_center_x,
            'cue_center_y': self.s.cue_center_y,
            'cue_x_error_px': cue_x_error,
            'cue_area': self.s.cue_area,
            'cue_good_for_handoff': self.cue_good_for_handoff(),
            'gesture_valid': self.s.gesture_valid,
            'gesture_label': self.s.gesture_label,
            'cmd': {
                'forward': round(self.s.cmd_forward, 3),
                'left': round(self.s.cmd_left, 3),
                'up': round(self.s.cmd_up, 3),
                'yaw': round(self.s.cmd_yaw, 3),
            },
            'cmd_nonzero': self.cmd_nonzero(),
            'cmd_source_guess': self.classify_cmd_source_guess(),
            'image_wh': [self.s.image_width, self.s.image_height],
            'fps_est': fps,
            'anomalies': self.build_anomalies(),
        }
        if self.print_heartbeat:
            self.emit('heartbeat', payload)

    def destroy_node(self) -> bool:
        if self.jsonl_fp is not None:
            self.jsonl_fp.close()
        return super().destroy_node()


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = ForensicTracker()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
