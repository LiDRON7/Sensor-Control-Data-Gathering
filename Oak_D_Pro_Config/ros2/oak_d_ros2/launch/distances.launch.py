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
        Node(
            package='oak_d_ros2', executable='distances', name='oak_distance_publisher',
            namespace=LaunchConfiguration('namespace'), output='screen',
            parameters=[LaunchConfiguration('params_file'), {
                'show_preview': ParameterValue(LaunchConfiguration('show_preview'), value_type=bool),
            }],
        ),
    ])
