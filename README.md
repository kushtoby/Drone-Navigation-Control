# Tello ROS 2 Project — Current Progress and Rebuild Guide

## Overview

This document describes **exactly what has been built so far**, **why it was built this way**, and **how to recreate it from scratch**.

At this stage, the project has **not** implemented gesture recognition, flight control, or landing logic. The current system only establishes a clean and safe foundation:

- a ROS 2 Python package
- a working Python virtual environment
- a `tello_adapter` node
- successful connection to the Tello drone
- publishing of basic telemetry topics:
  - `/tello/battery`
  - `/tello/link_ok`

This stage is important because it proves that:

1. ROS 2 can run the project package
2. the correct Python environment is being used
3. `djitellopy` works with the Tello on this machine
4. the drone can be reached over Wi-Fi
5. ROS 2 topics can publish live status from the drone

---

## Current Architecture

Right now the architecture is minimal:

```text
Tello drone  --->  djitellopy  --->  tello_adapter node  --->  ROS 2 topics
```

### Current ROS 2 topics
- `/tello/battery` (`std_msgs/Int32`)
- `/tello/link_ok` (`std_msgs/Bool`)

### Current working node
- `tello_adapter`

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

This made it possible to:
- import `djitellopy`
- communicate with the Tello
- build the ROS 2 package from the same Python environment

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

After rebuilding, the launcher can respect the active environment.

---

### 5. `tello_adapter.py` created and working
The current node:
- creates a Tello object
- connects to the drone
- reads battery percentage
- publishes battery and link status to ROS 2 topics

No movement or flight commands are used in the current version.

---

### 6. ROS 2 daemon issue identified
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

## Current Working Package Structure

Current package root:

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
    └── tello_adapter.py
```

---

## Current `tello_adapter.py`

This is the current minimal working version:

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

## How to Recreate Everything from Scratch

### Step 1 — Create the ROS 2 package

From the ROS 2 workspace source folder:

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

If that fails, install `venv` support first:

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

### Step 5 — Create `setup.cfg`

Create this file:

```text
~/ros2_ws/src/tello_call/setup.cfg
```

with this content:

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

### Step 6 — Edit `setup.py`

Make sure `setup.py` includes a console entry for `tello_adapter`.

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
        ],
    },
)
```

---

### Step 7 — Add `tello_adapter.py`

Place the file at:

```text
~/ros2_ws/src/tello_call/tello_call/tello_adapter.py
```

Use the current working code shown earlier in this README.

---

### Step 8 — Rebuild cleanly

From the workspace root:

```bash
cd ~/ros2_ws
rm -rf build install log
source ~/tello_venv/bin/activate
source /opt/ros/jazzy/setup.bash
colcon build --packages-select tello_call --symlink-install
source install/setup.bash
```

---

### Step 9 — Verify the launcher uses environment Python

Check:

```bash
head -n 1 ~/ros2_ws/install/tello_call/lib/tello_call/tello_adapter
```

It should preferably show:

```text
#!/usr/bin/env python3
```

If it says `/usr/bin/python3`, the environment fix is not applied correctly.

---

### Step 10 — Create a helper script for new terminals

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

Then every new terminal can use:

```bash
source ~/use_tello_env.sh
```

---

### Step 11 — Run the node

Connect the computer to the Tello Wi-Fi first.

Then run:

```bash
source ~/use_tello_env.sh
ros2 run tello_call tello_adapter
```

---

### Step 12 — Check topics

In another terminal:

```bash
source ~/use_tello_env.sh
ros2 topic list --no-daemon
ros2 node list --no-daemon
```

Expected outputs should include:

- `/tello/battery`
- `/tello/link_ok`
- `/tello_adapter`

To inspect the live topics:

```bash
ros2 topic echo /tello/battery --no-daemon
ros2 topic echo /tello/link_ok --no-daemon
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

### Problem: Tello connects unreliably
Possible causes:
- wrong Wi-Fi network
- stale Tello state
- temporary packet issues

Notes:
- one transient decode error was seen earlier, but the connection succeeded immediately after retry
- if the node reports connection success and battery, the basic link is working

---

## What We Have Not Built Yet

These are intentionally **not implemented yet**:

- video-stream node
- camera frame publishing
- image transport
- gesture recognition
- human pose estimation
- supervisor node
- approach logic
- flight command node
- landing logic

That is good. It means the project is being built in layers instead of mixing everything together.

---

## Recommended Next Stage

The next clean stage is:

### `tello_camera.py`
A separate node that:
- starts the video stream
- reads frames
- confirms frame reception
- optionally publishes a simple `frame_alive` topic

This should be separate from `tello_adapter.py`.

Reason:
- `tello_adapter.py` should stay responsible only for telemetry / health
- camera and image handling should be isolated

---

## Summary

At the current stage, the project has a verified hardware and ROS 2 baseline:

- package exists
- virtual environment works
- interpreter issue was fixed
- Tello can connect
- battery can be read
- ROS 2 topics publish live status

That is the correct foundation before moving to perception or control.
