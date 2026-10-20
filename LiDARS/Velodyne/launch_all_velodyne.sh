#!/bin/bash

# Source the ROS 2 installation and local workspace
if [ -f /opt/ros/jazzy/setup.bash ]; then
    source /opt/ros/jazzy/setup.bash
fi

if [ -f install/setup.bash ]; then
    source install/setup.bash
else
    echo "Error: install/setup.bash not found. Make sure you are in the workspace root and have run 'colcon build'."
    exit 1
fi

echo "Starting Velodyne VLP-16 Driver..."
# Launches the driver container
ros2 launch velodyne_driver velodyne_driver_node-VLP16-composed-launch.py &
PID_DRIVER=$!
sleep 2

echo "Starting Velodyne VLP-16 Pointcloud Transform..."
# Launches the pointcloud conversion container
ros2 launch velodyne_pointcloud velodyne_transform_node-VLP16-composed-launch.py &
PID_TRANSFORM=$!
sleep 2

echo "Starting Velodyne Laserscan..."
# Launches the laserscan node
ros2 launch velodyne_laserscan velodyne_laserscan_node-launch.py &
PID_SCAN=$!
sleep 2

echo "Starting RViz2..."
rviz2 &
PID_RVIZ=$!

# Trap SIGINT (Ctrl+C) to kill all background processes
trap "echo 'Stopping all nodes...'; kill $PID_DRIVER $PID_TRANSFORM $PID_SCAN $PID_RVIZ; exit" SIGINT

# Wait for processes to finish
wait