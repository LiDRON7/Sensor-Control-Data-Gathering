#!/usr/bin/env python3

import cv2
import depthai as dai


# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------
CAMERA_FPS = 15

# Detection model used by the current DepthAI v3 example
MODEL = "yolov6-nano"

# ---------------------------------------------------------
# CREATE PIPELINE
# ---------------------------------------------------------
with dai.Pipeline() as pipeline:

    # -----------------------------------------------------
    # CAMERA
    # -----------------------------------------------------
    # CAM_A is normally the main/color camera on the OAK-D Pro
    camera = pipeline.create(dai.node.Camera).build(
        dai.CameraBoardSocket.CAM_A,
        sensorFps=CAMERA_FPS
    )

    # -----------------------------------------------------
    # DETECTION NETWORK
    # -----------------------------------------------------
    detector = pipeline.create(dai.node.DetectionNetwork).build(
        camera,
        dai.NNModelDescription(MODEL)
    )

    # -----------------------------------------------------
    # OUTPUT QUEUES
    # -----------------------------------------------------
    # Frame that actually went through the detector.
    # Using passthrough keeps detections synchronized
    # with the displayed image.
    frameQueue = detector.passthrough.createOutputQueue()

    # Bounding-box detections
    detectionQueue = detector.out.createOutputQueue()

    # -----------------------------------------------------
    # START PIPELINE
    # -----------------------------------------------------
    pipeline.start()

    print("OAK-D Pro bounding-box camera started.")
    print("Press Q to quit.")

    # -----------------------------------------------------
    # MAIN LOOP
    # -----------------------------------------------------
    while pipeline.isRunning():

        # Get the image and its detections
        frameMessage = frameQueue.get()
        detectionMessage = detectionQueue.get()

        # Convert DepthAI image into OpenCV image
        frame = frameMessage.getCvFrame()

        height, width = frame.shape[:2]

        # -------------------------------------------------
        # DRAW ONLY BOUNDING BOXES
        # -------------------------------------------------
        for detection in detectionMessage.detections:

            # DepthAI detections use normalized coordinates:
            # 0.0 -> 1.0
            # Convert those coordinates to image pixels.
            x1 = int(detection.xmin * width)
            y1 = int(detection.ymin * height)

            x2 = int(detection.xmax * width)
            y2 = int(detection.ymax * height)

            # Keep coordinates inside the image
            x1 = max(0, min(x1, width - 1))
            y1 = max(0, min(y1, height - 1))

            x2 = max(0, min(x2, width - 1))
            y2 = max(0, min(y2, height - 1))

            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2
            )

        # -------------------------------------------------
        # DISPLAY
        # -------------------------------------------------
        cv2.imshow("OAK-D Pro - Bounding Boxes", frame)

        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break

cv2.destroyAllWindows()