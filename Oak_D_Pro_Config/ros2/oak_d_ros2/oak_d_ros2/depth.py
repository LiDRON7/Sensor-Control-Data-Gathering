"""Turn an OAK-D depth frame into the points the autonomy obstacle map reads."""

import numpy as np


def depth_points(depth_mm, intrinsics, step=8, min_m=0.2, max_m=20.0):
    """Back-project every step-th pixel to optical-frame XYZ in meters (x right, y down, z forward)."""
    (fx, _, cx), (_, fy, cy) = intrinsics[0], intrinsics[1]
    v, u = np.mgrid[0:depth_mm.shape[0]:step, 0:depth_mm.shape[1]:step]
    z = depth_mm[::step, ::step] / 1000.0
    keep = (z >= min_m) & (z <= max_m)
    z, u, v = z[keep], u[keep], v[keep]
    return np.column_stack(((u - cx) * z / fx, (v - cy) * z / fy, z)).astype(np.float32)
