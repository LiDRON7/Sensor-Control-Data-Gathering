#!/usr/bin/env python3

import cv2
import depthai as dai
import numpy as np

# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------
CAMERA_FPS = 15
MODEL = "yolov6-nano"

# Valid distance range
MIN_DISTANCE_M = 0.2
MAX_DISTANCE_M = 20.0

# Percentage of the bounding box used for depth sampling.
# 0.10 = center 10% of the bounding box.
DEPTH_ROI_SIZE = 0.10

# ---------------------------------------------------------
# CREATE PIPELINE
# ---------------------------------------------------------
with dai.Pipeline() as pipeline:

    # -----------------------------------------------------
    # RGB CAMERA
    # -----------------------------------------------------
    camera = pipeline.create(
        dai.node.Camera
    ).build(
        dai.CameraBoardSocket.CAM_A,
        sensorFps=CAMERA_FPS
    )

    # -----------------------------------------------------
    # STEREO DEPTH
    # -----------------------------------------------------

    stereo = pipeline.create(
        dai.node.StereoDepth
    ).build(
        True,
        dai.node.StereoDepth.PresetMode.FAST_DENSITY,
        (640, 400),
        CAMERA_FPS
    )

    # -----------------------------------------------------
    # ALIGN DEPTH TO RGB
    # -----------------------------------------------------
    #
    # This makes the depth map correspond to CAM_A.
    #
    # The YOLO bounding boxes are generated from CAM_A,
    # so this lets us sample depth at the corresponding
    # RGB location.
    #
    # -----------------------------------------------------
    stereo.setDepthAlign(
        dai.CameraBoardSocket.CAM_A
    )

    # -----------------------------------------------------
    # OBJECT DETECTION
    # -----------------------------------------------------
    #
    # We deliberately use DetectionNetwork instead of
    # SpatialDetectionNetwork.
    #
    # SpatialDetectionNetwork requires additional resources
    # and caused the original 8-SHAVE allocation failure.
    #
    # -----------------------------------------------------
    detector = pipeline.create(
        dai.node.DetectionNetwork
    ).build(
        camera,
        dai.NNModelDescription(MODEL)
    )

    # -----------------------------------------------------
    # OUTPUT QUEUES
    # -----------------------------------------------------
    frameQueue = detector.passthrough.createOutputQueue()
    detectionQueue = detector.out.createOutputQueue()
    depthQueue = stereo.depth.createOutputQueue()

    # -----------------------------------------------------
    # START PIPELINE
    # -----------------------------------------------------
    pipeline.start()

    print()
    print("============================================")
    print(" OAK-D Pro Object Detection + Distance")
    print("============================================")
    print(f"DepthAI version: {dai.__version__}")
    print(f"Model: {MODEL}")
    print("Distance: meters + feet")
    print()
    print("Press Q to quit.")
    print("============================================")
    print()

    # -----------------------------------------------------
    # MAIN LOOP
    # -----------------------------------------------------
    while pipeline.isRunning():

        # -------------------------------------------------
        # GET RGB FRAME
        # -------------------------------------------------
        frameMessage = frameQueue.get()
        frame = frameMessage.getCvFrame()
        height, width = frame.shape[:2]

        # -------------------------------------------------
        # GET DETECTIONS
        # -------------------------------------------------
        detectionMessage = detectionQueue.get()

        # -------------------------------------------------
        # GET DEPTH
        # -------------------------------------------------
        depthMessage = depthQueue.get()
        depthFrame = depthMessage.getFrame()
        depthHeight, depthWidth = depthFrame.shape[:2]

        # -------------------------------------------------
        # PROCESS EACH DETECTION
        # -------------------------------------------------
        for detection in detectionMessage.detections:

            # ---------------------------------------------
            # CONVERT NORMALIZED BOUNDING BOX
            # TO PIXEL COORDINATES
            # ---------------------------------------------
            x1 = int(detection.xmin * width)
            y1 = int(detection.ymin * height)

            x2 = int(detection.xmax * width)
            y2 = int(detection.ymax * height)

            # ---------------------------------------------
            # KEEP BOX INSIDE IMAGE
            # ---------------------------------------------
            x1 = max(
                0,
                min(x1, width - 1)
            )

            y1 = max(
                0,
                min(y1, height - 1)
            )

            x2 = max(
                0,
                min(x2, width - 1)
            )

            y2 = max(
                0,
                min(y2, height - 1)
            )

            # ---------------------------------------------
            # DRAW BOUNDING BOX
            # ---------------------------------------------
            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2
            )

            # ---------------------------------------------
            # OBJECT CENTER
            # ---------------------------------------------
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2

            # ---------------------------------------------
            # DRAW CENTER POINT
            # ---------------------------------------------
            cv2.circle(
                frame,
                (center_x, center_y),
                5,
                (0, 0, 255),
                -1
            )

            # ---------------------------------------------
            # CONVERT RGB CENTER TO DEPTH COORDINATES
            # ---------------------------------------------
            #
            # The depth map has been aligned to CAM_A.
            #
            # We therefore map the RGB pixel into the
            # aligned depth image.
            #
            # ---------------------------------------------
            depth_x = int(
                center_x * depthWidth / width
            )

            depth_y = int(
                center_y * depthHeight / height
            )

            # ---------------------------------------------
            # KEEP DEPTH COORDINATES INSIDE IMAGE
            # ---------------------------------------------
            depth_x = max(
                0,
                min(depth_x, depthWidth - 1)
            )

            depth_y = max(
                0,
                min(depth_y, depthHeight - 1)
            )

            # --------------------------------------------
            # CREATE DEPTH ROI
            # ---------------------------------------------
            #
            # Instead of using one pixel, sample a small
            # area around the object's center.
            #
            # Median filtering makes the distance more
            # stable.
            #
            # ---------------------------------------------
            box_width = max(
                1,
                x2 - x1
            )

            box_height = max(
                1,
                y2 - y1
            )

            roi_half_width = max(
                2,
                int(box_width * DEPTH_ROI_SIZE / 2)
            )

            roi_half_height = max(
                2,
                int(box_height * DEPTH_ROI_SIZE / 2)
            )

            roi_x1 = max(
                0,
                depth_x - roi_half_width
            )

            roi_x2 = min(
                depthWidth,
                depth_x + roi_half_width
            )

            roi_y1 = max(
                0,
                depth_y - roi_half_height
            )

            roi_y2 = min(
                depthHeight,
                depth_y + roi_half_height
            )

            # ---------------------------------------------
            # GET DEPTH ROI
            # ---------------------------------------------
            depthROI = depthFrame[
                roi_y1:roi_y2,
                roi_x1:roi_x2
            ]

            # ---------------------------------------------
            # REMOVE INVALID DEPTH
            # ---------------------------------------------
            validDepth = depthROI[
                (depthROI > 0)
                &
                (depthROI >= MIN_DISTANCE_M * 1000)
                &
                (depthROI <= MAX_DISTANCE_M * 1000)
            ]

            # ---------------------------------------------
            # CALCULATE DISTANCE
            # ---------------------------------------------
            if validDepth.size > 0:

                # Median is less sensitive to noisy pixels
                # than taking one individual depth value.
                distance_mm = float(
                    np.median(validDepth)
                )

                # Convert millimeters → meters
                distance_m = (
                    distance_mm / 1000.0
                )

                # Convert meters → feet
                distance_ft = (
                    distance_m * 3.28084
                )

                # -----------------------------------------
                # CREATE DISTANCE TEXT
                # -----------------------------------------
                distance_text = (
                    f"{distance_m:.2f} m "
                    f"({distance_ft:.2f} ft)"
                )

                # -----------------------------------------
                # TEXT POSITION
                # -----------------------------------------
                text_x = x1
                text_y = y1 - 10

                if text_y < 25:
                    text_y = y1 + 25

                # -----------------------------------------
                # DRAW DISTANCE
                # -----------------------------------------
                cv2.putText(
                    frame,
                    distance_text,
                    (text_x, text_y),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA
                )

            else:

                # -----------------------------------------
                # NO VALID DEPTH
                # -----------------------------------------
                cv2.putText(
                    frame,
                    "Distance unavailable",
                    (x1, max(25, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA
                )

        # -------------------------------------------------
        # DISPLAY
        # -------------------------------------------------
        cv2.imshow(
            "OAK-D Pro - Object Distance",
            frame
        )

        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break

cv2.destroyAllWindows()