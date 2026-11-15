FROM ros:jazzy-ros-base-noble

ENV DEBIAN_FRONTEND=noninteractive \
    ROS_DISTRO=jazzy

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        python3-colcon-common-extensions \
        python3-rosdep \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/velodyne_ws

COPY LiDARS/Velodyne/Velodyne_ROS_Package/ src/

RUN source "/opt/ros/${ROS_DISTRO}/setup.bash" \
    && rosdep update \
    && apt-get update \
    && rosdep install \
        --from-paths src \
        --ignore-src \
        --rosdistro "${ROS_DISTRO}" \
        -y \
    && rm -rf /var/lib/apt/lists/* \
    && colcon build \
        --merge-install \
        --executor sequential \
        --cmake-args -DCMAKE_BUILD_TYPE=Release

COPY LiDARS/Velodyne/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY LiDARS/Velodyne/run_velodyne_headless.sh /usr/local/bin/run_velodyne_headless.sh

RUN chmod +x \
    /usr/local/bin/docker-entrypoint.sh \
    /usr/local/bin/run_velodyne_headless.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["/usr/local/bin/run_velodyne_headless.sh"]