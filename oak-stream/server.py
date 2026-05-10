#!/usr/bin/env python3
"""
OAK-4 MJPEG Streaming Server

Connects to a Luxonis OAK-4 device, captures the main camera,
and streams it as MJPEG over HTTP.

Usage:
    pip install -r requirements.txt
    python server.py

Then open http://localhost:8080 in your browser.
Optional: python server.py --port 9000 --fps 30 --width 1280 --height 720
"""

import argparse
import threading
import time
import sys

try:
    import cv2
except ImportError:
    sys.exit("Missing dependency: pip install opencv-python")

try:
    import depthai as dai
except ImportError:
    sys.exit("Missing dependency: pip install depthai")

try:
    from flask import Flask, Response
except ImportError:
    sys.exit("Missing dependency: pip install flask")


app = Flask(__name__)

_frame_lock = threading.Lock()
_current_frame = None
_camera_error = None


INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>OAK-4 Live Stream</title>
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
      gap: 12px;
    }
    h1 { font-size: 1rem; letter-spacing: 0.05em; opacity: 0.5; }
    img {
      max-width: 100%;
      max-height: 90vh;
      display: block;
      border: 1px solid #333;
    }
    #status { font-size: 0.8rem; opacity: 0.4; }
  </style>
</head>
<body>
  <h1>OAK-4 LIVE</h1>
  <img src="/stream" alt="OAK-4 stream"
       onerror="document.getElementById('status').textContent = 'Stream error — is the device connected?'" />
  <p id="status">Connecting…</p>
  <script>
    const img = document.querySelector('img');
    img.onload = () => document.getElementById('status').textContent = 'Streaming';
  </script>
</body>
</html>"""


@app.route('/')
def index():
    return INDEX_HTML


def _generate_frames(quality: int):
    global _current_frame
    while True:
        with _frame_lock:
            frame = _current_frame

        if frame is None:
            time.sleep(0.02)
            continue

        ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ret:
            continue

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n'
        )


@app.route('/stream')
def stream():
    quality = app.config.get('JPEG_QUALITY', 85)
    return Response(
        _generate_frames(quality),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


def _camera_thread(width: int, height: int, fps: int):
    global _current_frame, _camera_error

    pipeline = dai.Pipeline()

    cam = pipeline.create(dai.node.Camera)
    cam.setBoardSocket(dai.CameraBoardSocket.CAM_A)
    cam.setFps(fps)

    # Resize via ImageManip so we control output resolution
    manip = pipeline.create(dai.node.ImageManip)
    manip.initialConfig.setResize(width, height)
    manip.initialConfig.setFrameType(dai.ImgFrame.Type.BGR888p)
    manip.setMaxOutputFrameSize(width * height * 3)
    cam.isp.link(manip.inputImage)

    xout = pipeline.create(dai.node.XLinkOut)
    xout.setStreamName("video")
    manip.out.link(xout.input)

    try:
        with dai.Device(pipeline) as device:
            queue = device.getOutputQueue("video", maxSize=4, blocking=False)
            print(f"[oak-stream] Camera ready — streaming {width}x{height} @ {fps} fps")
            while True:
                msg = queue.get()
                img = msg.getCvFrame()
                with _frame_lock:
                    _current_frame = img
    except Exception as exc:
        _camera_error = str(exc)
        print(f"[oak-stream] Camera error: {exc}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="OAK-4 MJPEG streaming server")
    parser.add_argument('--port',    type=int, default=8080,  help='HTTP port (default: 8080)')
    parser.add_argument('--fps',     type=int, default=30,    help='Camera FPS (default: 30)')
    parser.add_argument('--width',   type=int, default=1280,  help='Frame width  (default: 1280)')
    parser.add_argument('--height',  type=int, default=720,   help='Frame height (default: 720)')
    parser.add_argument('--quality', type=int, default=85,    help='JPEG quality 1-100 (default: 85)')
    args = parser.parse_args()

    app.config['JPEG_QUALITY'] = args.quality

    t = threading.Thread(
        target=_camera_thread,
        args=(args.width, args.height, args.fps),
        daemon=True
    )
    t.start()

    print(f"[oak-stream] Open http://localhost:{args.port} in your browser")
    app.run(host='0.0.0.0', port=args.port, threaded=True)


if __name__ == '__main__':
    main()
