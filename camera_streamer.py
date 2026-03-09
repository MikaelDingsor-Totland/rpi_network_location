#!/usr/bin/env python3
"""
Camera streaming module for Raspberry Pi.
Detects available video devices, validates them, and streams via RTSP using ffmpeg.
Supports V4L2 devices and libcamera fallback for modern Raspberry Pi OS.
"""

import os
import glob
import subprocess
import shutil
import logging
import threading
import re
import signal

import config

# Timeout (seconds) when terminating the streaming process
_SHUTDOWN_TIMEOUT = 5

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def find_video_devices():
    """Discover available V4L2 video devices.

    Returns:
        list[str]: Sorted list of device paths, e.g. ['/dev/video0', '/dev/video1'].
    """
    devices = sorted(glob.glob('/dev/video*'))
    return devices


def check_libcamera_available():
    """Check whether libcamera tools are installed and a camera is detected.

    Returns:
        bool: True if libcamera-vid (or rpicam-vid) is available and detects a camera.
    """
    for tool in ('rpicam-vid', 'libcamera-vid'):
        if shutil.which(tool):
            try:
                result = subprocess.run(
                    [tool, '--list-cameras'],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0 and 'Available cameras' in result.stdout:
                    logger.info("libcamera detected via %s", tool)
                    return True
            except (subprocess.TimeoutExpired, OSError) as exc:
                logger.debug("libcamera check with %s failed: %s", tool, exc)
    return False


def get_libcamera_tool():
    """Return the name of the available libcamera video tool.

    Returns:
        str or None: 'rpicam-vid' or 'libcamera-vid' if available, else None.
    """
    for tool in ('rpicam-vid', 'libcamera-vid'):
        if shutil.which(tool):
            return tool
    return None


def validate_video_device(device_path):
    """Validate that a V4L2 device exists and is readable.

    Args:
        device_path: Path to the video device (e.g. '/dev/video0').

    Returns:
        bool: True if the device file exists and the current user can read it.
    """
    if not os.path.exists(device_path):
        logger.error("Video device %s does not exist", device_path)
        return False
    if not os.access(device_path, os.R_OK):
        logger.error(
            "Video device %s exists but is not readable (check permissions)", device_path
        )
        return False
    return True


def get_v4l2_device_info(device_path):
    """Query V4L2 device capabilities using v4l2-ctl.

    Args:
        device_path: Path to the video device.

    Returns:
        str or None: Device info string, or None on failure.
    """
    if not shutil.which('v4l2-ctl'):
        return None
    try:
        result = subprocess.run(
            ['v4l2-ctl', '--device', device_path, '--all'],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("v4l2-ctl query failed for %s: %s", device_path, exc)
    return None


def detect_camera():
    """Detect the best available camera source.

    Checks V4L2 devices first, then falls back to libcamera.

    Returns:
        dict: Camera information with keys:
            - 'type': 'v4l2' or 'libcamera'
            - 'device': device path (for v4l2) or libcamera tool name
            - 'devices': list of all discovered V4L2 devices
            - 'libcamera_available': bool
        None if no camera is found.
    """
    v4l2_devices = find_video_devices()
    libcamera = check_libcamera_available()

    # Try configured device first
    configured = getattr(config, 'CAMERA_DEVICE', '/dev/video0')
    if validate_video_device(configured):
        return {
            'type': 'v4l2',
            'device': configured,
            'devices': v4l2_devices,
            'libcamera_available': libcamera,
        }

    # Try any other V4L2 device
    for dev in v4l2_devices:
        if dev != configured and validate_video_device(dev):
            logger.info("Falling back to alternative V4L2 device %s", dev)
            return {
                'type': 'v4l2',
                'device': dev,
                'devices': v4l2_devices,
                'libcamera_available': libcamera,
            }

    # Fall back to libcamera
    if libcamera:
        tool = get_libcamera_tool()
        logger.info("No V4L2 device found; using libcamera (%s)", tool)
        return {
            'type': 'libcamera',
            'device': tool,
            'devices': v4l2_devices,
            'libcamera_available': True,
        }

    logger.error(
        "No camera found. V4L2 devices: %s, libcamera available: %s",
        v4l2_devices, libcamera,
    )
    return None


def _validate_config_value(name, value):
    """Validate that a config value contains only safe characters.

    Raises:
        ValueError: If the value contains shell-unsafe characters.
    """
    if not re.match(r'^[A-Za-z0-9_./:@\-]+$', value):
        raise ValueError(
            f"Config value '{name}' contains unsafe characters: {value!r}"
        )


def build_ffmpeg_command(camera_info, rtsp_url=None):
    """Build the ffmpeg command list for RTSP streaming.

    Args:
        camera_info: dict returned by detect_camera().
        rtsp_url: RTSP URL to publish to (overrides config).

    Returns:
        list[str]: Command and arguments suitable for subprocess.Popen.

    Raises:
        FileNotFoundError: If ffmpeg is not installed.
        RuntimeError: If camera_info is None or has an unsupported type.
        ValueError: If a config value contains unsafe characters.
    """
    if not shutil.which('ffmpeg'):
        raise FileNotFoundError(
            "ffmpeg is not installed. Install it with: sudo apt install ffmpeg"
        )

    if camera_info is None:
        raise RuntimeError("No camera detected. Cannot build ffmpeg command.")

    url = rtsp_url or getattr(config, 'RTSP_URL', 'rtsp://localhost:8554/cam')
    resolution = getattr(config, 'CAMERA_RESOLUTION', '1280x720')
    framerate = str(getattr(config, 'CAMERA_FRAMERATE', 15))
    input_format = getattr(config, 'CAMERA_INPUT_FORMAT', 'mjpeg')
    encoder = getattr(config, 'CAMERA_ENCODER', 'libx264')
    preset = getattr(config, 'CAMERA_PRESET', 'ultrafast')
    transport = getattr(config, 'RTSP_TRANSPORT', 'tcp')

    # Validate all values that will be interpolated into a shell command
    for name, val in [('RTSP_URL', url), ('CAMERA_RESOLUTION', resolution),
                      ('CAMERA_FRAMERATE', framerate),
                      ('CAMERA_INPUT_FORMAT', input_format),
                      ('CAMERA_ENCODER', encoder), ('CAMERA_PRESET', preset),
                      ('RTSP_TRANSPORT', transport)]:
        _validate_config_value(name, val)

    if camera_info['type'] == 'v4l2':
        cmd = [
            'ffmpeg',
            '-f', 'v4l2',
            '-input_format', input_format,
            '-video_size', resolution,
            '-framerate', framerate,
            '-i', camera_info['device'],
            '-c:v', encoder,
            '-preset', preset,
            '-tune', 'zerolatency',
            '-f', 'rtsp',
            '-rtsp_transport', transport,
            url,
        ]
    elif camera_info['type'] == 'libcamera':
        width, height = resolution.split('x')
        libcamera_cmd = [
            camera_info['device'],
            '--width', width,
            '--height', height,
            '--framerate', framerate,
            '--codec', 'h264',
            '--inline',
            '-t', '0',
            '-o', '-',
        ]
        # Pipe libcamera output into ffmpeg
        cmd = [
            'sh', '-c',
            ' '.join(libcamera_cmd) + ' | ffmpeg -f h264 -i - '
            f'-c:v {encoder} -preset {preset} -tune zerolatency '
            f'-f rtsp -rtsp_transport {transport} {url}',
        ]
    else:
        raise RuntimeError(f"Unsupported camera type: {camera_info['type']}")

    return cmd


class CameraStreamer:
    """Manage the lifecycle of an RTSP camera stream.

    Supports automatic restart so that consumers like Frigate always
    have a live feed.  When *restart_delay* > 0 the streamer spawns a
    background watchdog thread that restarts ffmpeg whenever it exits
    unexpectedly.
    """

    def __init__(self, rtsp_url=None, restart_delay=None, max_restarts=None):
        """
        Args:
            rtsp_url: Optional RTSP URL override.
            restart_delay: Seconds to wait before restarting after a crash.
                           ``None`` reads from config (default 5).
                           ``0`` disables auto-restart.
            max_restarts: Maximum consecutive restart attempts before giving
                          up.  ``None`` reads from config (default 0 = unlimited).
        """
        self.rtsp_url = rtsp_url
        self.restart_delay = (
            restart_delay if restart_delay is not None
            else getattr(config, 'CAMERA_RESTART_DELAY', 5)
        )
        self.max_restarts = (
            max_restarts if max_restarts is not None
            else getattr(config, 'CAMERA_MAX_RESTARTS', 0)
        )
        self._process = None
        self._lock = threading.Lock()
        self._watchdog_stop = threading.Event()
        self._watchdog_thread = None
        self.camera_info = None
        self.error = None
        self.restart_count = 0

    # -- public API -----------------------------------------------------------

    def status(self):
        """Return the current streamer status as a dict."""
        with self._lock:
            running = self._process is not None and self._process.poll() is None
            return {
                'streaming': running,
                'camera': self.camera_info,
                'error': self.error,
                'restart_count': self.restart_count,
            }

    def start(self):
        """Detect camera and start streaming.

        Returns:
            dict: Status information.
        """
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return {'streaming': True, 'message': 'Already streaming'}

            self.error = None
            self.restart_count = 0
            self.camera_info = detect_camera()

            if self.camera_info is None:
                self.error = self._no_camera_message()
                logger.error(self.error)
                return {'streaming': False, 'error': self.error}

            ok = self._launch_process()
            if not ok:
                return {'streaming': False, 'error': self.error}

            # Start watchdog for auto-restart
            if self.restart_delay > 0:
                self._watchdog_stop.clear()
                self._watchdog_thread = threading.Thread(
                    target=self._watchdog, daemon=True,
                )
                self._watchdog_thread.start()

            return {
                'streaming': True,
                'camera': self.camera_info,
                'rtsp_url': self.rtsp_url or getattr(
                    config, 'RTSP_URL', 'rtsp://localhost:8554/cam'
                ),
            }

    def stop(self):
        """Stop the active stream and disable auto-restart.

        Returns:
            dict: Status information.
        """
        # Signal the watchdog to stop *before* acquiring the lock so the
        # watchdog can finish its current sleep and exit.
        self._watchdog_stop.set()

        with self._lock:
            if self._process is None or self._process.poll() is not None:
                self._process = None
                return {'streaming': False, 'message': 'Not streaming'}

            self._process.terminate()
            try:
                self._process.wait(timeout=_SHUTDOWN_TIMEOUT)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=_SHUTDOWN_TIMEOUT)

            self._process = None
            logger.info("Stream stopped")
            return {'streaming': False, 'message': 'Stream stopped'}

    # -- internal helpers -----------------------------------------------------

    def _launch_process(self):
        """Build the command and spawn ffmpeg.  Caller must hold *_lock*.

        Returns:
            bool: True on success.
        """
        try:
            cmd = build_ffmpeg_command(self.camera_info, self.rtsp_url)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            self.error = str(exc)
            logger.error(self.error)
            return False

        logger.info("Starting stream: %s", ' '.join(cmd))
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            self.error = f"Failed to start streaming process: {exc}"
            logger.error(self.error)
            return False

        return True

    def _watchdog(self):
        """Background thread that restarts the stream when ffmpeg exits."""
        while not self._watchdog_stop.is_set():
            # Sleep in small increments so we can react to stop() quickly.
            self._watchdog_stop.wait(timeout=2)
            if self._watchdog_stop.is_set():
                break

            with self._lock:
                if self._process is None:
                    break
                if self._process.poll() is None:
                    # Still running — nothing to do.
                    continue

                # Process exited.
                rc = self._process.returncode
                logger.warning(
                    "ffmpeg exited with code %s (restart #%d)",
                    rc, self.restart_count + 1,
                )

                if (self.max_restarts > 0
                        and self.restart_count >= self.max_restarts):
                    self.error = (
                        f"Stream crashed {self.restart_count} times; "
                        "giving up. Check camera and network."
                    )
                    logger.error(self.error)
                    self._process = None
                    break

            # Wait before restart (outside the lock).
            if self._watchdog_stop.wait(timeout=self.restart_delay):
                break

            with self._lock:
                self.restart_count += 1
                logger.info("Restarting stream (attempt #%d)…",
                            self.restart_count)
                if not self._launch_process():
                    logger.error("Restart failed: %s", self.error)
                    break

    @staticmethod
    def _no_camera_message():
        lines = [
            "No camera detected. Troubleshooting steps:",
            "1. Check that the camera is connected properly.",
            "2. Run 'ls /dev/video*' to list V4L2 devices.",
            "3. If using a Raspberry Pi Camera Module, ensure it is enabled:",
            "   - Run 'sudo raspi-config' -> Interface Options -> Camera -> Enable",
            "   - Or add 'start_x=1' and 'gpu_mem=128' to /boot/config.txt",
            "     (on Bookworm+: /boot/firmware/config.txt)",
            "4. Load the V4L2 driver: 'sudo modprobe bcm2835-v4l2'",
            "5. On modern Raspberry Pi OS (Bookworm+), use libcamera tools:",
            "   - Install: 'sudo apt install rpicam-apps'",
            "   - Test:   'rpicam-vid --list-cameras'",
        ]
        return '\n'.join(lines)


if __name__ == '__main__':
    print("=== Camera Detection ===")
    info = detect_camera()
    if info is None:
        print(CameraStreamer._no_camera_message())
    else:
        print(f"Camera type : {info['type']}")
        print(f"Device      : {info['device']}")
        print(f"V4L2 devices: {info['devices']}")
        print(f"libcamera   : {info['libcamera_available']}")

        try:
            cmd = build_ffmpeg_command(info)
            print(f"\nffmpeg command:\n  {' '.join(cmd)}")
        except (FileNotFoundError, RuntimeError) as exc:
            print(f"\nCannot build command: {exc}")

        print("\nStarting stream …")
        streamer = CameraStreamer()
        result = streamer.start()
        print(result)
        if result.get('streaming'):
            try:
                input("Press Enter to stop streaming …\n")
            except KeyboardInterrupt:
                pass
            streamer.stop()
