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
import signal

import config

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
        cmd = [
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
            ' '.join(cmd) + ' | ffmpeg -f h264 -i - '
            f'-c:v {encoder} -preset {preset} -tune zerolatency '
            f'-f rtsp -rtsp_transport {transport} {url}',
        ]
    else:
        raise RuntimeError(f"Unsupported camera type: {camera_info['type']}")

    return cmd


class CameraStreamer:
    """Manage the lifecycle of an RTSP camera stream."""

    def __init__(self, rtsp_url=None):
        """
        Args:
            rtsp_url: Optional RTSP URL override.
        """
        self.rtsp_url = rtsp_url
        self._process = None
        self._lock = threading.Lock()
        self.camera_info = None
        self.error = None

    # -- public API -----------------------------------------------------------

    def status(self):
        """Return the current streamer status as a dict."""
        with self._lock:
            running = self._process is not None and self._process.poll() is None
            return {
                'streaming': running,
                'camera': self.camera_info,
                'error': self.error,
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
            self.camera_info = detect_camera()

            if self.camera_info is None:
                self.error = self._no_camera_message()
                logger.error(self.error)
                return {'streaming': False, 'error': self.error}

            try:
                cmd = build_ffmpeg_command(self.camera_info, self.rtsp_url)
            except (FileNotFoundError, RuntimeError) as exc:
                self.error = str(exc)
                logger.error(self.error)
                return {'streaming': False, 'error': self.error}

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
                return {'streaming': False, 'error': self.error}

            return {
                'streaming': True,
                'camera': self.camera_info,
                'command': ' '.join(cmd),
            }

    def stop(self):
        """Stop the active stream.

        Returns:
            dict: Status information.
        """
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                self._process = None
                return {'streaming': False, 'message': 'Not streaming'}

            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)

            self._process = None
            logger.info("Stream stopped")
            return {'streaming': False, 'message': 'Stream stopped'}

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _no_camera_message():
        lines = [
            "No camera detected. Troubleshooting steps:",
            "1. Check that the camera is connected properly.",
            "2. Run 'ls /dev/video*' to list V4L2 devices.",
            "3. If using a Raspberry Pi Camera Module, ensure it is enabled:",
            "   - Run 'sudo raspi-config' -> Interface Options -> Camera -> Enable",
            "   - Or add 'start_x=1' and 'gpu_mem=128' to /boot/config.txt",
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
