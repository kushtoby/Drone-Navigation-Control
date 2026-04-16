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
    FOLLOW_BALLOON = auto()
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

        # Keep the existing parameter interface as much as possible so the current
        # launch file remains usable without edits.
        self.declare_parameter('hover_height_m', 0.91)
        self.declare_parameter('hover_height_tolerance_m', 0.10)
        self.declare_parameter('takeoff_settle_s', 2.5)
        self.declare_parameter('cue_detect_frames', 10)
        self.declare_parameter('cue_lost_frames', 30)
        self.declare_parameter('gesture_switch_frames', 2)
        self.declare_parameter('gesture_switch_label', 'ANY_VALID_GESTURE')
        self.declare_parameter('land_gesture_frames', 5)
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
        # The current launch file sets gesture_switch_frames=2. Per the requested
        # behavior, that becomes a 2-frame grace period and a 3-frame confirmation.
        self.gesture_grace_frames = int(self.get_parameter('gesture_switch_frames').value)
        self.gesture_confirm_frames = self.gesture_grace_frames + 1
        self.land_gesture_label = str(self.get_parameter('land_gesture_label').value)
        self.yaw_deadband_px = int(self.get_parameter('yaw_deadband_px').value)
        self.yaw_kp = float(self.get_parameter('yaw_kp').value)
        self.yaw_cmd_max = float(self.get_parameter('yaw_cmd_max').value)
        self.forward_cmd = float(self.get_parameter('forward_cmd').value)
        self.min_height_cm = int(round(self.hover_height_m * 100.0))
        self.max_height_cm = int(round(8.0 * 12.0 * 2.54))
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
        self.create_subscription(Int32, '/tello/pink_balloon_blob_count', self.pink_blob_count_callback, 10)
        self.create_subscription(Int32, '/tello/pink_balloon_mode_code', self.pink_mode_code_callback, 10)
        
        self.state = MissionState.IDLE
        self.cue = CueObservation()
        self.gesture_valid = False
        self.gesture_label = ''
        self.tof_cm = -1
        self.battery_pct = -1
        self.link_ok = False
        self.image_width = 960
        self.image_height = 720

        self.takeoff_started_at = 0.0
        self.takeoff_sent = False
        self.reported_low_battery = False
        self.last_link_warn_time = 0.0

        self.active_gesture_label = ''
        self.candidate_gesture_label = ''
        self.candidate_gesture_count = 0
        self.gesture_mismatch_count = 0

        self.pink_blob_count = 0
        self.pink_mode_code = 0
        self.two_blob_seen_count = 0

        self.declare_parameter('blob_switch_frames', 20)
        self.blob_switch_frames = int(self.get_parameter('blob_switch_frames').value)

        self.timer = self.create_timer(0.05, self.step)
        self.get_logger().info('mission_supervisor started.')

    def publish_state(self) -> None:
        self.state_pub.publish(String(data=self.state.name))
        mode = 'gesture' if self.state == MissionState.GESTURE_MODE else 'balloon'
        self.mode_pub.publish(String(data=mode))

    def transition_to(self, new_state: MissionState, reason: str = '') -> None:
        if self.state == new_state:
            return
        self.state = new_state
        if reason:
            self.get_logger().info(f'State -> {new_state.name} ({reason})')
        else:
            self.get_logger().info(f'State -> {new_state.name}')

    def reset_gesture_tracking(self) -> None:
        self.active_gesture_label = ''
        self.candidate_gesture_label = ''
        self.candidate_gesture_count = 0
        self.gesture_mismatch_count = 0

    def update_two_blob_counter(self) -> None:
        if self.pink_blob_count == 2:
            self.two_blob_seen_count += 1
        else:
            self.two_blob_seen_count = 0

    def current_observed_gesture(self) -> str:
        return self.gesture_label if self.gesture_valid and self.gesture_label else ''

    def update_candidate_gesture(self, observed_label: str) -> None:
        if not observed_label:
            self.candidate_gesture_label = ''
            self.candidate_gesture_count = 0
            return

        if observed_label == self.candidate_gesture_label:
            self.candidate_gesture_count += 1
        else:
            self.candidate_gesture_label = observed_label
            self.candidate_gesture_count = 1

    def candidate_gesture_confirmed(self) -> bool:
        return (
            bool(self.candidate_gesture_label)
            and self.candidate_gesture_count >= self.gesture_confirm_frames
        )

    def start_hover_callback(self, _: Empty) -> None:
        if self.state == MissionState.IDLE:
            self.takeoff_started_at = time.time()
            self.takeoff_sent = False
            self.reported_low_battery = False
            self.reset_gesture_tracking()
            self.two_blob_seen_count = 0
            self.publish_zero_cmd()
            self.transition_to(MissionState.TAKEOFF_HOVER, 'start_hover received')

    def emergency_callback(self, _: Empty) -> None:
        self.publish_zero_cmd()
        self.transition_to(MissionState.FAILSAFE, 'emergency signal received')

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

    def pink_blob_count_callback(self, msg: Int32) -> None:
        self.pink_blob_count = int(msg.data)

    def pink_mode_code_callback(self, msg: Int32) -> None:
        self.pink_mode_code = int(msg.data)

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

    def clamp_vertical_cmd(self, up_cmd: float) -> float:
        if self.tof_cm <= 0:
            return up_cmd
        if up_cmd < 0.0 and self.tof_cm <= self.min_height_cm:
            return 0.0
        if up_cmd > 0.0 and self.tof_cm >= self.max_height_cm:
            return 0.0
        return up_cmd

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
        cmd.linear.z = self.clamp_vertical_cmd(up)
        cmd.angular.z = yaw
        return cmd

    def compute_balloon_follow_cmd(self) -> Twist:
        msg = Twist()
        if not self.cue.detected:
            return msg

        image_center_x = self.image_width / 2.0
        image_center_y = self.image_height / 2.0
        error_x = float(self.cue.center_x) - image_center_x
        error_y = float(self.cue.center_y) - image_center_y

        yaw_cmd = 0.0
        if abs(error_x) > self.yaw_deadband_px:
            yaw_cmd = max(-self.yaw_cmd_max, min(self.yaw_cmd_max, self.yaw_kp * error_x))

        up_cmd = 0.0
        if abs(error_y) > self.yaw_deadband_px:
            up_cmd = max(-self.climb_cmd, min(self.climb_cmd, -self.yaw_kp * error_y))
        up_cmd = self.clamp_vertical_cmd(up_cmd)

        msg.linear.x = self.forward_cmd
        msg.linear.y = 0.0
        msg.linear.z = up_cmd
        msg.angular.z = yaw_cmd
        return msg

    def activate_gesture(self, label: str) -> None:
        self.active_gesture_label = label
        self.candidate_gesture_label = ''
        self.candidate_gesture_count = 0
        self.gesture_mismatch_count = 0

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
                self.transition_to(MissionState.FOLLOW_BALLOON, 'hover established')
            else:
                self.publish_cmd(up=up_cmd)
            return

        if self.state == MissionState.FOLLOW_BALLOON:
            observed_gesture = self.current_observed_gesture()
            self.update_candidate_gesture(observed_gesture)
            self.update_two_blob_counter()

            gesture_switch_ready = self.candidate_gesture_confirmed()
            blob_switch_ready = self.two_blob_seen_count >= self.blob_switch_frames

            self.get_logger().info(
                f'FOLLOW_BALLOON: blob_count={self.pink_blob_count}, '
                f'two_blob_seen_count={self.two_blob_seen_count}, '
                f'gesture_valid={self.gesture_valid}, '
                f'gesture_label="{self.gesture_label}", '
                f'candidate="{self.candidate_gesture_label}", '
                f'candidate_count={self.candidate_gesture_count}'
            )

            if gesture_switch_ready or blob_switch_ready:
                if gesture_switch_ready:
                    confirmed_label = self.candidate_gesture_label
                    self.activate_gesture(confirmed_label)
                    self.two_blob_seen_count = 0
                    self.transition_to(MissionState.GESTURE_MODE, f'gesture={confirmed_label} confirmed')

                    if confirmed_label == self.land_gesture_label:
                        self.publish_zero_cmd()
                        self.send_land()
                        self.transition_to(MissionState.LANDING, 'land gesture confirmed')
                    else:
                        self.cmd_pub.publish(self.gesture_to_cmd(confirmed_label))
                    return

                if blob_switch_ready:
                    self.reset_gesture_tracking()
                    self.two_blob_seen_count = 0
                    self.transition_to(MissionState.GESTURE_MODE, 'two-blob cue confirmed')
                    self.publish_zero_cmd()
                    return

            if self.cue.detected:
                self.cmd_pub.publish(self.compute_balloon_follow_cmd())
            else:
                self.publish_zero_cmd()
            return

        if self.state == MissionState.GESTURE_MODE:
            observed_gesture = self.current_observed_gesture()
            self.update_two_blob_counter()
            blob_land_ready = self.two_blob_seen_count >= self.blob_switch_frames

            if blob_land_ready:
                self.publish_zero_cmd()
                self.send_land()
                self.two_blob_seen_count = 0
                self.transition_to(MissionState.LANDING, 'two-blob cue confirmed in gesture mode')
                return

            if self.active_gesture_label:
                if observed_gesture == self.active_gesture_label:
                    self.gesture_mismatch_count = 0
                    self.candidate_gesture_label = ''
                    self.candidate_gesture_count = 0
                    if self.active_gesture_label == self.land_gesture_label:
                        self.publish_zero_cmd()
                        self.send_land()
                        self.transition_to(MissionState.LANDING, 'land gesture active')
                    else:
                        self.cmd_pub.publish(self.gesture_to_cmd(self.active_gesture_label))
                    return

                self.gesture_mismatch_count += 1
                if self.gesture_mismatch_count <= self.gesture_grace_frames:
                    if self.active_gesture_label == self.land_gesture_label:
                        self.publish_zero_cmd()
                        self.send_land()
                        self.transition_to(MissionState.LANDING, 'land gesture active during grace period')
                    else:
                        self.cmd_pub.publish(self.gesture_to_cmd(self.active_gesture_label))
                    return

                # Third consecutive non-matching frame: drop the old gesture and start
                # counting a new candidate from the current frame, if any.
                self.active_gesture_label = ''
                self.gesture_mismatch_count = 0
                self.candidate_gesture_label = ''
                self.candidate_gesture_count = 0
                self.update_candidate_gesture(observed_gesture)
                if self.candidate_gesture_confirmed():
                    confirmed_label = self.candidate_gesture_label
                    self.activate_gesture(confirmed_label)
                    if confirmed_label == self.land_gesture_label:
                        self.publish_zero_cmd()
                        self.send_land()
                        self.transition_to(MissionState.LANDING, 'land gesture confirmed')
                    else:
                        self.cmd_pub.publish(self.gesture_to_cmd(confirmed_label))
                else:
                    self.publish_zero_cmd()
                return

            # No active gesture: wait for a new one to be confirmed in gesture mode.
            self.update_candidate_gesture(observed_gesture)
            if self.candidate_gesture_confirmed():
                confirmed_label = self.candidate_gesture_label
                self.activate_gesture(confirmed_label)
                if confirmed_label == self.land_gesture_label:
                    self.publish_zero_cmd()
                    self.send_land()
                    self.transition_to(MissionState.LANDING, 'land gesture confirmed')
                else:
                    self.cmd_pub.publish(self.gesture_to_cmd(confirmed_label))
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
        if rclpy.ok():
            rclpy.shutdown()
