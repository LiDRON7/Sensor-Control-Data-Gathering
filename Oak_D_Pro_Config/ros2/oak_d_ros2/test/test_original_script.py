"""Exercise the original viewer without camera hardware or a desktop window."""

import ast
import math
import os
from pathlib import Path
import runpy
from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import depthai as dai
import numpy as np
import pytest
import rclpy

from oak_d_ros2.node import main


@pytest.mark.parametrize('depth_mm', [2500, 0, 100])
@pytest.mark.parametrize('mode', ['standalone', 'hook', 'entrypoint'])
def test_original_camera_graph_drawing_and_q_are_preserved(monkeypatch, depth_mm, mode):
    image = np.zeros((100, 200, 3), dtype=np.uint8)
    depth = np.full((80, 160), depth_mm, dtype=np.uint16)
    detection = SimpleNamespace(xmin=0.25, ymin=0.25, xmax=0.75, ymax=0.75,
                                label=0, confidence=0.9)
    timestamp = dai.Clock.now()
    rgb = SimpleNamespace(getCvFrame=lambda: image, getTimestamp=lambda: timestamp)
    detections = SimpleNamespace(detections=[detection])
    depth_packet = SimpleNamespace(getFrame=lambda: depth)
    pipeline = MagicMock()
    pipeline.__enter__.return_value = pipeline
    pipeline.isRunning.return_value = True
    nodes = {}

    def create(node_type):
        node = MagicMock()
        node.build.return_value = node
        nodes[node_type] = node
        if node_type is dai.node.DetectionNetwork:
            node.getClasses.return_value = ['bottle']
            node.passthrough.createOutputQueue.return_value.get.return_value = rgb
            node.out.createOutputQueue.return_value.get.return_value = detections
        if node_type is dai.node.StereoDepth:
            node.depth.createOutputQueue.return_value.get.return_value = depth_packet
        return node

    pipeline.create.side_effect = create
    monkeypatch.setattr(dai, 'Pipeline', lambda: pipeline)
    imshow, wait, destroy, resize = MagicMock(), MagicMock(return_value=ord('q')), MagicMock(), MagicMock()
    monkeypatch.setattr(cv2, 'imshow', imshow)
    monkeypatch.setattr(cv2, 'waitKey', wait)
    monkeypatch.setattr(cv2, 'destroyAllWindows', destroy)
    monkeypatch.setattr(cv2, 'resizeWindow', resize)
    bridge = SimpleNamespace(show_preview=True, ok=lambda: True,
                             set_labels=MagicMock(), submit_distances=MagicMock())
    script = Path(__file__).resolve().parents[3] / 'Object_Detection_With_Distance.py'
    if mode == 'entrypoint':
        monkeypatch.setenv('DISPLAY', ':0')  # All GUI functions are intercepted.
        main(args=[])
        assert not rclpy.ok()
    else:
        runpy.run_path(str(script), init_globals={'_ros_bridge': bridge} if mode == 'hook' else {})

    expected = np.zeros_like(image)
    cv2.rectangle(expected, (50, 25), (150, 75), (0, 255, 0), 2)
    cv2.circle(expected, (100, 50), 5, (0, 0, 255), -1)
    valid = depth_mm == 2500
    if valid:
        cv2.putText(expected, '2.50 m (8.20 ft)', (50, 50), cv2.FONT_HERSHEY_SIMPLEX,
                    0.65, (0, 255, 0), 2, cv2.LINE_AA)
    else:
        cv2.putText(expected, 'Distance unavailable', (50, 25), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, (0, 0, 255), 2, cv2.LINE_AA)
    assert imshow.call_args.args[0] == 'OAK-D Pro - Object Distance'
    np.testing.assert_array_equal(imshow.call_args.args[1], expected)
    wait.assert_called_once_with(1)
    destroy.assert_called_once_with()
    resize.assert_not_called()
    assert pipeline.isRunning.call_count == 1
    assert list(nodes) == [dai.node.Camera, dai.node.StereoDepth, dai.node.DetectionNetwork]
    detector = nodes[dai.node.DetectionNetwork]
    assert len(detector.build.call_args.args) == 2
    detector.setConfidenceThreshold.assert_not_called()
    detector.passthrough.createOutputQueue.assert_called_once_with()
    detector.out.createOutputQueue.assert_called_once_with()
    nodes[dai.node.StereoDepth].depth.createOutputQueue.assert_called_once_with()
    nodes[dai.node.StereoDepth].setDepthAlign.assert_called_once_with(dai.CameraBoardSocket.CAM_A)
    if mode == 'hook':
        stamp, records = bridge.submit_distances.call_args.args
        assert stamp == timestamp
        assert len(records) == 1 and records[0][0] == 0
        assert records[0][1] == 2.5 if valid else math.isnan(records[0][1])


@pytest.mark.skipif(not os.environ.get('OAK_REFERENCE_SCRIPT'), reason='Set OAK_REFERENCE_SCRIPT for source comparison')
def test_only_ros_hooks_differ_from_the_provided_reference():
    class StripRosHooks(ast.NodeTransformer):
        def visit_Assign(self, node):
            if any(isinstance(target, ast.Name) and target.id in {'_ros_bridge', 'ros_distances'}
                   for target in node.targets):
                return None
            return self.generic_visit(node)

        def visit_If(self, node):
            test = ast.unparse(node.test)
            if '_ros_bridge.show_preview' in test:
                return [self.visit(statement) for statement in node.body]
            if '_ros_bridge' in test:
                return None
            return self.generic_visit(node)

        def visit_While(self, node):
            if isinstance(node.test, ast.BoolOp) and '_ros_bridge' in ast.unparse(node.test):
                node.test = node.test.values[0]
            return self.generic_visit(node)

    source = Path(__file__).resolve().parents[3] / 'Object_Detection_With_Distance.py'
    original = ast.parse(Path(os.environ['OAK_REFERENCE_SCRIPT']).read_text())
    updated = StripRosHooks().visit(ast.parse(source.read_text()))
    assert ast.dump(updated, include_attributes=False) == ast.dump(original, include_attributes=False)
