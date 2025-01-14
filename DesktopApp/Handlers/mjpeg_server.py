import logging
from flask import Flask, Response 
import time
import threading
from cv2 import imencode
from numpy import ndarray, uint8


class mjpeg_server():
    from DesktopApp.iFrame import iFrame
    def __init__(self, frame:iFrame ):
        self.Frame = frame 
        self.is_running = True
        
    def update_live_frame(self, frame):
        self.live_frame = frame

    def generate_frame(self):
        """
        Generator to serve MJPEG frames from the live frame.
        Streams the live frame directly without resizing.
        """
        while self.is_running:
            if hasattr(self, 'live_frame') and self.live_frame is not None:
                try:
                    # Ensure the frame is a valid NumPy array
                    if isinstance(self.live_frame, ndarray) and self.live_frame.size > 0:
                        # Ensure the frame has the correct type and format
                        if self.live_frame.dtype != uint8:
                            self.live_frame = self.live_frame.astype(uint8)

                        # Encode the frame as JPEG
                        _, jpeg = imencode('.jpg', self.live_frame)
                        frame = jpeg.tobytes()

                        # Yield the MJPEG frame
                        yield (b'--frame\r\n'
                            b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                    else:
                        continue
                        #logging.warning("Invalid live_frame: Not a proper image array")
                except Exception as e:
                    self.Frame.logger.error(f"Error encoding frame: {e}")
            else:
                # Log a warning only once every few seconds
                if not hasattr(self, 'last_log_time') or time.time() - self.last_log_time > 5:
                    self.Frame.logger.warning("No live frame available to stream.")
                    self.last_log_time = time.time()
                time.sleep(0.1)  # Maintain loop frequency

            time.sleep(1/10)  # Maintain ~30 FPS


    def start_mjpeg_server(self, settings):
        """
        Starts an MJPEG server using Flask if allowed in the settings.
        Args:
            settings (dict): MJPEG server settings containing:
                            - allow_mjpeg_server (bool)
                            - server_port (int)
                            - host (str)
        """
        if not settings.get("allow_mjpeg_server", False):
            self.Frame.send_log_message("MJPEG server is disabled in settings.",logging.info)
            return

        app = Flask(__name__)

        @app.route('/video_feed')
        def video_feed():
            return Response(self.generate_frame(),
                            mimetype='multipart/x-mixed-replace; boundary=frame')

        host = settings.get("host", "0.0.0.0")
        port = settings.get("server_port", 5001)
        self.Frame.send_log_message(f"Starting MJPEG server on {host}:{port}...",logging.info)

        # Run the Flask app in a separate thread
        self.mjpeg_server_thread = threading.Thread(target=lambda: app.run(
            host=host, port=port, debug=False, use_reloader=False))
        self.mjpeg_server_thread.daemon = True  # Ensures thread stops with main program
        self.mjpeg_server_thread.start()
