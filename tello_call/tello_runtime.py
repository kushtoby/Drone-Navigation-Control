#!/usr/bin/env python3
from __future__ import annotations

from typing import Optional
import time

import cv2
from cv_bridge import CvBridge
from djitellopy import Tello
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
from sensor_msgs.msg import Image
from std_msgs.msg import Bool, Empty, Int32


class TelloRuntime(Node):
    """Single-owner Tello hardware interface for the final demo runtime."""

    def __init__(self) -> None:
        super().__init__('tello_runtime')

        # Parameters
        self.declare_parameter('video_period_s', 1.0 / 15.0)
        self.declare_parameter('telemetry_period_s', 0.5)
        self.declare_parameter('watchdog_timeout_s', 0.5)
        self.declare_parameter('rc_limit', 40)
        self.declare_parameter('stream_retry_count', 2)
        self.declare_parameter('publish_debug_logs', False)

        self.video_period_s = float(self.get_parameter('video_period_s').value)
        self.telemetry_period_s = float(self.get_parameter('telemetry_period_s').value)
        self.watchdog_timeout_s = float(self.get_parameter('watchdog_timeout_s').value)
        self.rc_limit = int(self.get_parameter('rc_limit').value)
        self.stream_retry_count = int(self.get_parameter('stream_retry_count').value)
        self.publish_debug_logs = bool(self.get_parameter('publish_debug_logs').value)

        # Publishers
        self.image_pub = self.create_publisher(Image, '/tello/image_raw', 10)
        self.frame_alive_pub = self.create_publisher(Bool, '/tello/frame_alive', 10)
        self.link_ok_pub = self.create_publisher(Bool, '/tello/link_ok', 10)
        self.battery_pub = self.create_publisher(Int32, '/tello/battery', 10)
        self.tof_pub = self.create_publisher(Int32, '/tello/tof_cm', 10)

        # Subscribers
        self.create_subscription(Twist, '/tello/cmd_vel', self.cmd_vel_callback, 10)
        self.create_subscription(Empty, '/tello/takeoff', self.takeoff_callback, 10)
        self.create_subscription(Empty, '/tello/land', self.land_callback, 10)
        self.create_subscription(Empty, '/tello/emergency', self.emergency_callback, 10)

        self.bridge = CvBridge()
        self.tello: Optional[Tello] = None
        self.frame_read = None
        self.connected = False
        self.stream_enabled = False
        self.airborne = False
        self.last_cmd_time = 0.0
        self.last_rc = (0, 0, 0, 0)

        self.connect_and_setup()

        self.video_timer = self.create_timer(self.video_period_s, self.publish_image)
        self.telemetry_timer = self.create_timer(self.telemetry_period_s, self.publish_telemetry)
        self.watchdog_timer = self.create_timer(0.1, self.watchdog_step)

        self.get_logger().info('tello_runtime started.')

    def connect_and_setup(self) -> None:
        try:
            self.get_logger().info('Creating Tello EDU interface...')
            self.tello = Tello()
            self.tello.connect()
            self.connected = True
            self.get_logger().info('Connected to Tello.')

            for i in range(self.stream_retry_count):
                try:
                    self.tello.streamon()
                    self.stream_enabled = True
                    self.frame_read = self.tello.get_frame_read()
                    self.get_logger().info('Video stream started.')
                    break
                except Exception as exc:
                    self.get_logger().warn(f'streamon attempt {i + 1} failed: {exc}')
                    time.sleep(0.5)

            if not self.stream_enabled:
                self.get_logger().error('Failed to start video stream.')
        except Exception as exc:
            self.connected = False
            self.stream_enabled = False
            self.get_logger().error(f'Failed to initialize tello_runtime: {exc}')

    def clamp(self, value: float) -> int:
        return int(max(-self.rc_limit, min(self.rc_limit, round(value))))

    def send_rc(self, left_right: int, forward_back: int, up_down: int, yaw: int) -> None:
        if not self.connected or self.tello is None:
            return
        cmd = (
            self.clamp(left_right),
            self.clamp(forward_back),
            self.clamp(up_down),
            self.clamp(yaw),
        )
        try:
            self.tello.send_rc_control(*cmd)
            self.last_rc = cmd
            if self.publish_debug_logs:
                self.get_logger().info(f'RC command: lr={cmd[0]} fb={cmd[1]} ud={cmd[2]} yaw={cmd[3]}')
        except Exception as exc:
            self.get_logger().error(f'Failed to send RC command: {exc}')

    def cmd_vel_callback(self, msg: Twist) -> None:
        # Direct mapping from Twist fields into Tello RC command units.
        self.last_cmd_time = time.time()
        left_right = msg.linear.y
        forward_back = msg.linear.x
        up_down = msg.linear.z
        yaw = msg.angular.z
        self.send_rc(left_right, forward_back, up_down, yaw)

    def takeoff_callback(self, _: Empty) -> None:
        if not self.connected or self.tello is None:
            self.get_logger().warn('Ignoring takeoff: drone is not connected.')
            return
        if self.airborne:
            self.get_logger().info('Ignoring takeoff: drone already airborne.')
            return
        try:
            self.get_logger().info('Sending takeoff command...')
            self.tello.takeoff()
            self.airborne = True
            self.last_cmd_time = time.time()
        except Exception as exc:
            self.get_logger().error(f'Takeoff failed: {exc}')

    def land_callback(self, _: Empty) -> None:
        if not self.connected or self.tello is None:
            return
        try:
            self.get_logger().info('Sending land command...')
            self.send_rc(0, 0, 0, 0)
            self.tello.land()
            self.airborne = False
        except Exception as exc:
            self.get_logger().error(f'Land failed: {exc}')

    def emergency_callback(self, _: Empty) -> None:
        if not self.connected or self.tello is None:
            return
        try:
            self.get_logger().warn('Emergency stop requested.')
            self.send_rc(0, 0, 0, 0)
            try:
                self.tello.emergency()
            except Exception:
                # Fallback if emergency is unavailable or rejected.
                self.tello.land()
            self.airborne = False
        except Exception as exc:
            self.get_logger().error(f'Emergency handling failed: {exc}')

    def publish_image(self) -> None:
        alive_msg = Bool()
        alive_msg.data = False

        if not self.connected or not self.stream_enabled or self.frame_read is None:
            self.frame_alive_pub.publish(alive_msg)
            self.link_ok_pub.publish(Bool(data=False))
            return

        try:
            frame = self.frame_read.frame
            if frame is None or frame.size == 0:
                self.frame_alive_pub.publish(alive_msg)
                return

            if len(frame.shape) == 3 and frame.shape[2] == 3:
                frame_bgr = frame
            else:
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

            image_msg = self.bridge.cv2_to_imgmsg(frame_bgr, encoding='bgr8')
            self.image_pub.publish(image_msg)

            alive_msg.data = True
            self.frame_alive_pub.publish(alive_msg)
            self.link_ok_pub.publish(Bool(data=True))
        except Exception as exc:
            self.frame_alive_pub.publish(alive_msg)
            self.link_ok_pub.publish(Bool(data=False))
            self.get_logger().error(f'Failed to publish image: {exc}')

    def publish_telemetry(self) -> None:
        if not self.connected or self.tello is None:
            self.link_ok_pub.publish(Bool(data=False))
            return

        link_ok = True
        battery = -1
        tof_cm = -1

        try:
            battery = int(self.tello.get_battery())
        except Exception as exc:
            link_ok = False
            self.get_logger().warn(f'Battery read failed: {exc}')

        try:
            if hasattr(self.tello, 'get_distance_tof'):
                tof_cm = int(self.tello.get_distance_tof())
            else:
                tof_cm = int(self.tello.get_height())
        except Exception as exc:
            self.get_logger().warn(f'ToF/height read failed: {exc}')

        self.link_ok_pub.publish(Bool(data=link_ok))
        self.battery_pub.publish(Int32(data=battery))
        self.tof_pub.publish(Int32(data=tof_cm))

    def watchdog_step(self) -> None:
        if not self.connected or self.tello is None or not self.airborne:
            return
        if time.time() - self.last_cmd_time > self.watchdog_timeout_s and self.last_rc != (0, 0, 0, 0):
            self.send_rc(0, 0, 0, 0)

    def destroy_node(self) -> None:
        try:
            if self.connected and self.tello is not None:
                try:
                    self.send_rc(0, 0, 0, 0)
                except Exception:
                    pass
                try:
                    if self.stream_enabled:
                        self.tello.streamoff()
                except Exception:
                    pass
        finally:
            super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TelloRuntime()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down tello_runtime.')
    finally:
        node.destroy_node()
        rclpy.shutdown()
