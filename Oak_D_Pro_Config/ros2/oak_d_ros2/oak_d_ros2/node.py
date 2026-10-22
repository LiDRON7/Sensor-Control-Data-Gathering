"""Publish only scalar distances calculated by the original camera script."""

import os
from pathlib import Path
import runpy
from threading import Condition, Thread

from ament_index_python.packages import get_package_share_directory
import rclpy
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.duration import Duration
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import Header

from oak_d_interfaces.msg import ObjectDistanceArray

from .messages import distance_message


class OakDistanceNode(Node):
    def __init__(self):
        super().__init__('oak_distance_publisher', namespace='oak')
        self._condition = Condition()
        self._pending = None
        self._stopping = False
        self._error = None
        self._worker = None
        self._labels = ()
        try:
            descriptor = ParameterDescriptor(read_only=True)
            self.frame_id = self.declare_parameter(
                'frame_id', 'oak_rgb_camera_optical_frame', descriptor).value
            self.show_preview = self.declare_parameter('show_preview', True, descriptor).value
            if not self.frame_id:
                raise ValueError('frame_id must not be empty')
            # Reliable delivery with only the latest sample retained by DDS.
            # Any DDS wait happens on the worker, never on the viewer thread.
            self.publisher = self.create_publisher(ObjectDistanceArray, 'object_distances', 1)
            self._worker = Thread(target=self._publish_loop, name='oak_distance_publisher', daemon=True)
            self._worker.start()
            self.get_logger().info(f'Publishing object distances on {self.publisher.topic_name}')
        except BaseException:
            self.destroy_node()
            raise

    def set_labels(self, labels):
        self._labels = tuple(str(label) for label in labels)

    def ok(self):
        if self._error is not None:
            raise RuntimeError('ROS distance publishing failed') from self._error
        if not rclpy.ok(context=self.context):
            return False
        rclpy.spin_once(self, timeout_sec=0)
        return rclpy.ok(context=self.context)

    def submit_distances(self, acquisition_time, measurements):
        """Copy only numeric labels/distances; retain no camera packets or pixels."""
        records = tuple((int(label), float(distance)) for label, distance in measurements)
        with self._condition:
            self._pending = (acquisition_time, records)
            self._condition.notify()

    def _publish_loop(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._stopping or self._pending is not None)
                if self._stopping:
                    return
                packet, self._pending = self._pending, None
            try:
                self._publish_distances(*packet)
            except Exception as error:
                if not self._stopping and rclpy.ok(context=self.context):
                    self._error = error
                return

    def _publish_distances(self, acquisition_time, records):
        from depthai import Clock
        age_ns = max(0, int((Clock.now() - acquisition_time).total_seconds() * 1e9))
        stamp = (self.get_clock().now() - Duration(nanoseconds=age_ns)).to_msg()
        header = Header(stamp=stamp, frame_id=self.frame_id)
        self.publisher.publish(distance_message(header, records, self._labels))

    def destroy_node(self):
        with self._condition:
            self._stopping = True
            self._pending = None
            self._condition.notify_all()
        if self._worker is not None:
            self._worker.join()
        return super().destroy_node()

    def run_original_script(self):
        if self.show_preview and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
            raise RuntimeError('The original viewer needs a desktop; use show_preview:=false for headless use')
        script = (Path(get_package_share_directory('oak_d_ros2')) / 'scripts'
                  / 'Object_Detection_With_Distance.py')
        try:
            runpy.run_path(str(script), run_name='__main__', init_globals={'_ros_bridge': self})
        except BaseException:
            if self.show_preview:
                import cv2
                cv2.destroyAllWindows()
            raise


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = OakDistanceNode()
        node.run_original_script()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
