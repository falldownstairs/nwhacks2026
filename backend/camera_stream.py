# camera_stream.py
"""
WebSocket streaming endpoint for the HeartRateMonitor.
Streams video frames and vitals data to the frontend.
"""

import asyncio
import base64
import json

import cv2
import numpy as np
from camera import HeartRateMonitor
from fastapi import WebSocket, WebSocketDisconnect


class WebSocketHeartRateMonitor(HeartRateMonitor):
    """Extended HeartRateMonitor that can stream frames via WebSocket"""

    def __init__(self):
        super().__init__()
        self.is_running = False

    def get_frame_data(self):
        """Process one frame and return data for streaming"""
        ret, frame = self.cap.read()
        if not ret:
            return None

        current_time = __import__("time").time()

        # Detect face
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100)
        )

        face_detected = len(faces) > 0

        if face_detected:
            # Use largest face or previously tracked face for stability
            if self.last_face is not None:
                face = min(
                    faces,
                    key=lambda f: abs(f[0] - self.last_face[0])
                    + abs(f[1] - self.last_face[1]),
                )
            else:
                face = max(faces, key=lambda f: f[2] * f[3])

            self.last_face = face

            # Get ROIs
            rois = self.get_face_rois(frame, face)

            # Draw face box
            x, y, w, h = face
            cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)

            # Extract signals from all ROIs
            signals = []
            for name, roi in rois.items():
                rx, ry, rw, rh = roi
                color = (0, 255, 0) if name == "forehead" else (0, 200, 200)
                cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), color, 2)

                sig = self.extract_ppg_signal(frame, roi)
                if sig is not None:
                    signals.append(sig)

            if signals:
                combined_signal = np.mean(signals)
                self.signal_buffer.append(combined_signal)
                self.time_buffer.append(current_time)

            # Calculate vitals
            hr, hrv = self.calculate_vitals()
            if hr is not None:
                self.current_hr = hr
                self.current_hrv = hrv

            # Display on frame
            if self.current_hr is not None:
                if 50 <= self.current_hr <= 100:
                    hr_color = (0, 255, 0)
                elif 40 <= self.current_hr <= 120:
                    hr_color = (0, 200, 255)
                else:
                    hr_color = (0, 0, 255)

                cv2.putText(
                    frame,
                    f"Heart Rate: {self.current_hr:.0f} BPM",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    hr_color,
                    2,
                )

                # Display HRV if available
                if self.current_hrv is not None:
                    cv2.putText(
                        frame,
                        f"HRV: {self.current_hrv:.1f} ms",
                        (20, 80),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (100, 255, 100),
                        2,
                    )
                else:
                    cv2.putText(
                        frame,
                        "HRV: Calculating...",
                        (20, 80),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (150, 150, 150),
                        2,
                    )

                confidence = min(100, len(self.hr_history) * 10)
                cv2.putText(
                    frame,
                    f"Confidence: {confidence}%",
                    (20, 120),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (200, 200, 200),
                    2,
                )
                cv2.putText(
                    frame,
                    "Status: MEASURING",
                    (20, 160),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 255, 0),
                    2,
                )
            else:
                buffer_progress = len(self.signal_buffer)
                min_needed = int(self.fps * 8)
                progress = min(100, buffer_progress / min_needed * 100)
                cv2.putText(
                    frame,
                    f"Calibrating: {progress:.0f}%",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 165, 255),
                    2,
                )
                cv2.putText(
                    frame,
                    "Please stay still...",
                    (20, 80),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (200, 200, 200),
                    2,
                )
        else:
            self.last_face = None
            cv2.putText(
                frame,
                "No face detected",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 0, 255),
                2,
            )
            cv2.putText(
                frame,
                "Please face the camera",
                (20, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (200, 200, 200),
                2,
            )

        # Add tips
        cv2.putText(
            frame,
            "TIP: Stay still, good lighting helps!",
            (20, frame.shape[0] - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (150, 150, 150),
            1,
        )

        # Encode frame to JPEG then base64
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frame_base64 = base64.b64encode(buffer).decode("utf-8")

        return {
            "frame": frame_base64,
            "face_detected": face_detected,
            "heart_rate": round(self.current_hr) if self.current_hr else None,
            "hrv": round(self.current_hrv, 1) if self.current_hrv is not None else None,
            "confidence": min(100, len(self.hr_history) * 10),
            "calibration_progress": min(
                100, len(self.signal_buffer) / (self.fps * 8) * 100
            )
            if self.current_hr is None
            else 100,
        }

    def release(self):
        """Release camera resources"""
        if self.cap:
            self.cap.release()


# Global monitor instance (will be created per session)
active_monitors = {}


async def camera_websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for camera streaming"""
    await websocket.accept()

    monitor = None
    try:
        monitor = WebSocketHeartRateMonitor()
        monitor.is_running = True

        while monitor.is_running:
            data = monitor.get_frame_data()
            if data:
                await websocket.send_json(data)

            # ~30 FPS
            await asyncio.sleep(0.033)

            # Check for stop command
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.001)
                if msg == "stop":
                    break
            except asyncio.TimeoutError:
                pass

    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        if monitor:
            monitor.release()
        print("Camera released")
