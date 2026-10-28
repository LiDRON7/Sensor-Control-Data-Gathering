# Containers walkthrough

How to set up, start, check and fix each container on the Raspberry Pi. Run every command from the repository root on the Pi. For the short version, see the [README](README.md).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/architecture/connections-dark.png">
  <img alt="What plugs into the Pi and the Pixhawk" src="docs/architecture/connections-light.png">
</picture>

## 1. Set up once

1. Install Docker and make it start at boot:

   ```bash
   sudo systemctl enable --now docker
   docker compose version
   ```

   Prefix Docker commands with `sudo` if you get a permission error.

2. Find the USB names of the Pixhawk and the SiK radio:

   ```bash
   ls -la /dev/serial/by-id/
   ```

   Use the Pixhawk entry ending in `-if00` and the FTDI radio entry ending in `-port0`. The Pixhawk name changes when you flash new firmware. Names are case-sensitive.

3. Find the serial group ID with `getent group dialout`. It's usually `20`.

4. Create a `.env` file next to `compose.yaml` with what you found:

   ```dotenv
   PIXHAWK_DEVICE=/dev/serial/by-id/<Pixhawk name ending in -if00>
   PX4_AGENT_DEVICE=/dev/ttyAMA0
   SERIAL_GID=20
   ROS_DOMAIN_ID=0
   ```

   The radio path is set directly in `compose.yaml` (`/dev/radio` line). Change the left side only if your radio has a different name.

5. Do the PX4, UART and OAK-D steps in the [README](README.md#set-up-a-new-pi-once).

6. LiDAR only: the VLP-16 sends to UDP port `2368` from `192.168.1.201`. Give the Pi's Ethernet port an address on `192.168.1.x`, then check with `ping -c 3 192.168.1.201`.

7. Check the configuration. No output means it's valid:

   ```bash
   docker compose config --quiet
   ```

## 2. Start the containers

| What | Command |
| --- | --- |
| Flight test (no LiDAR) | `docker compose up -d --build airborne-bridge px4-agent oak-d` |
| Everything | `docker compose up -d --build` |
| One container | `docker compose up -d --build oak-d` |
| Status | `docker compose ps` |

Leave out `--build` when nothing changed since the last build. The first build needs internet. After that the containers start offline.

## 3. Check each container works

First add this helper to your shell. It runs any `ros2` command inside the `airborne-bridge` container:

```bash
ros() { docker exec -it airborne-bridge bash -lc "source /opt/ros/jazzy/setup.bash && source /opt/airborne_ws/install/setup.bash && ros2 $*"; }
```

| Container | Log line that means it's working (`docker compose logs -f <name>`) | Data check |
| --- | --- | --- |
| `airborne-bridge` | `Opened pixhawk` and `Opened radio`, then `Forwarded ... uplinked ... from ground` every 5 s | `ros topic hz /telemetry/mavlink` |
| `px4-agent` | A `create_client` line once PX4 connects | `ros topic list \| grep fmu` |
| `oak-d` | `Publishing object distances on /oak/object_distances` | `ros topic hz /oakd/depth/points` |
| `velodyne` | `Velodyne ROS pipeline is running.` | `ros topic hz /velodyne_points` (about 9.9 Hz) |

`ros topic hz` only works for message types the container has installed, which is why `/fmu` topics are only listed above. To see PX4 data, run `ros2 topic hz /fmu/out/vehicle_status` inside `lidron_autonomy`.

Every topic and who uses it is in [docs/topics.md](docs/topics.md).

## 4. Everyday commands

| Task | Command |
| --- | --- |
| Follow all logs | `docker compose logs -f` |
| Last 100 lines of one container | `docker compose logs --tail 100 <name>` |
| Restart one container | `docker compose restart <name>` |
| Stop one container | `docker compose stop <name>` |
| Stop and remove everything | `docker compose down` |
| After changing `.env` or device paths | `docker compose up -d --force-recreate <name>` (no rebuild needed) |
| Update the code | `git pull`, then `docker compose up -d --build` |

The containers come back after a reboot by themselves (`restart: unless-stopped`), unless you stopped them by hand.

You can build the images on a laptop to check they compile, but they come out `amd64`. Rebuild on the Pi to get `arm64` images.

## 5. Fixing problems

| Symptom | Do this |
| --- | --- |
| `airborne-bridge` won't start | Check the path in `.env` exists: `ls -la /dev/serial/by-id/`. Inside the container: `docker exec airborne-bridge ls -l /dev/pixhawk /dev/radio`. |
| `airborne-bridge` logs `no valid MAVLink telemetry` | Check Pixhawk power, the USB cable, `PIXHAWK_DEVICE` and `SERIAL_GID`. The baud rate is `115200`. |
| QGroundControl gets data but can't change modes | Check the log shows `uplinked` going up. If it stays at 0, check the ground radio. |
| No `/fmu` topics | `docker compose logs px4-agent`. Check the TELEM2 wiring (TX to RX), `dtparam=uart0=on`, and the PX4 parameters `UXRCE_DDS_CFG = 102` and `SER_TEL2_BAUD = 921600`. |
| No `/oakd` topics | `docker compose logs oak-d`. Check `lsusb \| grep 03e7` and the udev rule from the README. Check `publish_depth: true` in `oak.yaml`. |
| Velodyne topics exist but have no data | `sudo tcpdump -ni any udp port 2368 -c 10` and `ping -c 3 192.168.1.201` |
| Topics show up but have no data in another container | All containers need `network_mode: host`, `ipc: host` and the same `ROS_DOMAIN_ID`. |
| Topics not visible from another computer | Same `ROS_DOMAIN_ID` on both, same network, and no firewall blocking DDS multicast. A wired Ethernet link to the Pi is enough, no internet needed. |
