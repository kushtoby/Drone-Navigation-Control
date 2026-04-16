# Tello ROS 2 Project — Detailed Walkthrough, Challenges, and Reproduction Guide

## Purpose of This Document

This README is a professional reconstruction guide for the current state of the Tello ROS 2 project.

It is written so that someone else can:
- understand what has already been built
- understand why it was built in this order
- reproduce the current working setup from scratch
- understand the main problems that came up during development
- know exactly how those problems were diagnosed and resolved

This is intentionally a walkthrough, not just a short summary.

Since the full package files will be uploaded separately, this document does not inline every script. Instead, it explains:
- what each node does
- how the system evolved
- what configuration changes were required
- what commands to run
- what failures happened
- how those failures were resolved
- which approaches were tried and later abandoned

At the current stage, the project now includes the integrated demo path:
- gesture recognition
- supervisor / state-machine logic
- motion command publishing
- landing logic
- a single-owner integrated Tello runtime for the full demo

The earlier telemetry, frame-health, image transport, hand-detection, and cue-detection stages are still documented here because they were the foundation used to reach the current integrated system.

---

# 1. Current Project Scope

The current system has successfully validated eight major stages:

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

5. **First perception stage**
   - MediaPipe Hands running on `/tello/image_raw`
   - hand presence detection
   - hand count publishing

6. **Long-range cue-detection stage**
   - multiple colored-object experiments
   - green cue detection experiments
   - orange balloon experiments
   - final shift to pink balloon detection
   - final shift from circularity-prioritized logic to pixel-count-prioritized logic
   - addition of debounced blob-count logic for mode switching

7. **Gesture-classification stage**
   - MediaPipe Hands plus a TFLite/LiteRT classifier on `/tello/image_raw`
   - gesture-valid publishing
   - gesture-label publishing

8. **Integrated demo stage**
   - single-owner `tello_runtime`
   - `mission_supervisor` state machine
   - pink-balloon following
   - blob-count or gesture-based transition into gesture mode
   - gesture-driven motion commands
   - landing through either the `Land` gesture or the two-blob cue while already in gesture mode

This means the project has already proven:
- ROS 2 package execution works
- Python environment management works
- DJITelloPy works with the Tello
- the drone can be reached over Wi-Fi
- basic telemetry can be published as ROS topics
- the Tello video stream can be received
- ROS image transport can be used successfully
- MediaPipe can process the live Tello image feed
- live hand detection and gesture classification from the Tello camera work through ROS 2
- a long-range colored cue can be detected from the Tello feed
- cue-detection logic can be adapted when lighting and glare break shape assumptions
- an integrated supervisor/runtime path can command takeoff, cue following, gesture control, and landing

---

# 2. Current Architecture

At this point the project has both an integrated demo runtime and the earlier standalone validation nodes documented below.

## Integrated demo path

```text
Tello drone
   ↓
tello_runtime
   ↓
/tello/image_raw
   ↓
+--------------------------+---------------------------+
|                          |                           |
pink_balloon_detector      gesture_recognizer         mission_supervisor
|                          |                           |
/tello/pink_balloon_*      /tello/gesture_*           /tello/takeoff
                                                    /tello/land
                                                    /tello/cmd_vel
                                                        ↓
                                                   tello_runtime
```

The demo is intended to run with one hardware owner (`tello_runtime`) plus separate perception and supervision nodes. The older nodes documented below remain useful for isolated testing.

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

## Hand-perception pipeline

```text
/tello/image_raw
   ↓
hand_detector
   ↓
/tello/hand_detected
/tello/hand_count
```

## Long-range cue pipeline (current direction)

```text
/tello/image_raw
   ↓
pink_balloon_detector
   ↓
/tello/pink_balloon_detected
/tello/pink_balloon_center_x
/tello/pink_balloon_center_y
/tello/pink_balloon_area
/tello/pink_balloon_blob_count
/tello/pink_balloon_mode_code
```

## Important architectural note

The older validation nodes are still useful for isolated testing.

That is intentional.

However, the current full-demo direction is no longer to let multiple nodes own the drone connection. The integrated demo is built around `tello_runtime` as the single hardware owner, with the higher-level nodes communicating through ROS topics. Standalone connection-owning nodes such as `tello_adapter`, `tello_camera`, and `tello_image_publisher` should be treated as development / validation tools rather than the final demo architecture.

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

## Hand-perception topics
- `/tello/hand_detected` → `std_msgs/Bool`
- `/tello/hand_count` → `std_msgs/Int32`

## Current long-range cue topics
- `/tello/pink_balloon_detected` → `std_msgs/Bool`
- `/tello/pink_balloon_center_x` → `std_msgs/Int32`
- `/tello/pink_balloon_center_y` → `std_msgs/Int32`
- `/tello/pink_balloon_area` → `std_msgs/Int32`
- `/tello/pink_balloon_blob_count` → `std_msgs/Int32`
- `/tello/pink_balloon_mode_code` → `std_msgs/Int32`

## Gesture topics
- `/tello/gesture_valid` → `std_msgs/Bool`
- `/tello/gesture_label` → `std_msgs/String`
- `/tello/gesture_id` → `std_msgs/Int32`
- `/tello/gesture_debug` → `sensor_msgs/Image`

## Integrated supervisor / runtime topics
- `/tello/takeoff` → `std_msgs/Empty`
- `/tello/land` → `std_msgs/Empty`
- `/tello/emergency` → `std_msgs/Empty`
- `/tello/cmd_vel` → `geometry_msgs/Twist`
- `/tello/tof_cm` → `std_msgs/Int32`
- `/tello/state` → `std_msgs/String`
- `/tello/mode` → `std_msgs/String`

---

# 4. Current Nodes and Their Roles

## `tello_runtime`
Responsible for:
- creating the single-owner Tello interface used by the full demo
- receiving `/tello/cmd_vel`, `/tello/takeoff`, `/tello/land`, and `/tello/emergency`
- publishing `/tello/image_raw`, `/tello/frame_alive`, `/tello/link_ok`, `/tello/battery`, and `/tello/tof_cm`

Why it exists:
- the final integrated demo should not have multiple high-level nodes trying to own the drone connection simultaneously

---

## `gesture_recognizer`
Responsible for:
- subscribing to `/tello/image_raw`
- running MediaPipe Hands
- classifying gestures with the keypoint classifier model
- publishing:
  - `/tello/gesture_valid`
  - `/tello/gesture_label`
  - `/tello/gesture_id`
  - `/tello/gesture_debug` when enabled

Why it exists:
- this is the current close-range command perception node for the integrated demo

---

## `mission_supervisor`
Responsible for:
- managing the high-level state machine
- commanding takeoff and hover
- following the pink balloon in balloon mode
- switching from balloon-following to gesture mode through either:
  - confirmed gesture recognition, or
  - confirmed two-blob pink-balloon cue
- sending gesture-derived motion commands in gesture mode
- commanding landing through either:
  - the `Land` gesture, or
  - the two-blob cue again while already in gesture mode

Why it exists:
- this is the node that decides when to trust cue tracking, when to trust gesture commands, and when to land

---

## `demo_tui`
Responsible for:
- publishing `/tello/start_hover`
- publishing `/tello/land` from the keyboard

Why it exists:
- this provides a simple intentional trigger and safe keyboard landing path for demo operation

---

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

## `hand_detector`
Responsible for:
- subscribing to `/tello/image_raw`
- converting incoming ROS images to OpenCV frames
- running MediaPipe Hands
- publishing:
  - `/tello/hand_detected`
  - `/tello/hand_count`

Why it exists:
- this is the first real perception node
- it proves the system can detect a live hand from the Tello image feed before attempting gesture classification

---

## `pink_balloon_detector`
Responsible for:
- subscribing to `/tello/image_raw`
- thresholding the balloon color in HSV
- cleaning the mask
- using color-pixel count as the main trigger
- selecting a reasonable blob to recover center and approximate blob area
- counting valid pink regions after per-blob filtering
- publishing:
  - standard cue topics
  - a debounced blob count
  - a debounced mode-code mirror of that blob count

Why it exists:
- long-range detection at 20 ft is too weak for hand-only perception
- the balloon provides a larger, simpler visual cue
- glare and distance made circularity unreliable as the main criterion
- pixel count proved more robust than perfect-shape assumptions
- the split-balloon cue provides a more reliable mode-switch / land signal than depending on gestures alone

---

# 5. Package and Environment Layout

## ROS 2 workspace
```text
~/ros2_ws
```

## Repository root
```text
~/ros2_ws/src/Drone-Navigation-Control
```

## Package root
```text
~/ros2_ws/src/Drone-Navigation-Control
```

## Python package directory
```text
~/ros2_ws/src/Drone-Navigation-Control/tello_call
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

# 6. Known Good Environment State

At the current stage, the following environment state is known to work:

- ROS 2 Jazzy
- `numpy==1.26.4`
- `cv2 4.11.0`
- `cv_bridge` import working
- `mediapipe==0.10.21`
- `mediapipe.solutions` available
- `djitellopy` import working
- `ai_edge_litert` import working

This matters because there were multiple compatibility issues during setup, especially around interpreter selection and the gesture-classifier runtime.

---

# 7. Reproducing the Project From Scratch

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

## Step 4 — Install base required Python packages

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

At the current stage, `setup.py` should register the current console scripts, including at least:

- `tello_runtime`
- `gesture_recognizer`
- `mission_supervisor`
- `demo_tui`
- `pink_balloon_detector`
- `status_monitor`
- `status_source`
- plus the earlier standalone validation nodes such as `tello_adapter`, `tello_camera`, `tello_image_publisher`, `image_listener`, `hand_detector`, and `hand_debug_viewer`

It should also include the model files under `tello_call/model/keypoint_classifier/`. Keep `setup.py` synchronized with the scripts and package data included in the repository.

---

## Step 7 — Add the package files

Place the node files inside:

```text
~/ros2_ws/src/tello_call/tello_call/
```

At the current stage, the relevant node files include:

- `tello_runtime.py`
- `gesture_recognizer.py`
- `mission_supervisor.py`
- `demo_tui.py`
- `pink_balloon_detector.py`
- `status_monitor.py`
- `status_source.py`
- and the earlier standalone validation nodes:
  - `tello_adapter.py`
  - `tello_camera.py`
  - `tello_image_publisher.py`
  - `image_listener.py`
  - `hand_detector.py`
  - `hand_debug_viewer.py`

Note: earlier experimental cue-detector files for green and orange were removed once they were no longer the chosen direction.

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
head -n 1 ~/ros2_ws/install/tello_call/lib/tello_call/tello_runtime
```

The correct result is:

```text
#!/usr/bin/env python3
```

If it instead shows:

```text
#!/usr/bin/python3
```

then ROS 2 is still using the system interpreter, which will cause environment-specific imports such as `djitellopy` and `mediapipe` to fail.

If a clean rebuild regenerates the wrong shebangs, patch them after the final build:

```bash
find ~/ros2_ws/install/tello_call/lib/tello_call -maxdepth 1 -type f -exec   sed -i '1 s|^#!.*python3$|#!/usr/bin/env python3|' {} ;
```

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

# 8. Additional Environment Fixes Required for Image and Perception Stages

These fixes were required after the base environment was already working.

## Fix A — `cv_bridge` / NumPy compatibility

When `cv_bridge` was tested, it failed because the ROS Jazzy `cv_bridge` binary had been compiled against NumPy 1.x, while the virtual environment had NumPy 2.x.

This produced an ABI compatibility error.

### Resolution

Downgrade NumPy:

```bash
python -m pip install --force-reinstall "numpy<2"
```

Then verify:

```bash
python -c "import numpy; print(numpy.__version__)"
python -c "import cv_bridge; print('cv_bridge ok')"
```

At the working state, NumPy was:

```text
1.26.4
```

---

## Fix B — MediaPipe Solutions API availability

The first hand detection implementation used:

```python
mp.solutions.hands
```

But the installed MediaPipe version did not expose `mp.solutions`, which caused the first `hand_detector` attempt to fail.

### Resolution

Pin MediaPipe to a version that still provides the Solutions API:

```bash
python -m pip install --force-reinstall "mediapipe==0.10.21"
```

Then verify:

```bash
python -c "import mediapipe as mp; print(mp.__version__, hasattr(mp, 'solutions'))"
```

The expected result is that `hasattr(mp, 'solutions')` returns `True`.

---

## Fix C — OpenCV / NumPy warning cleanup

During dependency repairs, package version conflicts were reported between newer OpenCV wheels and NumPy 1.x.

The environment was considered acceptable once all of the following were true:

```bash
python -c "import numpy; print('numpy', numpy.__version__)"
python -c "import cv2; print('cv2', cv2.__version__)"
python -c "import cv_bridge; print('cv_bridge ok')"
python -c "import mediapipe as mp; print('mediapipe', mp.__version__, 'solutions=', hasattr(mp, 'solutions'))"
```

The working results were:
- `numpy 1.26.4`
- `cv2 4.11.0`
- `cv_bridge ok`
- `mediapipe 0.10.21 solutions=True`

---

# 9. How to Run Each Working Stage

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

## E. First perception stage — hand detection

Run the image publisher in one terminal:

```bash
source ~/use_tello_env.sh
ros2 run tello_call tello_image_publisher
```

Run the hand detector in another terminal:

```bash
source ~/use_tello_env.sh
ros2 run tello_call hand_detector
```

Then inspect:

```bash
source ~/use_tello_env.sh
ros2 topic echo /tello/hand_detected --no-daemon
ros2 topic echo /tello/hand_count --no-daemon
```

Expected result:
- no hand visible → `hand_detected=false`, `hand_count=0`
- hand visible → `hand_detected=true`, `hand_count=1` or `2`

A successful log line from the working system looked like:

```text
[INFO] ... [hand_detector]: Hand detection: detected=True, hand_count=1
```

---

## F. Current long-range cue stage — pink balloon detection

Run the image publisher in one terminal:

```bash
source ~/use_tello_env.sh
ros2 run tello_call tello_image_publisher
```

Run the balloon detector in another terminal:

```bash
source ~/use_tello_env.sh
ros2 run tello_call pink_balloon_detector
```

Then inspect:

```bash
source ~/use_tello_env.sh
ros2 topic echo /tello/pink_balloon_detected --no-daemon
ros2 topic echo /tello/pink_balloon_center_x --no-daemon
ros2 topic echo /tello/pink_balloon_center_y --no-daemon
ros2 topic echo /tello/pink_balloon_area --no-daemon
ros2 topic echo /tello/pink_balloon_blob_count --no-daemon
```

Expected result:
- at long range the balloon may appear mainly as a color blob rather than a perfect geometric object
- detection should still succeed if enough target-color pixels are present over multiple frames
- center and approximate blob area should still be published when detection is confirmed
- the blob count should be:
  - `0` when no valid cue is present
  - `1` when the balloon is intact
  - `2` when the balloon is intentionally split into two valid pink regions

---

## G. Current integrated demo — launch-file path

Use the launch file for the non-interactive stack, and run the TUI separately.

Terminal 1:

```bash
source ~/use_tello_env.sh
ros2 launch tello_call accio_demo.launch.py
```

Terminal 2:

```bash
source ~/use_tello_env.sh
ros2 run tello_call demo_tui
```

Expected result:
- launch starts `tello_runtime`, `pink_balloon_detector`, `gesture_recognizer`, and `mission_supervisor`
- TUI starts separately and reports the keys `s=start hover, e=land, q=quit TUI`

---

## H. Current integrated demo — without the launch file

Run each node manually in separate terminals.

Terminal 1:

```bash
source ~/use_tello_env.sh
ros2 run tello_call tello_runtime
```

Terminal 2:

```bash
source ~/use_tello_env.sh
ros2 run tello_call pink_balloon_detector
```

Terminal 3:

```bash
source ~/use_tello_env.sh
ros2 run tello_call gesture_recognizer
```

Terminal 4:

```bash
source ~/use_tello_env.sh
ros2 run tello_call mission_supervisor
```

Terminal 5:

```bash
source ~/use_tello_env.sh
ros2 run tello_call demo_tui
```

---

## I. Listening to topics during the demo

These topic commands are useful while testing either the launch-file path or the manual path.

```bash
source ~/use_tello_env.sh
ros2 topic echo /tello/state
```

```bash
source ~/use_tello_env.sh
ros2 topic echo /tello/mode
```

```bash
source ~/use_tello_env.sh
ros2 topic echo /tello/gesture_label
```

```bash
source ~/use_tello_env.sh
ros2 topic echo /tello/gesture_valid
```

```bash
source ~/use_tello_env.sh
ros2 topic echo /tello/pink_balloon_detected
```

```bash
source ~/use_tello_env.sh
ros2 topic echo /tello/pink_balloon_blob_count
```

```bash
source ~/use_tello_env.sh
ros2 topic echo /tello/cmd_vel
```

```bash
source ~/use_tello_env.sh
ros2 topic echo /tello/battery
```

```bash
source ~/use_tello_env.sh
ros2 topic echo /tello/tof_cm
```

---

# 10. Development Challenges and How They Were Solved

## Challenge 1 — `djitellopy` imported in Python but not in `ros2 run`

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
The ROS Jazzy `cv_bridge` binary was compiled against NumPy 1.x, while the virtual environment had NumPy 2.x.

### Resolution
Downgrade NumPy inside the virtual environment:

```bash
python -m pip install --force-reinstall "numpy<2"
```

Then verify:

```bash
python -c "import numpy; print(numpy.__version__)"
python -c "import cv_bridge; print('cv_bridge ok')"
```

---

## Challenge 5 — MediaPipe did not expose `mp.solutions`

### Symptom
The first `hand_detector` attempt failed with:

```text
AttributeError: module 'mediapipe' has no attribute 'solutions'
```

### Diagnosis
The installed MediaPipe version did not provide the old Solutions API that the initial hand detector implementation expected.

### Resolution
Pin MediaPipe to:

```bash
mediapipe==0.10.21
```

Then verify:

```bash
python -c "import mediapipe as mp; print(hasattr(mp, 'solutions'))"
```

The working result was `True`.

---

## Challenge 6 — OpenCV / NumPy package conflicts created confusing warnings

### Symptom
Pip produced warnings about dependency conflicts between OpenCV wheels and NumPy versions during package repairs.

### Diagnosis
The environment temporarily contained incompatible package expectations while the image stack was being stabilized.

### Resolution
The environment was accepted as working only after direct import checks confirmed:
- NumPy imports correctly
- OpenCV imports correctly
- `cv_bridge` imports correctly
- MediaPipe imports correctly and exposes `solutions`

### Practical lesson
When package warnings are noisy, trust end-to-end import verification more than pip’s resolver messages alone.

---

## Challenge 7 — Tello connection included a transient decode error

### Symptom
During one connection attempt, a UTF-8 decode error appeared before a successful retry.

### Diagnosis
This appeared to be a transient bad or noisy packet rather than a fatal communication failure, because the next command succeeded and the Tello connected normally.

### Resolution
No code redesign was needed at this stage. The connection was reattempted and the Tello entered command mode successfully.

### Practical lesson
Not every console error means the node architecture is wrong. Look at the full sequence and decide whether the system actually recovered.

---

## Challenge 8 — Too many subsystems could have been debugged at once

### Symptom
There was a risk of mixing:
- ROS timers
- stream startup
- frame acquisition
- GUI handling
- image transport
- perception

into one debugging step.

### Diagnosis
That would have made failures much harder to isolate.

### Resolution
The system was intentionally broken into distinct stages:
1. telemetry only
2. frame-health only
3. ROS image publishing
4. ROS image subscribing
5. hand detection
6. long-range cue detection

### Practical lesson
Isolate one subsystem at a time.

---

## Challenge 9 — Hand detection worked only at shorter distances

### Symptom
MediaPipe hand detection performed well at short range but did not provide a reliable long-range trigger for the required 20-ft scenario.

### Diagnosis
At longer distances, the hand occupies too few pixels in the frame, and detector performance becomes strongly dependent on image scale, contrast, and lighting.

### Resolution
The project shifted from relying on hand detection as the long-range acquisition method to using a larger colored cue object instead.

### Practical lesson
A cue that is too small in the image should not be forced into a role it is not visually strong enough to serve.

---

## Challenge 10 — Skin-tone and lighting sensitivity affected hand detection

### Symptom
Hand detection quality was inconsistent across users and conditions.

### Diagnosis
The pretrained detector was sensitive to the combination of hand appearance, lighting, background clutter, and apparent hand size in the frame.

### Resolution
The project stopped treating hand perception as the only cue for the long-range problem and instead reserved hand detection for closer-range perception.

### Practical lesson
Separate long-range acquisition from closer-range fine perception when one model cannot robustly serve both roles.

---

## Challenge 11 — Green cue experiments produced false positives

### Symptom
Green cue detection picked up unrelated scene elements such as other greenish objects and floor markings.

### Diagnosis
The HSV thresholding worked, but the environment contained enough similar hues that the detector started seeing other objects as candidates.

### Resolution
The detector was tightened with additional filtering, but this reduced long-range sensitivity.

Ultimately, the green approach was not kept as the final direction and the green-cue code was removed.

### Practical lesson
A detector can fail by being too permissive or by becoming so strict that it loses the real target. Both sides of that tradeoff must be tested.

---

## Challenge 12 — Orange balloon appearance was distorted in the Tello feed

### Symptom
The orange balloon did not appear as a clean, stable orange target in the Tello image feed and looked shifted enough to make reliable tuning awkward.

### Diagnosis
The balloon’s real-world color was less important than how the Tello camera actually rendered it under the available lighting. Auto white balance, exposure, and small-camera color rendering made the orange cue less trustworthy than expected.

### Resolution
The project stopped pursuing the orange balloon as the main direction and the orange-balloon code was removed.

### Practical lesson
The correct cue color is the one that is stable in the actual sensing pipeline, not necessarily the one that looks ideal to the human eye.

---

## Challenge 13 — Circularity failed under glare and long-range appearance changes

### Symptom
At long distance, and especially under glare, the balloon often stopped looking like a clean circular object. The detector could still “see” the balloon color, but the contour was often partial, distorted, or not round enough to satisfy circularity-heavy logic.

### Diagnosis
The balloon was still present as a color region, but glare and distance degraded its apparent boundary quality. Circularity therefore became an unreliable primary trigger even though the color mask remained useful.

### Resolution
The detector design shifted from circularity-prioritized logic to pixel-count-prioritized logic.

The final reasoning was:
- at 20 ft, the cue may only appear as a small, stable color blob
- that is still enough to trigger acquisition
- demanding a perfect circle at that range is unnecessarily fragile

The detector now:
- keeps the same working HSV thresholds
- uses target-color pixel count as the main raw trigger
- uses temporal confirmation across recent frames
- still recovers blob center and approximate area from the largest valid region

### Practical lesson
At long range, reliable blob evidence can matter more than perfect geometry.

---

## Challenge 14 — launcher shebangs reverted after clean rebuilds

### Symptom
After a clean rebuild, previously working nodes suddenly failed with import errors such as:

```text
ModuleNotFoundError: No module named 'djitellopy'
```

or

```text
ModuleNotFoundError: No module named 'mediapipe'
```

### Diagnosis
The rebuild regenerated the installed ROS launcher wrappers with the wrong interpreter shebang. Even when the virtual environment itself was correct, `ros2 run` would fall back to system Python if the wrapper started with `#!/usr/bin/python3`.

### Resolution
Keep `setup.cfg` configured for `/usr/bin/env python3`, verify the installed launchers after rebuilds, and patch the installed wrappers after the final build if needed.

### Practical lesson
After any rebuild, verify the installed wrapper interpreter before assuming the Python environment itself is broken.

---

## Challenge 15 — gesture classifier runtime conflicts

### Symptom
The gesture pipeline reached a point where MediaPipe and the classifier model were both needed, but TensorFlow-based TFLite and MediaPipe dependency constraints conflicted inside the same environment.

### Diagnosis
The issue was not the gesture model itself. The real problem was keeping MediaPipe, protobuf compatibility, and a working TFLite/LiteRT interpreter in the same environment.

### Resolution
The current working path uses `mediapipe==0.10.21` with a LiteRT/TFLite-compatible classifier path in `gesture_recognizer.py`, rather than relying on the earlier broken TensorFlow-only setup.

### Practical lesson
When gesture classification depends on both perception and model-runtime dependencies, treat the runtime stack as part of the system design, not as a late install detail.

---

## Challenge 16 — full demo handoff logic needed to be more robust than a short timing window

### Symptom
Gesture labels could be publishing correctly, but the drone would still fail to move during the full demo if the supervisor never transitioned into `GESTURE_MODE`.

### Diagnosis
The integrated problem was not just recognition accuracy. The state machine and launch-time parameter overrides also controlled whether the supervisor would trust and apply gesture commands at all.

### Resolution
The current demo path uses the updated `mission_supervisor` and launch behavior developed during integration testing, with `demo_tui` run separately and the supervisor handling cue-following, gesture-mode switching, and landing in the full stack.

### Practical lesson
For the final demo, it is not enough for `/tello/gesture_label` to look correct. The state machine has to actually be in the mode that consumes those labels for motion.

---

## Challenge 17 — gesture recognition was not reliable enough to be the only mode-switch and landing trigger

### Symptom
The gesture pipeline could work, but it was not consistently reliable enough to be the only way to switch modes or land during the full demo.

### Diagnosis
The issue was not only classifier quality. The practical demo problem was that the user needed a backup signal that came from the same cue family as the balloon detector and did not depend entirely on gesture classification.

### Resolution
The pink-balloon detector was extended to publish a debounced blob count. The intended meanings became:
- `0` = no valid pink cue
- `1` = one intact balloon region
- `2` = two valid pink regions, produced by intentionally splitting the balloon visually with the hand

The supervisor was then updated so that:
- in `FOLLOW_BALLOON`, either a confirmed gesture or a confirmed two-blob cue can enter `GESTURE_MODE`
- in `GESTURE_MODE`, either the `Land` gesture or the two-blob cue can command landing

### Practical lesson
For the full demo, a backup transition signal from the same robust cue family can be more useful than forcing all control transitions through a weaker recognizer.

---

# 11. Why the Project Was Built in This Order

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

## Fifth: hand detection
Only after the ROS image pipeline worked end-to-end did it make sense to add MediaPipe-based perception

## Sixth: long-range cue detection
Only after the basic perception stack worked did it make sense to explore a larger acquisition cue appropriate for the 20-ft requirement

This layered approach reduced confusion and made each problem easier to isolate.

---

# 12. Current Detection Strategy Rationale

The project has now effectively split the perception problem into two roles:

## Closer-range perception
Handled by:
- `gesture_recognizer`
- the earlier `hand_detector` validation node

Purpose:
- determine and classify close-range hand commands once the system is already in gesture mode

## Long-range acquisition
Handled by:
- `pink_balloon_detector`

Purpose:
- provide a larger, simpler, more visible cue for long-range visual acquisition

## Backup mode-switch and landing cue
Also handled by:
- `pink_balloon_detector`

Purpose:
- use the number of valid pink regions as a robust auxiliary signal:
  - intact balloon → one region
  - split balloon → two regions

This reflects what the experiments showed:
- the hand is too small and variable to be the only long-range cue
- the balloon is visually simpler and larger
- at 20 ft, color-blob evidence is more reliable than perfect geometric shape
- the split-balloon cue provides a better backup transition/landing trigger than relying on gesture recognition alone

---

# 13. What Still Needs Improvement

The project now has a working integrated demo path, but several things still need refinement:
- cue-following reliability under real demo lighting and glare
- gesture-to-motion reliability and handoff tuning in the full demo
- launch and rebuild robustness across repeated test cycles
- continued safety tuning for flight and landing behavior
- threshold tuning for the blob-count backup path under representative demo conditions

The core integrated architecture now exists; the remaining work is mostly around reliability, tuning, and repeatability.

---

# 14. Recommended Next Stage

The next clean step is:

## integrated demo reliability refinement

Specifically:
- verify repeatable balloon-to-gesture handoff behavior during full runs
- verify safe landing behavior from both:
  - the `Land` gesture
  - the two-blob cue while already in gesture mode
- tighten launch / rebuild workflow documentation so demo-day operation is repeatable
- continue tuning cue detector and supervisor thresholds under representative lab conditions

---

# 15. Final Summary

At the current stage, the project has successfully built and validated:
- ROS 2 package structure
- virtual environment workflow
- environment-aware ROS launcher configuration
- Tello telemetry access
- Tello video stream access
- frame-health validation
- ROS image publishing
- ROS image subscribing
- live MediaPipe hand detection from the Tello image stream
- a workable long-range cue-detection pipeline
- gesture classification from the Tello image stream
- a single-owner integrated runtime (`tello_runtime`)
- a full-demo supervisor path (`mission_supervisor`)
- a current demo launch path plus a fully manual multi-terminal path
- resolution of the major environment and compatibility issues encountered so far

It also moved past several failed or suboptimal cue strategies:
- hand-only long-range acquisition
- green cue direction
- orange balloon direction
- circularity-prioritized balloon detection under glare
- earlier broken gesture-runtime combinations that did not coexist cleanly with MediaPipe
- a gesture-only mode-switch / landing path with no robust cue-based backup

The current chosen direction is:
- pink balloon detection for long-range cueing
- gesture recognition for close-range command control
- debounced blob-count interpretation of the pink balloon as a backup cue signal
- `mission_supervisor` for the high-level state machine
- `tello_runtime` as the single hardware owner during the full demo

That is the correct current foundation for the next phase of the project: improving reliability and repeatability of the integrated demo.