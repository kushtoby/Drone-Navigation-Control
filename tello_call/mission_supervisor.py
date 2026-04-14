#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, Empty, Int32, String


class MissionState(Enum):
    IDLE = auto()
    TAKEOFF_HOVER = auto()
    WAIT_FOR_CUE = auto()
    CUE_APPROACH = auto()
    GESTURE_MODE = auto()
    LANDING = auto()
    FAILSAFE = auto()


@dataclass
class CueObservation:
    detected: bool = False
    center_x: int = 0
    center_y: int = 0
    area: int = 0


class MissionSupervisor(Node):
    def __init__(self) -> None:
        super().__init__('mission_supervisor')

        self.declare_parameter('hover_height_m', 0.91)
        self.declare_parameter('hover_height_tolerance_m', 0.10)
        self.declare_parameter('takeoff_settle_s', 2.5)

        self.declare_parameter('cue_detect_frames', 10)
        self.declare_parameter('cue_lost_frames', 10)
        self.declare_parameter('gesture_switch_frames', 12)
        self.declare_parameter('land_gesture_frames', 15)
        self.declare_parameter('land_gesture_label', 'Land')

        self.declare_parameter('yaw_deadband_px', 80)
        self.declare_parameter('yaw_kp', 0.10)
        self.declare_parameter('yaw_cmd_max', 22.0)
        self.declare_parameter('forward_cmd', 18.0)
        self.declare_parameter('area_stop_threshold', 22000)
        self.declare_parameter('tof_min_cm', 45)
        self.declare_parameter('climb_cmd', 18.0)
        self.declare_parameter('gesture_cmd_mag', 20.0)
        self.declare_parameter('low_battery_warn_pct', 20)

        self.hover_height_m = float(self.get_parameter('hover_height_m').value)
        self.hover_height_tolerance_m = float(self.get_parameter('hover_height_tolerance_m').value)
        self.takeoff_settle_s = float(self.get_parameter('takeoff_settle_s').value)
        self.cue_detect_frames = int(self.get_parameter('cue_detect_frames').value)
        self.cue_lost_frames = int(self.get_parameter('cue_lost_frames').value)
        self.gesture_switch_frames = int(self.get_parameter('gesture_switch_frames').value)
        self.land_gesture_frames = int(self.get_parameter('land_gesture_frames').value)
        self.land_gesture_label = str(self.get_parameter('land_gesture_label').value)
        self.yaw_deadband_px = int(self.get_parameter('yaw_deadband_px').value)
        self.yaw_kp = float(self.get_parameter('yaw_kp').value)
        self.yaw_cmd_max = float(self.get_parameter('yaw_cmd_max').value)
        self.forward_cmd = float(self.get_parameter('forward_cmd').value)
        self.area_stop_threshold = int(self.get_parameter('area_stop_threshold').value)
        self.tof_min_cm = int(self.get_parameter('tof_min_cm').value)
        self.climb_cmd = float(self.get_parameter('climb_cmd').value)
        self.gesture_cmd_mag = float(self.get_parameter('gesture_cmd_mag').value)
        self.low_battery_warn_pct = int(self.get_parameter('low_battery_warn_pct').value)

        self.takeoff_pub = self.create_publisher(Empty, '/tello/takeoff', 10)
        self.land_pub = self.create_publisher(Empty, '/tello/land', 10)
        self.cmd_pub = self.create_publisher(Twist, '/tello/cmd_vel', 10)
        self.state_pub = self.create_publisher(String, '/tello/state', 10)
        self.mode_pub = self.create_publisher(String, '/tello/mode', 10)

        self.create_subscription(Empty, '/tello/start_hover', self.start_hover_callback, 10)
        self.create_subscription(Empty, '/tello/emergency', self.emergency_callback, 10)
        self.create_subscription(Bool, '/tello/pink_balloon_detected', self.cue_detected_callback, 10)
        self.create_subscription(Int32, '/tello/pink_balloon_center_x', self.cue_center_x_callback, 10)
        self.create_subscription(Int32, '/tello/pink_balloon_center_y', self.cue_center_y_callback, 10)
        self.create_subscription(Int32, '/tello/pink_balloon_area', self.cue_area_callback, 10)
        self.create_subscription(Bool, '/tello/gesture_valid', self.gesture_valid_callback, 10)
        self.create_subscription(String, '/tello/gesture_label', self.gesture_label_callback, 10)
        self.create_subscription(Int32, '/tello/tof_cm', self.tof_callback, 10)
        self.create_subscription(Int32, '/tello/battery', self.battery_callback, 10)
        self.create_subscription(Bool, '/tello/link_ok', self.link_ok_callback, 10)
        self.create_subscription(Image, '/tello/image_raw', self.image_info_callback, 10)

        self.state = MissionState.IDLE
        self.cue = CueObservation()
        self.gesture_valid = False
        self.gesture_label = ''
        self.last_valid_gesture_label = ''
        self.tof_cm = -1
        self.battery_pct = -1
        self.link_ok = False
        self.image_width = 960
        self.image_height = 720

        self.cue_seen_count = 0
        self.cue_lost_count = 0
        self.gesture_seen_count = 0
        self.land_seen_count = 0
        self.last_switch_label = ''
        self.takeoff_started_at = 0.0
        self.takeoff_sent = False
        self.reported_low_battery = False
        self.gesture_mode_locked = False
        self.last_link_warn_time = 0.0

        self.timer = self.create_timer(0.05, self.step)
        self.get_logger().info('mission_supervisor started.')

    def publish_state(self) -> None:
        self.state_pub.publish(String(data=self.state.name))
        self.mode_pub.publish(String(data=('gesture' if self.gesture_mode_locked else 'cue')))

    def start_hover_callback(self, _: Empty) -> None:
        if self.state == MissionState.IDLE:
            self.state = MissionState.TAKEOFF_HOVER
            self.takeoff_started_at = time.time()
            self.takeoff_sent = False
            self.cue_seen_count = 0
            self.cue_lost_count = 0
            self.gesture_seen_count = 0
            self.land_seen_count = 0
            self.gesture_mode_locked = False
            self.get_logger().info('Start-hover received. Entering TAKEOFF_HOVER.')

    def emergency_callback(self, _: Empty) -> None:
        self.state = MissionState.FAILSAFE
        self.publish_zero_cmd()
        self.get_logger().warn('Emergency signal received. Entering FAILSAFE.')

    def cue_detected_callback(self, msg: Bool) -> None:
        self.cue.detected = bool(msg.data)

    def cue_center_x_callback(self, msg: Int32) -> None:
        self.cue.center_x = int(msg.data)

    def cue_center_y_callback(self, msg: Int32) -> None:
        self.cue.center_y = int(msg.data)

    def cue_area_callback(self, msg: Int32) -> None:
        self.cue.area = int(msg.data)

    def gesture_valid_callback(self, msg: Bool) -> None:
        self.gesture_valid = bool(msg.data)

    def gesture_label_callback(self, msg: String) -> None:
        self.gesture_label = msg.data.strip()
        if self.gesture_label:
            self.last_valid_gesture_label = self.gesture_label

    def tof_callback(self, msg: Int32) -> None:
        self.tof_cm = int(msg.data)

    def battery_callback(self, msg: Int32) -> None:
        self.battery_pct = int(msg.data)
        if self.battery_pct > 0 and self.battery_pct <= self.low_battery_warn_pct and not self.reported_low_battery:
            self.reported_low_battery = True
            self.get_logger().warn(f'Battery is low: {self.battery_pct}%')

    def link_ok_callback(self, msg: Bool) -> None:
        self.link_ok = bool(msg.data)

    def image_info_callback(self, msg: Image) -> None:
        self.image_width = int(msg.width) if msg.width > 0 else self.image_width
        self.image_height = int(msg.height) if msg.height > 0 else self.image_height

    def publish_zero_cmd(self) -> None:
        self.cmd_pub.publish(Twist())

    def publish_cmd(self, forward: float = 0.0, left: float = 0.0, up: float = 0.0, yaw: float = 0.0) -> None:
        msg = Twist()
        msg.linear.x = float(forward)
        msg.linear.y = float(left)
        msg.linear.z = float(up)
        msg.angular.z = float(yaw)
        self.cmd_pub.publish(msg)

    def send_takeoff_once(self) -> None:
        if not self.takeoff_sent:
            self.takeoff_pub.publish(Empty())
            self.takeoff_sent = True
            self.takeoff_started_at = time.time()
            self.get_logger().info('Takeoff command published.')

    def send_land(self) -> None:
        self.land_pub.publish(Empty())
        self.get_logger().info('Land command published.')

    def target_hover_reached(self) -> bool:
        if self.tof_cm <= 0:
            return (time.time() - self.takeoff_started_at) >= self.takeoff_settle_s
        target_cm = self.hover_height_m * 100.0
        tol_cm = self.hover_height_tolerance_m * 100.0
        return abs(self.tof_cm - target_cm) <= tol_cm

    def hover_height_correction_cmd(self) -> float:
        if self.tof_cm <= 0:
            return 0.0
        target_cm = self.hover_height_m * 100.0
        tol_cm = self.hover_height_tolerance_m * 100.0
        if self.tof_cm < target_cm - tol_cm:
            return self.climb_cmd
        if self.tof_cm > target_cm + tol_cm:
            return -self.climb_cmd * 0.5
        return 0.0

    def update_cue_counters(self) -> None:
        if self.cue.detected:
            self.cue_seen_count += 1
            self.cue_lost_count = 0
        else:
            self.cue_lost_count += 1
            self.cue_seen_count = 0

    def update_gesture_switch_counter(self) -> None:
        if self.gesture_valid and self.gesture_label:
            if self.gesture_label == self.last_switch_label:
                self.gesture_seen_count += 1
            else:
                self.last_switch_label = self.gesture_label
                self.gesture_seen_count = 1
        else:
            self.last_switch_label = ''
            self.gesture_seen_count = 0

    def update_land_counter(self) -> None:
        if self.gesture_valid and self.gesture_label == self.land_gesture_label:
            self.land_seen_count += 1
        else:
            self.land_seen_count = 0

    def gesture_to_cmd(self, label: str) -> Twist:
        cmd = Twist()
        mag = self.gesture_cmd_mag
        mapping = {
            'Forward': (mag, 0.0, 0.0, 0.0),
            'Back': (-mag, 0.0, 0.0, 0.0),
            'Left': (0.0, -mag, 0.0, 0.0),
            'Right': (0.0, mag, 0.0, 0.0),
            'Up': (0.0, 0.0, mag, 0.0),
            'Down': (0.0, 0.0, -mag, 0.0),
            'Stop': (0.0, 0.0, 0.0, 0.0),
            'Land': (0.0, 0.0, 0.0, 0.0),
        }
        forward, left, up, yaw = mapping.get(label, (0.0, 0.0, 0.0, 0.0))
        cmd.linear.x = forward
        cmd.linear.y = left
        cmd.linear.z = up
        cmd.angular.z = yaw
        return cmd

    def step(self) -> None:
        self.publish_state()

        if self.state == MissionState.IDLE:
            self.publish_zero_cmd()
            return

        if self.state == MissionState.FAILSAFE:
            self.publish_zero_cmd()
            return

        if not self.link_ok and self.state != MissionState.TAKEOFF_HOVER:
            self.publish_zero_cmd()
            now = time.time()
            if now - self.last_link_warn_time > 5.0:
                self.get_logger().warn('Link not healthy. Holding hover commands at zero.')
                self.last_link_warn_time = now
            return

        if self.state == MissionState.TAKEOFF_HOVER:
            self.send_takeoff_once()
            up_cmd = self.hover_height_correction_cmd()
            if self.target_hover_reached():
                self.publish_zero_cmd()
                self.state = MissionState.WAIT_FOR_CUE
                self.get_logger().info('Hover established. Entering WAIT_FOR_CUE.')
            else:
                self.publish_cmd(up=up_cmd)
            return

        if self.state == MissionState.WAIT_FOR_CUE:
            self.publish_zero_cmd()
            self.update_cue_counters()
            self.update_gesture_switch_counter()
            if self.cue_seen_count >= self.cue_detect_frames:
                self.state = MissionState.CUE_APPROACH
                self.get_logger().info('Cue confirmed. Entering CUE_APPROACH.')
            return

        if self.state == MissionState.CUE_APPROACH:
            self.update_cue_counters()
            self.update_gesture_switch_counter()

            if self.gesture_seen_count >= self.gesture_switch_frames:
                self.gesture_mode_locked = True
                self.state = MissionState.GESTURE_MODE
                self.publish_zero_cmd()
                self.get_logger().info(
                    f'Gesture mode engaged by label "{self.last_switch_label}". Cue tracking is now disabled.'
                )
                return

            if self.cue_lost_count >= self.cue_lost_frames:
                self.publish_zero_cmd()
                self.state = MissionState.WAIT_FOR_CUE
                self.get_logger().info('Cue lost. Returning to WAIT_FOR_CUE.')
                return

            if not self.cue.detected:
                self.publish_zero_cmd()
                return

            image_center_x = self.image_width // 2
            error_x = self.cue.center_x - image_center_x
            yaw_cmd = 0.0
            forward_cmd = 0.0
            up_cmd = 0.0

            if abs(error_x) > self.yaw_deadband_px:
                yaw_cmd = max(-self.yaw_cmd_max, min(self.yaw_cmd_max, self.yaw_kp * error_x))
            else:
                if self.cue.area < self.area_stop_threshold:
                    forward_cmd = self.forward_cmd

            if self.tof_cm > 0 and self.tof_cm < self.tof_min_cm:
                up_cmd = self.climb_cmd

            self.publish_cmd(forward=forward_cmd, up=up_cmd, yaw=yaw_cmd)
            return

        if self.state == MissionState.GESTURE_MODE:
            self.update_land_counter()
            if self.land_seen_count >= self.land_gesture_frames:
                self.publish_zero_cmd()
                self.send_land()
                self.state = MissionState.LANDING
                return

            if self.gesture_valid and self.gesture_label:
                cmd = self.gesture_to_cmd(self.gesture_label)
                if self.tof_cm > 0 and self.tof_cm < self.tof_min_cm and cmd.linear.z <= 0.0:
                    cmd.linear.z = self.climb_cmd
                self.cmd_pub.publish(cmd)
            else:
                self.publish_zero_cmd()
            return

        if self.state == MissionState.LANDING:
            self.publish_zero_cmd()
            return


def main(args=None) -> None:
    rclpy.init(args=args)
    node = MissionSupervisor()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down mission_supervisor.')
    finally:
        node.destroy_node()
        rclpy.shutdown()
