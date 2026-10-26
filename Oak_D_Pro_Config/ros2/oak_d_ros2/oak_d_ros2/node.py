"""Publish only scalar distances calculated by the original camera script."""

import os
import queue
import subprocess
import threading
from pathlib import Path
import runpy

import cv2

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
        self._condition = threading.Condition()
        self._pending = None
        self._stopping = False
        self._error = None
        self._worker = None
        self._labels = ()

        self._stream_process = None
        self._stream_queue = queue.Queue(maxsize=2)
        self._stream_thread = None
        self._stream_stop = threading.Event()

        try:
            descriptor = ParameterDescriptor(read_only=True)
            self.frame_id = self.declare_parameter(
                'frame_id', 'oak_rgb_camera_optical_frame', descriptor).value
            self.show_preview = self.declare_parameter('show_preview', True, descriptor).value

            self.enable_stream = self.declare_parameter('enable_stream', False, descriptor).value
            self.stream_host = self.declare_parameter('stream_host', '10.42.0.113', descriptor).value
            self.stream_port = self.declare_parameter('stream_port', 5600, descriptor).value
            self.stream_width = self.declare_parameter('stream_width', 640, descriptor).value
            self.stream_height = self.declare_parameter('stream_height', 480, descriptor).value
            self.stream_bitrate = self.declare_parameter('stream_bitrate', 1000, descriptor).value
            self.stream_fps = self.declare_parameter('stream_fps', 15, descriptor).value

            if not self.frame_id:
                raise ValueError('frame_id must not be empty')

            self.publisher = self.create_publisher(ObjectDistanceArray, 'object_distances', 1)
            self._worker = threading.Thread(target=self._publish_loop, name='oak_distance_publisher', daemon=True)
            self._worker.start()
            self.get_logger().info(f'Publishing object distances on {self.publisher.topic_name}')

            if self.enable_stream:
                self._start_gstreamer()
                self._stream_thread = threading.Thread(target=self._stream_worker, name='oak_stream_worker', daemon=True)
                self._stream_thread.start()
                self.get_logger().info(
                    f'Streaming video to {self.stream_host}:{self.stream_port} '
                    f'({self.stream_width}x{self.stream_height}@{self.stream_fps}fps, {self.stream_bitrate}kbps)'
                )
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

    def stream_frame(self, frame):
        """Queue a frame for GStreamer streaming. Non-blocking, drops if full."""
        if not self.enable_stream:
            return
        try:
            resized = cv2.resize(frame, (self.stream_width, self.stream_height))
            if not resized.flags['C_CONTIGUOUS']:
                resized = resized.copy()
            self._stream_queue.put_nowait(resized.tobytes())
        except queue.Full:
            pass
        except Exception as e:
            self.get_logger().warning(f'Stream frame error: {e}')

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

    def _start_gstreamer(self):
        command = [
            'gst-launch-1.0',
            '-q',
            'fdsrc',
            '!',
            'rawvideoparse',
            'format=bgr',
            f'width={self.stream_width}',
            f'height={self.stream_height}',
            f'framerate={self.stream_fps}/1',
            '!',
            'videoconvert',
            '!',
            'x264enc',
            'tune=zerolatency',
            'speed-preset=ultrafast',
            f'bitrate={self.stream_bitrate}',
            f'key-int-max={self.stream_fps}',
            '!',
            'h264parse',
            '!',
            'rtph264pay',
            'pt=96',
            'config-interval=1',
            '!',
            'udpsink',
            f'host={self.stream_host}',
            f'port={self.stream_port}',
            'sync=false',
            'async=false'
        ]
        self.get_logger().info(f'Starting GStreamer: {" ".join(command)}')
        self._stream_process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE
        )

    def _stream_worker(self):
        while not self._stream_stop.is_set():
            try:
                frame_bytes = self._stream_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            if self._stream_process is None or self._stream_process.poll() is not None:
                self.get_logger().error('GStreamer process stopped')
                break
            try:
                self._stream_process.stdin.write(frame_bytes)
            except (BrokenPipeError, OSError) as e:
                self.get_logger().error(f'GStreamer pipe error: {e}')
                break

    def _stop_gstreamer(self):
        self._stream_stop.set()
        if self._stream_thread is not None:
            self._stream_thread.join(timeout=2)
        if self._stream_process is not None and self._stream_process.poll() is None:
            try:
                if self._stream_process.stdin:
                    self._stream_process.stdin.close()
                self._stream_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._stream_process.terminate()
                self._stream_process.wait(timeout=3)
            except Exception:
                pass

    def destroy_node(self):
        self._stop_gstreamer()
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