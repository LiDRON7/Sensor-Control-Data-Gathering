# Leddar ROS2 Package

ROS 2 package for LeddarTech sensors (M16 and LeddarOne).

## Requirements

- ROS 2 (Jazzy recommended, also works on Humble/Iron)
- Python `leddar` module (from LeddarTech SDK)

## Build

```bash
cd ~/workspace_directory
colcon build 
source install/setup.bash
```

---

## Launching the M16

The M16 connects over **USB**. `param1` is the device serial number printed on the unit (e.g. `AK47035`).

```bash
ros2 launch leddar_ros2 example.launch.py  param1:=<SERIAL_NUMBER> device_type:=M16
```

---

## Launching the LeddarOne

The LeddarOne connects over **Serial** (typically via a USB-to-serial adapter). Identify the port with `ls /dev/ttyUSB*`.

| Parameter   | Meaning              | Typical value         |
|-------------|----------------------|-----------------------|
| `param1`    | Serial port          | `/dev/ttyUSB0`        |
| `device_type` | Device type        | `LeddarOne`           |

```bash
source install/setup.bash

ros2 launch leddar_ros2 example.launch.py param1:=/dev/ttyUSB0 device_type:=LeddarOne 
    
```

## Published Topics

| Topic             | Type                          | Description                              |
|-------------------|-------------------------------|------------------------------------------|
| `specs`           | `leddar_ros2/msg/Specs`       | Sensor specs (channels, FOV)             |
| `scan_cloud`      | `sensor_msgs/PointCloud2`     | XYZ + intensity point cloud              |
| `scan_raw`        | `sensor_msgs/PointCloud2`     | Raw echoes (XYZ + intensity + distance)  |
| `distances_feet`  | `std_msgs/Float32MultiArray`  | Per-echo distances in feet               |

---

## Visualize in RViz2

```bash
rviz2
```

Add a **PointCloud2** display and set the topic to `/scan_cloud`. Set the **Fixed Frame** to match your `frame_id` (e.g. `sensor_frame`).
