#!/usr/bin/env python3
from __future__ import annotations

import select
import sys
import termios
import tty

import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty


class DemoTUI(Node):
    def __init__(self) -> None:
        super().__init__('demo_tui')
        self.start_pub = self.create_publisher(Empty, '/tello/start_hover', 10)
        self.land_pub = self.create_publisher(Empty, '/tello/land', 10)
        self.timer = self.create_timer(0.05, self.poll_keyboard)

        self.stdin_fd = sys.stdin.fileno()
        self.old_term = termios.tcgetattr(self.stdin_fd)
        tty.setcbreak(self.stdin_fd)

        self.get_logger().info('demo_tui started. Keys: s=start hover, e=land, q=quit TUI.')

    def poll_keyboard(self) -> None:
        dr, _, _ = select.select([sys.stdin], [], [], 0.0)
        if not dr:
            return
        ch = sys.stdin.read(1)
        if ch in ('s', 'S'):
            self.start_pub.publish(Empty())
            self.get_logger().info('Published /tello/start_hover')
        elif ch in ('e', 'E'):
            self.land_pub.publish(Empty())
            self.get_logger().warn('Published /tello/land')
        elif ch in ('q', 'Q'):
            self.get_logger().info('Quit requested. Stopping TUI node.')
            raise KeyboardInterrupt

    def destroy_node(self) -> None:
        termios.tcsetattr(self.stdin_fd, termios.TCSADRAIN, self.old_term)
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = DemoTUI()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()