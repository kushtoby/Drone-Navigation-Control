from setuptools import find_packages, setup

package_name = 'tello_call'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/status_demo.launch.py']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='kush',
    maintainer_email='kush@todo.todo',
    description='Implementation of Hand Gesture Control for DJI Tello',
    license='MIT',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'tello_adapter = tello_call.tello_adapter:main',
            'tello_camera = tello_call.tello_camera:main',
            'tello_image_publisher = tello_call.tello_image_publisher:main',
            'image_listener = tello_call.image_listener:main',
            'hand_detector = tello_call.hand_detector:main',
            'hand_debug_viewer = tello_call.hand_debug_viewer:main',
            'green_cue_detector = tello_call.green_cue_detector:main',
        ],
    },
)