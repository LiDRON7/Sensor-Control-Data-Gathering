#!/usr/bin/env python3

import cv2
import subprocess
import threading

# ---------------------------------------------------------
# SETTINGS
# ---------------------------------------------------------

# Choose "TEST" or "OAK"
MODE = "OAK"

# TEST mode:
# 0 = default Windows webcam
# Or use a video filename, e.g. "test_video.mp4"
TEST_SOURCE = 0

# Ground Control Station laptop IP address
GCS_IP = "10.42.0.113"  # CHANGE THIS

VIDEO_PORT = 5600

CAMERA_FPS = 15

STREAM_WIDTH = 640
STREAM_HEIGHT = 480

MODEL = "yolov6-nano"


# ---------------------------------------------------------
# GSTREAMER VIDEO STREAMER
# ---------------------------------------------------------

class VideoStreamer:

    def __init__(self):

        command = [
            "gst-launch-1.0",
            "-q",

            "fdsrc",
            "!",
            "rawvideoparse",
            "format=bgr",
            f"width={STREAM_WIDTH}",
            f"height={STREAM_HEIGHT}",
            f"framerate={CAMERA_FPS}/1",

            "!",
            "videoconvert",

            "!",
            "x264enc",
            "tune=zerolatency",
            "speed-preset=ultrafast",
            "bitrate=1000",
            "key-int-max=15",

            "!",
            "h264parse",

            "!",
            "rtph264pay",
            "pt=96",
            "config-interval=1",

            "!",
            "udpsink",
            f"host={GCS_IP}",
            f"port={VIDEO_PORT}",
            "sync=false",
            "async=false"
        ]

        print("Starting video stream...")
        print(f"Destination: {GCS_IP}:{VIDEO_PORT}")

        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE
        )

    def send(self, frame):

        if self.process.poll() is not None:
            raise RuntimeError("GStreamer has stopped")

        frame = cv2.resize(
            frame,
            (STREAM_WIDTH, STREAM_HEIGHT)
        )

        # GStreamer expects 8-bit BGR frames
        frame = frame.astype("uint8")

        if not frame.flags["C_CONTIGUOUS"]:
            frame = frame.copy()

        self.process.stdin.write(frame.tobytes())

    def close(self):

        if self.process.poll() is None:

            if self.process.stdin:
                self.process.stdin.close()

            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=5)


# ---------------------------------------------------------
# DISPLAY AND STREAM
# ---------------------------------------------------------

def display_and_stream(frame, streamer):

    # Send the processed frame to the GCS
    streamer.send(frame)

    # Also display it locally on Computer 1
    cv2.imshow("Camera - Bounding Boxes", frame)

    key = cv2.waitKey(1) & 0xFF

    return key != ord("q")


# ---------------------------------------------------------
# TEST MODE - NO OAK-D PRO REQUIRED
# ---------------------------------------------------------

def run_test_mode(streamer):

    print("Starting TEST mode...")

    capture = cv2.VideoCapture(TEST_SOURCE)

    if not capture.isOpened():
        raise RuntimeError(
            "Could not open test webcam or video."
        )

    try:
        while True:

            success, frame = capture.read()

            if not success:
                print("End of video or camera unavailable.")
                break

            height, width = frame.shape[:2]

            # Draw a simulated bounding box
            # to verify that annotations are transmitted
            x1 = int(width * 0.25)
            y1 = int(height * 0.25)
            x2 = int(width * 0.75)
            y2 = int(height * 0.75)

            cv2.rectangle(
                frame,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2
            )

            cv2.putText(
                frame,
                "TEST MODE - SIMULATED BOX",
                (15, 35),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )

            if not display_and_stream(frame, streamer):
                break

    finally:
        capture.release()


# ---------------------------------------------------------
# OAK-D PRO MODE
# ---------------------------------------------------------

def run_oak_mode(streamer):

    import depthai as dai

    print("Starting OAK-D Pro mode...")

    # Original DepthAI v3 pipeline
    with dai.Pipeline() as pipeline:

        camera = pipeline.create(
            dai.node.Camera
        ).build(
            dai.CameraBoardSocket.CAM_A,
            sensorFps=CAMERA_FPS
        )

        detector = pipeline.create(
            dai.node.DetectionNetwork
        ).build(
            camera,
            dai.NNModelDescription(MODEL)
        )

        frameQueue = (
            detector.passthrough.createOutputQueue()
        )

        detectionQueue = (
            detector.out.createOutputQueue()
        )

        pipeline.start()

        print("OAK-D Pro bounding-box camera started.")

        while pipeline.isRunning():

            frameMessage = frameQueue.get()
            detectionMessage = detectionQueue.get()

            frame = frameMessage.getCvFrame()

            height, width = frame.shape[:2]

            # Original bounding-box detection code
            for detection in detectionMessage.detections:

                x1 = int(detection.xmin * width)
                y1 = int(detection.ymin * height)

                x2 = int(detection.xmax * width)
                y2 = int(detection.ymax * height)

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

            # Stream the annotated frame
            if not display_and_stream(frame, streamer):
                break


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    streamer = None

    try:

        streamer = VideoStreamer()

        if MODE.upper() == "TEST":

            run_test_mode(streamer)

        elif MODE.upper() == "OAK":

            run_oak_mode(streamer)

        else:
            raise ValueError(
                "MODE must be TEST or OAK"
            )

    except KeyboardInterrupt:
        print("Stopped by user.")

    finally:

        if streamer is not None:
            streamer.close()

        cv2.destroyAllWindows()

        print("Video streaming stopped.")


if __name__ == "__main__":
    main()
