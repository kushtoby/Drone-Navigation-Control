from setuptools import find_packages, setup


package_name = 'tello_call'


setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    include_package_data=True,
    package_data={
        'tello_call': [
            'model/keypoint_classifier/*.csv',
            'model/keypoint_classifier/*.tflite',
        ],
    },
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', [
            'launch/status_demo.launch.py',
            'launch/accio_demo.launch.py',
        ]),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='kush',
    maintainer_email='kush@todo.todo',
    description='Implementation of Hand Gesture Control for DJI Tello',
    license='MIT',
    extras_require={
        'test': ['pytest'],
    },
    entry_points={
        'console_scripts': [
            'tello_adapter = tello_call.tello_adapter:main',
            'tello_camera = tello_call.tello_camera:main',
            'tello_image_publisher = tello_call.tello_image_publisher:main',
            'tello_runtime = tello_call.tello_runtime:main',
            'image_listener = tello_call.image_listener:main',
            'status_monitor = tello_call.status_monitor:main',
            'status_source = tello_call.status_source:main',
            'hand_detector = tello_call.hand_detector:main',
            'hand_debug_viewer = tello_call.hand_debug_viewer:main',
            'pink_balloon_detector = tello_call.pink_balloon_detector:main',
            'gesture_recognizer = tello_call.gesture_recognizer:main',
            'mission_supervisor = tello_call.mission_supervisor:main',
            'demo_tui = tello_call.demo_tui:main',
        ],
    },
)
