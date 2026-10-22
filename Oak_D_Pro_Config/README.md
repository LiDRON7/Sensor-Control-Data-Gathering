# OAK-D Pro: original viewer with distance-only ROS 2 output

This version runs `Object_Detection_With_Distance.py` and publishes only its
calculated object distances. The camera setup, model, original output queues,
ROI sampling, median calculation, green bounding boxes, red center dots,
meter/feet labels, native OpenCV window, and Q-to-quit behavior are preserved
from the supplied reference script.

The reference used for this revision was:

```text
/home/lidron/Documents/oakd-og-ws/Sensor-Control-Data-Gathering/Oak_D_Pro_Config/Object_Detection_With_Distance.py
```

Small hooks collect numeric class labels and already-calculated distances.
They hand only these scalars and an acquisition timestamp to a background ROS
publisher. There are no ROS image copies, point-cloud generation, extra camera
nodes, separate detection messages, or replacement frame-pairing logic. The
standalone `Object_Detection.py` is restored, and both original scripts still
run directly with Python without ROS publishing.

## Run

From `Oak_D_Pro_Config`, stop any previous camera application, then:

```bash
source /opt/ros/jazzy/setup.bash
source ~/oak_depthai_venv/bin/activate
source install/setup.bash
ros2 launch oak_d_ros2 distances.launch.py
```

The original viewer opens automatically. Q or Ctrl+C stops it and the ROS node.
The old `autonomy.launch.py` and `detection.launch.py` names are compatibility
aliases for this same distance-only launcher.

For operation without a desktop window:

```bash
ros2 launch oak_d_ros2 distances.launch.py show_preview:=false
```

## Distance topic

| Topic | Type | QoS |
| --- | --- | --- |
| `/oak/object_distances` | `oak_d_interfaces/msg/ObjectDistanceArray` | Reliable, volatile, keep-last 1 |

There is one entry per detected object. Example payload:

```yaml
header:
  stamp: {sec: 0, nanosec: 0}  # Actual RGB acquisition time during operation.
  frame_id: oak_rgb_camera_optical_frame
objects:
- class_id: bottle
  distance_m: 1.25
  distance_valid: true
```

Each entry contains only:

- `class_id`: the model's class name, or its numeric label as a string.
- `distance_m`: the original median depth estimate in meters along the camera's
  optical Z axis.
- `distance_valid`: false when the original script has no valid depth; distance
  is then NaN.

An empty array means no objects were detected in that frame. It does not establish
that the surrounding space is clear. Multiple objects may have the same class;
array entries identify measurements within one frame, not tracked identities
across frames.

The original script calculates distance once. The same value is drawn on its
window and submitted to ROS. Sample limits remain 0.2–20 m and the center ROI
fraction remains 0.10, as in the reference. These are sampling settings, not a
guarantee of measurement accuracy. The original RGB/depth alignment and queue
assumptions are retained.

The publisher holds one pending scalar sample. If DDS is slow, a newer sample
replaces pending work instead of building a queue of old measurements or blocking
the live viewer. The timestamp remains the source RGB acquisition time, converted
from DepthAI's host-synchronized clock to ROS time. Use wall-clock ROS time for
this physical camera. Camera exposure and inference still contribute latency;
15 FPS is the original camera setting, not a guaranteed detection output rate.

In another terminal, source ROS and the workspace, then:

```bash
ros2 topic echo /oak/object_distances --once
ros2 topic hz /oak/object_distances
ros2 run oak_d_ros2 distance_subscriber
```

The previous image topics, `/oak/detections`, `/oakd/depth/image`, and
`/oakd/depth/points` are no longer published.

## Connect an autonomous algorithm

The message schema changed from the previous implementation. Rebuild
`oak_d_interfaces` in every consuming workspace and update code to read
`obj.class_id` directly instead of the old embedded detection message.

```python
from oak_d_interfaces.msg import ObjectDistanceArray

# In your rclpy Node:
self.subscription = self.create_subscription(
    ObjectDistanceArray, '/oak/object_distances', self.on_distances, 10)

def on_distances(self, message):
    for obj in message.objects:
        if obj.distance_valid:
            class_name = obj.class_id
            distance_m = obj.distance_m
            # Provide these measurements to your algorithm.
```

Declare an `oak_d_interfaces` dependency in the consuming ROS package. The topic
is relative to the default `oak` namespace and can be remapped normally.

The autonomy README supplied earlier lists **depth images and point clouds** as
its camera inputs. Those existing subscribers cannot consume this distance array
without a code change. Their distance-consuming logic needs a subscriber like the
example above. Their occupancy-map input also needs 3D points, which scalar object
distances do not provide. This distance-only bridge therefore does not satisfy
those old image/cloud inputs by itself. It does not publish flight commands or
replace the team's existing perception outputs.

For a container consumer, use the same `ROS_DOMAIN_ID` and working DDS discovery
between the camera process and the container.

## Build

From `Oak_D_Pro_Config`:

```bash
source /opt/ros/jazzy/setup.bash
sudo apt install python3-opencv python3-colcon-common-extensions python3-rosdep python3-venv
python3 -m venv --system-site-packages ~/oak_depthai_venv
source ~/oak_depthai_venv/bin/activate
python -m pip install -r ros2/oak_d_ros2/requirements.txt

# rosdep must already be initialized: sudo rosdep init, then rosdep update.
rosdep install --from-paths ros2 --ignore-src -r -y
python /usr/bin/colcon build --base-paths ros2 --symlink-install
source install/setup.bash
```

The build installs the original distance script under `share/oak_d_ros2/scripts`;
symlink installation links to the source. The bridge no longer depends on
`vision_msgs` or `sensor_msgs`. DepthAI 3.11.0 was used for validation.
Camera access still requires appropriate USB/udev setup. The first model load may
download model assets. Only one process should own the camera at a time.

Only `frame_id` and `show_preview` are ROS startup parameters, stored in
`ros2/oak_d_ros2/config/oak.yaml`. Camera/model/distance settings remain in the
original Python script. Setting `frame_id` names the optical frame; it does not
create a TF transform.

## Tests

With the packages built and sourced:

```bash
python -m pytest ros2/oak_d_ros2/test -q

# Also compare the Python processing code directly against your reference:
OAK_REFERENCE_SCRIPT=/absolute/path/to/original/Object_Detection_With_Distance.py \
  python -m pytest ros2/oak_d_ros2/test -q
```

Tests use ROS domain 101 (override with `OAK_TEST_ROS_DOMAIN_ID`) to isolate
synthetic data from a live camera. They check scalar-only messages, invalid and
empty measurements, real ROS delivery, acquisition timestamps, nonblocking
submission under a slow publisher, and the original camera graph and rendered
pixels. The optional source comparison verifies that removing only the ROS hooks
recovers the reference Python processing code. GUI calls and hardware are mocked
in these tests; live-camera latency and measured distance accuracy still need a
physical-camera check.
