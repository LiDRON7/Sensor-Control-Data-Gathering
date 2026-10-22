"""Serialize scalar-only object distances."""

import math

from oak_d_interfaces.msg import ObjectDistance, ObjectDistanceArray


def distance_message(header, records, labels):
    message = ObjectDistanceArray(header=header)
    for label, distance in records:
        valid = math.isfinite(distance) and distance > 0
        message.objects.append(ObjectDistance(
            class_id=labels[label] if 0 <= label < len(labels) else str(label),
            distance_m=float(distance) if valid else math.nan,
            distance_valid=valid,
        ))
    return message
