#!/usr/bin/env python3
"""
OAK-4 MJPEG Streaming Server

Streams the main camera with YOLO-World annotations from a connected Luxonis OAK device 
over HTTP. No complex HostNode syncing required.
"""

import argparse
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from pathlib import Path
from time import sleep

import cv2
import depthai as dai
from depthai_nodes.node import ParsingNeuralNetwork

from backend.utils import compute_text_embeddings, MY_CLASSES

DEFAULT_PORT = 8083
DEFAULT_FPS  = 30

INDEX_HTML = b"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>OAK Live Stream</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: #111;
      color: #eee;
      font-family: sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      gap: 10px;
    }
    h1 { font-size: 0.9rem; letter-spacing: 0.1em; opacity: 0.4; text-transform: uppercase; }
    img { max-width: 100%; max-height: 90vh; display: block; }
    p  { font-size: 0.75rem; opacity: 0.3; }
  </style>
</head>
<body>
  <h1>OAK Live</h1>
  <img src="/stream" alt="camera stream" />
  <p>MJPEG &mdash; refreshes automatically</p>
</body>
</html>"""


class VideoStreamHandler(BaseHTTPRequestHandler):
    """Serves the HTML viewer on / and the MJPEG stream on /stream."""

    def log_message(self, *args):
        pass  # silence per-request logs

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path.split("?")[0] == "/stream":
            self._serve_stream()
        else:
            self._serve_html()

    def _serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(INDEX_HTML)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(INDEX_HTML)

    def _serve_stream(self):
        self.send_response(200)
        self.send_header(
            "Content-Type", "multipart/x-mixed-replace; boundary=--jpgboundary"
        )
        self._send_cors_headers()
        self.end_headers()
        while True:
            sleep(0.03)
            frame = getattr(self.server, "frametosend", None)
            if frame is None:
                continue
            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                continue
            try:
                self.wfile.write(b"--jpgboundary\r\n")
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded.tobytes())
                self.wfile.write(b"\r\n")
            except BrokenPipeError:
                break


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handles each connection in its own thread."""
    pass


class MJPEGStreamer:
    """
    Manages the background HTTP threaded server and stores the latest 
    annotated frame to serve to connected clients.
    """
    def __init__(self, port: int):
        self.server = ThreadedHTTPServer(("0.0.0.0", port), VideoStreamHandler)
        t = threading.Thread(target=self.server.serve_forever, daemon=True)
        t.start()
        print(f"[oak-stream] Viewer  →  http://localhost:{port}")
        print(f"[oak-stream] Stream  →  http://localhost:{port}/stream")

    def send_frame(self, frame):
        """Push a newly annotated OpenCV frame to the server."""
        self.server.frametosend = frame


def fetch_model():
    model_desc = dai.NNModelDescription(model="luxonis/yolo-world-l", platform="RVC4")
    model_path = dai.getModelFromZoo(model_desc, useCached=True, progressFormat="pretty")
    return dai.NNArchive(str(model_path))


def add_model_prediction(pipeline, archive, cam_nn, streamer):
    texts_u8 = compute_text_embeddings(MY_CLASSES)

    nn = pipeline.create(ParsingNeuralNetwork)
    nn.setNNArchive(archive)
    nn.setBackend("snpe")
    nn.setBackendProperties({"runtime": "dsp", "performance_profile": "default"})
    nn.setNumInferenceThreads(1)

    # Configure parsing thresholds
    parser = nn.getParser(0)
    parser.setConfidenceThreshold(0.1)
    parser.setIouThreshold(0.4)

    # Link Image output to Neural Network
    cam_nn.link(nn.inputs["images"])

    # Create queues
    text_in_q = nn.inputs["texts"].createInputQueue()
    nn.inputs["texts"].setReusePreviousMessage(True)
    
    video_out_q = cam_nn.createOutputQueue(maxSize=1, blocking=False)
    det_out_q = nn.out.createOutputQueue(maxSize=1, blocking=False)

    # Start the pipeline
    pipeline.start()

    # Send the calculated embeddings to the device
    nn_data = dai.NNData()
    nn_data.addTensor("texts", texts_u8, dataType=dai.TensorInfo.DataType.U8F)
    text_in_q.send(nn_data)
    print("Sent custom text embeddings to YOLO-World parser!")

    print("Running pipeline... Press Ctrl+C in the terminal to quit.")

    latest_frame = None
    latest_detections = []
    
    try:
        while pipeline.isRunning():
            # 1. Grab the latest frame if available
            frame_msg = video_out_q.tryGet()
            if frame_msg is not None:
                latest_frame = frame_msg.getCvFrame()
            
            # 2. Grab the latest detections if available
            det_msg = det_out_q.tryGet()
            if det_msg is not None:
                latest_detections = det_msg.detections

            # 3. If we have a frame, annotate it and send directly to the streamer
            if latest_frame is not None:
                display_frame = latest_frame.copy()
                h, w = display_frame.shape[:2]

                for det in latest_detections:
                    class_id = int(det.label)
                    if class_id >= len(MY_CLASSES):
                        continue
                    
                    label = MY_CLASSES[class_id]
                    
                    x1 = int(max(0, min(w, det.xmin * w)))
                    y1 = int(max(0, min(h, det.ymin * h)))
                    x2 = int(max(0, min(w, det.xmax * w)))
                    y2 = int(max(0, min(h, det.ymax * h)))

                    cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(
                        display_frame, 
                        f"{label}", 
                        (x1, max(y1 - 10, 20)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 
                        0.5, (0, 255, 0), 2
                    )
                
                # Directly hand the raw OpenCV frame to the HTTP server!
                streamer.send_frame(display_frame)

            sleep(0.01)

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        print("Closing pipeline and cleaning up resources...")


def main():
    parser = argparse.ArgumentParser(description="OAK MJPEG streaming server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"HTTP port (default: {DEFAULT_PORT})")
    parser.add_argument("--fps",  type=int, default=DEFAULT_FPS,  help=f"Camera FPS (default: {DEFAULT_FPS})")
    parser.add_argument("--device", type=str, default=None, help="Device name, ID, or IP (default: auto-detect)")
    args = parser.parse_args()

    device = dai.Device(dai.DeviceInfo(args.device)) if args.device else dai.Device()

    with dai.Pipeline(device) as pipeline:
        cam_node = pipeline.create(dai.node.Camera)
        cam_node.build(boardSocket=dai.CameraBoardSocket.CAM_A)

        archive = fetch_model()
        model_w, model_h = archive.getInputSize()

        cam_out = cam_node.requestOutput(size=(model_w, model_h), type=dai.ImgFrame.Type.BGR888i, fps=15.0)
        
        # Instantiate the streamer cleanly
        streamer = MJPEGStreamer(port=args.port)
        
        add_model_prediction(pipeline, archive, cam_out, streamer)


if __name__ == "__main__":
    main()