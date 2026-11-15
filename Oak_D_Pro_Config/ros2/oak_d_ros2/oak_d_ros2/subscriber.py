"""Example algorithm input: scalar distances grouped by camera frame."""

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node

from oak_d_interfaces.msg import ObjectDistanceArray


class DistanceSubscriber(Node):
    def __init__(self):
        super().__init__('oak_distance_subscriber')
        self.subscription = self.create_subscription(
            ObjectDistanceArray, '/oak/object_distances', self.on_objects, 10)

    def on_objects(self, message):
        for obj in message.objects:
            distance = f'{obj.distance_m:.2f} m' if obj.distance_valid else 'unavailable'
            self.get_logger().info(f'{obj.class_id}: {distance}')


def main(args=None):
    rclpy.init(args=args)
    node = DistanceSubscriber()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
