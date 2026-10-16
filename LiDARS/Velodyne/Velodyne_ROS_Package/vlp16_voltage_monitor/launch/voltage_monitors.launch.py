"""Run independent voltage monitors for configured robot components."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    """Load standard ROS parameter YAML and enable available voltage sources."""
    config = LaunchConfiguration('config_file')
    actions = [DeclareLaunchArgument(
        'config_file', default_value=PathJoinSubstitution([
            FindPackageShare('vlp16_voltage_monitor'), 'config', 'voltage_monitors.yaml']))]
    for device, name, executable, enabled in (
            ('velodyne', 'vlp16_voltage_monitor', 'voltage_monitor', 'true'),
            ('telemetry', 'telemetry_voltage_monitor', 'voltage_topic_monitor', 'false'),
            ('oakd', 'oakd_voltage_monitor', 'voltage_topic_monitor', 'false')):
        option = f'enable_{device}'
        actions.append(DeclareLaunchArgument(option, default_value=enabled))
        actions.append(Node(
            package='vlp16_voltage_monitor', executable=executable, name=name,
            parameters=[config], output='screen',
            condition=IfCondition(LaunchConfiguration(option))))
    return LaunchDescription(actions)
