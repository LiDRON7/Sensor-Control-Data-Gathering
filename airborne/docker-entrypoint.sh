#!/usr/bin/env bash

set -e

source "/opt/ros/${ROS_DISTRO}/setup.bash"
source "${VIRTUAL_ENV}/bin/activate"
source "/opt/airborne_ws/install/setup.bash"

exec "$@"