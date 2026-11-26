"""Isolated MAVLink timeout notification tests."""

import io

from pymavlink.dialects.v20 import ardupilotmega as mavlink
from airborne_telemetry.command_bridge import CommandBridge


def test_timeout_warning_mavlink_encoding():
    """Verify that the timeout warning survives MAVLink encoding."""

    buffer = io.BytesIO()
    encoder = mavlink.MAVLink(buffer)

    class TestConnection:
        mav = encoder

    class TestBridge:
        connection = TestConnection()
        statustext_id = 0

    expected = "LIDRON_START:Timeout; outcome not confirmed"

    CommandBridge.send_statustext(
        TestBridge(),
        expected,
        mavlink.MAV_SEVERITY_WARNING,
    )

    decoder = mavlink.MAVLink(None)
    messages = decoder.parse_buffer(buffer.getvalue())

    assert messages
    assert len(messages) == 1

    message = messages[0]

    assert message.get_type() == "STATUSTEXT"
    assert message.severity == mavlink.MAV_SEVERITY_WARNING
    assert message.text == expected


def test_mission_state_mavlink_encoding():
    """Verify MAVLink encoding of a synthetic state notification."""

    buffer = io.BytesIO()
    encoder = mavlink.MAVLink(buffer)

    class TestConnection:
        mav = encoder

    class TestBridge:
        connection = TestConnection()
        statustext_id = 0

    expected = "LIDRON_STATE:IDLE"

    CommandBridge.send_statustext(
        TestBridge(),
        expected,
        mavlink.MAV_SEVERITY_INFO,
    )

    decoder = mavlink.MAVLink(None)
    messages = decoder.parse_buffer(buffer.getvalue())

    assert len(messages) == 1
    assert messages[0].get_type() == "STATUSTEXT"
    assert messages[0].severity == mavlink.MAV_SEVERITY_INFO
    assert messages[0].text == expected
