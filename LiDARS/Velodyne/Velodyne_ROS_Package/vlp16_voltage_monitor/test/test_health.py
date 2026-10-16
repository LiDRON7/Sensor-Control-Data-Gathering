"""Exercise limit, step, invalid-measurement, and stale-data behavior."""

import pytest

from vlp16_voltage_monitor.health import VoltageHealth


@pytest.mark.parametrize('voltage,code', [
    (4.5, 'low'), (4.75, 'ok'), (5.0, 'ok'), (5.25, 'ok'), (5.5, 'high'), (0.0, 'low')])
def test_range_boundaries(voltage, code):
    """Warn strictly outside configured bounds, including a zero-volt supply."""
    health = VoltageHealth(4.75, 5.25, 0.0, 3.0)
    assert health.update(voltage, 10.0)
    assert health.status(10.0)[1] == (code,)


def test_step_and_recovery():
    """Assess upward and downward steps and clear warnings on stable samples."""
    health = VoltageHealth(0.0, 0.0, 0.5, 3.0)
    health.update(5.0, 0.0)
    health.update(6.0, 1.0)
    assert health.status(1.0)[1] == ('step',)
    health.update(6.0, 2.0)
    assert health.status(2.0)[0] == 0
    health.update(5.0, 3.0)
    assert health.status(3.0)[1] == ('step',)


def test_stale_and_recovery():
    """Do not compare steps across stale gaps or source errors."""
    health = VoltageHealth(0.0, 0.0, 0.1, 3.0)
    assert health.status(0.0)[0] == 3
    health.update(5.0, 10.0)
    assert health.status(12.99)[0] == 0
    assert health.status(13.0)[0] == 3
    health.update(6.0, 13.0)
    assert health.status(13.0)[0] == 0
    health.unavailable('Disconnected')
    assert health.status(13.1)[0] == 3
    health.update(7.0, 13.2)
    assert health.status(13.2)[0] == 0


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf'), -1.0])
def test_invalid_measurement(value):
    """Invalidate a previous reading without treating a bad value as fresh."""
    health = VoltageHealth(0.0, 0.0, 0.0, 3.0)
    health.update(5.0, 0.0)
    assert not health.update(value, 1.0)
    assert health.voltage is None
    assert health.received_at == 0.0
    assert health.status(1.0)[0] == 3


@pytest.mark.parametrize('limits', [
    (-1.0, 6.0, 0.0, 3.0), (6.0, 5.0, 0.0, 3.0),
    (5.0, 5.0, 0.0, 3.0), (0.0, 0.0, 0.0, 0.0),
    (0.0, 0.0, -1.0, 3.0), (float('nan'), 6.0, 0.0, 3.0),
    (0.0, float('inf'), 0.0, 3.0)])
def test_invalid_configuration(limits):
    """Reject impossible or nonfinite monitor settings."""
    with pytest.raises(ValueError):
        VoltageHealth(*limits)
