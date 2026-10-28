# Topics

Every ROS 2 topic these containers publish, and who uses it. The autonomy side is in [Autonomous-Systems docs/topics.md](https://github.com/LiDRON7/Autonomous-Systems/blob/main/docs/topics.md).

To see them live: `docker exec oak-d bash -lc "source /opt/ros/jazzy/setup.bash && ros2 topic list"`.

## Camera (`oak-d`)

Code: [node.py](../Oak_D_Pro_Config/ros2/oak_d_ros2/oak_d_ros2/node.py). The depth topics only exist when `publish_depth: true` in [oak.yaml](../Oak_D_Pro_Config/ros2/oak_d_ros2/config/oak.yaml).

| Topic | Type | Used by | For |
| --- | --- | --- | --- |
| `/oakd/depth/image` | `sensor_msgs/Image`, 16-bit millimeters | autonomy perception and diagnostics | Closest obstacle straight ahead |
| `/oakd/depth/points` | `sensor_msgs/PointCloud2`, x forward, y left, z up (`oak_d_link`) | autonomy mission and diagnostics | Obstacle map for path planning |
| `/oak/object_distances` | `oak_d_interfaces/ObjectDistanceArray` | `distance_subscriber` (debug tool) | Distance to each object the camera detects |

## PX4 (`px4-agent`)

The micro-ROS agent turns PX4's internal messages into ROS 2 topics over TELEM2. It has no code of its own, and PX4 decides the topic list.

| Topic | Direction | Used by | For |
| --- | --- | --- | --- |
| `/fmu/out/vehicle_local_position` | PX4 → ROS | autonomy mission, diagnostics | Drone position |
| `/fmu/out/vehicle_attitude` | PX4 → ROS | autonomy mission | Heading |
| `/fmu/out/vehicle_status` | PX4 → ROS | autonomy mission, diagnostics | Armed, flight mode |
| `/fmu/out/vehicle_command_ack` | PX4 → ROS | autonomy mission | Command accepted or rejected |
| `/fmu/out/vehicle_gps_position` | PX4 → ROS | autonomy diagnostics | GPS is alive |

The autonomy mission node sends `/fmu/in/offboard_control_mode`, `/fmu/in/trajectory_setpoint` and `/fmu/in/vehicle_command` back the same way. PX4 1.15 publishes more `/fmu/out` topics than these; this table only lists the ones the code uses.

## Telemetry (`airborne-bridge`)

Code: [bridge.py](../airborne/airborne/bridge.py). The bridge also passes raw MAVLink between the Pixhawk USB port and the SiK radio, both ways, for QGroundControl.

| Topic | Type | Used by | For |
| --- | --- | --- | --- |
| `/telemetry/mavlink` | `std_msgs/String` (JSON) | nobody yet | Every MAVLink message from the Pixhawk, decoded |
| `/telemetry/mavlink_raw` | `std_msgs/UInt8MultiArray` | nobody yet | The same messages as raw bytes |

## LiDAR (`velodyne`)

Off for the flight test.

| Topic | Type | Used by | For |
| --- | --- | --- | --- |
| `/velodyne_points` | `sensor_msgs/PointCloud2` | not connected yet | 3D point cloud |
| `/velodyne_packets` | `velodyne_msgs/VelodyneScan` | the point cloud converter | Raw scans |
| `/scan` | `sensor_msgs/LaserScan` | nobody yet | 2D slice of the cloud |

Autonomy reads the LiDAR on `/lidar/points`. When the LiDAR is mounted, point the autonomy `lidar_topic` parameter at `/velodyne_points`.
