from flask import Blueprint, request, jsonify, current_app, Response, stream_with_context
import time
import numpy as np
import cv2

stream_bp = Blueprint('stream_bp', __name__, url_prefix='/api/stream')

@stream_bp.route("/", methods=["GET"], strict_slashes=False)
def stream():
    backend = current_app.config['backend']
    default_w, default_h = 1920, 1080
    try:
        w = int(request.args.get("width", default_w))
        h = int(request.args.get("height", default_h))
    except ValueError:
        w, h = default_w, default_h

    headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return Response(
        stream_with_context(backend.mjpeg_stream(w, h)),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers=headers,
        direct_passthrough=True,
    )

@stream_bp.route("/test", methods=["GET"])
def stream_test():
    boundary_line = b"--frame\r\n"

    def gen():
        w, h = 640, 360
        t = 0
        while True:
            bars = np.zeros((h, w, 3), dtype="uint8")
            for i, c in enumerate(
                [
                    (255, 0, 0),
                    (0, 255, 0),
                    (0, 0, 255),
                    (255, 255, 0),
                    (0, 255, 255),
                    (255, 0, 255),
                ]
            ):
                x0 = int(i * w / 6)
                x1 = int((i + 1) * w / 6)
                bars[:, x0:x1, :] = c
            cv2.putText(
                bars,
                f"TEST STREAM t={t}",
                (10, h - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (20, 20, 20),
                2,
                cv2.LINE_AA,
            )
            ok, jpg = cv2.imencode(".jpg", bars, [cv2.IMWRITE_JPEG_QUALITY, 80])
            data = jpg.tobytes() if ok else b""
            yield (
                boundary_line
                + b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(data)}\r\n\r\n".encode("ascii")
                + data
                + b"\r\n"
            )
            t += 1
            time.sleep(0.2)

    return Response(
        gen(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
