#!/usr/bin/env python3

from pathlib import Path
import cv2
import depthai as dai
import numpy as np
import argparse

# Path to model blob
nnPathDefault = str((Path(__file__).parent / Path('../models/mobilenet-ssd_openvino_2021.4_6shave.blob')).resolve().absolute())

parser = argparse.ArgumentParser()
parser.add_argument('nnPath', nargs='?', help="Path to mobilenet detection network blob", default=nnPathDefault)
parser.add_argument('-s', '--sync', action="store_true", help="Sync RGB output with NN output", default=False)
args = parser.parse_args()

if not Path(nnPathDefault).exists():
    import sys
    raise FileNotFoundError(f'Required file/s not found, please run "{sys.executable} install_requirements.py"')

# -----------------------------
# Create pipeline
# -----------------------------
pipeline = dai.Pipeline()

camRgb = pipeline.create(dai.node.ColorCamera)
nn = pipeline.create(dai.node.MobileNetDetectionNetwork)
xoutRgb = pipeline.create(dai.node.XLinkOut)
nnOut = pipeline.create(dai.node.XLinkOut)

xoutRgb.setStreamName("rgb")
nnOut.setStreamName("nn")

# -----------------------------
# Camera Configuration (FIXED)
# -----------------------------
camRgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_720_P)
camRgb.setPreviewSize(300, 300)  # Required by MobileNet
camRgb.setInterleaved(False)
camRgb.setFps(30)

# -----------------------------
# Neural Network Configuration
# -----------------------------
nn.setConfidenceThreshold(0.5)
nn.setBlobPath(args.nnPath)
nn.setNumInferenceThreads(2)
nn.input.setBlocking(False)

# -----------------------------
# Linking
# -----------------------------
if args.sync:
    nn.passthrough.link(xoutRgb.input)
else:
    camRgb.preview.link(xoutRgb.input)

camRgb.preview.link(nn.input)
nn.out.link(nnOut.input)

# -----------------------------
# Run Device
# -----------------------------
with dai.Device(pipeline) as device:

    qRgb = device.getOutputQueue(name="rgb", maxSize=4, blocking=False)
    qDet = device.getOutputQueue(name="nn", maxSize=4, blocking=False)

    frame = None
    detections = []

    # Normalize bounding box
    def frameNorm(frame, bbox):
        normVals = np.full(len(bbox), frame.shape[0])
        normVals[::2] = frame.shape[1]
        return (np.clip(np.array(bbox), 0, 1) * normVals).astype(int)

    # Display only square outline
    def displayFrame(name, frame):
        color = (0, 255, 0)  # Green square

        for detection in detections:
            if detection.confidence > 0.5:

                bbox = frameNorm(frame, (
                    detection.xmin,
                    detection.ymin,
                    detection.xmax,
                    detection.ymax
                ))

                # Create perfect square
                box_width = bbox[2] - bbox[0]
                box_height = bbox[3] - bbox[1]
                box_size = min(box_width, box_height)

                cv2.rectangle(
                    frame,
                    (bbox[0], bbox[1]),
                    (bbox[0] + box_size, bbox[1] + box_size),
                    color,
                    2
                )

        cv2.imshow(name, frame)

    # -----------------------------
    # Main Loop
    # -----------------------------
    while True:

        if args.sync:
            inRgb = qRgb.get()
            inDet = qDet.get()
        else:
            inRgb = qRgb.tryGet()
            inDet = qDet.tryGet()

        if inRgb is not None:
            frame = inRgb.getCvFrame()

        if inDet is not None:
            detections = inDet.detections

        if frame is not None:
            displayFrame("rgb", frame)

        if cv2.waitKey(1) == ord('q'):
            break

cv2.destroyAllWindows()
