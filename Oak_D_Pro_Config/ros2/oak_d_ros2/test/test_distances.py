"""Check scalar-only topic delivery and isolation from a slow ROS subscriber."""

from datetime import timedelta
import math
from threading import Event
import time

import depthai as dai
import pytest
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import Header

from oak_d_interfaces.msg import ObjectDistanceArray
from oak_d_ros2.messages import distance_message
from oak_d_ros2.node import OakDistanceNode


def spin_until(executor, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        executor.spin_once(timeout_sec=0.01)
    assert predicate(), 'Timed out waiting for ROS discovery/delivery'


def test_distance_message_contains_only_scalar_data():
    message = distance_message(Header(frame_id='optical'), [(0, 2.5), (99, math.nan)], ('bottle',))
    assert list(message.objects[0].get_fields_and_field_types()) == ['class_id', 'distance_m', 'distance_valid']
    assert message.objects[0].class_id == 'bottle'
    assert message.objects[0].distance_valid and message.objects[0].distance_m == 2.5
    assert message.objects[1].class_id == '99'
    assert not message.objects[1].distance_valid and math.isnan(message.objects[1].distance_m)
    assert not distance_message(Header(), [], ()).objects


@pytest.mark.parametrize('value', [math.nan, math.inf, 0, -1])
def test_invalid_distances_stay_unavailable(value):
    obj = distance_message(Header(), [(0, value)], ()).objects[0]
    assert not obj.distance_valid and math.isnan(obj.distance_m)


def test_real_ros_topic_and_acquisition_stamp():
    rclpy.init(args=['--ros-args', '-p', 'show_preview:=false'])
    node, observer = OakDistanceNode(), Node('distance_test_consumer')
    executor = SingleThreadedExecutor()
    executor.add_node(observer)
    received = []
    subscription = observer.create_subscription(ObjectDistanceArray, '/oak/object_distances', received.append, 10)
    try:
        node.set_labels(['bottle'])
        spin_until(executor, lambda: node.publisher.get_subscription_count() == 1)
        records = [(0, 2.5), (3, math.nan)]
        acquisition_time = dai.Clock.now() - timedelta(milliseconds=100)
        node.submit_distances(acquisition_time, records)
        records.clear()  # The worker owns only its immutable scalar snapshot.
        spin_until(executor, lambda: bool(received))
        message = received[-1]
        assert message.header.frame_id == 'oak_rgb_camera_optical_frame'
        assert message.objects[0].class_id == 'bottle'
        assert message.objects[0].distance_m == 2.5 and message.objects[0].distance_valid
        assert not message.objects[1].distance_valid
        stamp_ns = message.header.stamp.sec * 10**9 + message.header.stamp.nanosec
        age_s = (node.get_clock().now().nanoseconds - stamp_ns) / 1e9
        assert 0.08 < age_s < 1
        for topic in ('/oak/detections', '/oak/rgb/image_raw', '/oak/rgb/image_annotated',
                      '/oak/depth/image_raw', '/oakd/depth/image', '/oakd/depth/points'):
            assert observer.count_publishers(topic) == 0
        received.clear()
        node.submit_distances(dai.Clock.now(), [])
        spin_until(executor, lambda: bool(received))
        assert not received[-1].objects
        assert subscription
    finally:
        executor.shutdown()
        node.destroy_node()
        observer.destroy_node()
        rclpy.shutdown()


def test_slow_publishing_keeps_only_newest_scalar_measurements(monkeypatch):
    rclpy.init(args=['--ros-args', '-p', 'show_preview:=false'])
    node = OakDistanceNode()
    started, release, finished = Event(), Event(), Event()
    published = []

    def slow_publish(stamp, records):
        published.append((stamp, records))
        if stamp == timedelta(0):
            started.set()
            assert release.wait(3)
        else:
            finished.set()

    monkeypatch.setattr(node, '_publish_distances', slow_publish)
    try:
        node.submit_distances(timedelta(0), [(0, 1)])
        assert started.wait(3)
        for index in range(1, 100):
            node.submit_distances(timedelta(seconds=index), [(0, index)])
        assert not release.is_set()  # No camera submission waited for ROS.
        with node._condition:
            assert node._pending == (timedelta(seconds=99), ((0, 99.0),))
        release.set()
        assert finished.wait(3)
        assert published == [(timedelta(0), ((0, 1.0),)),
                             (timedelta(seconds=99), ((0, 99.0),))]
    finally:
        release.set()
        node.destroy_node()
        rclpy.shutdown()
