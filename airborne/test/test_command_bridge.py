"""Unit tests for the MAVLink command bridge."""

import time
from unittest.mock import Mock 
import pytest
from airborne_telemetry.command_bridge import CommandBridge

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