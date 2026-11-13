"""
ROS 2 launch file for leddar_ros2.

Equivalent to the ROS1 example.launch, converted to Python launch format.

Example usage:
  ros2 launch leddar_ros2 example.launch.py param1:=AK47035 device_type:=M16
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription([
        # --- Launch Arguments ---
        DeclareLaunchArgument(
            'param1', default_value='null',
            description=(
                '[All] GetDeviceList name, [Serial] COM port, '
                '[USB] serial number, [SPI-FTDI] FTDI cable id, '
                '[CANBus] Baudrate kbps, [Ethernet] IP address'
            )
        ),
        DeclareLaunchArgument(
            'device_type', default_value='not specified',
            description='Device type from leddar.device_types (e.g. M16, LCA2, LCA3)'
        ),
        DeclareLaunchArgument('param3', default_value='0',
            description='[Serial] modbus addr, [CANBus] Tx, [Ethernet] port'
        ),
        DeclareLaunchArgument('param4', default_value='0',
            description='[Serial] baudrate, [CANBus] Rx, [Ethernet] timeout'
        ),
        DeclareLaunchArgument('frame_id', default_value='sensor_frame'),
        DeclareLaunchArgument('parent_frame_id', default_value='map'),
        DeclareLaunchArgument('x', default_value='0.0'),
        DeclareLaunchArgument('y', default_value='0.0'),
        DeclareLaunchArgument('z', default_value='0.0'),
        DeclareLaunchArgument('roll', default_value='0.0'),
        DeclareLaunchArgument('pitch', default_value='0.0'),
        DeclareLaunchArgument('yaw', default_value='0.0'),

        # --- Leddar sensor node ---
        # ParameterValue with value_type=str ensures LaunchConfiguration
        # substitutions are properly resolved as strings, avoiding the
        # "Got NoneType" error from ROS2's parameter type inference.
        Node(
            package='leddar_ros2',
            executable='device.py',
            name='sensor',
            parameters=[{
                'device_type': ParameterValue(LaunchConfiguration('device_type'), value_type=str),
                'frame_id': ParameterValue(LaunchConfiguration('frame_id'), value_type=str),
                'param1': ParameterValue(LaunchConfiguration('param1'), value_type=str),
                'param3': ParameterValue(LaunchConfiguration('param3'), value_type=str),
                'param4': ParameterValue(LaunchConfiguration('param4'), value_type=str),
            }],
            output='screen',
        ),

        # --- Static transform publisher (replaces tf static_transform_publisher) ---
        Node(
            package='tf2_ros',
            executable='static_transform_publisher',
            name='leddar_to_map',
            arguments=[
                '--x', LaunchConfiguration('x'),
                '--y', LaunchConfiguration('y'),
                '--z', LaunchConfiguration('z'),
                '--roll', LaunchConfiguration('roll'),
                '--pitch', LaunchConfiguration('pitch'),
                '--yaw', LaunchConfiguration('yaw'),
                '--frame-id', LaunchConfiguration('parent_frame_id'),
                '--child-frame-id', LaunchConfiguration('frame_id'),
            ],
        ),
    ])