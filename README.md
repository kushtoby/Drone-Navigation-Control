# Tello ROS 2 Project — Detailed Walkthrough, Challenges, and Reproduction Guide

## Purpose of This Document

This README is a **professional reconstruction guide** for the current state of the Tello ROS 2 project.

It is written so that someone else can:

- understand what has already been built
- understand why it was built in this order
- reproduce the current working setup from scratch
- understand the main problems that came up during development
- know exactly how those problems were diagnosed and resolved

This version is intentionally different from a short project summary.  
It is a **walkthrough**.

Since the full package files will be uploaded separately, this document does **not** need to include all script contents inline. Instead, it explains:

- what each node does
- how the system evolved
- what configuration changes were required
- what commands to run
- what failures happened
- how to fix them

At the current stage, the project does **not** yet implement:
- hand detection
- gesture recognition
- supervisor logic
- motion commands
- landing logic

What *has* been completed is the full ROS 2 and Tello communication baseline needed before perception and control can be added.

---

# 1. Current Project Scope

The current system has successfully validated four major stages:

1. **Telemetry stage**
   - Tello connection
   - battery reading
   - link-health publishing

2. **Frame-health stage**
   - Tello video stream startup
   - frame availability checks
   - frame size reporting

3. **ROS image publishing stage**
   - OpenCV frame acquisition from Tello
   - conversion to ROS image messages using `cv_bridge`
   - publishing to `/tello/image_raw`

4. **ROS image subscriber stage**
   - subscribing to `/tello/image_raw`
   - converting ROS image messages back to OpenCV format
   - validating the full image pipeline

This means the project has already proven:

- ROS 2 package execution works
- Python environment management works
- DJITelloPy works with the Tello
- the Tello can be reached over Wi-Fi
- basic telemetry can be published as ROS topics
- the Tello video stream can be received
- ROS image transport can be used successfully

---

# 2. Current Architecture

At this point the system is still being tested in isolated layers rather than as one final integrated runtime.

## Telemetry path

```text
Tello drone
   ↓
DJITelloPy
   ↓
tello_adapter
   ↓
/tello/battery
/tello/link_ok
```

## Frame-health path

```text
Tello drone
   ↓
DJITelloPy
   ↓
tello_camera
   ↓
/tello/frame_alive
/tello/frame_width
/tello/frame_height
```

## ROS image pipeline

```text
Tello drone
   ↓
DJITelloPy
   ↓
tello_image_publisher
   ↓
/tello/image_raw
   ↓
image_listener
   ↓
/tello/image_received
```

## Important architectural note

At the current stage, these nodes are **validated independently**.

That is intentional.

Each node currently creates its own `Tello()` object and manages its own connection when run. That is acceptable for testing each stage one at a time, but it is **not** the final architecture for the full project.

The final integrated system will eventually need a cleaner hardware interface design so multiple high-level nodes are not all trying to own the drone connection separately.

---

# 3. Current ROS 2 Topics

## Telemetry topics
- `/tello/battery` → `std_msgs/Int32`
- `/tello/link_ok` → `std_msgs/Bool`

## Camera frame-health topics
- `/tello/frame_alive` → `std_msgs/Bool`
- `/tello/frame_width` → `std_msgs/Int32`
- `/tello/frame_height` → `std_msgs/Int32`

## ROS image transport topics
- `/tello/image_raw` → `sensor_msgs/Image`
- `/tello/image_received` → `std_msgs/Bool`

---

# 4. Current Nodes and Their Roles

## `tello_adapter`
Responsible for:
- creating the Tello object
- connecting to the drone
- reading battery percentage
- publishing telemetry status

Why it exists:
- before doing anything with vision or perception, the project needed to prove that the machine could reliably talk to the Tello through ROS 2

---

## `tello_camera`
Responsible for:
- starting the Tello video stream
- verifying that frames are arriving
- publishing frame-alive status and frame dimensions

Why it exists:
- before trying to publish ROS images, the project needed to prove that raw frames could be acquired reliably from the Tello stream

---

## `tello_image_publisher`
Responsible for:
- starting the Tello stream
- receiving OpenCV frames
- converting them to ROS `sensor_msgs/Image`
- publishing `/tello/image_raw`

Why it exists:
- the final perception stack should consume ROS image topics, not talk directly to DJITelloPy

---

## `image_listener`
Responsible for:
- subscribing to `/tello/image_raw`
- converting ROS images back to OpenCV frames
- validating that the image pipeline works end-to-end
- publishing `/tello/image_received`

Why it exists:
- this validates the image transport chain before any real perception is added

---

# 5. Package and Environment Layout

## ROS 2 workspace
```text
~/ros2_ws
```

## Package root
```text
~/ros2_ws/src/tello_call
```

## Python virtual environment
```text
~/tello_venv
```

## Helper environment script
```text
~/use_tello_env.sh
```

---

# 6. Reproducing the Project From Scratch

This section describes the exact rebuild process from zero.

## Step 1 — Create the package

From the workspace source directory:

```bash
cd ~/ros2_ws/src
ros2 pkg create --build-type ament_python tello_call
```

This creates the base Python ROS 2 package.

---

## Step 2 — Create a virtual environment

A virtual environment is required because installing packages directly into the system Python was blocked by the OS package-management policy.

Create it with:

```bash
cd ~
python3 -m venv tello_venv
```

If `venv` is missing:

```bash
sudo apt install python3-venv
```

---

## Step 3 — Activate the environment

```bash
source ~/tello_venv/bin/activate
```

You should see the shell prompt change to indicate the virtual environment is active.

---

## Step 4 — Install required Python packages

Inside the activated environment:

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install djitellopy opencv-python colcon-common-extensions
```

These packages are needed for:
- Tello communication
- OpenCV frame handling
- ROS 2 build tooling inside the same Python environment

---

## Step 5 — Create `setup.cfg`

This file is critical. Without it, ROS 2 may generate launcher scripts that hardcode `/usr/bin/python3` instead of respecting the active virtual environment.

Create:

```text
~/ros2_ws/src/tello_call/setup.cfg
```

with:

```ini
[develop]
script_dir=$base/lib/tello_call

[install]
install_scripts=$base/lib/tello_call

[build_scripts]
executable=/usr/bin/env python3
```

This ensures `ros2 run` uses the environment Python rather than the system Python.

---

## Step 6 — Update `setup.py`

`setup.py` must register the node entry points in `console_scripts`.

At the current stage, the package should register:

- `tello_adapter`
- `tello_camera`
- `tello_image_publisher`
- `image_listener`

Since the full package files will be uploaded separately, keep `setup.py` synchronized with the scripts included in the package.

---

## Step 7 — Add the package files

Place the node files inside:

```text
~/ros2_ws/src/tello_call/tello_call/
```

At the current stage, the relevant node files are:

- `tello_adapter.py`
- `tello_camera.py`
- `tello_image_publisher.py`
- `image_listener.py`

---

## Step 8 — Rebuild the workspace cleanly

From the workspace root:

```bash
cd ~/ros2_ws
rm -rf build install log
source ~/tello_venv/bin/activate
source /opt/ros/jazzy/setup.bash
colcon build --packages-select tello_call --symlink-install
source install/setup.bash
```

This is the clean rebuild sequence used throughout development.

---

## Step 9 — Verify the generated launcher uses the correct interpreter

Check one of the installed launchers:

```bash
head -n 1 ~/ros2_ws/install/tello_call/lib/tello_call/tello_adapter
```

The correct result is:

```text
#!/usr/bin/env python3
```

If it instead shows:

```text
#!/usr/bin/python3
```

then ROS 2 is still using the system interpreter, which will cause environment-specific imports such as `djitellopy` to fail.

---

## Step 10 — Create a helper script for every terminal

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

Then in every new terminal, use:

```bash
source ~/use_tello_env.sh
```

This avoids repeated interpreter and environment mistakes.

---

# 7. How to Run Each Working Stage

## A. Telemetry stage

Connect the laptop to the Tello Wi-Fi first.

Then run:

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

Expected result:
- `/tello_adapter` should appear
- `/tello/battery` should publish battery values
- `/tello/link_ok` should publish `true`

---

## B. Frame-health stage

Run:

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

Expected result:
- `frame_alive` becomes `true`
- width and height are published

---

## C. ROS image publishing stage

Run:

```bash
source ~/use_tello_env.sh
ros2 run tello_call tello_image_publisher
```

In another terminal:

```bash
source ~/use_tello_env.sh
ros2 topic list --no-daemon
ros2 topic info /tello/image_raw --no-daemon
ros2 topic echo /tello/frame_alive --no-daemon
```

Expected result:
- `/tello/image_raw` exists
- `/tello/frame_alive` becomes `true`

---

## D. ROS image subscriber stage

Run the publisher in one terminal:

```bash
source ~/use_tello_env.sh
ros2 run tello_call tello_image_publisher
```

Run the subscriber in another terminal:

```bash
source ~/use_tello_env.sh
ros2 run tello_call image_listener
```

Then inspect:

```bash
source ~/use_tello_env.sh
ros2 topic echo /tello/image_received --no-daemon
```

Expected result:
- `/tello/image_received` becomes `true`
- the listener logs image width, height, and encoding

---

# 8. Development Challenges and How They Were Solved

This section is important because it captures the real engineering problems that appeared during development.

## Challenge 1 — `djitellopy` could be imported in Python but not by `ros2 run`

### Symptom
Inside the virtual environment:

```bash
python3 -c "import djitellopy"
```

worked.

But:

```bash
ros2 run tello_call tello_adapter
```

failed with:

```text
ModuleNotFoundError: No module named 'djitellopy'
```

### Diagnosis
The problem was not that `djitellopy` was missing. The problem was that ROS 2 was launching the node with the wrong interpreter.

This was confirmed by checking the installed launcher:

```bash
head -n 1 ~/ros2_ws/install/tello_call/lib/tello_call/tello_adapter
```

It showed:

```text
#!/usr/bin/python3
```

That meant the node was being run with system Python, not the virtual environment.

### Resolution
Add `setup.cfg` with:

```ini
[build_scripts]
executable=/usr/bin/env python3
```

Then rebuild cleanly.

After that, the launcher respected the active environment.

---

## Challenge 2 — Ubuntu blocked system-wide `pip install`

### Symptom
Trying to install Python packages system-wide caused an error about an externally managed environment.

### Diagnosis
The OS Python installation was protected by package-management policy.

### Resolution
A dedicated virtual environment was created:

```bash
python3 -m venv ~/tello_venv
```

All project-specific Python packages were installed there instead.

---

## Challenge 3 — ROS topics were being published, but `ros2 topic list` did not show them

### Symptom
The node logs showed publishers firing, but `ros2 topic list` only showed:

```text
/parameter_events
/rosout
```

### Diagnosis
This was not a publisher bug. It was a ROS graph discovery / daemon issue.

### Resolution
Using:

```bash
ros2 topic list --no-daemon
ros2 node list --no-daemon
```

showed the real graph.

Restarting the daemon also helped:

```bash
ros2 daemon stop
ros2 daemon start
```

### Practical lesson
When ROS graph results look wrong, verify with `--no-daemon` before changing code unnecessarily.

---

## Challenge 4 — `cv_bridge` failed because of NumPy compatibility

### Symptom
Importing `cv_bridge` produced an error explaining that the module had been built with NumPy 1.x but was being used with NumPy 2.x.

### Diagnosis
The ROS Jazzy `cv_bridge` binary was compiled against NumPy 1.x, while the virtual environment had NumPy 2.x installed.

### Resolution
Downgrade NumPy inside the virtual environment:

```bash
python -m pip install "numpy<2"
```

Then verify:

```bash
python -c "import numpy; print(numpy.__version__)"
python -c "import cv_bridge; print('cv_bridge ok')"
```

After that, `cv_bridge` worked correctly.

---

## Challenge 5 — Tello connection included a transient decode error

### Symptom
During one connection attempt, a UTF-8 decode error appeared before a successful retry.

### Diagnosis
This appeared to be a transient bad or noisy packet rather than a fatal communication failure, because the next command succeeded and the Tello connected normally.

### Resolution
No code redesign was needed at this stage. The connection was reattempted and the Tello entered command mode successfully.

### Practical lesson
Not every single console error means the node architecture is wrong. Look at the full sequence and decide whether the system actually recovered.

---

## Challenge 6 — OpenCV display path risked complicating debugging too early

### Symptom
During earlier testing, the video path and GUI path risked becoming mixed together, which made it harder to isolate whether failures were due to:
- ROS timers
- stream startup
- frame acquisition
- GUI behavior
- Wayland / display issues

### Diagnosis
Too many subsystems were being tested at once.

### Resolution
The system was broken into distinct stages:
1. telemetry only
2. frame-health only
3. ROS image publishing
4. ROS image subscribing

### Practical lesson
Isolate one subsystem at a time.  
Do not mix hardware, ROS messaging, image transport, GUI, and perception in the same debugging step unless necessary.

---

# 9. Why the Project Was Built in This Order

This order was deliberate.

## First: telemetry
Before anything else, the project needed to prove:
- the Tello could connect
- battery could be read
- ROS 2 publishers worked

## Second: frame health
Before publishing ROS images, the project needed to prove:
- the stream starts
- frames actually arrive

## Third: ROS image publishing
Only after raw frame reception worked did it make sense to add `cv_bridge` and publish `/tello/image_raw`

## Fourth: ROS image subscribing
Only after publishing worked did it make sense to validate the receive side

This layered approach reduced confusion and made each problem easier to isolate.

---

# 10. What Has Not Been Built Yet

These are intentionally still pending:

- hand detection
- gesture recognition
- human pose estimation
- command gating
- supervisor/state machine
- motion logic
- landing logic
- final integrated Tello interface architecture

That is correct and expected. The current focus has been on building a clean, verified foundation.

---

# 11. Recommended Next Stage

The next clean step is:

## `hand_detector.py`

This should be the first actual perception node.

It should:
- subscribe to `/tello/image_raw`
- run MediaPipe Hands
- publish a simple topic such as:
  - `/tello/hand_detected` (`std_msgs/Bool`)

This keeps the next milestone small and measurable.

It does **not** need to do classification yet. The first job is simply:

**Can the system reliably detect the presence of a hand in the Tello image stream?**

That should come before gesture vocabulary, state machines, or control logic.

---

# 12. Final Summary

At the current stage, the project has successfully built and validated:

- ROS 2 package structure
- virtual environment workflow
- environment-aware ROS launcher configuration
- Tello telemetry access
- Tello video stream access
- frame-health validation
- ROS image publishing
- ROS image subscribing
- resolution of the major environment and compatibility issues encountered so far

This is the correct foundation for the next phase of the project: **perception**.
