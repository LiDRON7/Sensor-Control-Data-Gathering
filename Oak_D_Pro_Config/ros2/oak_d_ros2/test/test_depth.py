import numpy as np

from oak_d_ros2.depth import depth_points

INTRINSICS = [[100.0, 0.0, 8.0], [0.0, 100.0, 4.0], [0.0, 0.0, 1.0]]


def test_center_pixel_is_straight_ahead():
    depth = np.full((8, 16), 2000, dtype=np.uint16)
    points = depth_points(depth, INTRINSICS, step=4)
    assert [2.0, 0.0, 0.0] in points.tolist()
    assert points.dtype == np.float32 and len(points) == 2 * 4


def test_top_left_pixel_is_left_and_up():
    depth = np.full((8, 16), 2000, dtype=np.uint16)
    forward, left, up = depth_points(depth, INTRINSICS, step=4)[0]
    np.testing.assert_allclose((forward, left, up), (2.0, 0.16, 0.08), rtol=1e-6)


def test_invalid_and_out_of_range_depth_is_dropped():
    depth = np.array([[0, 100, 2000, 30000]], dtype=np.uint16)
    points = depth_points(depth, INTRINSICS, step=1)
    np.testing.assert_allclose(points, [[2.0, (8 - 2) * 2 / 100, 0.08]], rtol=1e-6)


def test_upside_down_camera_sees_top_left_pixel_as_right_and_down():
    # The camera is mounted upside down: what lands in its top-left pixel is really down and to the right.
    from oak_d_ros2.depth import upright
    depth = np.zeros((8, 16), dtype=np.uint16)
    depth[0, 0] = 2000
    turned, intrinsics = upright(depth, INTRINSICS)
    forward, left, up = depth_points(turned, intrinsics, step=1)[0]
    assert forward == 2.0 and left < 0 and up < 0
    np.testing.assert_allclose((left, up), (-0.16, -0.08), rtol=1e-6)   # mirror of the upright case
