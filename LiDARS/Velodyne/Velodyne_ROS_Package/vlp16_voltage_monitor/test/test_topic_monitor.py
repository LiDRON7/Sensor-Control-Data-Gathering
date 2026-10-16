"""Test selection of real voltage fields and shared ROS status output."""

from unittest.mock import MagicMock, patch

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
import pytest
from sensor_msgs.msg import BatteryState
from std_msgs.msg import Float32, Float64

from vlp16_voltage_monitor.health import VoltageHealth
from vlp16_voltage_monitor.monitor_base import MonitorBase
from vlp16_voltage_monitor.topic_monitor import extract_voltage, TopicVoltageMonitor


@pytest.mark.parametrize('message', [
    Float32(data=5.0), Float64(data=5.0), BatteryState(voltage=5.0, present=True)])
def test_numeric_sources(message):
    """Read scalar volts and supply voltage from a present BatteryState."""
    assert extract_voltage(message) == 5.0


def test_absent_battery():
    """An absent supply must not generate a valid zero-volt reading."""
    with pytest.raises(ValueError, match='absent'):
        extract_voltage(BatteryState(voltage=5.0, present=False))


def test_diagnostic_selection():
    """Ignore unrelated statuses and require an exact numeric voltage key."""
    other = DiagnosticStatus(name='camera_temperature')
    voltage = DiagnosticStatus(name='usb_power', values=[KeyValue(key='VBUS', value='5.1')])
    assert extract_voltage(DiagnosticArray(status=[other]), 'usb_power', 'VBUS') is None
    assert extract_voltage(
        DiagnosticArray(status=[other, voltage]), 'usb_power', 'VBUS') == 5.1
    with pytest.raises(ValueError, match='exactly one'):
        extract_voltage(DiagnosticArray(status=[voltage]), 'usb_power', 'missing')
    with pytest.raises(ValueError, match='ambiguous'):
        extract_voltage(DiagnosticArray(status=[voltage, voltage]), 'usb_power', 'VBUS')
    voltage.values[0].value = '5.1 V'
    with pytest.raises(ValueError):
        extract_voltage(DiagnosticArray(status=[voltage]), 'usb_power', 'VBUS')


@pytest.mark.parametrize('level', [DiagnosticStatus.ERROR, DiagnosticStatus.STALE])
def test_unavailable_diagnostic_source(level):
    """Do not use a measurement explicitly marked invalid by its driver."""
    message = DiagnosticArray(status=[DiagnosticStatus(
        name='power', level=level, values=[KeyValue(key='voltage', value='5.0')])])
    with pytest.raises(ValueError, match='unavailable'):
        extract_voltage(message, 'power', 'voltage')


def test_adapter_scaling():
    """Convert millivolts to volts only through the configured scale."""
    node = MagicMock()
    node._scale = 0.001
    TopicVoltageMonitor._receive(node, Float32(data=5000.0))
    node.accept_voltage.assert_called_once_with(5.0)


def test_status_warning_throttle_and_recovery():
    """Publish fresh diagnostics while warning logs are rate limited."""
    node = MagicMock()
    node.device = 'usb'
    node.get_namespace.return_value = '/'
    node._health = VoltageHealth(4.75, 5.25, 0.0, 3.0)
    node._last_status = None
    node._last_warning = float('-inf')
    node._warning_interval = 10.0
    # Use a real ROS stamp so message construction and serialization are valid.
    from builtin_interfaces.msg import Time
    node.get_clock().now().to_msg.return_value = Time()
    with patch('vlp16_voltage_monitor.monitor_base.time.monotonic', return_value=10.0):
        node._health.update(4.5, 10.0)
        MonitorBase._publish_status(node)
        MonitorBase._publish_status(node)
    node.get_logger().warning.assert_called_once()
    status = node._diagnostics.publish.call_args.args[0].status[0]
    assert status.level == DiagnosticStatus.WARN
    assert status.name == 'voltage/usb'
    assert node._status_publisher.publish.call_args.args[0].data.startswith('WARNING:')
    with patch('vlp16_voltage_monitor.monitor_base.time.monotonic', return_value=11.0):
        node._health.update(5.0, 11.0)
        MonitorBase._publish_status(node)
    assert node._diagnostics.publish.call_args.args[0].status[0].level == DiagnosticStatus.OK
    node.get_logger().info.assert_called_once()
    with patch('vlp16_voltage_monitor.monitor_base.time.monotonic', return_value=14.0):
        MonitorBase._publish_status(node)
    assert node._publisher.publish.call_args.args[0].data == 'Voltage: unavailable'
    status = node._diagnostics.publish.call_args.args[0].status[0]
    assert status.level == DiagnosticStatus.STALE
    assert 'voltage_V' not in [v.key for v in status.values]


def test_invalid_data_does_not_publish_numeric():
    """Numeric plots get only valid new samples, never synthetic zeros."""
    node = MagicMock()
    node._health = VoltageHealth(0.0, 0.0, 0.0, 3.0)
    MonitorBase.accept_voltage(node, float('nan'))
    node._numeric.publish.assert_not_called()
    MonitorBase.accept_voltage(node, 5.0)
    assert node._numeric.publish.call_args.args[0].data == 5.0
    assert node._publisher.publish.call_args.args[0].data == 'Voltage: 5.00 V'
