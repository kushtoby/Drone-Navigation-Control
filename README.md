# Tello ROS 2 Project — Current Progress and Rebuild Guide

## Overview

This document describes **exactly what has been built so far**, **why it was built this way**, and **how to recreate it from scratch**.

At this stage, the project still has **not** implemented gesture recognition, flight control, or landing logic. What has been built is the ROS 2 and hardware foundation needed before perception and control can be added safely and cleanly.

The current system now includes:

- a ROS 2 Python package
- a working Python virtual environment
- a `tello_adapter` node for telemetry
- a `tello_camera` node for frame-health checks
- a `tello_image_publisher` node for ROS image publishing
- an `image_listener` node for subscribing to ROS images
- successful connection to the Tello drone
- working ROS 2 topics for battery, link, frame health, and image transport

This stage proves that:

1. ROS 2 can run the package correctly
2. the correct Python environment is being used
3. `djitellopy` works with the Tello on this machine
4. the drone can be reached over Wi-Fi
5. ROS 2 topics can publish live telemetry
6. the Tello video stream can be received
7. OpenCV frames can be converted to ROS images with `cv_bridge`
8. ROS image subscribers can receive and decode those images successfully

---

## Current Architecture

The project has moved from a minimal telemetry-only layout to a basic ROS vision pipeline.

### Telemetry side

```text
Tello drone  --->  djitellopy  --->  tello_adapter  --->  ROS 2 topics
```

### Vision side

```text
Tello drone  --->  djitellopy  --->  tello_image_publisher  --->  /tello/image_raw  --->  image_listener
```

### Important note

At the current stage, these nodes are still tested **individually**, not all at once.  
That is intentional.

Each of these nodes currently creates its own `Tello()` connection when run, so they should **not** all be run simultaneously in the final system. Right now they are being used as isolated validation stages.

---

## Current Working ROS 2 Topics

### Telemetry topics
- `/tello/battery` (`std_msgs/Int32`)
- `/tello/link_ok` (`std_msgs/Bool`)

### Camera/frame-health topics
- `/tello/frame_alive` (`std_msgs/Bool`)
- `/tello/frame_width` (`std_msgs/Int32`)
- `/tello/frame_height` (`std_msgs/Int32`)

### ROS image transport topics
- `/tello/image_raw` (`sensor_msgs/Image`)
- `/tello/image_received` (`std_msgs/Bool`)

---

## Current Working Nodes

- `tello_adapter`
- `tello_camera`
- `tello_image_publisher`
- `image_listener`

---

## What Has Been Completed

### 1. ROS 2 package created
A Python ROS 2 package named:

```text
tello_call
```

was created inside the workspace:

```text
~/ros2_ws/src/tello_call
```

---

### 2. Python virtual environment created
A virtual environment was created to avoid system Python package conflicts:

```text
~/tello_venv
```

This was necessary because Ubuntu / Debian Python is externally managed, so `pip install` into system Python was blocked.

---

### 3. Required Python packages installed inside the virtual environment
Installed packages include:

- `djitellopy`
- `opencv-python`
- `colcon-common-extensions`

Later, ROS-side image transport was also used through:

- `cv_bridge` from ROS Jazzy

---

### 4. Interpreter mismatch issue fixed
A major issue occurred where:

- `python3` inside the virtual environment could import `djitellopy`
- but `ros2 run tello_call tello_adapter` failed with:

```text
ModuleNotFoundError: No module named 'djitellopy'
```

The cause was that ROS 2 had generated the launcher script with this shebang:

```text
#!/usr/bin/python3
```

instead of using the active virtual environment.

This was fixed by adding a `setup.cfg` file in the package root with:

```ini
[develop]
script_dir=$base/lib/tello_call

[install]
install_scripts=$base/lib/tello_call

[build_scripts]
executable=/usr/bin/env python3
```

After rebuilding, the launcher respects the active environment.

---

### 5. ROS 2 daemon discovery issue identified
At one point the node was publishing, but `ros2 topic list` showed only:

```text
/parameter_events
/rosout
```

This turned out to be a ROS daemon / discovery issue, not a node failure.

Using:

```bash
ros2 topic list --no-daemon
ros2 node list --no-daemon
```

showed the real topics correctly.

So for debugging, `--no-daemon` is useful.

---

### 6. `tello_adapter.py` created and working
The telemetry node:
- creates a Tello object
- connects to the drone
- reads battery percentage
- publishes battery and link status to ROS 2 topics

No movement or flight commands are used.

---

### 7. `tello_camera.py` created and working
A camera-health node was added to test the Tello video stream without trying to display frames or publish ROS images yet.

This node:
- connects to Tello
- starts the stream
- reads frames
- confirms whether a frame is alive
- publishes width and height

This stage proved the video stream itself worked reliably before introducing `cv_bridge`.

---

### 8. `cv_bridge` / NumPy compatibility issue fixed
When `cv_bridge` was tested, it failed because the ROS Jazzy `cv_bridge` binary had been compiled against NumPy 1.x, while the virtual environment had NumPy 2.x.

This caused an ABI compatibility error.

The fix was to downgrade NumPy inside the virtual environment to a 1.x version.

After that, `cv_bridge` imported and worked correctly.

---

### 9. `tello_image_publisher.py` created and working
A ROS image publisher node was added.

This node:
- connects to Tello
- starts the stream
- grabs OpenCV frames
- converts them with `cv_bridge`
- publishes ROS images on:

```text
/tello/image_raw
```

It also publishes `/tello/frame_alive`.

This stage proved the Tello camera stream could be turned into a proper ROS image topic.

---

### 10. `image_listener.py` created and working
A ROS image subscriber node was added to validate the full image pipeline.

This node:
- subscribes to `/tello/image_raw`
- converts ROS images back to OpenCV frames using `cv_bridge`
- publishes `/tello/image_received`
- logs image width, height, and encoding

This proved the full image chain works:

```text
Tello stream -> OpenCV frame -> ROS image -> subscriber -> OpenCV frame
```

---

## Current Working Package Structure

Package root:

```text
~/ros2_ws/src/tello_call
```

Expected structure:

```text
tello_call/
├── package.xml
├── setup.py
├── setup.cfg
├── resource/
│   └── tello_call
├── launch/
│   └── ...
└── tello_call/
    ├── __init__.py
    ├── tello_adapter.py
    ├── tello_camera.py
    ├── tello_image_publisher.py
    └── image_listener.py
```

---

## Current Core Files

## `tello_adapter.py`

```python
import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32, Bool
from djitellopy import Tello


class TelloAdapter(Node):
    def __init__(self) -> None:
        super().__init__('tello_adapter')

        self.battery_pub = self.create_publisher(Int32, '/tello/battery', 10)
        self.link_pub = self.create_publisher(Bool, '/tello/link_ok', 10)

        self.tello = None
        self.connected = False

        self.connect_and_setup()

        self.status_timer = self.create_timer(1.0, self.publish_status)

        self.get_logger().info('Tello adapter started.')

    def connect_and_setup(self) -> None:
        try:
            self.get_logger().info('Creating Tello object...')
            self.tello = Tello()

            self.get_logger().info('Connecting to Tello...')
            self.tello.connect()
            self.connected = True

            battery = int(self.tello.get_battery())
            self.get_logger().info(f'Connected to Tello. Battery: {battery}%')

        except Exception as e:
            self.connected = False
            self.get_logger().error(f'Failed to connect/setup Tello: {e}')

    def publish_status(self) -> None:
        link_msg = Bool()
        battery_msg = Int32()

        if not self.connected or self.tello is None:
            link_msg.data = False
            self.link_pub.publish(link_msg)
            self.get_logger().warn('Tello not connected.')
            return

        try:
            battery = int(self.tello.get_battery())

            link_msg.data = True
            battery_msg.data = battery

            self.link_pub.publish(link_msg)
            self.battery_pub.publish(battery_msg)

            self.get_logger().info(f'Published battery={battery}%, link_ok=True')

        except Exception as e:
            link_msg.data = False
            self.link_pub.publish(link_msg)
            self.get_logger().error(f'Failed to read battery/status: {e}')

    def destroy_node(self) -> None:
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TelloAdapter()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down Tello adapter.')
    finally:
        node.destroy_node()
        rclpy.shutdown()
```

---

## `tello_camera.py`

```python
import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Int32
from djitellopy import Tello


class TelloCamera(Node):
    def __init__(self) -> None:
        super().__init__('tello_camera')

        self.frame_alive_pub = self.create_publisher(Bool, '/tello/frame_alive', 10)
        self.frame_width_pub = self.create_publisher(Int32, '/tello/frame_width', 10)
        self.frame_height_pub = self.create_publisher(Int32, '/tello/frame_height', 10)

        self.tello = None
        self.frame_read = None
        self.connected = False
        self.stream_enabled = False

        self.connect_and_setup()

        self.frame_timer = self.create_timer(0.1, self.check_frame)
        self.get_logger().info('Tello camera node started.')

    def connect_and_setup(self) -> None:
        try:
            self.get_logger().info('Creating Tello object...')
            self.tello = Tello()

            self.get_logger().info('Connecting to Tello...')
            self.tello.connect()
            self.connected = True
            self.get_logger().info('Connected to Tello.')

            self.get_logger().info('Starting video stream...')
            self.tello.streamon()
            self.stream_enabled = True

            self.frame_read = self.tello.get_frame_read()
            self.get_logger().info('Video stream started.')

        except Exception as e:
            self.connected = False
            self.stream_enabled = False
            self.get_logger().error(f'Failed to connect/setup camera: {e}')

    def check_frame(self) -> None:
        alive_msg = Bool()
        width_msg = Int32()
        height_msg = Int32()

        if not self.connected or not self.stream_enabled or self.frame_read is None:
            alive_msg.data = False
            self.frame_alive_pub.publish(alive_msg)
            self.get_logger().warn('Camera not ready.')
            return

        try:
            frame = self.frame_read.frame

            if frame is None:
                alive_msg.data = False
                self.frame_alive_pub.publish(alive_msg)
                self.get_logger().warn('No frame received.')
                return

            height, width = frame.shape[:2]

            alive_msg.data = True
            width_msg.data = int(width)
            height_msg.data = int(height)

            self.frame_alive_pub.publish(alive_msg)
            self.frame_width_pub.publish(width_msg)
            self.frame_height_pub.publish(height_msg)

            self.get_logger().info(f'Frame received: width={width}, height={height}')

        except Exception as e:
            alive_msg.data = False
            self.frame_alive_pub.publish(alive_msg)
            self.get_logger().error(f'Failed to read frame: {e}')

    def destroy_node(self) -> None:
        try:
            if self.tello is not None and self.stream_enabled:
                self.tello.streamoff()
        except Exception as e:
            self.get_logger().warn(f'Failed to stop stream cleanly: {e}')

        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TelloCamera()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down Tello camera.')
    finally:
        node.destroy_node()
        rclpy.shutdown()
```

---

## `tello_image_publisher.py`

```python
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Bool
from cv_bridge import CvBridge
from djitellopy import Tello


class TelloImagePublisher(Node):
    def __init__(self) -> None:
        super().__init__('tello_image_publisher')

        self.image_pub = self.create_publisher(Image, '/tello/image_raw', 10)
        self.frame_alive_pub = self.create_publisher(Bool, '/tello/frame_alive', 10)

        self.bridge = CvBridge()

        self.tello = None
        self.frame_read = None
        self.connected = False
        self.stream_enabled = False

        self.connect_and_setup()

        self.timer = self.create_timer(0.1, self.publish_image)
        self.get_logger().info('Tello image publisher started.')

    def connect_and_setup(self) -> None:
        try:
            self.get_logger().info('Creating Tello object...')
            self.tello = Tello()

            self.get_logger().info('Connecting to Tello...')
            self.tello.connect()
            self.connected = True
            self.get_logger().info('Connected to Tello.')

            self.get_logger().info('Starting video stream...')
            self.tello.streamon()
            self.stream_enabled = True

            self.frame_read = self.tello.get_frame_read()
            self.get_logger().info('Video stream started.')

        except Exception as e:
            self.connected = False
            self.stream_enabled = False
            self.get_logger().error(f'Failed to connect/setup image publisher: {e}')

    def publish_image(self) -> None:
        alive_msg = Bool()

        if not self.connected or not self.stream_enabled or self.frame_read is None:
            alive_msg.data = False
            self.frame_alive_pub.publish(alive_msg)
            self.get_logger().warn('Image publisher not ready.')
            return

        try:
            frame = self.frame_read.frame

            if frame is None:
                alive_msg.data = False
                self.frame_alive_pub.publish(alive_msg)
                self.get_logger().warn('No frame received.')
                return

            image_msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')

            self.image_pub.publish(image_msg)

            alive_msg.data = True
            self.frame_alive_pub.publish(alive_msg)

            self.get_logger().info(
                f'Published image: width={frame.shape[1]}, height={frame.shape[0]}'
            )

        except Exception as e:
            alive_msg.data = False
            self.frame_alive_pub.publish(alive_msg)
            self.get_logger().error(f'Failed to publish image: {e}')

    def destroy_node(self) -> None:
        try:
            if self.tello is not None and self.stream_enabled:
                self.tello.streamoff()
        except Exception as e:
            self.get_logger().warn(f'Failed to stop stream cleanly: {e}')

        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = TelloImagePublisher()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down Tello image publisher.')
    finally:
        node.destroy_node()
        rclpy.shutdown()
```

---

## `image_listener.py`

```python
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Bool
from cv_bridge import CvBridge


class ImageListener(Node):
    def __init__(self) -> None:
        super().__init__('image_listener')

        self.bridge = CvBridge()

        self.image_received_pub = self.create_publisher(Bool, '/tello/image_received', 10)

        self.create_subscription(
            Image,
            '/tello/image_raw',
            self.image_callback,
            10
        )

        self.last_image_time = None
        self.watchdog_timer = self.create_timer(1.0, self.check_image_health)

        self.get_logger().info('Image listener started.')

    def image_callback(self, msg: Image) -> None:
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
            self.last_image_time = self.get_clock().now()

            received_msg = Bool()
            received_msg.data = True
            self.image_received_pub.publish(received_msg)

            height, width = frame.shape[:2]
            self.get_logger().info(
                f'Received image: width={width}, height={height}, encoding={msg.encoding}'
            )

        except Exception as e:
            received_msg = Bool()
            received_msg.data = False
            self.image_received_pub.publish(received_msg)
            self.get_logger().error(f'Failed to convert incoming image: {e}')

    def check_image_health(self) -> None:
        msg = Bool()

        if self.last_image_time is None:
            msg.data = False
            self.image_received_pub.publish(msg)
            self.get_logger().warn('No image received yet.')
            return

        age_sec = (self.get_clock().now() - self.last_image_time).nanoseconds / 1e9

        if age_sec > 2.0:
            msg.data = False
            self.image_received_pub.publish(msg)
            self.get_logger().warn(f'Image stream stale: last image {age_sec:.2f}s ago')

    def destroy_node(self) -> None:
        super().destroy_node()


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ImageListener()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info('Shutting down image listener.')
    finally:
        node.destroy_node()
        rclpy.shutdown()
```

---

## How to Recreate Everything from Scratch

### Step 1 — Create the ROS 2 package

```bash
cd ~/ros2_ws/src
ros2 pkg create --build-type ament_python tello_call
```

---

### Step 2 — Create the virtual environment

```bash
cd ~
python3 -m venv tello_venv
```

If that fails:

```bash
sudo apt install python3-venv
```

---

### Step 3 — Activate the environment

```bash
source ~/tello_venv/bin/activate
```

---

### Step 4 — Install required Python packages

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install djitellopy opencv-python colcon-common-extensions
```

---

### Step 5 — If `cv_bridge` later fails with NumPy compatibility issues

Downgrade NumPy in the virtual environment:

```bash
python -m pip install "numpy<2"
```

Then verify:

```bash
python -c "import numpy; print(numpy.__version__)"
python -c "import cv_bridge; print('cv_bridge ok')"
```

---

### Step 6 — Create `setup.cfg`

File:

```text
~/ros2_ws/src/tello_call/setup.cfg
```

Content:

```ini
[develop]
script_dir=$base/lib/tello_call

[install]
install_scripts=$base/lib/tello_call

[build_scripts]
executable=/usr/bin/env python3
```

This is required so `ros2 run` uses the Python interpreter from the active environment.

---

### Step 7 — Edit `setup.py`

Make sure `setup.py` includes the console entries for all current nodes.

Example:

```python
from setuptools import setup

package_name = 'tello_call'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='kush',
    maintainer_email='you@example.com',
    description='Tello ROS 2 project',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'tello_adapter = tello_call.tello_adapter:main',
            'tello_camera = tello_call.tello_camera:main',
            'tello_image_publisher = tello_call.tello_image_publisher:main',
            'image_listener = tello_call.image_listener:main',
        ],
    },
)
```

---

### Step 8 — Add the Python node files

Place the files at:

```text
~/ros2_ws/src/tello_call/tello_call/
```

Files:
- `tello_adapter.py`
- `tello_camera.py`
- `tello_image_publisher.py`
- `image_listener.py`

---

### Step 9 — Rebuild cleanly

```bash
cd ~/ros2_ws
rm -rf build install log
source ~/tello_venv/bin/activate
source /opt/ros/jazzy/setup.bash
colcon build --packages-select tello_call --symlink-install
source install/setup.bash
```

---

### Step 10 — Verify launcher uses environment Python

Check one of the installed launchers:

```bash
head -n 1 ~/ros2_ws/install/tello_call/lib/tello_call/tello_adapter
```

It should show:

```text
#!/usr/bin/env python3
```

If it says `/usr/bin/python3`, the environment fix is not applied correctly.

---

### Step 11 — Create helper script for new terminals

Create:

```text
~/use_tello_env.sh
```

with:

```bash
source ~/tello_venv/bin/activate
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
```

Then in every new terminal:

```bash
source ~/use_tello_env.sh
```

---

## How to Run the Current Stages

### Telemetry stage

```bash
source ~/use_tello_env.sh
ros2 run tello_call tello_adapter
```

In another terminal:

```bash
source ~/use_tello_env.sh
ros2 topic list --no-daemon
ros2 node list --no-daemon
ros2 topic echo /tello/battery --no-daemon
ros2 topic echo /tello/link_ok --no-daemon
```

---

### Camera frame-health stage

```bash
source ~/use_tello_env.sh
ros2 run tello_call tello_camera
```

In another terminal:

```bash
source ~/use_tello_env.sh
ros2 topic echo /tello/frame_alive --no-daemon
ros2 topic echo /tello/frame_width --no-daemon
ros2 topic echo /tello/frame_height --no-daemon
```

---

### ROS image publishing stage

Run the publisher:

```bash
source ~/use_tello_env.sh
ros2 run tello_call tello_image_publisher
```

Then inspect:

```bash
source ~/use_tello_env.sh
ros2 topic list --no-daemon
ros2 topic info /tello/image_raw --no-daemon
ros2 topic echo /tello/frame_alive --no-daemon
```

---

### ROS image subscriber stage

Run the publisher in one terminal:

```bash
source ~/use_tello_env.sh
ros2 run tello_call tello_image_publisher
```

Run the subscriber in another:

```bash
source ~/use_tello_env.sh
ros2 run tello_call image_listener
```

Then inspect:

```bash
source ~/use_tello_env.sh
ros2 topic echo /tello/image_received --no-daemon
```

---

## Troubleshooting

### Problem: `ModuleNotFoundError: No module named 'djitellopy'`
Cause:
- node is being run with system Python instead of the virtual environment

Fix:
- activate the venv
- ensure `setup.cfg` exists
- rebuild cleanly
- verify launcher shebang

---

### Problem: `ros2 topic list` only shows `/parameter_events` and `/rosout`
Cause:
- stale ROS daemon / graph discovery issue

Fix:

```bash
ros2 daemon stop
ros2 daemon start
ros2 topic list --no-daemon
ros2 node list --no-daemon
```

---

### Problem: `cv_bridge` import fails with NumPy ABI errors
Cause:
- `cv_bridge` binary built against NumPy 1.x
- virtual environment has NumPy 2.x

Fix:

```bash
python -m pip install "numpy<2"
```

---

### Problem: Tello connects unreliably
Possible causes:
- wrong Wi-Fi network
- stale Tello state
- temporary packet issues

Notes:
- one transient decode error was seen earlier, but the connection succeeded immediately after retry
- if the node reports connection success and battery, the basic link is working

---

## What Has Not Been Built Yet

These are intentionally **not implemented yet**:

- hand detection
- gesture recognition
- human pose estimation
- supervisor/state machine
- approach logic
- flight command node
- landing logic
- integrated single hardware interface node

That is good. The project is still being built in layers.

---

## Recommended Next Stage

The next clean stage is:

### `hand_detector.py`
A subscriber node that:
- subscribes to `/tello/image_raw`
- runs MediaPipe Hands
- publishes a simple boolean topic like:
  - `/tello/hand_detected`

That should be the first real perception node.

---

## Summary

At the current stage, the project has a verified ROS 2 and hardware baseline with image transport:

- package exists
- virtual environment works
- interpreter issue was fixed
- ROS daemon discovery issue was understood
- Tello can connect
- battery can be read
- video stream can be received
- camera frame health can be checked
- ROS images can be published
- ROS images can be subscribed to and decoded

That is the correct foundation before moving to perception and then control.
