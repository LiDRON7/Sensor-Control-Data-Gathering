import numpy as np

from oak_d_ros2.depth import depth_points

INTRINSICS = [[100.0, 0.0, 8.0], [0.0, 100.0, 4.0], [0.0, 0.0, 1.0]]


def test_center_pixel_is_straight_ahead():
    depth = np.full((8, 16), 2000, dtype=np.uint16)
    points = depth_points(depth, INTRINSICS, step=4)
    assert [0.0, 0.0, 2.0] in points.tolist()
    assert points.dtype == np.float32 and len(points) == 2 * 4


def test_offset_pixels_scale_with_depth():
    depth = np.full((8, 16), 2000, dtype=np.uint16)
    x, y, z = depth_points(depth, INTRINSICS, step=4)[0]
    np.testing.assert_allclose((x, y, z), (-0.16, -0.08, 2.0), rtol=1e-6)


def test_invalid_and_out_of_range_depth_is_dropped():
    depth = np.array([[0, 100, 2000, 30000]], dtype=np.uint16)
    points = depth_points(depth, INTRINSICS, step=1)
    np.testing.assert_allclose(points, [[(2 - 8) * 2 / 100, -0.08, 2.0]], rtol=1e-6)
