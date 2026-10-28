# Sensor-Control-Data-Gathering

These containers run on the drone's Raspberry Pi 5. They connect the Pixhawk, the OAK-D Pro camera and the VLP-16 LiDAR to ROS 2, so the [Autonomous-Systems](https://github.com/LiDRON7/Autonomous-Systems) code can read them and fly the drone.

## Start the flight-test containers

```bash
docker compose up -d --build airborne-bridge px4-agent oak-d
```

The flight-test drone has no LiDAR, so `velodyne` stays off. To check that PX4 and the camera are publishing:

```bash
docker exec oak-d bash -lc "source /opt/ros/jazzy/setup.bash && ros2 topic list | grep -E 'fmu|oakd'"
```

You should see `/fmu/out/vehicle_status` and `/oakd/depth/points`, among others.

## What each container does

| Container | Connects | Publishes |
| --- | --- | --- |
| `airborne-bridge` | Pixhawk USB and the SiK radio, both ways | `/telemetry/mavlink` |
| `px4-agent` | Pixhawk TELEM2 to ROS 2 | `/fmu/out/*`, and listens on `/fmu/in/*` |
| `oak-d` | OAK-D Pro over USB | `/oakd/depth/image`, `/oakd/depth/points`, `/oak/object_distances` |
| `velodyne` | VLP-16 over Ethernet | `/velodyne_points` |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/architecture/data-flow-dark.png">
  <img alt="How data moves from the sensors to PX4" src="docs/architecture/data-flow-light.png">
</picture>

How everything is wired and powered:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/architecture/connections-dark.png">
  <img alt="Power, data and radio connections" src="docs/architecture/connections-light.png">
</picture>

## Set up a new Pi (once)

Follow [docs/pi-setup.md](docs/pi-setup.md): wiring, Pi and PX4 settings, `.env`, and a 7-step check that everything works.

## Ground station

Use QGroundControl with the second SiK radio. Mission Planner can't switch PX4 flight modes reliably, so don't fly PX4 with it.

## Tests

```bash
docker compose config --quiet
docker run --rm --entrypoint bash sensor-control-data-gathering-oak-d:latest -lc "source /opt/ros/jazzy/setup.bash && source /opt/oak-venv/bin/activate && source /opt/oak_ws/install/setup.bash && python -m pytest -p no:cacheprovider /opt/oak_ws/src/oak_d_ros2/test -q"
```

## More

- [docs/connect-to-pi.md](docs/connect-to-pi.md): how to SSH into the drone's Pi, at the university or in the field.
- [docs/pi-setup.md](docs/pi-setup.md): wire the Pi, start the containers and check everything works.
- [docs/pi-known-issues.md](docs/pi-known-issues.md): every problem we hit on the Pi, why, and the fix.
- [docs/topics.md](docs/topics.md): every topic, who sends it and who uses it.
- [CONTAINERS-WALKTHROUGH.md](CONTAINERS-WALKTHROUGH.md): every command for building, running and debugging each container.
- `docs/architecture/`: the data flow and wiring diagrams. Open the `.excalidraw` files at [excalidraw.com](https://excalidraw.com) to edit them.
