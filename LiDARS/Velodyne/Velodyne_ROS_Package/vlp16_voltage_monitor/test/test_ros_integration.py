"""Verify ROS transport, concurrent components, and watchdog behavior."""

import time
from unittest.mock import patch

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from std_msgs.msg import Float32, Float64, String

from vlp16_voltage_monitor.topic_monitor import TopicVoltageMonitor
from vlp16_voltage_monitor.voltage_monitor import VoltageMonitor


def test_components_publish_warn_stale_and_recover():
    """Exercise three independent monitors over actual ROS publishers/subscribers."""
    context = Context()
    context.init(args=[], domain_id=91)
    executor = SingleThreadedExecutor(context=context)
    nodes = []
    text = {}
    numeric = {}
    status = {}
    diagnostics = {}

    def spin_until(condition, timeout=5.0):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.05)
        assert condition(), (text, numeric, status)

    try:
        observer = Node('voltage_test', context=context)
        nodes.append(observer)
        lidar = VoltageMonitor(context=context, parameter_overrides=[
            Parameter('log_readings', value=False)])
        nodes.append(lidar)
        publishers = {}
        readings = {'telemetry': 5.0, 'oakd': 5.0}
        for device in readings:
            monitor = TopicVoltageMonitor(
                context=context, cli_args=['--ros-args', '-r', f'__node:={device}_monitor'],
                parameter_overrides=[
                    Parameter('device_name', value=device),
                    Parameter('input_topic', value=f'/test/{device}'),
                    Parameter('min_voltage', value=4.75),
                    Parameter('max_voltage', value=5.25),
                    Parameter('max_step_voltage', value=0.25),
                    Parameter('stale_timeout_sec', value=0.6),
                    Parameter('log_readings', value=False)])
            nodes.append(monitor)
            publishers[device] = observer.create_publisher(Float32, f'/test/{device}', 10)
        for device in ('velodyne', 'telemetry', 'oakd'):
            observer.create_subscription(
                String, f'/{device}/voltage',
                lambda msg, d=device: text.__setitem__(d, msg.data), 10)
            observer.create_subscription(
                Float64, f'/{device}/voltage_value',
                lambda msg, d=device: numeric.__setitem__(d, msg.data), 10)
            observer.create_subscription(
                String, f'/{device}/voltage_status',
                lambda msg, d=device: status.__setitem__(d, msg.data), 10)

        def receive_diagnostics(message):
            for item in message.status:
                diagnostics[item.name] = item.level

        observer.create_subscription(DiagnosticArray, '/diagnostics', receive_diagnostics, 10)

        def send_readings():
            for device, value in readings.items():
                publishers[device].publish(Float32(data=value))

        observer.create_timer(0.1, send_readings)
        for node in nodes:
            executor.add_node(node)
        with patch.object(lidar._client, 'read_voltage', return_value=12.21923828125):
            spin_until(lambda: len(numeric) == 3 and len(diagnostics) == 3)
            assert text['velodyne'] == 'Voltage: 12.22 V'
            assert numeric['telemetry'] == 5.0
            assert numeric['oakd'] == 5.0
            readings['telemetry'] = 4.5
            spin_until(lambda: 'Low voltage' in status.get('telemetry', ''))
            assert status['oakd'].startswith('OK:')
            readings['oakd'] = 5.6
            spin_until(lambda: 'High voltage' in status.get('oakd', ''))
            del readings['telemetry']
            spin_until(lambda: diagnostics.get('voltage/telemetry') == DiagnosticStatus.STALE)
            spin_until(lambda: text.get('telemetry') == 'Voltage: unavailable')
            assert numeric['telemetry'] == 4.5
            assert numeric['velodyne'] > 12.0
            readings['telemetry'] = 5.0
            spin_until(lambda: diagnostics.get('voltage/telemetry') == DiagnosticStatus.OK)
            spin_until(lambda: numeric['telemetry'] == 5.0)
            readings['oakd'] = float('nan')
            spin_until(lambda: 'Invalid voltage' in status.get('oakd', ''))
            assert numeric['oakd'] > 5.5  # Last valid sample, never a fabricated zero.
    finally:
        executor.shutdown()
        for node in reversed(nodes):
            node.destroy_node()
        context.try_shutdown()
