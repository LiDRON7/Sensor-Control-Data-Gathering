"""Evaluate voltage limits and freshness without depending on ROS clocks."""

import math


class VoltageHealth:
    """Track the latest measurement and independently configured warnings."""

    def __init__(self, minimum, maximum, max_step, stale_sec):
        """Validate limits; zero disables each voltage threshold."""
        values = (minimum, maximum, max_step, stale_sec)
        if any(not math.isfinite(v) or v < 0 for v in values) or stale_sec == 0:
            raise ValueError('Thresholds must be finite/nonnegative; stale_sec > 0')
        if maximum and minimum >= maximum:
            raise ValueError('min_voltage must be less than max_voltage')
        self.minimum = minimum
        self.maximum = maximum
        self.max_step = max_step
        self.stale_sec = stale_sec
        self.voltage = None
        self.received_at = None
        self.problem = 'Waiting for the first voltage reading'
        self.alerts = []

    def unavailable(self, reason):
        """Invalidate output immediately and reset the step comparison baseline."""
        self.problem = reason
        self.voltage = None
        self.alerts = []

    def update(self, voltage, now):
        """Accept finite nonnegative volts and evaluate consecutive fresh samples."""
        if not math.isfinite(voltage) or voltage < 0:
            self.unavailable('Invalid voltage reading: expected finite nonnegative volts')
            return False
        previous = self.voltage
        fresh = self.received_at is not None and now - self.received_at < self.stale_sec
        self.alerts = []
        if self.minimum and voltage < self.minimum:
            self.alerts.append(('low', f'Low voltage: {voltage:.2f} V < {self.minimum:g} V'))
        if self.maximum and voltage > self.maximum:
            self.alerts.append(('high', f'High voltage: {voltage:.2f} V > {self.maximum:g} V'))
        if previous is not None and fresh and self.max_step:
            step = abs(voltage - previous)
            if step > self.max_step:
                self.alerts.append(('step', f'Sudden voltage change: {step:.2f} V'))
        self.voltage = voltage
        self.received_at = now
        self.problem = None
        return True

    def status(self, now):
        """Return diagnostic level, stable warning identity, and readable detail."""
        if self.problem:
            return 3, ('unavailable',), self.problem
        age = now - self.received_at
        if age >= self.stale_sec:
            return 3, ('stale',), f'No fresh voltage reading for {age:.1f} s'
        if self.alerts:
            return 1, tuple(code for code, _ in self.alerts), '; '.join(
                text for _, text in self.alerts)
        return 0, ('ok',), 'Voltage within configured limits'
