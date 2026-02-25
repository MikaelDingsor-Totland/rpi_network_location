#!/usr/bin/env python3
"""
Flask web server for live location dashboard
Now with WiFi-based location for better accuracy!
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import threading
import os

# Try WiFi tracker first, fall back to IP-based
try:
    from wifi_location_tracker import WiFiLocationTracker
    tracker = WiFiLocationTracker(update_interval=60)
    print("Using WiFi-based location (higher accuracy)")
except ImportError:
    from location_tracker import MultiSourceTracker
    tracker = MultiSourceTracker(update_interval=60)
    print("Using IP-based location (lower accuracy)")

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
        'current_location': location,
        'source': location.get('source', 'unknown') if location else 'none',
        'accuracy': location.get('accuracy', 'unknown') if location else 'none'
    })


def background_tracker():
    tracker.run_continuous()


if __name__ == '__main__':
    tracker_thread = threading.Thread(target=background_tracker, daemon=True)
    tracker_thread.start()
    print("Getting initial location...")
    tracker.update_location()
    print("Starting web server on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)