# Sensor Control and Data Gathering Containers Walkthrough

This repository contains Dockerized services for airborne MAVLink telemetry and
Velodyne VLP-16 LiDAR processing on a Raspberry Pi.

Docker Compose manages both services. They can be built and started together or
operated independently.

## System Overview

```text
Pixhawk
   |
   | MAVLink over USB serial
   v
airborne-bridge container
   |                         |
   | unchanged MAVLink       | ROS 2 telemetry topics
   v                         v
Telemetry transmitter     Onboard ROS algorithms
   |
   | Radio link
   v
Ground telemetry radio
   |
   v
Windows ground bridge -> Mission Planner


Velodyne VLP-16
   |
   | Ethernet UDP port 2368
   v
velodyne container
   |
   +-> /velodyne_packets
   +-> /velodyne_points
   +-> /scan
```

## Containers

### Airborne Telemetry

Compose service:

```text
airborne-bridge
```

The airborne telemetry container:

- Uses ROS 2 Jazzy.
- Reads MAVLink from the Pixhawk at `115200` baud.
- Forwards the original MAVLink frames to the telemetry transmitter at `57600`
  baud.
- Requests Pixhawk data streams at `4 Hz`.
- Publishes decoded MAVLink messages to ROS 2.
- Publishes the original MAVLink frame bytes to ROS 2.
- Reconnects after serial failures or heartbeat loss.
- Runs as a non-root user with serial-device group access.

Published topics:

| Topic | ROS type | Description |
| --- | --- | --- |
| `/telemetry/mavlink` | `std_msgs/msg/String` | JSON-decoded MAVLink messages |
| `/telemetry/mavlink_raw` | `std_msgs/msg/UInt8MultiArray` | Original MAVLink frame bytes |

The `/telemetry/mavlink` JSON contains:

- ROS receipt timestamp
- MAVLink system ID
- MAVLink component ID
- MAVLink sequence number
- MAVLink message type
- Decoded MAVLink fields

The airborne container does not replace or repackage the data sent to the
telemetry transmitter. The ground station continues to receive standard
MAVLink.

### Velodyne LiDAR

Compose service:

```text
velodyne
```

The Velodyne container:

- Uses ROS 2 Jazzy.
- Receives VLP-16 packets from `192.168.1.201`.
- Listens for LiDAR data on UDP port `2368`.
- Runs the VLP-16 driver.
- Converts packet scans into `PointCloud2` messages.
- Converts point clouds into `LaserScan` messages.
- Runs headlessly without RViz.

Published topics:

| Topic | ROS type | Description |
| --- | --- | --- |
| `/velodyne_packets` | `velodyne_msgs/msg/VelodyneScan` | Raw Velodyne packet scans |
| `/velodyne_points` | `sensor_msgs/msg/PointCloud2` | Decoded 3D point cloud |
| `/scan` | `sensor_msgs/msg/LaserScan` | 2D laser scan |
| `/diagnostics` | `diagnostic_msgs/msg/DiagnosticArray` | ROS diagnostic information |

The expected VLP-16 publication rate is approximately `9.9 Hz`.

## Ground Station

The ground bridge and Mission Planner remain on the Windows ground-station
laptop. They are not included in the Raspberry Pi containers.

The data path remains:

```text
Pixhawk -> RPi -> airborne radio -> ground radio -> ground bridge -> Mission Planner
```

## Requirements

The target Raspberry Pi should have:

- Docker
- Docker Compose
- Pixhawk connected through USB
- FTDI telemetry transmitter connected through USB
- Velodyne VLP-16 connected through Ethernet

Check Docker:

```bash
docker --version
docker compose version
```

Enable Docker at boot:

```bash
sudo systemctl enable --now docker
```

If Docker reports a permission error, prefix Docker commands with `sudo`.

## Find Serial Device Paths

Before starting the telemetry container, connect the Pixhawk and telemetry
transmitter to the Raspberry Pi and list the persistent USB device paths:

```bash
ls -la /dev/serial/by-id/
```

Example output:

```text
usb-ArduPilot_Pixhawk6X_43004E000251323436333634-if00 -> ../../ttyACM0
usb-ArduPilot_Pixhawk6X_43004E000251323436333634-if02 -> ../../ttyACM1
usb-FTDI_FT231X_USB_UART_D30IL4V3-if00-port0 -> ../../ttyUSB0
```

Use the Pixhawk `if00` entry and the FTDI radio `port0` entry.

Copy the exact paths into the left side of the `devices` mappings in
`compose.yaml`:

```yaml
devices:
  - /dev/serial/by-id/PIXHAWK_DEVICE_NAME:/dev/pixhawk
  - /dev/serial/by-id/RADIO_DEVICE_NAME:/dev/radio
```

Only change the host paths on the left. Keep the container paths
`/dev/pixhawk` and `/dev/radio` unchanged.

Linux paths are case-sensitive. For example, `Pixhawk6X` and `Pixhawk6x` are
different paths.

The currently configured paths are:

```yaml
devices:
  - /dev/serial/by-id/usb-ArduPilot_Pixhawk6X_43004E000251323436333634-if00:/dev/pixhawk
  - /dev/serial/by-id/usb-FTDI_FT231X_USB_UART_D30IL4V3-if00-port0:/dev/radio
```

If `/dev/serial/by-id/` does not exist or is empty, check whether Linux detected
the devices:

```bash
ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
lsusb
sudo dmesg --ctime | tail -n 60
```

## Serial Permissions

Check the RPi serial-device group:

```bash
getent group dialout
```

A typical result is:

```text
dialout:x:20:
```

Compose uses group ID `20` by default.

If the RPi uses a different group ID, create a `.env` file beside
`compose.yaml`:

```dotenv
SERIAL_GID=20
ROS_DOMAIN_ID=0
```

Replace `20` with the actual `dialout` group ID.

## Verify The Velodyne Network

Check that the RPi can reach the VLP-16:

```bash
ping -c 3 192.168.1.201
```

The sensor must be configured to send UDP data to the RPi on port `2368`.

The RPi Ethernet interface and the VLP-16 must be on compatible subnets.

## Validate Docker Compose

From the repository root:

```bash
docker compose config --quiet
```

No output means the Compose configuration is valid.

## Build And Run Everything

Build both images:

```bash
docker compose build
```

Start both containers:

```bash
docker compose up -d
```

Build and start both containers with one command:

```bash
docker compose up -d --build
```

This starts:

```text
airborne-bridge
velodyne
```

Check their status:

```bash
docker compose ps
```

Both services should show `Up`.

## Run Only Airborne Telemetry

Build and start only the telemetry service:

```bash
docker compose up -d --build airborne-bridge
```

If the image is already built:

```bash
docker compose up -d airborne-bridge
```

Check its status:

```bash
docker compose ps airborne-bridge
```

Follow its logs:

```bash
docker compose logs -f airborne-bridge
```

Expected messages include:

```text
Opening Pixhawk /dev/pixhawk and radio /dev/radio; waiting for heartbeat
Pixhawk heartbeat received; bridge running
Forwarded ... messages (... bytes)
```

Press `Ctrl+C` to stop following the logs. The container continues running.

## Run Only Velodyne

Build and start only the Velodyne service:

```bash
docker compose up -d --build velodyne
```

If the image is already built:

```bash
docker compose up -d velodyne
```

Check its status:

```bash
docker compose ps velodyne
```

Follow its logs:

```bash
docker compose logs -f velodyne
```

Expected messages include:

```text
Starting Velodyne VLP-16 driver...
Starting Velodyne VLP-16 point-cloud transform...
Starting Velodyne laser-scan conversion...
Velodyne ROS pipeline is running.
```

## Verify Airborne ROS Topics

List ROS topics from the airborne container:

```bash
docker exec airborne-bridge bash -lc \
  'source /opt/ros/jazzy/setup.bash &&
   source /opt/airborne_ws/install/setup.bash &&
   ros2 topic list -t'
```

Expected telemetry topics:

```text
/telemetry/mavlink [std_msgs/msg/String]
/telemetry/mavlink_raw [std_msgs/msg/UInt8MultiArray]
```

Check the decoded telemetry publication rate:

```bash
docker exec -it airborne-bridge bash -lc \
  'source /opt/ros/jazzy/setup.bash &&
   source /opt/airborne_ws/install/setup.bash &&
   ros2 topic hz /telemetry/mavlink'
```

Inspect one decoded MAVLink message:

```bash
docker exec airborne-bridge bash -lc \
  'source /opt/ros/jazzy/setup.bash &&
   source /opt/airborne_ws/install/setup.bash &&
   ros2 topic echo /telemetry/mavlink --once'
```

Inspect one raw MAVLink frame:

```bash
docker exec airborne-bridge bash -lc \
  'source /opt/ros/jazzy/setup.bash &&
   source /opt/airborne_ws/install/setup.bash &&
   ros2 topic echo /telemetry/mavlink_raw --once'
```

## Verify Velodyne ROS Topics

Enter the Velodyne container:

```bash
docker exec -it velodyne bash
```

Source ROS and the workspace:

```bash
source /opt/ros/jazzy/setup.bash
source /opt/velodyne_ws/install/setup.bash
```

List topics:

```bash
ros2 topic list -t
```

Expected topics include:

```text
/velodyne_packets [velodyne_msgs/msg/VelodyneScan]
/velodyne_points [sensor_msgs/msg/PointCloud2]
/scan [sensor_msgs/msg/LaserScan]
```

Check each publication rate separately:

```bash
ros2 topic hz /velodyne_packets
```

Press `Ctrl+C`, then run:

```bash
ros2 topic hz /velodyne_points
```

Press `Ctrl+C`, then run:

```bash
ros2 topic hz /scan
```

A nonzero rate near `9.9 Hz` confirms that the VLP-16 pipeline is working.

Inspect one laser-scan message:

```bash
ros2 topic echo /scan --once --qos-reliability best_effort
```

Exit the container shell:

```bash
exit
```

## Point-Cloud Subscribers

`/velodyne_points` uses the standard ROS 2
`sensor_msgs/msg/PointCloud2` message.

Point data is stored in the message's binary `data` field for efficiency.
Subscribers should use standard ROS point-cloud libraries to decode the actual
`x`, `y`, `z`, `intensity`, and `ring` values.

The binary representation does not mean the point information is unavailable.
RViz and standard ROS subscriber libraries decode it automatically.

## View All Logs

Follow logs from both services:

```bash
docker compose logs -f
```

Show the last 100 telemetry log lines:

```bash
docker compose logs --tail 100 airborne-bridge
```

Show the last 100 Velodyne log lines:

```bash
docker compose logs --tail 100 velodyne
```

## Container Management

Restart both services:

```bash
docker compose restart
```

Restart telemetry only:

```bash
docker compose restart airborne-bridge
```

Restart Velodyne only:

```bash
docker compose restart velodyne
```

Stop telemetry only:

```bash
docker compose stop airborne-bridge
```

Stop Velodyne only:

```bash
docker compose stop velodyne
```

Start existing containers:

```bash
docker compose up -d
```

Stop and remove both containers:

```bash
docker compose down
```

Remove only the telemetry container:

```bash
docker compose rm -f airborne-bridge
```

Remove only the Velodyne container:

```bash
docker compose rm -f velodyne
```

## Recreate After Device Path Changes

After changing serial-device paths in `compose.yaml`, validate the file:

```bash
docker compose config --quiet
```

Recreate only the airborne container:

```bash
docker compose up -d --force-recreate airborne-bridge
```

A source-code rebuild is not required when only Compose device paths change.

## Update The Deployment

Pull repository changes:

```bash
git pull
```

Rebuild and restart both services:

```bash
docker compose up -d --build
```

Rebuild only telemetry:

```bash
docker compose up -d --build airborne-bridge
```

Rebuild only Velodyne:

```bash
docker compose up -d --build velodyne
```

## Automatic Startup

Both services use:

```yaml
restart: unless-stopped
```

When Docker starts after an RPi reboot, previously created containers restart
automatically unless they were manually stopped.

Ensure Docker itself starts at boot:

```bash
sudo systemctl enable --now docker
```

## Offline Operation

The deployed system does not require Wi-Fi or internet during normal operation.

Runtime connections are local:

- Pixhawk through USB serial
- Telemetry transmitter through USB serial
- VLP-16 through Ethernet
- ROS communication through the RPi host network
- Ground station through the physical telemetry-radio link

Internet access is normally needed only for:

- Cloning or pulling the repository
- Downloading Docker base images
- Downloading dependencies during the initial Docker build

After both images are built, start them offline with:

```bash
docker compose up -d
```

Avoid rebuilding offline unless all required Docker layers and dependencies are
already cached.

ROS subscribers running on another computer require a network connection to the
RPi, but this can be wired Ethernet and does not require internet.

## Laptop Builds

The images can be built on a Windows laptop for validation:

```powershell
docker compose --progress plain build airborne-bridge
docker compose --progress plain build velodyne
```

The complete Compose stack should not be started on Windows because the Linux
serial-device paths and the VLP-16 network are available only on the RPi.

Laptop builds produce `amd64` images. The RPi should rebuild the images locally
to produce `arm64` images:

```bash
docker compose up -d --build
```

## Troubleshooting

### Airborne Container Does Not Start

Confirm that the exact host device paths exist:

```bash
ls -la /dev/serial/by-id/
```

Check the container state:

```bash
docker compose ps airborne-bridge
docker compose logs --tail 100 airborne-bridge
```

Confirm that the mapped devices exist inside the container:

```bash
docker exec airborne-bridge ls -l /dev/pixhawk /dev/radio
```

### Airborne Waits For A Heartbeat

Check:

- Pixhawk power
- USB cable
- Pixhawk device path
- Pixhawk baud rate of `115200`
- Serial permissions

Follow the logs:

```bash
docker compose logs -f airborne-bridge
```

### Velodyne Topics Exist But Have No Data

Confirm that UDP packets reach the RPi:

```bash
sudo tcpdump -ni any udp port 2368 -c 10
```

Check connectivity:

```bash
ping -c 3 192.168.1.201
```

Check Velodyne logs:

```bash
docker compose logs --tail 100 velodyne
```

### ROS Topics Are Not Visible On Another Computer

Confirm:

- Both systems use `ROS_DOMAIN_ID=0`.
- Both systems are on the same reachable network.
- DDS multicast traffic is allowed.
- Firewalls are not blocking ROS 2 traffic.
- The subscriber uses compatible ROS message types and QoS.