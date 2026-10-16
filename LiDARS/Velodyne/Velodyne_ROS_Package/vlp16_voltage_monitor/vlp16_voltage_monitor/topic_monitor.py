"""Adapt voltage topics from radios, cameras, power monitors, or other sensors."""

import math

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import BatteryState
from std_msgs.msg import Float32, Float64

from vlp16_voltage_monitor.monitor_base import MonitorBase


MESSAGE_TYPES = {
    'std_msgs/msg/Float32': Float32,
    'std_msgs/msg/Float64': Float64,
    'sensor_msgs/msg/BatteryState': BatteryState,
    'diagnostic_msgs/msg/DiagnosticArray': DiagnosticArray,
}


def extract_voltage(message, diagnostic_name='', diagnostic_key=''):
    """Read volts from an explicitly selected message field or diagnostic key."""
    if isinstance(message, BatteryState):
        if not message.present:
            raise ValueError('BatteryState reports the monitored supply absent')
        return float(message.voltage)
    if isinstance(message, DiagnosticArray):
        statuses = [s for s in message.status if s.name == diagnostic_name]
        if not statuses:
            return None  # Other components can share the diagnostics topic.
        if len(statuses) != 1:
            raise ValueError('Diagnostic status name is ambiguous')
        status = statuses[0]
        if status.level in (DiagnosticStatus.ERROR, DiagnosticStatus.STALE):
            raise ValueError(f'Source diagnostics unavailable: {status.message}')
        values = [v.value for v in status.values if v.key == diagnostic_key]
        if len(values) != 1:
            raise ValueError('Expected exactly one matching voltage diagnostic key')
        return float(values[0])
    return float(message.data)


class TopicVoltageMonitor(MonitorBase):
    """Monitor an existing measurement source without opening the device itself."""

    def __init__(self, **kwargs):
        """Configure a topic adapter with best-effort input compatibility."""
        super().__init__('voltage_topic_monitor', 'sensor', **kwargs)
        source = self.parameter('input_topic', '')
        message_type = self.parameter('input_type', 'std_msgs/msg/Float32')
        self._diagnostic_name = self.parameter('diagnostic_name', '')
        self._diagnostic_key = self.parameter('diagnostic_key', '')
        self._scale = self.parameter('voltage_scale', 1.0)
        if not math.isfinite(self._scale) or self._scale <= 0:
            raise ValueError('voltage_scale must be finite and positive')
        if not source or message_type not in MESSAGE_TYPES:
            raise ValueError(f'Set input_topic and input_type from {list(MESSAGE_TYPES)}')
        if message_type == 'diagnostic_msgs/msg/DiagnosticArray':
            if not self._diagnostic_name or not self._diagnostic_key:
                raise ValueError('Set diagnostic_name and diagnostic_key for diagnostic input')
            if self._diagnostic_name.startswith('voltage/'):
                raise ValueError('Cannot consume voltage monitor output diagnostics')
        outputs = (self._publisher, self._numeric, self._status_publisher)
        if self.resolve_topic_name(source) in [p.topic_name for p in outputs]:
            raise ValueError('input_topic must differ from the monitor output topics')
        self._subscription = self.create_subscription(
            MESSAGE_TYPES[message_type], source, self._receive, qos_profile_sensor_data)
        self.get_logger().info(f'Monitoring {self.device} from {source} ({message_type})')

    def _receive(self, message):
        try:
            voltage = extract_voltage(message, self._diagnostic_name, self._diagnostic_key)
        except (ValueError, TypeError) as exc:
            self.unavailable(str(exc))
            return
        if voltage is not None:
            self.accept_voltage(voltage * self._scale)


def main(args=None):
    """Run a topic adapter until interrupted."""
    rclpy.init(args=args)
    node = None
    try:
        node = TopicVoltageMonitor()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()
