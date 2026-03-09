#!/usr/bin/env python3
"""
Flask web server for live location dashboard
Uses IP-based geolocation
Provides camera streaming control via RTSP
"""

from flask import Flask, render_template, jsonify
from flask_cors import CORS
import threading

from location_tracker import MultiSourceTracker
from camera_streamer import CameraStreamer, detect_camera, find_video_devices
import config as app_config

tracker = MultiSourceTracker(update_interval=60)
print("Using IP-based location")

streamer = CameraStreamer()

app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/location')
def get_location():
    location = tracker.get_current_location()
    if location:
        return jsonify(location)
    return jsonify({'error': 'No location data available'}), 404

@app.route('/api/location/update')
def update_location():
    location = tracker.update_location()
    if location:
        return jsonify(location)
    return jsonify({'error': 'Failed to update location'}), 500

@app.route('/api/history')
def get_history():
    history = tracker.get_location_history(limit=100)
    return jsonify(history)

@app.route('/api/status')
def get_status():
    location = tracker.get_current_location()
    return jsonify({
        'tracking_active': True,
        'update_interval': tracker.update_interval,
        'history_count': len(tracker.location_history),
        'current_location': location
    })


# ---- Camera streaming endpoints ----

@app.route('/api/camera/status')
def camera_status():
    return jsonify(streamer.status())


@app.route('/api/camera/detect')
def camera_detect():
    info = detect_camera()
    if info:
        return jsonify(info)
    return jsonify({
        'error': 'No camera detected',
        'devices': find_video_devices(),
    }), 404


@app.route('/api/camera/start')
def camera_start():
    result = streamer.start()
    code = 200 if result.get('streaming') else 500
    return jsonify(result), code


@app.route('/api/camera/stop')
def camera_stop():
    result = streamer.stop()
    return jsonify(result)


def background_tracker():
    tracker.run_continuous()


if __name__ == '__main__':
    tracker_thread = threading.Thread(target=background_tracker, daemon=True)
    tracker_thread.start()
    print("Getting initial location...")
    tracker.update_location()

    # Auto-start camera stream for Frigate / go2rtc if configured
    if getattr(app_config, 'CAMERA_AUTO_START', False):
        print("Auto-starting camera stream → "
              + getattr(app_config, 'RTSP_URL', '(not configured)'))
        result = streamer.start()
        if result.get('streaming'):
            print("Camera stream started successfully")
        else:
            print(f"Camera stream failed: {result.get('error', 'unknown')}")

    print("Starting web server on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)