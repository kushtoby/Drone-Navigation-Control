from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='tello_call',
            executable='tello_adapter',
            name='tello_adapter',
            output='screen',
        ),
        Node(
            package='tello_call',
            executable='status_monitor',
            name='status_monitor',
            output='screen',
        ),
    ])