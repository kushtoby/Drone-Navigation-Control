from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    return LaunchDescription([
        Node(
            package='tello_call',
            executable='tello_runtime',
            name='tello_runtime',
            output='screen',
            parameters=[{
                'video_period_s': 1.0 / 15.0,
                'telemetry_period_s': 0.5,
                'watchdog_timeout_s': 0.5,
                'rc_limit': 35,
            }],
        ),
        Node(
            package='tello_call',
            executable='pink_balloon_detector',
            name='pink_balloon_detector',
            output='screen',
            parameters=[{
                'show_debug': True,
                'min_pixel_count': 320,
                'min_blob_area': 120,
                'roi_top_frac': 0.0,
                'roi_bottom_frac': 0.9,
                'required_hits': 3,
                'history_len': 5,
                'pink_hsv_lower': [140, 80, 80],
                'pink_hsv_upper': [179, 255, 255],
            }],
        ),
        Node(
            package='tello_call',
            executable='gesture_recognizer',
            name='gesture_recognizer',
            output='screen',
            parameters=[{
                'show_debug': False,
            }],
        ),
        Node(
            package='tello_call',
            executable='mission_supervisor',
            name='mission_supervisor',
            output='screen',
            parameters=[{
                'hover_height_m': 0.91,
                'cue_detect_frames': 10,
                'cue_lost_frames': 10,
                'gesture_switch_frames': 12,
                'land_gesture_frames': 15,
                'land_gesture_label': 'Land',
                'yaw_deadband_px': 80,
                'yaw_kp': 0.10,
                'yaw_cmd_max': 22.0,
                'forward_cmd': 18.0,
                'area_stop_threshold': 22000,
                'tof_min_cm': 45,
                'climb_cmd': 18.0,
                'gesture_cmd_mag': 20.0,
            }],
        ),
        Node(
            package='tello_call',
            executable='demo_tui',
            name='demo_tui',
            output='screen',
        ),
    ])
