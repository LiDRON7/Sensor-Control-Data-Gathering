FROM ros:jazzy-ros-base-noble

ENV DEBIAN_FRONTEND=noninteractive \
    ROS_DISTRO=jazzy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIRTUAL_ENV=/opt/airborne-venv \
    HOME=/home/airborne

ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        python3-colcon-common-extensions \
        python3-pip \
        python3-rosdep \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt

RUN python3 -m venv --system-site-packages "${VIRTUAL_ENV}" \
    && python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install \
        --no-cache-dir \
        --requirement /tmp/requirements.txt \
    && python -m pip install \
        --no-cache-dir \
        --force-reinstall \
        --no-deps \
        colcon-core

WORKDIR /opt/airborne_ws

COPY airborne/ src/airborne/

RUN source "/opt/ros/${ROS_DISTRO}/setup.bash" \
    && rosdep update \
    && apt-get update \
    && rosdep install \
        --from-paths src \
        --ignore-src \
        --rosdistro "${ROS_DISTRO}" \
        --skip-keys "python3-pymavlink-pip python3-serial" \
        -y \
    && rm -rf /var/lib/apt/lists/* \
    && python -m colcon build \
        --merge-install \
        --packages-select airborne

RUN addgroup --system airborne \
    && adduser \
        --system \
        --ingroup airborne \
        --home /home/airborne \
        airborne \
    && mkdir -p /home/airborne/.ros \
    && chown -R airborne:airborne /home/airborne

COPY airborne/docker-entrypoint.sh /usr/local/bin/airborne-entrypoint.sh

RUN chmod +x /usr/local/bin/airborne-entrypoint.sh

USER airborne

ENTRYPOINT ["/usr/local/bin/airborne-entrypoint.sh"]
CMD ["ros2", "run", "airborne", "airborne_bridge"]