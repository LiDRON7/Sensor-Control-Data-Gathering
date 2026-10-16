"""Launch the voltage monitor with configurable sensor network settings."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    """Declare the sensor address, timing, and console output options."""
    limits = {
        'min_voltage': '8.0', 'max_voltage': '19.0', 'max_step_voltage': '0.0',
        'stale_timeout_sec': '3.0', 'warning_repeat_sec': '10.0',
    }
    return LaunchDescription([
        *[DeclareLaunchArgument(key, default_value=value) for key, value in limits.items()],
        DeclareLaunchArgument('sensor_ip', default_value='192.168.1.201'),
        DeclareLaunchArgument('poll_period_sec', default_value='1.0'),
        DeclareLaunchArgument('timeout_sec', default_value='0.8'),
        DeclareLaunchArgument('log_readings', default_value='true'),
        Node(
            package='vlp16_voltage_monitor',
            executable='voltage_monitor',
            output='screen',
            parameters=[{
                **{key: ParameterValue(LaunchConfiguration(key), value_type=float)
                   for key in limits},
                'sensor_ip': ParameterValue(
                    LaunchConfiguration('sensor_ip'), value_type=str),
                'poll_period_sec': ParameterValue(
                    LaunchConfiguration('poll_period_sec'), value_type=float),
                'timeout_sec': ParameterValue(
                    LaunchConfiguration('timeout_sec'), value_type=float),
                'log_readings': ParameterValue(
                    LaunchConfiguration('log_readings'), value_type=bool),
            }],
        ),
    ])
