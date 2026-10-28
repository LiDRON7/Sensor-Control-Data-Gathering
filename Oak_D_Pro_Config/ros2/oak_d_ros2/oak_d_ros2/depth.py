"""Turn an OAK-D depth frame into the points the autonomy obstacle map reads."""

import numpy as np


def depth_points(depth_mm, intrinsics, step=8, min_m=0.2, max_m=20.0):
    """Back-project every step-th pixel to meters, as FLU (x forward, y left, z up).

    Autonomy's obstacle map (navigation/mapping.py) reads FLU, not the optical frame.
    """
    (fx, _, cx), (_, fy, cy) = intrinsics[0], intrinsics[1]
    v, u = np.mgrid[0:depth_mm.shape[0]:step, 0:depth_mm.shape[1]:step]
    forward = depth_mm[::step, ::step] / 1000.0
    keep = (forward >= min_m) & (forward <= max_m)
    forward, u, v = forward[keep], u[keep], v[keep]
    left = -(u - cx) * forward / fx
    up = -(v - cy) * forward / fy
    return np.column_stack((forward, left, up)).astype(np.float32)
