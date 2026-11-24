import os

os.environ["MAVLINK20"] = "1"

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger, SetBool
from std_msgs.msg import String
from pymavlink import mavutil

class CommandBridge(Node):

    def __init__(self):
        super().__init__("mavlink_command_bridge")

        # MAVLink connection parameters
        self.declare_parameter("mavlink_endpoint", "udpin:0.0.0.0:14540")
        self.declare_parameter("system_id", 1)
        self.declare_parameter("component_id", 192)

        endpoint = self.get_parameter("mavlink_endpoint").value
        self.system_id = self.get_parameter("system_id").value
        component_id = self.get_parameter("component_id").value

        self.connection = mavutil.mavlink_connection(endpoint, source_system=self.system_id,
                                                    source_component=component_id)
        self.get_logger().info(f"MAVLink connection opened: {endpoint}")

        self.get_logger().info("MAVLink Command Bridge initialized")

        self.px4_connected = False

        #MAVLink timers
        self.receive_timer = self.create_timer(0.01, self.receive_messages)
        self.heartbeat_timer = self.create_timer(1.0, self.send_heartbeat)

    def receive_messages(self):
        for _ in range(100):
            message = self.connection.recv_match(blocking=False)

            if message is None:
                break

            if message.get_type() == "HEARTBEAT":
                if (
                    message.get_srcSystem() == self.system_id
                    and message.get_srcComponent() == 1
                ):

                    if not self.px4_connected:
                        self.px4_connected = True
                        self.get_logger().info("PX4 heartbeat received")

    def send_heartbeat(self):
        if not self.px4_connected:
            return

        self.connection.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
            mavutil.mavlink.MAV_AUTOPILOT_INVALID,
            0,
            0,
            mavutil.mavlink.MAV_STATE_ACTIVE
        )

def main(args=None):
    rclpy.init(args=args)
    node = CommandBridge()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.connection.close()
        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()

if __name__ == "__main__":
    main()