import os
import json
import time
import math

os.environ["MAVLINK20"] = "1"

import rclpy
from rclpy.node import Node
from rclpy.clock import Clock, ClockType
from std_srvs.srv import Trigger, SetBool
from interfaces.srv import StartMission
from std_msgs.msg import String
from pymavlink import mavutil

# LiDRON autonomy MAVLink command IDs
CMD_CHECK = mavutil.mavlink.MAV_CMD_USER_1
CMD_START = mavutil.mavlink.MAV_CMD_USER_2
CMD_PAUSE = mavutil.mavlink.MAV_CMD_USER_3
CMD_RESUME = mavutil.mavlink.MAV_CMD_USER_4
CMD_ABORT = mavutil.mavlink.MAV_CMD_USER_5

COMMAND_NAMES = {
    CMD_CHECK: "Check",
    CMD_START: "Start",
    CMD_PAUSE: "Pause",
    CMD_RESUME: "Resume",
    CMD_ABORT: "Abort",
}

VALID_MISSION_STATES = {
    "IDLE",
    "PREFLIGHT",
    "TAKEOFF",
    "PLANNING",
    "NAVIGATING",
    "REPLANNING",
    "APPROACH",
    "LANDING_CHECK",
    "LANDING",
    "COMPLETE",
    "HOLD",
    "ABORT",
    "PILOT_OVERRIDE",
}

START_ALLOWED_STATES = {
    "IDLE",
    "COMPLETE",
    "ABORT"
}

class CommandBridge(Node):

    def __init__(self):
        super().__init__("mavlink_command_bridge")

        # MAVLink connection parameters
        self.declare_parameter("mavlink_endpoint", "udpin:0.0.0.0:14540")
        self.declare_parameter("system_id", 1)
        self.declare_parameter("component_id", 192)

        endpoint = self.get_parameter("mavlink_endpoint").value
        self.system_id = self.get_parameter("system_id").value
        self.component_id = self.get_parameter("component_id").value

        self.connection = mavutil.mavlink_connection(endpoint, source_system=self.system_id,
                                                    source_component=self.component_id)
        self.get_logger().info(f"MAVLink connection opened: {endpoint}")

        self.get_logger().info("MAVLink Command Bridge initialized")

        self.px4_connected = False

        # ROS 2 autonomy service clients
        self.preflight_client = self.create_client(Trigger, "/autonomy/preflight_check")
        self.prepare_start_client = self.create_client(Trigger, "/autonomy/prepare_start")
        self.start_client = self.create_client(StartMission, "/autonomy/start")
        self.enable_client = self.create_client(SetBool, "/autonomy/enable")
        self.resume_client = self.create_client(Trigger, "/autonomy/resume")
        self.abort_client = self.create_client(Trigger, "/autonomy/abort")

        # Autonomy state and preflight tracking
        self.preflight_result = None
        self.preflight_received_at = None
        self.preflight_result_count = 0
        self.mission_state = None
        self.state_received_at = None

        # Pending autonomy command
        self.pending_command = None
        self.command_timeout_s = 5.0

        # STATUSTEXT message tracking
        self.statustext_id = 0

        # ROS 2 autonomy subscribers
        self.preflight_subscription = self.create_subscription(
            String,
            "/autonomy/preflight_result",
            self.on_preflight_result,
            10
        )
        self.state_subscription = self.create_subscription(
            String,
            "/autonomy/state",
            self.on_mission_state,
            10
        )

        # Independent clock for communication and timeouts
        self.steady_clock = Clock(clock_type=ClockType.STEADY_TIME)

        # MAVLink timers
        self.receive_timer = self.create_timer(
            0.01,
            self.receive_messages,
            clock=self.steady_clock
        )
        self.heartbeat_timer = self.create_timer(
            1.0,
            self.send_heartbeat,
            clock=self.steady_clock
        )

        # Pending command processing timer
        self.command_timer = self.create_timer(
            0.05,
            self.process_pending_command,
            clock=self.steady_clock
        )

    def on_preflight_result(self, message):

        if self.pending_command is not None:
            self.preflight_result_count += 1

        try:
            result = json.loads(message.data)

            if not isinstance(result, dict):
                raise ValueError("Invalid preflight result")

            success = result["success"]
            checked_at = result["checked_at_s"]

            if not isinstance(success, bool):
                raise ValueError("Invalid success value")

            if (
                isinstance(checked_at, bool)
                or not isinstance(checked_at, (int, float))
                or not math.isfinite(checked_at)
            ):
                raise ValueError("Invalid preflight timestamp")

            self.preflight_result = result
            self.preflight_received_at = time.monotonic()

            self.get_logger().info(f"Preflight result received {result}")

        except (ValueError, KeyError, TypeError, OverflowError) as error:
            self.preflight_result = None
            self.preflight_received_at = None

            self.get_logger().warning(f"Invalid preflight result: {error}")

    def on_mission_state(self, message):
        state = message.data.strip()

        if state not in VALID_MISSION_STATES:
            self.mission_state = None
            self.state_received_at = None

            self.get_logger().warning(f"Invalid mission state: {state}")

            return

        previous_state = self.mission_state

        self.mission_state = state
        self.state_received_at = time.monotonic()

        if previous_state != state:
            self.get_logger().info(f"Mission state changed: {previous_state} -> {state}")
            self.send_mission_status()

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

            elif message.get_type() == "COMMAND_LONG":
                self.handle_command(message)

    def handle_command(self, message):

        # Ignore commands addressed to other components
        if (
            message.target_system != self.system_id
            or message.target_component != self.component_id
        ):
            return

        command_id = message.command
        command_name = COMMAND_NAMES.get(command_id, "Unknown")

        source_system = message.get_srcSystem()
        source_component = message.get_srcComponent()

        self.get_logger().info(
            f"Command received: {command_name} "
            f"(ID: {command_id}) from "
            f"system {source_system}, "
            f"component {source_component}"
        )

        if command_id == CMD_CHECK:
            self.request_preflight(
                command_id,
                source_system,
                source_component
            )

        elif command_id == CMD_START:
            self.request_start_authorization(
                command_id,
                source_system,
                source_component
            )

        elif command_id in (CMD_PAUSE, CMD_RESUME, CMD_ABORT):
            self.request_mission_action(
                command_id,
                source_system,
                source_component
            )

        else:
            self.send_ack(
                command_id,
                mavutil.mavlink.MAV_RESULT_UNSUPPORTED,
                source_system,
                source_component
            )

    def request_mission_action(self, command_id, source_system, source_component):

        # Abort has priority over other pending commands
        if self.pending_command is not None:
            if (
                command_id != CMD_ABORT
                or self.pending_command["command_id"] == CMD_ABORT
            ):
                self.send_ack(
                    command_id,
                    mavutil.mavlink.MAV_RESULT_TEMPORARILY_REJECTED,
                    source_system,
                    source_component
                )
                return

            interrupted = self.pending_command
            future = interrupted["future"]

            self.get_logger().warning(
                f"Abort interrupted {COMMAND_NAMES[interrupted['command_id']]}"
            )

            if not future.done():
                future.cancel()

            self.send_statustext(
                f"LIDRON_{COMMAND_NAMES[interrupted['command_id']].upper()}:Interrupted by Abort",
                mavutil.mavlink.MAV_SEVERITY_WARNING
            )

            self.finish_command(
                mavutil.mavlink.MAV_RESULT_FAILED
            )

            self.preflight_result = None
            self.preflight_received_at = None
            self.preflight_result_count = 0

        # Resume must not start a new mission
        if command_id == CMD_RESUME:
            if (
                not self.is_mission_state_fresh()
                or self.mission_state != "HOLD"
            ):

                self.get_logger().warning("Resume requires a fresh HOLD state")
                self.send_ack(
                    command_id,
                    mavutil.mavlink.MAV_RESULT_DENIED,
                    source_system,
                    source_component
                )
                return

        # Select the appropriate autonomy service
        if command_id == CMD_ABORT:
            client = self.abort_client
            request = Trigger.Request()

        elif command_id == CMD_RESUME:
            client = self.resume_client
            request = Trigger.Request()

        else:
            client = self.enable_client
            request = SetBool.Request()
            request.data = False

        # Verify service availability
        if not client.service_is_ready():
            self.get_logger().warning("Autonomy service unavailable")
            if command_id == CMD_ABORT:
                self.send_statustext(
                    "LIDRON_ABORT:Service unavailable; not confirmed",
                    mavutil.mavlink.MAV_SEVERITY_WARNING
                )
            self.send_ack(
                command_id,
                mavutil.mavlink.MAV_RESULT_FAILED,
                source_system,
                source_component
            )
            return

        # Send asynchronous service request
        try:
            future = client.call_async(request)

        except Exception as error:
            self.get_logger().error(f"Mission action request failed: {error}")
            if command_id == CMD_ABORT:
                self.send_statustext(
                    "LIDRON_ABORT:Request failed; not confirmed",
                    mavutil.mavlink.MAV_SEVERITY_WARNING
                )
            self.send_ack(
                command_id,
                mavutil.mavlink.MAV_RESULT_FAILED,
                source_system,
                source_component
            )
            return

        self.pending_command = {
            "command_id": command_id,
            "source_system": source_system,
            "source_component": source_component,
            "future": future,
            "stage": "MISSION_ACTION",
            "deadline": time.monotonic() + self.command_timeout_s
        }

        self.get_logger().info(f"{COMMAND_NAMES[command_id]} requested")

    def request_start_authorization(self, command_id, source_system, source_component):

        if self.pending_command is not None:
            self.send_ack(
                command_id,
                mavutil.mavlink.MAV_RESULT_TEMPORARILY_REJECTED,
                source_system,
                source_component
            )
            return

        if not self.prepare_start_client.service_is_ready():
            self.get_logger().warning("Prepare Start service unavailable")
            self.send_ack(
                command_id,
                mavutil.mavlink.MAV_RESULT_FAILED,
                source_system,
                source_component
            )
            return

        try:
            future = self.prepare_start_client.call_async(
                Trigger.Request()
            )

        except Exception as error:
            self.get_logger().error(f"Prepare Start request error: {error}")
            self.send_ack(
                command_id,
                mavutil.mavlink.MAV_RESULT_FAILED,
                source_system,
                source_component
            )
            return

        self.pending_command = {
            "command_id": command_id,
            "source_system": source_system,
            "source_component": source_component,
            "future": future,
            "stage": "PREPARE_START",
            "deadline": time.monotonic() + self.command_timeout_s
        }

        self.get_logger().info("Start authorization requested")

    def request_preflight(self, command_id, source_system, source_component):

        if self.pending_command is not None:
            self.send_ack(
                command_id,
                mavutil.mavlink.MAV_RESULT_TEMPORARILY_REJECTED,
                source_system,
                source_component
            )
            return

        if not self.preflight_client.service_is_ready():
            self.get_logger().warning("Preflight service unavailable")
            self.send_ack(
                command_id,
                mavutil.mavlink.MAV_RESULT_FAILED,
                source_system,
                source_component
            )
            return

        # Clear previous preflight results
        self.preflight_result = None
        self.preflight_received_at = None
        self.preflight_result_count = 0

        # Record request timestamps
        requested_at_ros = self.get_clock().now().nanoseconds / 1e9
        requested_at_monotonic = time.monotonic()

        try:
            request = Trigger.Request()
            future = self.preflight_client.call_async(request)

        except Exception as error:
            self.get_logger().error(f"Preflight request error: {error}")
            self.send_ack(
                command_id,
                mavutil.mavlink.MAV_RESULT_FAILED,
                source_system,
                source_component
            )
            return

        self.pending_command = {
            "command_id": command_id,
            "source_system": source_system,
            "source_component": source_component,
            "future": future,
            "stage": "PREFLIGHT",
            "requested_at_ros": requested_at_ros,
            "requested_at_monotonic": requested_at_monotonic,
            "deadline": time.monotonic() + self.command_timeout_s
        }

        self.get_logger().info("Preflight check requested")

    def is_mission_state_fresh(self):

        if self.mission_state is None:
            return False

        if self.state_received_at is None:
            return False

        age = time.monotonic() - self.state_received_at

        return 0.0 <= age <= 2.0

    def is_preflight_valid(self, pending):

        if self.preflight_result is None:
            return False

        if self.preflight_received_at is None:
            return False

        if self.preflight_result["success"] is not True:
            return False

        if self.preflight_received_at < pending["requested_at_monotonic"]:
            return False

        checked_at = self.preflight_result["checked_at_s"]
        requested_at = pending["requested_at_ros"]

        now = self.get_clock().now().nanoseconds / 1e9

        if now <= 0 or requested_at <= 0:
            return False

        if checked_at < requested_at:
            return False

        age = now - checked_at

        if not 0.0 <= age <= 30.0:
            return False

        if self.preflight_result_count != 1:
            return False

        return True

    def process_service_response(self, future):
        if not future.done():
            return

        try:
            response = future.result()

            self.get_logger().info(
                f"Service response: success={response.success}, "
                f"message={response.message}"
            )
            result = (
                mavutil.mavlink.MAV_RESULT_ACCEPTED
                if response.success
                else mavutil.mavlink.MAV_RESULT_DENIED
            )

            if not response.success and self.pending_command is not None:
                command_id = self.pending_command["command_id"]

                if command_id in (CMD_START, CMD_ABORT):
                    name = COMMAND_NAMES[command_id].upper()
                    self.send_statustext(
                        f"LIDRON_{name}:{response.message}",
                        mavutil.mavlink.MAV_SEVERITY_WARNING
                    )

        except Exception as exc:
            self.get_logger().error(f"Service request failed: {exc}")
            if self.pending_command is not None:
                command_id = self.pending_command["command_id"]

                if command_id in (CMD_START, CMD_ABORT):
                    name = COMMAND_NAMES[command_id].upper()
                    self.send_statustext(
                        f"LIDRON_{name}:Outcome not confirmed",
                        mavutil.mavlink.MAV_SEVERITY_WARNING
                    )
            result = mavutil.mavlink.MAV_RESULT_FAILED

        self.finish_command(result)


    def finish_command(self, result):

        if self.pending_command is None:
            return

        pending = self.pending_command

        self.pending_command = None

        self.send_ack(
            pending["command_id"],
            result,
            pending["source_system"],
            pending["source_component"]
        )

    def process_pending_command(self):

        if self.pending_command is None:
            return

        pending = self.pending_command
        future = pending["future"]

        # Handle command timeout
        if time.monotonic() >= pending["deadline"]:

            if not future.done():
                future.cancel()

            self.get_logger().warning(f"Command timed out during {pending['stage']}")
            if pending["command_id"] == CMD_ABORT:
                self.send_statustext(
                    "LIDRON_ABORT:Timeout; not confirmed",
                    mavutil.mavlink.MAV_SEVERITY_WARNING
                )
            elif pending["command_id"] == CMD_START:
                self.send_statustext(
                    "LIDRON_START:Timeout; outcome not confirmed",
                    mavutil.mavlink.MAV_SEVERITY_WARNING
                )
            self.finish_command(mavutil.mavlink.MAV_RESULT_FAILED)
            return

        # Process Start authorization response
        if pending["stage"] == "PREPARE_START":

            if not future.done():
                return

            try:
                response = future.result()

                if not response.success:
                    self.send_statustext(
                        f"LIDRON_START:{response.message}",
                        mavutil.mavlink.MAV_SEVERITY_WARNING
                    )
                    self.finish_command(
                        mavutil.mavlink.MAV_RESULT_DENIED
                    )
                    return

                token = response.message

                if (
                    not isinstance(token, str)
                    or len(token) != 32
                    or any(c not in "0123456789abcdef" for c in token)
                ):
                    self.get_logger().warning(
                        "Invalid Start authorization token"
                    )
                    self.finish_command(
                        mavutil.mavlink.MAV_RESULT_FAILED
                    )
                    return

                if not self.preflight_client.service_is_ready():
                    self.get_logger().warning(
                        "Preflight service unavailable"
                    )
                    self.finish_command(
                        mavutil.mavlink.MAV_RESULT_FAILED
                    )
                    return

                # Clear previous preflight results
                self.preflight_result = None
                self.preflight_received_at = None
                self.preflight_result_count = 0

                pending["authorization_token"] = token
                pending["requested_at_ros"] = (
                    self.get_clock().now().nanoseconds / 1e9
                )
                pending["requested_at_monotonic"] = time.monotonic()

                pending["future"] = self.preflight_client.call_async(
                    Trigger.Request()
                )
                pending["stage"] = "PREFLIGHT"
                pending["deadline"] = (
                    time.monotonic() + self.command_timeout_s
                )

                self.get_logger().info(
                    "Start authorized; preflight requested"
                )

            except Exception as error:
                self.get_logger().error(
                    f"Start authorization error: {error}"
                )
                self.finish_command(
                    mavutil.mavlink.MAV_RESULT_FAILED
                )

            return

        # Process preflight service response
        if pending["stage"] == "PREFLIGHT":

            if not future.done():
                return

            try:
                response = future.result()

                self.get_logger().info(
                    f"Preflight response: success={response.success}, "
                    f"message={response.message}"
                )

                # Handle Check command
                if pending["command_id"] == CMD_CHECK:

                    if response.success:
                        result = mavutil.mavlink.MAV_RESULT_ACCEPTED
                        severity = mavutil.mavlink.MAV_SEVERITY_INFO
                    else:
                        result = mavutil.mavlink.MAV_RESULT_DENIED
                        severity = mavutil.mavlink.MAV_SEVERITY_WARNING

                    self.send_statustext(
                        f"LIDRON_CHECK:{response.message}",
                        severity
                    )
                    self.finish_command(result)
                    return

                # Handle failed Start preflight
                if not response.success:

                    self.send_statustext(
                        f"LIDRON_START:{response.message}",
                        mavutil.mavlink.MAV_SEVERITY_WARNING
                    )
                    self.finish_command(mavutil.mavlink.MAV_RESULT_DENIED)
                    return

                # Wait for the corresponding preflight result
                pending["stage"] = "WAIT_PREFLIGHT_RESULT"
                self.get_logger().info("Waiting for preflight result validation")

            except Exception as error:
                self.get_logger().error(f"Preflight service error: {error}")
                self.finish_command(mavutil.mavlink.MAV_RESULT_FAILED)

        # Validate the published preflight result
        elif pending["stage"] == "WAIT_PREFLIGHT_RESULT":

            # Wait until a result is received
            if self.preflight_result_count == 0:
                return

            # Reject ambiguous preflight results
            if self.preflight_result_count > 1:
                self.get_logger().warning("Multiple preflight results received")
                self.finish_command(mavutil.mavlink.MAV_RESULT_DENIED)
                return

            # Validate the preflight result
            if not self.is_preflight_valid(pending):
                self.get_logger().warning("Preflight result is invalid or expired")
                self.finish_command(mavutil.mavlink.MAV_RESULT_DENIED)
                return

            self.get_logger().info("Preflight result successfully validated")
            pending["stage"] = "READY_TO_START"

        # Final validation before enabling autonomy
        elif pending["stage"] == "READY_TO_START":

            # Verify that mission state is current
            if not self.is_mission_state_fresh():
                self.get_logger().warning("Mission state is unavailable or stale")
                self.finish_command(mavutil.mavlink.MAV_RESULT_DENIED)
                return

            # Verify that Start is allowed
            if self.mission_state not in START_ALLOWED_STATES:

                self.get_logger().warning(f"Start not allowed in state {self.mission_state}")
                self.finish_command(mavutil.mavlink.MAV_RESULT_DENIED)
                return

            # Revalidate preflight before enabling
            if not self.is_preflight_valid(pending):
                self.get_logger().warning("Preflight validation is no longer valid")
                self.finish_command(mavutil.mavlink.MAV_RESULT_DENIED)
                return

            # Verify Start service availability
            if not self.start_client.service_is_ready():
                self.get_logger().warning("Start service unavailable")
                self.finish_command(mavutil.mavlink.MAV_RESULT_FAILED)
                return

            token = pending.get("authorization_token")

            if not token:
                self.send_statustext(
                    "LIDRON_START:Missing Start authorization",
                    mavutil.mavlink.MAV_SEVERITY_WARNING
                )
                self.finish_command(mavutil.mavlink.MAV_RESULT_DENIED)
                return

            # Request explicit mission activation
            try:
                request = StartMission.Request()
                request.authorization_token = token

                pending["future"] = self.start_client.call_async(request)
                pending["stage"] = "START"
                pending["deadline"] = (
                    time.monotonic() + self.command_timeout_s
                )
                self.get_logger().info("Authorized Start requested")

            except Exception as error:
                self.get_logger().error(f"Start request error: {error}")
                self.finish_command(mavutil.mavlink.MAV_RESULT_FAILED)

        # Process autonomy service responses
        elif pending["stage"] in ("START", "MISSION_ACTION"):
            self.process_service_response(future)

    def send_statustext(self, text, severity):
        payload = text.encode("utf-8")

        if len(payload) < 50:
            self.connection.mav.statustext_send(
                severity,
                payload,
                0,
                0
            )
            return

        self.statustext_id = (self.statustext_id % 65535) + 1

        payload += b"\x00"

        for chunk_seq, offset in enumerate(range(0, len(payload), 50)):
            chunk = payload[offset:offset + 50]
            self.connection.mav.statustext_send(
                severity,
                chunk,
                self.statustext_id,
                chunk_seq
            )

    def send_ack(self, command_id, result, source_system, source_component):
        self.connection.mav.command_ack_send(
            command_id,
            result,
            0,
            0,
            source_system,
            source_component
        )
        self.get_logger().info(
            f"COMMAND_ACK sent: command={command_id}, "
            f"result={result}, "
            f"target={source_system}/{source_component}"
        )

    def send_mission_status(self):

        if not self.px4_connected:
            return

        if not self.is_mission_state_fresh():
            return

        self.send_statustext(
            f"LIDRON_STATE:{self.mission_state}",
            mavutil.mavlink.MAV_SEVERITY_INFO
        )

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

        self.send_mission_status()

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