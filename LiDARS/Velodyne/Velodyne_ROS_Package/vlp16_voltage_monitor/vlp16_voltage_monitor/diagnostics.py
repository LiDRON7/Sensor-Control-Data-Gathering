"""Read input supply voltage from the VLP-16 HTTP diagnostics interface."""

import ipaddress
import json
from urllib.request import build_opener, ProxyHandler


def input_voltage(payload):
    """
    Convert volt_temp.bot.pwr_v_in ADC counts to supply volts.

    VLP-16 User Manual, section bot:pwr_v_in:
    https://data.ouster.io/downloads/velodyne/user-manual/vlp-16-user-manual-revf.pdf
    """
    try:
        raw = payload['volt_temp']['bot']['pwr_v_in']
    except (KeyError, TypeError) as exc:
        raise ValueError('Missing volt_temp.bot.pwr_v_in diagnostic field') from exc
    if type(raw) is not int or not 0 <= raw <= 4095:
        raise ValueError('pwr_v_in must be an integer ADC count from 0 to 4095')
    return raw * 5.0 / 4096.0 * 11.0


class DiagnosticsClient:
    """Fetch diagnostics directly from the sensor, bypassing HTTP proxies."""

    def __init__(self, sensor_ip, timeout_sec):
        """Configure a sensor IPv4 address and a socket timeout."""
        address = ipaddress.IPv4Address(sensor_ip)
        self.url = f'http://{address}/cgi/diag.json'
        self.timeout_sec = timeout_sec
        self._opener = build_opener(ProxyHandler({}))

    def read_voltage(self):
        """Fetch and decode one reading; propagate connection or data errors."""
        with self._opener.open(self.url, timeout=self.timeout_sec) as response:
            payload = json.load(response)
        return input_voltage(payload)
