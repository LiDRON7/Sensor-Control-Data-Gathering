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

## MAVLink Command Bridge (Issue #139)

Proposed interface contract for the Raspberry Pi bridge that translates QGroundControl MAVLink commands into existing ROS 2 autonomy services.

The interface has been implemented and tested using PX4 SITL.
QGroundControl SITL command validation has been performed.
Full Resume state recovery remains unconfirmed.
Team review remains pending.
Integrated Widow hardware validation is tracked under Autonomous-Systems#144.

### Component identity
| Parameter | Value |
| --- | --- |
| MAVLink protocol | MAVLink 2.0 |
| System ID | Same as PX4 (default: 1, configurable) |
| Component ID | `MAV_COMP_ID_ONBOARD_COMPUTER2` (192) |
| Component type | `MAV_TYPE_ONBOARD_CONTROLLER` (18) |
| Autopilot type | `MAV_AUTOPILOT_INVALID` (8) |
| System status | `MAV_STATE_ACTIVE` (4) |
| Base mode | 0 |
| Custom mode | 0 |
| Heartbeat frequency | 1 Hz |
| Mission state freshness limit | 2 seconds |
| Command processing timeout | 5 seconds per applicable stage |

Heartbeat transmission begins after the bridge receives
a PX4 heartbeat.

The heartbeat identifies the bridge as an onboard component, not as a flight controller. Component ID uniqueness must be verified before deployment.

### Command mapping

Commands use `COMMAND_LONG` and explicitly target the bridge's system and component IDs. All unused command parameters are set to zero.

| Action | MAVLink command | Command ID | ROS 2 interface |
| --- | --- | --- | --- |
| Check | `MAV_CMD_USER_1` | 31010 | `/autonomy/preflight_check` |
| Start | `MAV_CMD_USER_2` | 31011 | `/autonomy/prepare_start`, preflight check, then `/autonomy/start` |
| Pause | `MAV_CMD_USER_3` | 31012 | `/autonomy/enable` (`false`) |
| Resume | `MAV_CMD_USER_4` | 31013 | `/autonomy/resume` |
| Abort | `MAV_CMD_USER_5` | 31014 | `/autonomy/abort` |

### ROS 2 interfaces

| Interface | Type | Bridge role |
| --- | --- | --- |
| `/autonomy/preflight_check` | `std_srvs/Trigger` | Service client |
| `/autonomy/preflight_result` | `std_msgs/String` (JSON) | Subscriber |
| `/autonomy/enable` | `std_srvs/SetBool` | Service client (Pause only) |
| `/autonomy/prepare_start` | `std_srvs/Trigger` | Start authorization client |
| `/autonomy/start` | `interfaces/StartMission` | Authorized Start client |
| `/autonomy/resume` | `std_srvs/Trigger` | Explicit Resume client |
| `/autonomy/abort` | `std_srvs/Trigger` | Service client |
| `/autonomy/state` | `std_msgs/String` | Subscriber |

### Start sequence

A single Start command performs the following sequence:

1. Request a one-time Start authorization through `/autonomy/prepare_start`.
2. Request `/autonomy/preflight_check`.
3. Wait for the service response and corresponding `/autonomy/preflight_result`.
4. Validate the passing result and its timestamp within the 30-second window.
5. Request `/autonomy/start` using the authorization token.
6. Return a final `COMMAND_ACK` based on the service response.

Failed Start preflight responses are reported to QGroundControl through `STATUSTEXT` with the prefix `LIDRON_START:`.

A failed, missing, stale, or uncorrelated preflight result must not enable the mission. A previously cached result must not be reused as the result of a new Start request.

#### Preflight correlation limitation

The existing preflight result interface does not include a unique
request identifier. The bridge validates result timestamps,
reception time, and the number of received results.

SITL integration tests assume the bridge is the only active
preflight client. Concurrent external preflight requests require
additional coordination before hardware deployment.

### Command acknowledgements

The bridge returns one final `COMMAND_ACK` per received command addressed to it. The acknowledgment includes the original command ID and targets the requesting system and component.

| Result | Value | Meaning |
| --- | --- | --- |
| `MAV_RESULT_ACCEPTED` | 0 | Requested operation accepted by autonomy |
| `MAV_RESULT_TEMPORARILY_REJECTED` | 1 | Bridge is busy processing another request |
| `MAV_RESULT_DENIED` | 2 | Autonomy rejected the request or preflight failed |
| `MAV_RESULT_UNSUPPORTED` | 3 | Command is not supported by the bridge |
| `MAV_RESULT_FAILED` | 4 | Service unavailable, timeout, or internal error |

An accepted acknowledgment confirms that the requested operation was accepted, not that the entire mission or flight maneuver has completed.

For Resume, an accepted acknowledgment does not guarantee an
immediate transition out of HOLD. Mission recovery remains
subject to the existing autonomy health and obstacle checks.

For Check, the bridge also returns the preflight service response
message through MAVLink `STATUSTEXT`, using the prefix `LIDRON_CHECK:`.
Messages exceeding the 50-byte text limit use MAVLink 2 STATUSTEXT chunking to preserve the complete preflight result.
The final `COMMAND_ACK` indicates whether the check passed or failed.

### Mission status

The bridge subscribes to `/autonomy/state` and reports the current mission state through MAVLink `STATUSTEXT`.

| Parameter | Value |
| --- | --- |
| Severity | `MAV_SEVERITY_INFO` |
| Text format | `LIDRON_STATE:<STATE>` |
| Encoding | ASCII |
| Maximum text length | 50 bytes |
| Transmission | On state change and periodically at 1 Hz |

Supported states:

- `IDLE`
- `PREFLIGHT`
- `TAKEOFF`
- `PLANNING`
- `NAVIGATING`
- `REPLANNING`
- `APPROACH`
- `LANDING_CHECK`
- `LANDING`
- `COMPLETE`
- `HOLD`
- `ABORT`
- `PILOT_OVERRIDE`

Example: `LIDRON_STATE:NAVIGATING`

The bridge forwards the state reported by autonomy without changing its meaning. Stale state information must not be reported as current.

### Transport and validation

The bridge uses a MAVLink connection to PX4.
SITL integration testing uses a pymavlink test client over UDP.
The development bridge listens on UDP port 14540.
QGroundControl SITL command validation was performed. See the integration test results for observed outcomes and remaining limitations.

See [Issue #139 integration test results](testing/issue-139.md)
for test evidence, results, and known limitations.

Integrated Raspberry Pi, Pixhawk, and Widow hardware validation is tracked under Autonomous-Systems#144.

### Safety constraints

- The bridge must not publish directly to PX4 flight-control topics.
- All mission actions must use the existing autonomy services.
- Start must not bypass the preflight check.
- Pause must use `/autonomy/enable` (`false`), not QGroundControl's
  native Hold command.
- Resume requires a fresh mission state of `HOLD`.
- Start requires a fresh mission state of `IDLE`, `COMPLETE`,
  or `ABORT`.
- Start must not be treated as Resume.
- Existing pilot override and autonomy safety checks must be preserved.


### Abort priority and command isolation

- Abort takes priority over other pending bridge commands.
- Interrupted commands receive a failure acknowledgment.
- The autonomy service invalidates pending Start authorization when processing Abort.
- Start authorization is single-use and expires.
- Explicit Start and Resume services validate their intended action independently.
- Cancellation of a local service future does not guarantee cancellation of an already executing remote operation.
- Abort failures and timeouts must not be interpreted as confirmed mission cancellation.

### Cross-repository dependency

The updated bridge requires the corresponding autonomy services and
StartMission interface implemented in Autonomous-Systems.
Both repositories must use compatible versions.
