#!/usr/bin/env python3
"""
OAK-4 MJPEG Streaming Server

Streams the main camera from a connected Luxonis OAK device over HTTP
using the depthai v3 HostNode API. No AI model required.

Usage:
    pip install -r requirements.txt
    python server.py

Open http://localhost:8083 in your browser.
Optional flags:
    --port 9000
    --fps  25
"""

import argparse
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from time import sleep

import cv2
import depthai as dai

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


class MJPEGStreamer(dai.node.HostNode):
    """
    depthai v3 HostNode that receives ImgFrames from the pipeline
    and pushes them to the HTTP server for MJPEG streaming.
    """

    def build(self, camera_output: dai.Node.Output, port: int) -> "MJPEGStreamer":
        self.link_args(camera_output)
        self.sendProcessingToPipeline(True)

        self.server = ThreadedHTTPServer(("0.0.0.0", port), VideoStreamHandler)
        t = threading.Thread(target=self.server.serve_forever, daemon=True)
        t.start()
        print(f"[oak-stream] Viewer  →  http://localhost:{port}")
        print(f"[oak-stream] Stream  →  http://localhost:{port}/stream")
        return self

    def process(self, frame: dai.Buffer) -> None:
        assert isinstance(frame, dai.ImgFrame)
        self.server.frametosend = frame.getCvFrame()


def main():
    parser = argparse.ArgumentParser(description="OAK MJPEG streaming server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"HTTP port (default: {DEFAULT_PORT})")
    parser.add_argument("--fps",  type=int, default=DEFAULT_FPS,  help=f"Camera FPS (default: {DEFAULT_FPS})")
    parser.add_argument("--device", type=str, default=None, help="Device name, ID, or IP (default: auto-detect)")
    args = parser.parse_args()

    device = dai.Device(dai.DeviceInfo(args.device)) if args.device else dai.Device()

    with dai.Pipeline(device) as pipeline:
        cam = pipeline.create(dai.node.Camera).build(fps=args.fps)
        pipeline.create(MJPEGStreamer).build(cam, port=args.port)
        print(f"[oak-stream] Pipeline running — press Ctrl+C to stop")
        pipeline.run()


if __name__ == "__main__":
    main()
