"""Exercise generic telemetry, typed GPS, and unchanged UDP forwarding."""

import json
import math
import socket
import time
from unittest.mock import Mock

import pytest
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from sensor_msgs.msg import NavSatFix
from std_msgs.msg import Bool, String, UInt8, UInt8MultiArray
from pymavlink.dialects.v10 import ardupilotmega as v1
from pymavlink.dialects.v20 import ardupilotmega as v2

from airborne_telemetry.node import AirborneBridge, json_value


def udp_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.setblocking(False)
    return sock


def free_port():
    sock = udp_socket()
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.fixture
def bridge():
    rclpy.init()
    input_port = free_port()
    radio = udp_socket()
    node = AirborneBridge(parameter_overrides=[
        Parameter("pixhawk", value=f"udpin:127.0.0.1:{input_port}"),
        Parameter("radio", value=f"udpout:127.0.0.1:{radio.getsockname()[1]}"),
        Parameter("skip_stream_request", value=True),
        Parameter("gps_timeout", value=0.25),
        Parameter("reconnect_delay", value=0.1),
    ])
    observer = Node("telemetry_test_observer")
    received = {
        "fix": [], "fix_type": [], "rtk_fixed": [], "fresh": [],
        "telemetry": [], "raw": [],
    }
    subscriptions = []
    for name, msg_type in (("fix", NavSatFix), ("fix_type", UInt8),
                           ("rtk_fixed", Bool), ("fresh", Bool),
                           ("telemetry", String), ("raw", UInt8MultiArray)):
        topic = f"gps/{name}" if name not in ("telemetry", "raw") else {
            "telemetry": "telemetry/mavlink",
            "raw": "telemetry/mavlink_raw",
        }[name]
        subscriptions.append(observer.create_subscription(
            msg_type, topic, lambda msg, key=name: received[key].append(msg), 10
        ))
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    executor.add_node(observer)
    sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def spin_until(condition, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=0.01)
            if condition():
                return
        raise AssertionError("Timed out waiting for telemetry")

    spin_until(lambda: node.fix_pub.get_subscription_count() > 0
               and node.type_pub.get_subscription_count() > 0
               and node.rtk_pub.get_subscription_count() > 0
               and node.fresh_pub.get_subscription_count() > 0
               and node.telemetry_pub.get_subscription_count() > 0
               and node.raw_pub.get_subscription_count() > 0
               and node.connections["pixhawk"] is not None)
    try:
        yield node, received, radio, lambda frame: sender.sendto(frame, ("127.0.0.1", input_port)), spin_until
    finally:
        executor.shutdown()
        observer.destroy_node()
        node.destroy_node()
        sender.close()
        radio.close()
        rclpy.shutdown()


def gps_frame(dialect, fix=6, system=1):
    encoder = dialect.MAVLink(None, srcSystem=system, srcComponent=1)
    return dialect.MAVLink_gps_raw_int_message(
        1000000, fix, 182345678, -661234567, 100000, 80, 120, 0, 0, 18
    ).pack(encoder)


@pytest.mark.parametrize("dialect", [v1, v2])
def test_original_packets_reach_radio_generic_ros_and_typed_gps(bridge, dialect):
    node, received, radio, send, spin_until = bridge
    encoder = dialect.MAVLink(None, srcSystem=1, srcComponent=1)
    if dialect is v2:
        encoder.signing.secret_key = bytes(range(32))
        encoder.signing.sign_outgoing = True
        encoder.signing.timestamp = 100000
    heartbeat = dialect.MAVLink_heartbeat_message(2, 3, 0, 0, 4, 3).pack(encoder)
    gps = gps_frame(dialect)
    send(heartbeat)
    send(gps)
    packets = []

    def complete():
        try:
            while True:
                packets.append(radio.recv(65535))
        except BlockingIOError:
            pass
        return (heartbeat in packets and gps in packets
                and len(received["telemetry"]) >= 2
                and len(received["raw"]) >= 2
                and any(msg.data == 6 for msg in received["fix_type"]))

    spin_until(complete)
    spin_until(lambda: any(msg.data for msg in received["rtk_fixed"]))
    decoded = [json.loads(message.data) for message in received["telemetry"]]
    assert {item["message"]["mavpackettype"] for item in decoded} >= {
        "HEARTBEAT", "GPS_RAW_INT"}
    assert all(item["system_id"] == 1 and item["component_id"] == 1
               for item in decoded)
    raw_frames = [bytes(message.data) for message in received["raw"]]
    assert heartbeat in raw_frames and gps in raw_frames
    fixes = [msg for msg in received["fix"] if msg.status.status == 2]
    assert fixes[-1].latitude == pytest.approx(18.2345678)
    assert fixes[-1].longitude == pytest.approx(-66.1234567)


def test_groundspeed_is_available_in_generic_vfr_hud_json(bridge):
    node, received, radio, send, spin_until = bridge
    encoder = v2.MAVLink(None, srcSystem=1, srcComponent=1)
    frame = v2.MAVLink_vfr_hud_message(
        13.0, 12.5, 270, 55, 120.0, -0.25).pack(encoder)
    send(frame)

    def received_vfr_hud():
        return any(json.loads(message.data)["message"]["mavpackettype"] == "VFR_HUD"
                   for message in received["telemetry"])

    spin_until(received_vfr_hud)
    payload = next(json.loads(message.data) for message in received["telemetry"]
                   if json.loads(message.data)["message"]["mavpackettype"] == "VFR_HUD")
    assert payload["message"]["groundspeed"] == pytest.approx(12.5)
    spin_until(lambda: node.forwarded == 1)
    assert radio.recv(65535) == frame


def test_rtk_changes_source_filter_and_stale_data(bridge):
    node, received, radio, send, spin_until = bridge
    for quality in (5, 6, 3, 1):
        received["fix_type"].clear()
        received["rtk_fixed"].clear()
        send(gps_frame(v2, quality))
        spin_until(lambda: any(msg.data == quality for msg in received["fix_type"]))
        spin_until(lambda: bool(received["rtk_fixed"]))
        assert received["rtk_fixed"][-1].data == (quality == 6)
    received["fix_type"].clear()
    send(gps_frame(v2, 6, system=2))
    spin_until(lambda: received["fresh"] and not received["fresh"][-1].data)
    assert not any(msg.data == 6 for msg in received["fix_type"])
    assert received["fix_type"][-1].data == 0
    send(gps_frame(v2, 6))
    spin_until(lambda: any(msg.data == 6 for msg in received["fix_type"]))


def test_radio_failure_does_not_stop_ros_and_recovers(bridge):
    node, received, radio, send, spin_until = bridge

    class BrokenRadio:
        def write(self, frame):
            raise OSError("radio unplugged")

        def close(self):
            pass

    node.close_link("radio")
    node.connections["radio"] = BrokenRadio()
    send(gps_frame(v1))
    spin_until(lambda: any(msg.data == 6 for msg in received["fix_type"])
               and bool(received["telemetry"]) and bool(received["raw"]))
    assert json.loads(received["telemetry"][-1].data)["message"]["mavpackettype"] == "GPS_RAW_INT"
    assert bytes(received["raw"][-1].data) == gps_frame(v1)
    assert node.dropped == 1
    spin_until(lambda: node.connections["radio"] is not None)
    send(gps_frame(v1, 5))
    spin_until(lambda: node.forwarded == 1)
    assert radio.recv(65535) == gps_frame(v1, 5)


def test_stream_request_targets_configured_autopilot_once(bridge, monkeypatch):
    node, received, radio, send, spin_until = bridge
    request = Mock()
    monkeypatch.setattr(node.connections["pixhawk"].mav, "request_data_stream_send", request)
    node.config["skip_stream_request"] = False
    for system in (2, 1, 1):
        encoder = v1.MAVLink(None, srcSystem=system, srcComponent=1)
        frame = v1.MAVLink_heartbeat_message(2, 3, 0, 0, 4, 3).pack(encoder)
        send(frame)
    spin_until(lambda: node.forwarded == 3)
    request.assert_called_once_with(1, 1, v1.MAV_DATA_STREAM_ALL, 10, 1)


def test_pixhawk_timeout_reconnects_and_resumes_gps(bridge):
    node, received, radio, send, spin_until = bridge
    original = node.connections["pixhawk"]
    node.last_rx = time.monotonic() - 10.0
    spin_until(lambda: node.connections["pixhawk"] is None)
    spin_until(lambda: node.connections["pixhawk"] is not None)
    assert node.connections["pixhawk"] is not original
    send(gps_frame(v2))
    spin_until(lambda: any(msg.data == 6 for msg in received["fix_type"]))


def test_raw_gps_log_precedes_conversion_and_tracks_updates(bridge, monkeypatch):
    node, received, radio, send, spin_until = bridge
    node.config["debug_gps"] = True
    records = []
    logger = Mock()
    logger.info.side_effect = lambda line: records.append(json.loads(line.removeprefix("RAW_GPS ")))
    monkeypatch.setattr(node, "get_logger", lambda: logger)
    publish_gps = node.publish_gps
    published_inputs = []

    def checked_publish(message, now):
        # Logging must already have happened, with original values even for no fix.
        assert records[-1]["fields"] == message.to_dict()
        published_inputs.append(message.fix_type)
        publish_gps(message, now)

    monkeypatch.setattr(node, "publish_gps", checked_publish)
    encoder = v2.MAVLink(None, srcSystem=1, srcComponent=1)
    for index, (fix, latitude) in enumerate(((0, 182345678), (0, 182345678), (6, 182345679))):
        encoder.seq = index
        frame = v2.MAVLink_gps_raw_int_message(
            (index + 1) * 1000000, fix, latitude, -661234567, 100000, 80, 120, 0, 0, 18
        ).pack(encoder)
        send(frame)
        spin_until(lambda: len(records) == index + 1)
        assert radio.recv(65535) == frame
    assert published_inputs == [0, 0, 6]
    assert [r["rx_count"] for r in records] == [1, 2, 3]
    assert [r["sequence"] for r in records] == [0, 1, 2]
    assert [r["values_changed"] for r in records] == [None, False, True]
    assert records[0]["rx_gap_ms"] is None
    assert records[1]["rx_gap_ms"] >= 0
    assert all(r["gps_topic_input"] and r["source_match"] for r in records)
    assert records[0]["fields"]["fix_type"] == 0
    assert records[0]["fields"]["lat"] == 182345678
    assert records[-1]["fields"]["lat"] == 182345679


def test_raw_gps_log_includes_filtered_secondary_and_fused_position(bridge, monkeypatch):
    node, received, radio, send, spin_until = bridge
    node.config["debug_gps"] = True
    records = []
    logger = Mock()
    logger.info.side_effect = lambda line: records.append(json.loads(line.removeprefix("RAW_GPS ")))
    monkeypatch.setattr(node, "get_logger", lambda: logger)
    publish = Mock()
    monkeypatch.setattr(node, "publish_gps", publish)
    encoder = v2.MAVLink(None, srcSystem=1, srcComponent=1)
    frames = [
        gps_frame(v2, 6, system=2),
        v2.MAVLink_gps2_raw_message(
            time_usec=1000000, fix_type=6, lat=182345678, lon=-661234567,
            alt=100000, eph=80, epv=120, vel=0, cog=0,
            satellites_visible=18, dgps_numch=0, dgps_age=0,
        ).pack(encoder),
        v2.MAVLink_global_position_int_message(
            1000, 182345678, -661234567, 100000, 20000, 0, 0, 0, 0
        ).pack(encoder),
    ]
    for index, frame in enumerate(frames):
        send(frame)
        spin_until(lambda: len(records) == index + 1)
        assert radio.recv(65535) == frame
    assert [r["message_type"] for r in records] == ["GPS_RAW_INT", "GPS2_RAW", "GLOBAL_POSITION_INT"]
    assert [r["source_match"] for r in records] == [False, True, True]
    assert all(not r["gps_topic_input"] for r in records)
    assert all(r["rx_count"] == 1 for r in records)
    assert records[0]["source_system"] == 2
    publish.assert_not_called()


def test_raw_gps_logging_is_disabled_by_default(bridge, monkeypatch):
    node, received, radio, send, spin_until = bridge
    logger = Mock()
    monkeypatch.setattr(node, "get_logger", lambda: logger)
    send(gps_frame(v2))
    spin_until(lambda: node.forwarded == 1)
    logger.info.assert_not_called()
    assert node.gps_debug_state == {}


def test_json_value_sanitizes_nonfinite_and_binary_values():
    assert json_value({"unknown": math.nan, "data": b"\x01\x02"}) == {
        "unknown": None, "data": [1, 2]}
