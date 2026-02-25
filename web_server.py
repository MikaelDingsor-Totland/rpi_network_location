#!/usr/bin/env python3
"""
Flask web server for live location dashboard
"""

from flask import Flask, render_template, jsonify
from flask_cors import CORS
from location_tracker import MultiSourceTracker
import threading

app = Flask(__name__)
CORS(app)

# Global tracker instance
tracker = MultiSourceTracker(update_interval=60)

@app.route('/')
def index():
    """Serve the main dashboard page"""
    return render_template('index.html')

@app.route('/api/location')
def get_location():
    """API endpoint for current location"""
    location = tracker.get_current_location()
    if location:
        return jsonify(location)
    return jsonify({'error': 'No location data available'}), 404

@app.route('/api/location/update')
def update_location():
    """Force a location update"""
    location = tracker.update_location()
    if location:
        return jsonify(location)
    return jsonify({'error': 'Failed to update location'}), 500

@app.route('/api/history')
def get_history():
    """Get location history"""
    history = tracker.get_location_history(limit=100)
    return jsonify(history)

@app.route('/api/status')
def get_status():
    """Get tracker status"""
    return jsonify({
        'tracking_active': True,
        'update_interval': tracker.update_interval,
        'history_count': len(tracker.location_history),
        'current_location': tracker.get_current_location()
    })


def background_tracker():
    """Run the tracker in the background"""
    tracker.run_continuous()


if __name__ == '__main__':
    # Start background tracking thread
    tracker_thread = threading.Thread(target=background_tracker, daemon=True)
    tracker_thread.start()
    
    # Get initial location
    tracker.update_location()
    
    # Start web server
    print("Starting web server on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)