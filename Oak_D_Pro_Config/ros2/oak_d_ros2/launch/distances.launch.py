"""Run the original viewer with only a scalar object-distance ROS topic."""

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('params_file', default_value=PathJoinSubstitution([
            get_package_share_directory('oak_d_ros2'), 'config', 'oak.yaml',
        ])),
        DeclareLaunchArgument('namespace', default_value='oak'),
        DeclareLaunchArgument('show_preview', default_value='true'),
        DeclareLaunchArgument('enable_stream', default_value='false'),
        DeclareLaunchArgument('stream_host', default_value='10.42.0.113'),
        DeclareLaunchArgument('stream_port', default_value='5600'),
        DeclareLaunchArgument('stream_width', default_value='640'),
        DeclareLaunchArgument('stream_height', default_value='480'),
        DeclareLaunchArgument('stream_bitrate', default_value='1000'),
        DeclareLaunchArgument('stream_fps', default_value='15'),
        Node(
            package='oak_d_ros2', executable='distances', name='oak_distance_publisher',
            namespace=LaunchConfiguration('namespace'), output='screen',
            parameters=[LaunchConfiguration('params_file'), {
                'show_preview': ParameterValue(LaunchConfiguration('show_preview'), value_type=bool),
                'enable_stream': ParameterValue(LaunchConfiguration('enable_stream'), value_type=bool),
                'stream_host': LaunchConfiguration('stream_host'),
                'stream_port': ParameterValue(LaunchConfiguration('stream_port'), value_type=int),
                'stream_width': ParameterValue(LaunchConfiguration('stream_width'), value_type=int),
                'stream_height': ParameterValue(LaunchConfiguration('stream_height'), value_type=int),
                'stream_bitrate': ParameterValue(LaunchConfiguration('stream_bitrate'), value_type=int),
                'stream_fps': ParameterValue(LaunchConfiguration('stream_fps'), value_type=int),
            }],
        ),
    ])