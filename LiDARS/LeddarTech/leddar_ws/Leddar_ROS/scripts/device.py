#!/usr/bin/env python3

import leddar
import math
import numpy as np
import time
import struct

import rclpy
from rclpy.node import Node

from std_msgs.msg import Header, Float32MultiArray
from sensor_msgs.msg import PointCloud2, PointField
from leddar_ros2.msg import Specs

METERS_TO_FEET = 3.28084

TIMESTAMPS, DISTANCE, AMPLITUDE = range(3)


def create_pointcloud2(header, points_xyz, intensities=None):
    """
    Create a PointCloud2 message from numpy arrays.
    Replaces the ros_numpy dependency from ROS1.

    Args:
        header: std_msgs/Header
        points_xyz: Nx3 numpy array of (x, y, z)
        intensities: optional N-length numpy array of intensity values
    Returns:
        sensor_msgs/PointCloud2
    """
    msg = PointCloud2()
    msg.header = header

    has_intensity = intensities is not None
    n_points = points_xyz.shape[0]

    fields = [
        PointField(name='x', offset=0, datatype=PointField.FLOAT32, count=1),
        PointField(name='y', offset=4, datatype=PointField.FLOAT32, count=1),
        PointField(name='z', offset=8, datatype=PointField.FLOAT32, count=1),
    ]
    point_step = 12

    if has_intensity:
        fields.append(
            PointField(name='intensity', offset=12, datatype=PointField.FLOAT32, count=1)
        )
        point_step = 16

    msg.fields = fields
    msg.height = 1
    msg.width = n_points
    msg.is_bigendian = False
    msg.point_step = point_step
    msg.row_step = point_step * n_points
    msg.is_dense = True

    # Pack data into bytes
    if has_intensity:
        cloud_data = np.zeros(n_points, dtype=[
            ('x', np.float32), ('y', np.float32), ('z', np.float32),
            ('intensity', np.float32)
        ])
        cloud_data['x'] = points_xyz[:, 0]
        cloud_data['y'] = points_xyz[:, 1]
        cloud_data['z'] = points_xyz[:, 2]
        cloud_data['intensity'] = intensities
    else:
        cloud_data = np.zeros(n_points, dtype=[
            ('x', np.float32), ('y', np.float32), ('z', np.float32)
        ])
        cloud_data['x'] = points_xyz[:, 0]
        cloud_data['y'] = points_xyz[:, 1]
        cloud_data['z'] = points_xyz[:, 2]

    msg.data = cloud_data.tobytes()
    return msg


def create_raw_pointcloud2(header, echo_data):
    """
    Create a PointCloud2 message from raw echo data with all fields.
    Replaces ros_numpy.msgify for the raw echo data.

    Args:
        header: std_msgs/Header
        echo_data: structured numpy array from leddar callback
    Returns:
        sensor_msgs/PointCloud2
    """
    n_points = echo_data.shape[0]

    fields = [
        PointField(name='x', offset=0, datatype=PointField.FLOAT32, count=1),
        PointField(name='y', offset=4, datatype=PointField.FLOAT32, count=1),
        PointField(name='z', offset=8, datatype=PointField.FLOAT32, count=1),
        PointField(name='intensity', offset=12, datatype=PointField.FLOAT32, count=1),
        PointField(name='distance', offset=16, datatype=PointField.FLOAT32, count=1),
    ]
    point_step = 20

    msg = PointCloud2()
    msg.header = header
    msg.fields = fields
    msg.height = 1
    msg.width = n_points
    msg.is_bigendian = False
    msg.point_step = point_step
    msg.row_step = point_step * n_points
    msg.is_dense = True

    cloud_data = np.zeros(n_points, dtype=[
        ('x', np.float32), ('y', np.float32), ('z', np.float32),
        ('intensity', np.float32), ('distance', np.float32)
    ])
    cloud_data['x'] = echo_data['x']
    cloud_data['y'] = echo_data['y']
    cloud_data['z'] = echo_data['z']
    cloud_data['intensity'] = echo_data['amplitudes']
    cloud_data['distance'] = echo_data['distances']

    msg.data = cloud_data.tobytes()
    return msg


class LeddarNode(Node):
    def __init__(self):
        super().__init__('leddar_ros2')

        # Declare parameters (ROS2 equivalent of rospy.get_param)
        self.declare_parameter('frame_id', 'map')
        self.declare_parameter('param1', '')
        self.declare_parameter('device_type', 'not specified')
        self.declare_parameter('param3', '0')
        self.declare_parameter('param4', '0')

        self.frame_id = self.get_parameter('frame_id').get_parameter_value().string_value
        param1 = self.get_parameter('param1').get_parameter_value().string_value
        device_type = self.get_parameter('device_type').get_parameter_value().string_value
        param3 = int(self.get_parameter('param3').get_parameter_value().string_value)
        param4 = int(self.get_parameter('param4').get_parameter_value().string_value)

        # Connect to device
        self.dev = leddar.Device()

        dev_type = 0
        if device_type != 'not specified':
            dev_type = leddar.device_types[device_type]

        if not self.dev.connect(param1, dev_type, param3, param4):
            err_msg = (
                f'Error connecting to device type {device_type} '
                f'with connection info {param1}/{param3}/{param4}.'
            )
            self.get_logger().error(err_msg)
            raise RuntimeError(err_msg)

        # Read sensor specs and publish
        specs = Specs()
        specs.v = int(self.dev.get_property_value('ID_VERTICAL_CHANNEL_NBR'))
        specs.h = int(self.dev.get_property_value('ID_HORIZONTAL_CHANNEL_NBR'))
        specs.v_fov = float(self.dev.get_property_value('ID_VFOV'))
        specs.h_fov = float(self.dev.get_property_value('ID_HFOV'))

        self.pub_specs = self.create_publisher(Specs, 'specs', 10)
        self.pub_cloud = self.create_publisher(PointCloud2, 'scan_cloud', 10)
        self.pub_raw = self.create_publisher(PointCloud2, 'scan_raw', 10)
        self.pub_distances_feet = self.create_publisher(Float32MultiArray, 'distances_feet', 10)

        # Publish specs once
        self.pub_specs.publish(specs)

        # Set up Leddar callback
        self.dev.set_callback_echo(self._echoes_callback)
        self.dev.set_data_thread_delay(1000)
        self.dev.start_data_thread()

        self.get_logger().info(
            f'Leddar device connected: {device_type} ({param1}), '
            f'channels={specs.h}x{specs.v}, FOV={specs.h_fov}x{specs.v_fov}'
        )

    def _echoes_callback(self, echo):
        """Callback from the leddar SDK data thread."""
        # Keep valid echoes only
        echo['data'] = echo['data'][
            np.bitwise_and(echo['data']['flags'], 0x01).astype(bool)
        ]

        data = echo['data']
        indices = data['indices']
        distances = data['distances']
        amplitudes = data['amplitudes']
        x = data['x']
        y = data['y']
        z = data['z']

        stamp = self.get_clock().now().to_msg()
        header = Header()
        header.stamp = stamp
        header.frame_id = self.frame_id

        # Publish raw point cloud (all fields)
        if self.pub_raw.get_subscription_count() > 0:
            raw_msg = create_raw_pointcloud2(header, data)
            self.pub_raw.publish(raw_msg)

        # Publish clean XYZ + intensity cloud
        if self.pub_cloud.get_subscription_count() > 0:
            points_xyz = np.column_stack((x, y, z)).astype(np.float32)
            cloud_msg = create_pointcloud2(header, points_xyz, amplitudes.astype(np.float32))
            self.pub_cloud.publish(cloud_msg)

        # Publish per-channel distances in feet (one value per echo, meters -> feet)
        if self.pub_distances_feet.get_subscription_count() > 0:
            feet_msg = Float32MultiArray()
            feet_msg.data = (distances * METERS_TO_FEET).astype(np.float32).tolist()
            self.pub_distances_feet.publish(feet_msg)

    def destroy_node(self):
        """Clean up the leddar device on shutdown."""
        try:
            self.dev.stop_data_thread()
            self.dev.disconnect()
        except Exception:
            pass
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = LeddarNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()