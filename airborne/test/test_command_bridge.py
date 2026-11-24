"""Unit tests for the MAVLink command bridge."""

import time
from unittest.mock import Mock
import json
import pytest
from airborne_telemetry.command_bridge import (
    CommandBridge,
    CMD_CHECK,
    CMD_START,
    CMD_PAUSE,
    CMD_RESUME,
    CMD_ABORT,
)
from pymavlink import mavutil
from std_srvs.srv import Trigger, SetBool

@pytest.fixture
def bridge():
    node = Mock(spec=CommandBridge)
    node.mission_state = "IDLE"
    node.state_received_at = time.monotonic()
    node.px4_connected = True

    node.is_mission_state_fresh.side_effect = (lambda: CommandBridge.is_mission_state_fresh(node))
    return node

def test_fresh_mission_state(bridge):
    assert CommandBridge.is_mission_state_fresh(bridge) is True

def test_stale_mission_state(bridge):
    bridge.state_received_at = time.monotonic() - 3.0
    assert CommandBridge.is_mission_state_fresh(bridge) is False

def test_missing_mission_state(bridge):
    bridge.mission_state = None
    assert CommandBridge.is_mission_state_fresh(bridge) is False

def test_missing_state_timestamp(bridge):
    bridge.state_received_at = None
    assert CommandBridge.is_mission_state_fresh(bridge) is False

def test_mission_status_format(bridge):
    CommandBridge.send_mission_status(bridge)
    bridge.send_statustext.assert_called_once_with("LIDRON_STATE:IDLE", 6)

def test_stale_status_not_transmitted(bridge):
    bridge.state_received_at = time.monotonic() - 3.0
    CommandBridge.send_mission_status(bridge)
    bridge.send_statustext.assert_not_called()

def test_disconnected_status_not_transmitted(bridge):
    bridge.px4_connected = False
    CommandBridge.send_mission_status(bridge)
    bridge.send_statustext.assert_not_called()

def test_invalid_mission_state(bridge):
    message = Mock()
    message.data = "INVALID_STATE"
    CommandBridge.on_mission_state(bridge, message)

    assert bridge.mission_state is None
    assert bridge.state_received_at is None
    bridge.send_mission_status.assert_not_called()

def test_repeated_mission_state(bridge):
    message = Mock()
    message.data = "IDLE"
    CommandBridge.on_mission_state(bridge, message)

    assert bridge.mission_state == "IDLE"
    bridge.send_mission_status.assert_not_called()

def test_mission_state_change(bridge):
    message = Mock()
    message.data = "COMPLETE"
    CommandBridge.on_mission_state(bridge, message)

    assert bridge.mission_state == "COMPLETE"
    bridge.send_mission_status.assert_called_once()

def test_mission_state_timestamp_updated(bridge):
    bridge.state_received_at = time.monotonic() - 10.0

    message = Mock()
    message.data = "IDLE"
    CommandBridge.on_mission_state(bridge, message)
    assert CommandBridge.is_mission_state_fresh(bridge)

@pytest.fixture
def preflight_bridge(bridge):
    bridge.preflight_result = {
        "success": True,
        "checked_at_s": 100.0
    }
    bridge.preflight_received_at = 51.0
    bridge.preflight_result_count = 1

    bridge.get_clock.return_value.now.return_value.nanoseconds = (105_000_000_000)
    pending = {
        "requested_at_ros": 99.0,
        "requested_at_monotonic": 50.0
    }

    return bridge, pending

def test_valid_preflight(preflight_bridge):
    bridge, pending = preflight_bridge
    assert CommandBridge.is_preflight_valid(bridge, pending)

def test_failed_preflight(preflight_bridge):
    bridge, pending = preflight_bridge
    bridge.preflight_result["success"] = False

    assert not CommandBridge.is_preflight_valid(bridge, pending)

def test_missing_preflight(preflight_bridge):
    bridge, pending = preflight_bridge
    bridge.preflight_result = None

    assert not CommandBridge.is_preflight_valid(bridge, pending)

def test_missing_preflight_timestamp(preflight_bridge):
    bridge, pending = preflight_bridge
    bridge.preflight_received_at = None
    assert not CommandBridge.is_preflight_valid(bridge, pending)

def test_previous_preflight_reception(preflight_bridge):
    bridge, pending = preflight_bridge
    bridge.preflight_received_at = 49.0

    assert not CommandBridge.is_preflight_valid(bridge, pending)

def test_previous_preflight_timestamp(preflight_bridge):
    bridge, pending = preflight_bridge
    bridge.preflight_result["checked_at_s"] = 98.0

    assert not CommandBridge.is_preflight_valid(bridge, pending)

def test_expired_preflight(preflight_bridge):
    bridge, pending = preflight_bridge
    bridge.get_clock.return_value.now.return_value.nanoseconds = (131_000_000_000)
    assert not CommandBridge.is_preflight_valid(bridge, pending)

def test_preflight_at_30_second_limit(preflight_bridge):
    bridge, pending = preflight_bridge
    bridge.get_clock.return_value.now.return_value.nanoseconds = (130_000_000_000)
    assert CommandBridge.is_preflight_valid(bridge, pending)

def test_future_preflight(preflight_bridge):
    bridge, pending = preflight_bridge
    bridge.preflight_result["checked_at_s"] = 106.0
    assert not CommandBridge.is_preflight_valid(bridge, pending)

def test_multiple_preflight_results(preflight_bridge):
    bridge, pending = preflight_bridge
    bridge.preflight_result_count = 2
    assert not CommandBridge.is_preflight_valid(bridge, pending)

def test_invalid_preflight_json(bridge):
    bridge.pending_command = None
    bridge.preflight_result = {"success": True}
    bridge.preflight_received_at = time.monotonic()

    message = Mock()
    message.data = "invalid JSON"

    CommandBridge.on_preflight_result(bridge, message)

    assert bridge.preflight_result is None
    assert bridge.preflight_received_at is None

def test_ack_preserves_command_and_recipient(bridge):
    bridge.connection = Mock()

    CommandBridge.send_ack(bridge, 31010, 0, 254, 190)

    bridge.connection.mav.command_ack_send.assert_called_once_with(
        31010, 0, 0, 0, 254, 190
    )

def test_finish_command_clears_pending(bridge):
    bridge.pending_command = {
        "command_id": 31010,
        "source_system": 254,
        "source_component": 190
    }

    CommandBridge.finish_command(bridge, 0)

    assert bridge.pending_command is None
    bridge.send_ack.assert_called_once_with(31010, 0, 254, 190)

def test_finish_command_without_pending(bridge):
    bridge.pending_command = None
    CommandBridge.finish_command(bridge, 0)
    bridge.send_ack.assert_not_called()

@pytest.fixture
def action_bridge(bridge):
    bridge.pending_command = None
    bridge.command_timeout_s = 5.0

    bridge.enable_client = Mock()
    bridge.enable_client.service_is_ready.return_value = True

    bridge.abort_client = Mock()
    bridge.abort_client.service_is_ready.return_value = True

    return bridge

def test_pause_requests_enable_false(action_bridge):
    CommandBridge.request_mission_action(action_bridge, CMD_PAUSE, 254, 190)
    action_bridge.enable_client.call_async.assert_called_once()
    request = (action_bridge.enable_client.call_async.call_args.args[0])

    assert isinstance(request, SetBool.Request)
    assert request.data is False
    assert action_bridge.pending_command["command_id"] == CMD_PAUSE
    assert action_bridge.pending_command["stage"] == "MISSION_ACTION"
    action_bridge.send_ack.assert_not_called()

def test_resume_requests_enable_true(action_bridge):
    action_bridge.mission_state = "HOLD"

    CommandBridge.request_mission_action(action_bridge, CMD_RESUME, 254, 190)
    action_bridge.enable_client.call_async.assert_called_once()

    request = (action_bridge.enable_client.call_async.call_args.args[0])

    assert isinstance(request, SetBool.Request)
    assert request.data is True
    assert action_bridge.pending_command["command_id"] == CMD_RESUME
    action_bridge.send_ack.assert_not_called()

def test_resume_rejected_outside_hold(action_bridge):
    action_bridge.mission_state = "IDLE"

    CommandBridge.request_mission_action(action_bridge, CMD_RESUME, 254, 190)
    action_bridge.enable_client.call_async.assert_not_called()
    action_bridge.send_ack.assert_called_once_with(
        CMD_RESUME,
        mavutil.mavlink.MAV_RESULT_DENIED,
        254,
        190
    )
    assert action_bridge.pending_command is None

def test_resume_rejected_with_stale_state(action_bridge):
    action_bridge.mission_state = "HOLD"
    action_bridge.state_received_at = time.monotonic() - 3.0

    CommandBridge.request_mission_action(action_bridge, CMD_RESUME, 254, 190)
    action_bridge.enable_client.call_async.assert_not_called()
    action_bridge.send_ack.assert_called_once_with(
        CMD_RESUME,
        mavutil.mavlink.MAV_RESULT_DENIED,
        254,
        190
    )
    assert action_bridge.pending_command is None

def test_abort_requests_trigger(action_bridge):
    CommandBridge.request_mission_action(action_bridge, CMD_ABORT, 254, 190)
    action_bridge.abort_client.call_async.assert_called_once()
    action_bridge.enable_client.call_async.assert_not_called()

    request = (action_bridge.abort_client.call_async.call_args.args[0])

    assert isinstance(request, Trigger.Request)
    assert action_bridge.pending_command["command_id"] == CMD_ABORT
    assert action_bridge.pending_command["stage"] == "MISSION_ACTION"
    action_bridge.send_ack.assert_not_called()

def test_mission_action_rejected_when_busy(action_bridge):
    pending = {"command_id": CMD_PAUSE}
    action_bridge.pending_command = pending
    CommandBridge.request_mission_action(action_bridge, CMD_ABORT, 254, 190)
    action_bridge.abort_client.call_async.assert_not_called()

    action_bridge.send_ack.assert_called_once_with(
        CMD_ABORT,
        mavutil.mavlink.MAV_RESULT_TEMPORARILY_REJECTED,
        254,
        190
    )
    assert action_bridge.pending_command is pending

def test_mission_action_service_unavailable(action_bridge):
    action_bridge.enable_client.service_is_ready.return_value = False
    CommandBridge.request_mission_action(action_bridge, CMD_PAUSE, 254, 190)
    action_bridge.enable_client.call_async.assert_not_called()

    action_bridge.send_ack.assert_called_once_with(
        CMD_PAUSE,
        mavutil.mavlink.MAV_RESULT_FAILED,
        254,
        190
    )
    assert action_bridge.pending_command is None

def test_mission_action_request_exception(action_bridge):
    action_bridge.enable_client.call_async.side_effect = (RuntimeError("Service request failed"))
    CommandBridge.request_mission_action(action_bridge, CMD_PAUSE, 254, 190)

    action_bridge.send_ack.assert_called_once_with(
        CMD_PAUSE,
        mavutil.mavlink.MAV_RESULT_FAILED,
        254,
        190
    )
    assert action_bridge.pending_command is None

def test_service_response_accepted(bridge):
    future = Mock()
    future.done.return_value = True

    response = Mock()
    response.success = True
    response.message = "Operation accepted"

    future.result.return_value = response

    CommandBridge.process_service_response(bridge, future)

    bridge.finish_command.assert_called_once_with(mavutil.mavlink.MAV_RESULT_ACCEPTED)

def test_service_response_denied(bridge):
    future = Mock()
    future.done.return_value = True

    response = Mock()
    response.success = False
    response.message = "Operation denied"

    future.result.return_value = response

    CommandBridge.process_service_response(bridge, future)

    bridge.finish_command.assert_called_once_with(mavutil.mavlink.MAV_RESULT_DENIED)

def test_service_response_exception(bridge):
    future = Mock()
    future.done.return_value = True
    future.result.side_effect = RuntimeError("Response failed")

    CommandBridge.process_service_response(bridge, future)

    bridge.finish_command.assert_called_once_with(mavutil.mavlink.MAV_RESULT_FAILED)

def test_service_response_not_ready(bridge):
    future = Mock()
    future.done.return_value = False

    CommandBridge.process_service_response(bridge, future)

    future.result.assert_not_called()
    bridge.finish_command.assert_not_called()

def test_process_without_pending_command(action_bridge):
    action_bridge.pending_command = None

    CommandBridge.process_pending_command(action_bridge)

    action_bridge.finish_command.assert_not_called()
    action_bridge.send_ack.assert_not_called()

def test_pending_command_timeout(action_bridge):
    future = Mock()
    future.done.return_value = False

    action_bridge.pending_command = {
        "command_id": CMD_CHECK,
        "source_system": 254,
        "source_component": 190,
        "future": future,
        "stage": "PREFLIGHT",
        "deadline": time.monotonic() - 1.0
    }

    CommandBridge.process_pending_command(action_bridge)

    future.cancel.assert_called_once()

    action_bridge.finish_command.assert_called_once_with(mavutil.mavlink.MAV_RESULT_FAILED)

def test_pending_preflight_waits_for_response(action_bridge):
    future = Mock()
    future.done.return_value = False

    action_bridge.pending_command = {
        "command_id": CMD_CHECK,
        "source_system": 254,
        "source_component": 190,
        "future": future,
        "stage": "PREFLIGHT",
        "deadline": time.monotonic() + 5.0
    }

    CommandBridge.process_pending_command(action_bridge)

    future.result.assert_not_called()
    action_bridge.finish_command.assert_not_called()

    assert action_bridge.pending_command["stage"] == "PREFLIGHT"

def test_valid_preflight_message(action_bridge):
    action_bridge.preflight_result_count = 0

    message = Mock()
    message.data = json.dumps({
        "success": True,
        "checked_at_s": 100.0})

    before = time.monotonic()

    CommandBridge.on_preflight_result(action_bridge, message)

    assert action_bridge.preflight_result["success"] is True
    assert action_bridge.preflight_result["checked_at_s"] == 100.0
    assert action_bridge.preflight_received_at >= before

@pytest.mark.parametrize("payload", [
    [],
    None,
    {},
    {"success": "true", "checked_at_s": 100.0},
    {"success": True, "checked_at_s": "100"},
    {"success": True, "checked_at_s": True},
    {"success": True, "checked_at_s": float("nan")},
    {"success": True, "checked_at_s": float("inf")},
])

def test_invalid_preflight_payload(action_bridge, payload):
    action_bridge.preflight_result = {"success": True}
    action_bridge.preflight_received_at = time.monotonic()

    message = Mock()
    message.data = json.dumps(payload)

    CommandBridge.on_preflight_result(action_bridge, message)

    assert action_bridge.preflight_result is None
    assert action_bridge.preflight_received_at is None

def test_preflight_result_count_increment(action_bridge):
    action_bridge.pending_command = {"command_id": CMD_CHECK}
    action_bridge.preflight_result_count = 0

    message = Mock()
    message.data = json.dumps({
        "success": True,
        "checked_at_s": 100.0 })

    CommandBridge.on_preflight_result(action_bridge, message)

    assert action_bridge.preflight_result_count == 1

    CommandBridge.on_preflight_result(action_bridge, message)

    assert action_bridge.preflight_result_count == 2

@pytest.mark.parametrize("success, expected_result, severity", [
    (True,
    mavutil.mavlink.MAV_RESULT_ACCEPTED,
    mavutil.mavlink.MAV_SEVERITY_INFO),
    (False,
    mavutil.mavlink.MAV_RESULT_DENIED,
    mavutil.mavlink.MAV_SEVERITY_WARNING),
])

def test_check_service_response(action_bridge, success, expected_result, severity):
    future = Mock()
    future.done.return_value = True

    response = Mock()
    response.success = success
    response.message = "Preflight test result"

    future.result.return_value = response

    action_bridge.pending_command = {
        "command_id": CMD_CHECK,
        "source_system": 254,
        "source_component": 190,
        "future": future,
        "stage": "PREFLIGHT",
        "deadline": time.monotonic() + 5.0
    }

    CommandBridge.process_pending_command(action_bridge)
    action_bridge.send_statustext.assert_called_once_with("LIDRON_CHECK:Preflight test result", severity)
    action_bridge.finish_command.assert_called_once_with(expected_result)
    action_bridge.enable_client.call_async.assert_not_called()

@pytest.mark.parametrize("command_id", [CMD_CHECK, CMD_START])

def test_request_preflight_creates_pending(action_bridge, command_id):
    action_bridge.preflight_client = Mock()
    action_bridge.preflight_client.service_is_ready.return_value = True

    action_bridge.get_clock.return_value.now.return_value.nanoseconds = (100_000_000_000)

    action_bridge.preflight_result = {"success": True}
    action_bridge.preflight_received_at = time.monotonic()
    action_bridge.preflight_result_count = 1

    CommandBridge.request_preflight(action_bridge, command_id, 254, 190)

    pending = action_bridge.pending_command

    assert pending["command_id"] == command_id
    assert pending["stage"] == "PREFLIGHT"
    assert pending["source_system"] == 254
    assert pending["source_component"] == 190
    assert pending["requested_at_ros"] == 100.0

    assert action_bridge.preflight_result is None
    assert action_bridge.preflight_received_at is None
    assert action_bridge.preflight_result_count == 0

    action_bridge.preflight_client.call_async.assert_called_once()
    action_bridge.send_ack.assert_not_called()

@pytest.mark.parametrize("command_id", [CMD_CHECK, CMD_START])

def test_preflight_service_unavailable(action_bridge, command_id):
    action_bridge.preflight_client = Mock()
    action_bridge.preflight_client.service_is_ready.return_value = False

    CommandBridge.request_preflight(action_bridge, command_id, 254, 190)

    action_bridge.preflight_client.call_async.assert_not_called()

    action_bridge.send_ack.assert_called_once_with(
        command_id,
        mavutil.mavlink.MAV_RESULT_FAILED,
        254,
        190
    )

    assert action_bridge.pending_command is None