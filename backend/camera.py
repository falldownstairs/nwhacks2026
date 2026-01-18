import time
from collections import deque

import cv2
import numpy as np
from scipy import signal as scipy_signal
from scipy.fft import fft, fftfreq


class HeartRateMonitor:
    def __init__(self):
        self.cap = cv2.VideoCapture(0)

        # Get actual camera FPS
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.fps == 0:
            self.fps = 30
        print(f"Camera FPS: {self.fps}")

        self.buffer_size = int(self.fps * 15)  # 15 seconds of data
        self.signal_buffer = deque(maxlen=self.buffer_size)
        self.time_buffer = deque(maxlen=self.buffer_size)

        # Face detection
        self.face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )

        self.current_hr = None
        self.current_hrv = None
        self.hr_history = deque(maxlen=10)  # For smoothing results
        self.last_peaks = None  # Store peaks for HRV calculation

        # Bandpass filter for heart rate (0.7 - 3.0 Hz = 42-180 BPM)
        self.lowcut = 0.7
        self.highcut = 3.0

        self.start_time = time.time()
        self.last_face = None

    def create_bandpass_filter(self, lowcut, highcut, fs, order=3):
        """Create Butterworth bandpass filter"""
        nyq = 0.5 * fs
        low = lowcut / nyq
        high = highcut / nyq
        # Clamp to valid range
        low = max(0.01, min(low, 0.99))
        high = max(low + 0.01, min(high, 0.99))
        b, a = scipy_signal.butter(order, [low, high], btype="band")
        return b, a

    def bandpass_filter(self, data, lowcut, highcut, fs, order=3):
        """Apply bandpass filter to signal"""
        b, a = self.create_bandpass_filter(lowcut, highcut, fs, order)
        # Use filtfilt for zero-phase filtering
        y = scipy_signal.filtfilt(
            b, a, data, padlen=min(len(data) - 1, 3 * max(len(a), len(b)))
        )
        return y

    def extract_ppg_signal(self, frame, roi):
        """Extract PPG signal using green channel with spatial averaging"""
        x, y, w, h = roi

        # Ensure ROI is within frame bounds
        h_frame, w_frame = frame.shape[:2]
        x = max(0, min(x, w_frame - 1))
        y = max(0, min(y, h_frame - 1))
        w = min(w, w_frame - x)
        h = min(h, h_frame - y)

        if w <= 0 or h <= 0:
            return None

        roi_frame = frame[y : y + h, x : x + w]

        if roi_frame.size == 0:
            return None

        # Use green channel (best for PPG) with some red channel
        # Green has strongest PPG signal in skin
        b, g, r = cv2.split(roi_frame)

        # Weighted combination - green is primary
        signal = 0.7 * np.mean(g) + 0.3 * np.mean(r)

        return signal

    def get_face_rois(self, frame, face):
        """Get multiple ROIs from face for better signal"""
        x, y, w, h = face

        rois = {}

        # Forehead ROI
        rois["forehead"] = (
            x + int(w * 0.25),
            y + int(h * 0.05),
            int(w * 0.5),
            int(h * 0.15),
        )

        # Left cheek
        rois["left_cheek"] = (
            x + int(w * 0.1),
            y + int(h * 0.45),
            int(w * 0.25),
            int(h * 0.25),
        )

        # Right cheek
        rois["right_cheek"] = (
            x + int(w * 0.65),
            y + int(h * 0.45),
            int(w * 0.25),
            int(h * 0.25),
        )

        return rois

    def detrend_signal(self, signal):
        """Remove slow trends from signal using polynomial detrending"""
        if len(signal) < 10:
            return signal
        x = np.arange(len(signal))
        # Fit and remove 2nd order polynomial trend
        coeffs = np.polyfit(x, signal, 2)
        trend = np.polyval(coeffs, x)
        return signal - trend

    def calculate_hr_fft(self, signal, fs):
        """Calculate heart rate using FFT - more robust"""
        n = len(signal)

        # Apply Hanning window to reduce spectral leakage
        window = np.hanning(n)
        signal_windowed = signal * window

        # Compute FFT
        yf = np.abs(fft(signal_windowed))
        xf = fftfreq(n, 1 / fs)

        # Only look at positive frequencies in heart rate range
        mask = (xf >= self.lowcut) & (xf <= self.highcut)
        xf_hr = xf[mask]
        yf_hr = yf[mask]

        if len(yf_hr) == 0:
            return None

        # Find peak frequency
        peak_idx = np.argmax(yf_hr)
        peak_freq = xf_hr[peak_idx]

        # Convert to BPM
        hr = peak_freq * 60

        return hr

    def calculate_hrv_from_peaks(self, peaks, fs):
        """
        Calculate proper HRV using RMSSD (Root Mean Square of Successive Differences).

        HRV (Heart Rate Variability) measures the variation in time intervals between
        consecutive heartbeats. This is a key indicator of autonomic nervous system function.

        RMSSD is the most common time-domain HRV metric for short-term measurements:
        - Calculates R-R intervals (time between peaks) in milliseconds
        - Computes successive differences between intervals
        - Returns root mean square of these differences

        Typical RMSSD values for healthy adults at rest: 20-100ms
        - Higher values indicate better cardiovascular fitness
        - Lower values may indicate stress or poor cardiovascular health

        Args:
            peaks: Array of peak indices in the signal
            fs: Sampling frequency (Hz)

        Returns:
            RMSSD value in milliseconds, or None if calculation fails
        """
        if peaks is None or len(peaks) < 3:
            return None

        # Calculate R-R intervals in milliseconds
        rr_intervals = np.diff(peaks) / fs * 1000  # Convert to ms

        # Filter physiologically valid intervals (300-2000ms = 30-200 BPM)
        valid_rr = rr_intervals[(rr_intervals >= 300) & (rr_intervals <= 2000)]

        if len(valid_rr) < 3:
            return None

        # Calculate RMSSD (most common HRV metric for short-term measurements)
        successive_diffs = np.diff(valid_rr)
        rmssd = np.sqrt(np.mean(successive_diffs**2))

        # Typical RMSSD values range from 20-100ms for healthy adults
        # Values outside this range may indicate measurement issues
        if rmssd < 5 or rmssd > 200:
            return None

        return rmssd

    def calculate_hr_peaks(self, signal, fs):
        """Calculate heart rate using peak detection and return peaks for HRV"""
        # Find peaks
        min_distance = int(fs * 0.4)  # Minimum 0.4s between beats (150 BPM max)

        # Normalize signal
        signal_norm = (signal - np.min(signal)) / (
            np.max(signal) - np.min(signal) + 1e-10
        )

        peaks, properties = scipy_signal.find_peaks(
            signal_norm, distance=min_distance, prominence=0.1, height=0.3
        )

        if len(peaks) < 3:
            return None, None

        # Calculate intervals between peaks
        intervals = np.diff(peaks) / fs  # in seconds

        # Remove outliers (intervals outside reasonable range)
        valid_intervals = intervals[
            (intervals > 0.33) & (intervals < 1.5)
        ]  # 40-180 BPM

        if len(valid_intervals) < 2:
            return None, None

        # Calculate mean HR from intervals
        mean_interval = np.median(valid_intervals)
        hr = 60 / mean_interval

        return hr, peaks

    def calculate_vitals(self):
        """Calculate heart rate using multiple methods"""
        min_samples = int(self.fps * 5)  # Need at least 5 seconds

        if len(self.signal_buffer) < min_samples:
            return None, None

        try:
            signal = np.array(self.signal_buffer)

            # Calculate actual sample rate from timestamps
            if len(self.time_buffer) > 1:
                time_arr = np.array(self.time_buffer)
                actual_duration = time_arr[-1] - time_arr[0]
                actual_fs = (
                    len(signal) / actual_duration if actual_duration > 0 else self.fps
                )
            else:
                actual_fs = self.fps

            # Step 1: Detrend to remove slow drifts
            signal = self.detrend_signal(signal)

            # Step 2: Normalize
            signal = (signal - np.mean(signal)) / (np.std(signal) + 1e-10)

            # Step 3: Bandpass filter
            try:
                signal_filtered = self.bandpass_filter(
                    signal, self.lowcut, self.highcut, actual_fs
                )
            except Exception:
                signal_filtered = signal

            # Method 1: FFT-based (more robust)
            hr_fft = self.calculate_hr_fft(signal_filtered, actual_fs)

            # Method 2: Peak detection (also returns peaks for HRV)
            hr_peaks, peaks = self.calculate_hr_peaks(signal_filtered, actual_fs)

            # Combine results
            hr_estimates = [
                hr for hr in [hr_fft, hr_peaks] if hr is not None and 45 < hr < 160
            ]

            if not hr_estimates:
                return None, None

            # Use median of valid estimates
            hr = np.median(hr_estimates)

            # Add to history for smoothing
            self.hr_history.append(hr)

            # Return smoothed HR (median of last few readings)
            if len(self.hr_history) >= 3:
                smoothed_hr = np.median(list(self.hr_history)[-5:])
            else:
                smoothed_hr = hr

            # Calculate proper HRV using RMSSD from inter-beat intervals
            hrv = None
            if peaks is not None and len(peaks) >= 3:
                hrv = self.calculate_hrv_from_peaks(peaks, actual_fs)
                self.last_peaks = peaks  # Store for reference

            # If HRV calculation failed, return None instead of 0
            return smoothed_hr, hrv

        except Exception as e:
            print(f"Processing error: {e}")
            return None, None

    def run(self):
        """Main loop"""
        print("=" * 50)
        print("     IMPROVED HEART RATE MONITOR")
        print("=" * 50)
        print("\nInstructions for best results:")
        print("1. Ensure GOOD, EVEN lighting (avoid shadows)")
        print("2. Stay VERY STILL - movement ruins the signal")
        print("3. Face the camera directly")
        print("4. Wait 10-15 seconds for accurate reading")
        print("5. Press 'q' to quit")
        print("-" * 50)

        frame_count = 0

        while True:
            ret, frame = self.cap.read()
            if not ret:
                break

            frame_count += 1
            current_time = time.time()

            # Detect face
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(
                gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100)
            )

            if len(faces) > 0:
                # Use largest face or previously tracked face for stability
                if self.last_face is not None:
                    # Find face closest to last position
                    face = min(
                        faces,
                        key=lambda f: abs(f[0] - self.last_face[0])
                        + abs(f[1] - self.last_face[1]),
                    )
                else:
                    face = max(faces, key=lambda f: f[2] * f[3])  # Largest face

                self.last_face = face

                # Get multiple ROIs
                rois = self.get_face_rois(frame, face)

                # Draw face box
                x, y, w, h = face
                cv2.rectangle(frame, (x, y), (x + w, y + h), (255, 0, 0), 2)

                # Extract signals from all ROIs and average them
                signals = []
                for name, roi in rois.items():
                    rx, ry, rw, rh = roi
                    # Draw ROI
                    color = (0, 255, 0) if name == "forehead" else (0, 200, 200)
                    cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), color, 2)

                    # Extract signal
                    sig = self.extract_ppg_signal(frame, roi)
                    if sig is not None:
                        signals.append(sig)

                if signals:
                    # Average all ROI signals for robustness
                    combined_signal = np.mean(signals)
                    self.signal_buffer.append(combined_signal)
                    self.time_buffer.append(current_time)

                # Calculate every 15 frames (~0.5 second)
                if frame_count % 15 == 0:
                    hr, hrv = self.calculate_vitals()
                    if hr is not None:
                        self.current_hr = hr
                        self.current_hrv = hrv

                # Display results
                if self.current_hr is not None:
                    # Color code the HR
                    if 50 <= self.current_hr <= 100:
                        hr_color = (0, 255, 0)  # Green - normal range
                    elif 40 <= self.current_hr <= 120:
                        hr_color = (0, 200, 255)  # Orange - borderline
                    else:
                        hr_color = (0, 0, 255)  # Red - unusual

                    cv2.putText(
                        frame,
                        f"Heart Rate: {self.current_hr:.0f} BPM",
                        (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1,
                        hr_color,
                        2,
                    )

                    # Display HRV if available (RMSSD in milliseconds)
                    if self.current_hrv is not None:
                        cv2.putText(
                            frame,
                            f"HRV (RMSSD): {self.current_hrv:.1f} ms",
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
                    min_needed = int(self.fps * 3)
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

            # Add tips at bottom
            cv2.putText(
                frame,
                "TIP: Stay still, good lighting helps!",
                (20, frame.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (150, 150, 150),
                1,
            )

            # Show frame
            cv2.imshow("Heart Rate Monitor - Press Q to quit", frame)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        self.cap.release()
        cv2.destroyAllWindows()

        # Print final stats
        if self.hr_history:
            print("\n" + "=" * 50)
            print("Session Summary:")
            print(f"  Average HR: {np.mean(list(self.hr_history)):.1f} BPM")
            print(f"  Min HR: {np.min(list(self.hr_history)):.1f} BPM")
            print(f"  Max HR: {np.max(list(self.hr_history)):.1f} BPM")
            print("=" * 50)


if __name__ == "__main__":
    monitor = HeartRateMonitor()
    monitor.run()
