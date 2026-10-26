FROM ros:jazzy-ros-base-noble

ENV DEBIAN_FRONTEND=noninteractive \
    ROS_DISTRO=jazzy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIRTUAL_ENV=/opt/oak-venv \
    DEPTHAI_ZOO_CACHE_PATH=/opt/depthai-models \
    DEPTHAI_DISABLE_CRASHDUMP_COLLECTION=1 \
    HOME=/home/oak

ENV PATH="${VIRTUAL_ENV}/bin:${PATH}"

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        libusb-1.0-0 \
        python3-colcon-common-extensions \
        python3-numpy \
        python3-opencv \
        python3-pip \
        python3-rosdep \
        python3-venv \
        gstreamer1.0-tools \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-ugly \
        gstreamer1.0-libav \
    && rm -rf /var/lib/apt/lists/*

COPY Oak_D_Pro_Config/ros2/oak_d_ros2/requirements.txt \
    /tmp/oak-requirements.txt

RUN python3 -m venv --system-site-packages "${VIRTUAL_ENV}" \
    && python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install \
        --no-cache-dir \
        --requirement /tmp/oak-requirements.txt

WORKDIR /opt/oak_ws

# setup.py installs this script through ../../Object_Detection_With_Distance.py,
# so it must remain at the workspace root relative to src/oak_d_ros2.
COPY Oak_D_Pro_Config/Object_Detection_With_Distance.py ./
COPY Oak_D_Pro_Config/ros2/ src/

RUN source "/opt/ros/${ROS_DISTRO}/setup.bash" \
    && rosdep update \
    && apt-get update \
    && rosdep install \
        --from-paths src \
        --ignore-src \
        --rosdistro "${ROS_DISTRO}" \
        -y \
    && rm -rf /var/lib/apt/lists/* \
    && python /usr/bin/colcon build \
        --merge-install \
        --packages-up-to oak_d_ros2

# OAK-D Pro is an RVC2 device. Preloading this archive makes normal container
# startup independent of HubAI and internet access.
RUN mkdir -p "${DEPTHAI_ZOO_CACHE_PATH}" \
    && python -c 'import depthai as dai; description = dai.NNModelDescription(); description.model = "yolov6-nano"; description.platform = "RVC2"; assert description.check(); print(dai.getModelFromZoo(description, useCached=True, cacheDirectory="/opt/depthai-models", progressFormat="pretty"))'

RUN addgroup --system oak \
    && adduser \
        --system \
        --ingroup oak \
        --home /home/oak \
        oak \
    && mkdir -p /home/oak/.ros \
    && chown -R oak:oak \
        /home/oak \
        "${DEPTHAI_ZOO_CACHE_PATH}"

COPY Oak_D_Pro_Config/docker-entrypoint.sh \
    /usr/local/bin/oak-entrypoint.sh

RUN chmod +x /usr/local/bin/oak-entrypoint.sh

USER oak

ENTRYPOINT ["/usr/local/bin/oak-entrypoint.sh"]

CMD ["ros2", "launch", "oak_d_ros2", "distances.launch.py", "show_preview:=false"]