#!/usr/bin/env bash

set -euo pipefail

declare -a child_pids=()

shutdown() {
    trap - SIGINT SIGTERM EXIT

    if [ "${#child_pids[@]}" -gt 0 ]; then
        echo "Stopping Velodyne ROS nodes..."
        kill -TERM "${child_pids[@]}" 2>/dev/null || true
        wait "${child_pids[@]}" 2>/dev/null || true
    fi
}

trap 'shutdown; exit 0' SIGINT SIGTERM
trap shutdown EXIT

echo "Starting Velodyne VLP-16 driver..."
ros2 launch \
    velodyne_driver \
    velodyne_driver_node-VLP16-composed-launch.py &
child_pids+=("$!")

sleep 2

echo "Starting Velodyne VLP-16 point-cloud transform..."
ros2 launch \
    velodyne_pointcloud \
    velodyne_transform_node-VLP16-composed-launch.py &
child_pids+=("$!")

sleep 2

echo "Starting Velodyne laser-scan conversion..."
ros2 launch \
    velodyne_laserscan \
    velodyne_laserscan_node-launch.py &
child_pids+=("$!")

echo "Velodyne ROS pipeline is running."

set +e
wait -n "${child_pids[@]}"
status=$?
set -e

echo "A Velodyne ROS process exited with status ${status}."
exit "${status}"