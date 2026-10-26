# Sensor-Control-Data-Gathering

docker compose config --quiet
docker compose --progress plain build oak-d

echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="03e7", MODE="0666"' | sudo tee /etc/udev/rules.d/80-movidius.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
# Reconnect OAK-D, then:
lsusb | grep 03e7

docker run --rm --entrypoint bash sensor-control-data-gathering-oak-d:latest -lc "source /opt/ros/jazzy/setup.bash && source /opt/oak-venv/bin/activate && source /opt/oak_ws/install/setup.bash && python -m pytest -p no:cacheprovider /opt/oak_ws/src/oak_d_ros2/test -q"
