# Sensor-Control-Data-Gathering

Containers that run on the drone's Raspberry Pi 5. They connect the Pixhawk, the OAK-D Pro and the VLP-16 to ROS 2, so the code in [Autonomous-Systems](https://github.com/LiDRON7/Autonomous-Systems) can use them.

## Start the flight-test stack

```bash
docker compose up -d --build airborne-bridge px4-agent oak-d
```

The VLP-16 is not on the flight-test drone, so `velodyne` stays off.

Check it worked:

```bash
docker compose ps
docker exec oak-d bash -lc "source /opt/ros/jazzy/setup.bash && ros2 topic list | grep -E 'fmu|oakd'"
```

You should see `/fmu/out/vehicle_status`, `/oakd/depth/points` and the other topics.

## Containers

| Container | Connects | ROS 2 topics |
| --- | --- | --- |
| `airborne-bridge` | Pixhawk USB ↔ SiK radio (both ways) | `/telemetry/mavlink`, `/telemetry/mavlink_raw` |
| `px4-agent` | Pixhawk TELEM2 → ROS 2 (micro-ROS agent) | `/fmu/out/*`, `/fmu/in/*` |
| `oak-d` | OAK-D Pro over USB | `/oakd/depth/image`, `/oakd/depth/points`, `/oak/object_distances` |
| `velodyne` | VLP-16 over Ethernet | `/velodyne_points`, `/scan` |

All containers use the host network and `ipc: host`, so they share ROS 2 topics with each other and with the autonomy container.

## One-time Pi setup

1. Flash the Pixhawk with PX4 v1.15. In QGroundControl set `UXRCE_DDS_CFG = 102` (TELEM2), `SER_TEL2_BAUD = 921600` and `MAV_1_CONFIG = 0`.
2. Wire Pixhawk TELEM2 to the Pi UART (TX→RX, RX→TX, GND→GND).
3. Turn on the Pi UART: add `dtparam=uart0=on` to `/boot/firmware/config.txt`, then reboot.
4. Find the Pixhawk's USB name with `ls /dev/serial/by-id/`. It changes after flashing PX4.
5. Put the device paths in a `.env` file next to `compose.yaml`:

```bash
PIXHAWK_DEVICE=/dev/serial/by-id/<the PX4 name from step 4>
PX4_AGENT_DEVICE=/dev/ttyAMA0
ROS_DOMAIN_ID=0
```

6. Let the OAK-D be used without root:

```bash
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"' | sudo tee /etc/udev/rules.d/80-movidius.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
lsusb | grep 03e7   # after reconnecting the OAK-D
```

## Ground station

Use QGroundControl with the other SiK radio. Mission Planner cannot change PX4 flight modes reliably.

## Tests

```bash
docker compose config --quiet
docker run --rm --entrypoint bash sensor-control-data-gathering-oak-d:latest -lc "source /opt/ros/jazzy/setup.bash && source /opt/oak-venv/bin/activate && source /opt/oak_ws/install/setup.bash && python -m pytest -p no:cacheprovider /opt/oak_ws/src/oak_d_ros2/test -q"
```

## More

- [CONTAINERS-WALKTHROUGH.md](CONTAINERS-WALKTHROUGH.md): every command for building, running and debugging each container.
- Architecture diagrams: `docs/architecture/` in Autonomous-Systems.
