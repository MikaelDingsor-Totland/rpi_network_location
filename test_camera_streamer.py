#!/usr/bin/env python3
"""Tests for the camera_streamer module."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import camera_streamer


class TestFindVideoDevices(unittest.TestCase):
    @patch('camera_streamer.glob.glob', return_value=['/dev/video0', '/dev/video1'])
    def test_returns_sorted_devices(self, mock_glob):
        devices = camera_streamer.find_video_devices()
        self.assertEqual(devices, ['/dev/video0', '/dev/video1'])
        mock_glob.assert_called_once_with('/dev/video*')

    @patch('camera_streamer.glob.glob', return_value=[])
    def test_returns_empty_when_no_devices(self, mock_glob):
        self.assertEqual(camera_streamer.find_video_devices(), [])


class TestValidateVideoDevice(unittest.TestCase):
    @patch('os.access', return_value=True)
    @patch('os.path.exists', return_value=True)
    def test_valid_device(self, mock_exists, mock_access):
        self.assertTrue(camera_streamer.validate_video_device('/dev/video0'))

    @patch('os.path.exists', return_value=False)
    def test_device_does_not_exist(self, mock_exists):
        self.assertFalse(camera_streamer.validate_video_device('/dev/video0'))

    @patch('os.access', return_value=False)
    @patch('os.path.exists', return_value=True)
    def test_device_not_readable(self, mock_exists, mock_access):
        self.assertFalse(camera_streamer.validate_video_device('/dev/video0'))


class TestCheckLibcameraAvailable(unittest.TestCase):
    @patch('camera_streamer.subprocess.run')
    @patch('camera_streamer.shutil.which', return_value='/usr/bin/rpicam-vid')
    def test_libcamera_detected(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout='Available cameras\n  0: ...'
        )
        self.assertTrue(camera_streamer.check_libcamera_available())

    @patch('camera_streamer.shutil.which', return_value=None)
    def test_no_libcamera_tool(self, mock_which):
        self.assertFalse(camera_streamer.check_libcamera_available())

    @patch('camera_streamer.subprocess.run')
    @patch('camera_streamer.shutil.which', return_value='/usr/bin/rpicam-vid')
    def test_libcamera_no_cameras(self, mock_which, mock_run):
        mock_run.return_value = MagicMock(
            returncode=1, stdout='No cameras detected'
        )
        self.assertFalse(camera_streamer.check_libcamera_available())


class TestDetectCamera(unittest.TestCase):
    @patch('camera_streamer.check_libcamera_available', return_value=False)
    @patch('camera_streamer.validate_video_device', return_value=True)
    @patch('camera_streamer.find_video_devices', return_value=['/dev/video0'])
    def test_detects_v4l2_device(self, mock_find, mock_validate, mock_libcam):
        result = camera_streamer.detect_camera()
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'v4l2')
        self.assertEqual(result['device'], '/dev/video0')

    @patch('camera_streamer.get_libcamera_tool', return_value='rpicam-vid')
    @patch('camera_streamer.check_libcamera_available', return_value=True)
    @patch('camera_streamer.validate_video_device', return_value=False)
    @patch('camera_streamer.find_video_devices', return_value=[])
    def test_falls_back_to_libcamera(self, mock_find, mock_validate, mock_libcam, mock_tool):
        result = camera_streamer.detect_camera()
        self.assertIsNotNone(result)
        self.assertEqual(result['type'], 'libcamera')
        self.assertEqual(result['device'], 'rpicam-vid')

    @patch('camera_streamer.check_libcamera_available', return_value=False)
    @patch('camera_streamer.validate_video_device', return_value=False)
    @patch('camera_streamer.find_video_devices', return_value=[])
    def test_no_camera_returns_none(self, mock_find, mock_validate, mock_libcam):
        result = camera_streamer.detect_camera()
        self.assertIsNone(result)


class TestBuildFfmpegCommand(unittest.TestCase):
    @patch('camera_streamer.shutil.which', return_value='/usr/bin/ffmpeg')
    def test_v4l2_command(self, mock_which):
        info = {'type': 'v4l2', 'device': '/dev/video0'}
        cmd = camera_streamer.build_ffmpeg_command(info, 'rtsp://localhost:8554/cam')
        self.assertEqual(cmd[0], 'ffmpeg')
        self.assertIn('/dev/video0', cmd)
        self.assertIn('rtsp://localhost:8554/cam', cmd)
        self.assertIn('-f', cmd)
        self.assertIn('v4l2', cmd)

    @patch('camera_streamer.shutil.which', return_value='/usr/bin/ffmpeg')
    def test_libcamera_command(self, mock_which):
        info = {'type': 'libcamera', 'device': 'rpicam-vid'}
        cmd = camera_streamer.build_ffmpeg_command(info, 'rtsp://localhost:8554/cam')
        self.assertEqual(cmd[0], 'sh')
        self.assertIn('-c', cmd)
        self.assertIn('rpicam-vid', cmd[2])
        self.assertIn('ffmpeg', cmd[2])

    @patch('camera_streamer.shutil.which', return_value=None)
    def test_ffmpeg_not_installed(self, mock_which):
        info = {'type': 'v4l2', 'device': '/dev/video0'}
        with self.assertRaises(FileNotFoundError):
            camera_streamer.build_ffmpeg_command(info)

    @patch('camera_streamer.shutil.which', return_value='/usr/bin/ffmpeg')
    def test_no_camera_info(self, mock_which):
        with self.assertRaises(RuntimeError):
            camera_streamer.build_ffmpeg_command(None)


class TestValidateConfigValue(unittest.TestCase):
    def test_safe_values_pass(self):
        for val in ['libx264', 'ultrafast', 'tcp', '1280x720',
                     'rtsp://192.168.100.101:30555/cam01', '15']:
            camera_streamer._validate_config_value('test', val)

    def test_unsafe_values_rejected(self):
        for val in ['$(rm -rf /)', '; echo pwned', 'a b', 'foo|bar']:
            with self.assertRaises(ValueError):
                camera_streamer._validate_config_value('test', val)


class TestCameraStreamer(unittest.TestCase):
    def test_initial_status(self):
        s = camera_streamer.CameraStreamer(restart_delay=0)
        status = s.status()
        self.assertFalse(status['streaming'])
        self.assertIsNone(status['camera'])
        self.assertIsNone(status['error'])
        self.assertEqual(status['restart_count'], 0)

    @patch('camera_streamer.detect_camera', return_value=None)
    def test_start_no_camera(self, mock_detect):
        s = camera_streamer.CameraStreamer(restart_delay=0)
        result = s.start()
        self.assertFalse(result['streaming'])
        self.assertIn('error', result)

    @patch('camera_streamer.subprocess.Popen')
    @patch('camera_streamer.build_ffmpeg_command', return_value=['ffmpeg', '-i', '/dev/video0'])
    @patch('camera_streamer.detect_camera', return_value={
        'type': 'v4l2', 'device': '/dev/video0',
        'devices': ['/dev/video0'], 'libcamera_available': False,
    })
    def test_start_and_stop(self, mock_detect, mock_build, mock_popen):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # process is running
        mock_popen.return_value = mock_proc

        s = camera_streamer.CameraStreamer(restart_delay=0)
        result = s.start()
        self.assertTrue(result['streaming'])

        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0
        result = s.stop()
        self.assertFalse(result['streaming'])

    @patch('camera_streamer.subprocess.Popen')
    @patch('camera_streamer.build_ffmpeg_command', return_value=['ffmpeg', '-i', '/dev/video0'])
    @patch('camera_streamer.detect_camera', return_value={
        'type': 'v4l2', 'device': '/dev/video0',
        'devices': ['/dev/video0'], 'libcamera_available': False,
    })
    def test_double_start_returns_already_streaming(self, mock_detect, mock_build, mock_popen):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        s = camera_streamer.CameraStreamer(restart_delay=0)
        s.start()
        result = s.start()
        self.assertTrue(result['streaming'])
        self.assertEqual(result['message'], 'Already streaming')

    def test_stop_when_not_streaming(self):
        s = camera_streamer.CameraStreamer(restart_delay=0)
        result = s.stop()
        self.assertFalse(result['streaming'])
        self.assertEqual(result['message'], 'Not streaming')

    def test_restart_delay_from_constructor(self):
        s = camera_streamer.CameraStreamer(restart_delay=10, max_restarts=3)
        self.assertEqual(s.restart_delay, 10)
        self.assertEqual(s.max_restarts, 3)

    @patch('camera_streamer.subprocess.Popen')
    @patch('camera_streamer.build_ffmpeg_command', return_value=['ffmpeg', '-i', '/dev/video0'])
    @patch('camera_streamer.detect_camera', return_value={
        'type': 'v4l2', 'device': '/dev/video0',
        'devices': ['/dev/video0'], 'libcamera_available': False,
    })
    def test_status_includes_restart_count(self, mock_detect, mock_build, mock_popen):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        s = camera_streamer.CameraStreamer(restart_delay=0)
        s.start()
        status = s.status()
        self.assertTrue(status['streaming'])
        self.assertEqual(status['restart_count'], 0)

    @patch('camera_streamer.subprocess.Popen')
    @patch('camera_streamer.build_ffmpeg_command', return_value=['ffmpeg', '-i', '/dev/video0'])
    @patch('camera_streamer.detect_camera', return_value={
        'type': 'v4l2', 'device': '/dev/video0',
        'devices': ['/dev/video0'], 'libcamera_available': False,
    })
    def test_start_returns_rtsp_url(self, mock_detect, mock_build, mock_popen):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        s = camera_streamer.CameraStreamer(
            rtsp_url='rtsp://192.168.100.101:30555/cam01',
            restart_delay=0,
        )
        result = s.start()
        self.assertTrue(result['streaming'])
        self.assertEqual(result['rtsp_url'], 'rtsp://192.168.100.101:30555/cam01')


if __name__ == '__main__':
    unittest.main()
