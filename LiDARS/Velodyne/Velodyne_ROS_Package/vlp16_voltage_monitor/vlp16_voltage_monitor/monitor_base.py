"""Shared ROS output, warning, and stale-data handling for voltage sources."""

import math
import re
import time

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from std_msgs.msg import Float64, String

from vlp16_voltage_monitor.health import VoltageHealth


class MonitorBase(Node):
    """Publish readable and numeric voltage alongside standard ROS diagnostics."""

    def __init__(self, node_name, default_device, minimum=0.0, maximum=0.0, **kwargs):
        """Create outputs and a watchdog independent of simulated ROS time."""
        super().__init__(node_name, **kwargs)
        self.device = self.parameter('device_name', default_device)
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', self.device):
            raise ValueError('device_name must be a single valid ROS name token')
        self._log_readings = self.parameter('log_readings', True)
        self._warning_interval = self.parameter('warning_repeat_sec', 10.0)
        if not math.isfinite(self._warning_interval) or self._warning_interval <= 0:
            raise ValueError('warning_repeat_sec must be finite and positive')
        self._health = VoltageHealth(
            self.parameter('min_voltage', minimum),
            self.parameter('max_voltage', maximum),
            self.parameter('max_step_voltage', 0.0),
            self.parameter('stale_timeout_sec', 3.0))
        self._publisher = self.create_publisher(String, f'{self.device}/voltage', 10)
        self._numeric = self.create_publisher(Float64, f'{self.device}/voltage_value', 10)
        self._status_publisher = self.create_publisher(
            String, f'{self.device}/voltage_status', 10)
        self._diagnostics = self.create_publisher(DiagnosticArray, '/diagnostics', 10)
        self._last_status = None
        self._last_warning = float('-inf')
        self._steady_clock = Clock(clock_type=ClockType.STEADY_TIME)
        self._watchdog = self.create_timer(
            0.5, self._publish_status, clock=self._steady_clock)

    def parameter(self, name, default):
        """Declare a startup-only parameter and return its resolved value."""
        return self.declare_parameter(
            name, default, ParameterDescriptor(read_only=True)).value

    def accept_voltage(self, voltage):
        """Publish a fresh numeric sample or mark an invalid reading unavailable."""
        if self._health.update(voltage, time.monotonic()):
            text = f'Voltage: {voltage:.2f} V'
            self._publisher.publish(String(data=text))
            self._numeric.publish(Float64(data=float(voltage)))
            if self._log_readings:
                self.get_logger().info(text)
        self._publish_status()

    def unavailable(self, reason):
        """Expose a source failure without repeating a previous numeric value."""
        self._health.unavailable(reason)
        self._publish_status()

    def _publish_status(self):
        now = time.monotonic()
        level, identity, detail = self._health.status(now)
        level = bytes([level])
        prefix = 'OK' if level == DiagnosticStatus.OK else 'WARNING'
        message = f'{prefix}: {detail}'
        self._status_publisher.publish(String(data=message))
        if level == DiagnosticStatus.STALE:
            self._publisher.publish(String(data='Voltage: unavailable'))
        status = DiagnosticStatus(
            level=level, name=f'voltage{self.get_namespace().rstrip("/")}/{self.device}',
            hardware_id=self.device, message=detail)
        if self._health.received_at is not None:
            status.values.append(KeyValue(
                key='last_valid_sample_age_sec',
                value=f'{now - self._health.received_at:.3f}'))
        if level != DiagnosticStatus.STALE:
            status.values.append(KeyValue(key='voltage_V', value=str(self._health.voltage)))
        for key, value in (
                ('min_voltage', self._health.minimum),
                ('max_voltage', self._health.maximum),
                ('max_step_voltage', self._health.max_step)):
            status.values.append(KeyValue(key=key, value=str(value)))
        diagnostics = DiagnosticArray(status=[status])
        diagnostics.header.stamp = self.get_clock().now().to_msg()
        self._diagnostics.publish(diagnostics)
        if level != DiagnosticStatus.OK:
            if identity != self._last_status or now - self._last_warning >= self._warning_interval:
                self.get_logger().warning(f'{self.device}: {detail}')
                self._last_warning = now
        elif self._last_status is not None and self._last_status != identity:
            self.get_logger().info(f'{self.device}: voltage monitoring recovered')
        self._last_status = identity
