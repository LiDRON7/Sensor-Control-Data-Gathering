"""Publish a readable VLP-16 input supply voltage over ROS 2."""

from http.client import HTTPException
import math

import rclpy
from rclpy.executors import ExternalShutdownException

from vlp16_voltage_monitor.diagnostics import DiagnosticsClient
from vlp16_voltage_monitor.monitor_base import MonitorBase


class VoltageMonitor(MonitorBase):
    """Poll the sensor HTTP interface and publish voltage text."""

    def __init__(self, **kwargs):
        """Configure the reader, publisher, and wall-time polling timer."""
        super().__init__(
            'vlp16_voltage_monitor', 'velodyne', minimum=8.0, maximum=19.0, **kwargs)
        sensor_ip = self.parameter('sensor_ip', '192.168.1.201')
        poll_period = self.parameter('poll_period_sec', 1.0)
        timeout = self.parameter('timeout_sec', 0.8)
        # The manual recommends at most one HTTP command per second.
        if not math.isfinite(poll_period) or poll_period < 1.0:
            raise ValueError('poll_period_sec must be finite and at least 1.0')
        if not math.isfinite(timeout) or timeout <= 0 or timeout > poll_period:
            raise ValueError('timeout_sec must be positive and <= poll_period_sec')
        if self._health.stale_sec <= poll_period + timeout:
            raise ValueError('stale_timeout_sec must exceed poll_period_sec + timeout_sec')

        self._client = DiagnosticsClient(sensor_ip, timeout)
        self._timer = self.create_timer(
            poll_period, self._poll, clock=self._steady_clock)
        self.get_logger().info(
            f'Reading {self._client.url}; publishing on '
            f'{self._publisher.topic_name}')

    def _poll(self):
        try:
            voltage = self._client.read_voltage()
        except (OSError, ValueError, HTTPException) as exc:
            self.unavailable(
                f'Cannot read voltage: {exc}. Check sensor_ip and Ethernet IPv4 settings; '
                'polling will retry automatically.')
            return
        self.accept_voltage(voltage)


def main(args=None):
    """Run the voltage monitor until ROS shuts down or Ctrl+C is pressed."""
    rclpy.init(args=args)
    node = None
    try:
        node = VoltageMonitor()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()
