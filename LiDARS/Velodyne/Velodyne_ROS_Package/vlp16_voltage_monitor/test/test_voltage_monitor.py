"""Test ADC conversion, HTTP decoding, and publish/failure/recovery behavior."""

from io import BytesIO
from unittest.mock import MagicMock
from urllib.error import URLError

import pytest

from vlp16_voltage_monitor.diagnostics import DiagnosticsClient, input_voltage
from vlp16_voltage_monitor.voltage_monitor import VoltageMonitor


def test_input_supply_conversion():
    """Use the manufacturer's raw example, preserving full precision."""
    payload = {'volt_temp': {'bot': {'pwr_v_in': 910}}}
    assert input_voltage(payload) == pytest.approx(12.21923828125)


@pytest.mark.parametrize('raw', [True, None, '910', -1, 4096, 910.5, float('nan')])
def test_invalid_adc(raw):
    """Reject malformed readings instead of reporting misleading voltages."""
    with pytest.raises(ValueError):
        input_voltage({'volt_temp': {'bot': {'pwr_v_in': raw}}})


@pytest.mark.parametrize('payload', [{}, None, [], {'volt_temp': {'bot': {}}}])
def test_missing_adc(payload):
    """Reject diagnostic responses without the input supply field."""
    with pytest.raises(ValueError, match='Missing'):
        input_voltage(payload)


def test_http_reader():
    """Read nested JSON through a response that closes after consumption."""
    client = DiagnosticsClient('192.168.1.201', 0.8)
    response = BytesIO(b'{"volt_temp":{"bot":{"pwr_v_in":910}}}')
    client._opener = MagicMock()
    client._opener.open.return_value = response
    assert client.read_voltage() == pytest.approx(12.21923828125)
    assert response.closed
    client._opener.open.assert_called_once_with(
        'http://192.168.1.201/cgi/diag.json', timeout=0.8)


def test_invalid_json():
    """An HTML error page must not produce a voltage."""
    client = DiagnosticsClient('192.168.1.201', 0.8)
    client._opener = MagicMock()
    client._opener.open.return_value = BytesIO(b'<html>Error</html>')
    with pytest.raises(ValueError):
        client.read_voltage()


def test_publish_failure_and_recovery():
    """Publish unavailable during an outage and resume with a fresh reading."""
    node = MagicMock()
    node._client.read_voltage.side_effect = [
        12.21923828125, URLError('offline'), TimeoutError(), 12.1,
    ]
    for _ in range(4):
        VoltageMonitor._poll(node)
    assert [call.args[0] for call in node.accept_voltage.call_args_list] == [
        12.21923828125, 12.1]
    assert node.unavailable.call_count == 2
