#!/usr/bin/env bash

set -e

source "/opt/ros/${ROS_DISTRO}/setup.bash"
source "/opt/airborne_ws/install/setup.bash"

exec "$@"