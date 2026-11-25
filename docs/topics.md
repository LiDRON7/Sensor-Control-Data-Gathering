# Topics

Every ROS 2 topic these containers publish, and who uses it. The autonomy side is in [Autonomous-Systems docs/topics.md](https://github.com/LiDRON7/Autonomous-Systems/blob/main/docs/topics.md).

To see them live: `docker exec oak-d bash -lc "source /opt/ros/jazzy/setup.bash && ros2 topic list"`.

## Autonomy topics for flight recording

Record these topics for the [automatic flight recorder](https://github.com/LiDRON7/Sensor-Control-Data-Gathering/issues/97) and the [post-flight mission timeline](https://github.com/LiDRON7/Autonomous-Systems/issues/145).

| Topic | Type | Used by | For |
| --- | --- | --- | --- |
| `/autonomy/state` | `std_msgs/String` | flight recorder | Mission state, such as `HOLD` or `ABORT` |
| Structured status from [Autonomous-Systems #142](https://github.com/LiDRON7/Autonomous-Systems/issues/142) | Pending confirmation from Edwin | flight recorder, mission timeline | Mission state and the reason for changes |
| `/autonomy/preflight_result` | `std_msgs/String` (JSON) | flight recorder, mission timeline | Pass/fail and the check timestamp |
| `/autonomy/path` | `nav_msgs/Path` | flight recorder | Planned route |
| `/autonomy/occupancy_grid` | `nav_msgs/OccupancyGrid` | flight recorder | Obstacle map used for planning |
| `/landing/assessment` | `std_msgs/String` (JSON) | flight recorder | Landing-site assessment and reason when published |
| `/fmu/out/vehicle_status` | `px4_msgs/VehicleStatus` | flight recorder, mission timeline | Arming, disarming, and PX4 mode changes |
| `/fmu/out/vehicle_command_ack` | `px4_msgs/VehicleCommandAck` | flight recorder, mission timeline | PX4 command outcomes, including rejections |

The #142 status topic is still pending. Add its exact ROS 2 topic name and message type to the recorder list once Edwin confirms them.

Record `/oakd/depth/image` at a reduced rate per #97. Omit full-rate `/oakd/depth/points`.

Preflight runs before arming, when the per-flight bag has yet to start. The current result message carries only `success` and `checked_at_s`. The failure details are in the `/autonomy/preflight_check` service response. The recorder and autonomy owners still need to agree on how to preserve pre-arm results and their failure details.

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

Code: [node.py](../airborne/airborne_telemetry/node.py). The bridge also passes raw MAVLink between the Pixhawk USB port and the SiK radio, both ways, for QGroundControl.

| Topic | Type | Used by | For |
| --- | --- | --- | --- |
| `/telemetry/mavlink` | `std_msgs/String` (JSON) | nobody yet | Every MAVLink message from the Pixhawk, decoded |
| `/telemetry/mavlink_raw` | `std_msgs/UInt8MultiArray` | nobody yet | The same messages as raw bytes |
| `/gps/fix` | `sensor_msgs/NavSatFix` | nobody yet | GPS position from the Pixhawk (`GPS_RAW_INT`) |
| `/gps/fix_type`, `/gps/satellites` | `std_msgs/UInt8` | nobody yet | Fix quality (6 is RTK fixed) and satellite count |
| `/gps/rtk_fixed`, `/gps/fresh` | `std_msgs/Bool` | nobody yet | RTK fixed, and GPS heard in the last 3 s |
| `/gps/altitude_msl` | `std_msgs/Float64` | nobody yet | Altitude above sea level |

Autonomy gets its GPS straight from PX4 (`/fmu/out/vehicle_gps_position`), so it doesn't use the `/gps` topics.

## LiDAR (`velodyne`)

Off for the flight test.

| Topic | Type | Used by | For |
| --- | --- | --- | --- |
| `/velodyne_points` | `sensor_msgs/PointCloud2` | not connected yet | 3D point cloud |
| `/velodyne_packets` | `velodyne_msgs/VelodyneScan` | the point cloud converter | Raw scans |

Autonomy reads the LiDAR on `/lidar/points`. When the LiDAR is mounted, point the autonomy `lidar_topic` parameter at `/velodyne_points`.
