#!/usr/bin/env python3
"""
WiFi-based location tracker for Raspberry Pi 5
Uses nearby WiFi networks to triangulate position via Mozilla Location Service
Much more accurate than IP-based geolocation (~50m vs ~25km)
"""

import subprocess
import requests
import json
import time
from datetime import datetime
import logging
import re

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class WiFiLocationTracker:
    MLS_URL = "https://location.services.mozilla.com/v1/geolocate?key=test"
    
    def __init__(self, update_interval=60, wifi_interface=None):
        self.update_interval = update_interval
        self.wifi_interface = wifi_interface or self._detect_wifi_interface()
        self.current_location = None
        self.location_history = []
        logger.info(f"Using WiFi interface: {self.wifi_interface}")
    
    def _detect_wifi_interface(self):
        try:
            result = subprocess.run(['iw', 'dev'], capture_output=True, text=True, timeout=10)
            for line in result.stdout.split('\n'):
                if 'Interface' in line:
                    return line.split()[-1]
            return 'wlan0'
        except Exception as e:
            logger.warning(f"Could not detect WiFi interface: {e}")
            return 'wlan0'
    
    def scan_wifi_networks(self):
        try:
            result = subprocess.run(
                ['sudo', 'iwlist', self.wifi_interface, 'scan'],
                capture_output=True, text=True, timeout=30
            )
            return self._parse_iwlist_scan(result.stdout)
        except Exception as e:
            logger.error(f"WiFi scan failed: {e}")
            return []
    
    def _parse_iwlist_scan(self, output):
        access_points = []
        current_ap = {}
        for line in output.split('\n'):
            line = line.strip()
            if 'Cell ' in line and 'Address:' in line:
                if current_ap.get('macAddress'):
                    access_points.append(current_ap)
                mac = line.split('Address:')[1].strip().upper()
                current_ap = {'macAddress': mac}
            elif 'Signal level' in line:
                try:
                    if 'dBm' in line:
                        signal = int(re.search(r'-?\d+', line.split('=')[1]).group())
                    else:
                        match = re.search(r'(\d+)/100', line)
                        if match:
                            percent = int(match.group(1))
                            signal = int(-100 + (percent * 0.6))
                        else:
                            continue
                    current_ap['signalStrength'] = signal
                except:
                    pass
            elif 'Channel:' in line:
                try:
                    current_ap['channel'] = int(line.split(':')[1].strip())
                except:
                    pass
        if current_ap.get('macAddress'):
            access_points.append(current_ap)
        logger.info(f"Found {len(access_points)} WiFi networks")
        return access_points
    
    def get_location_from_wifi(self):
        access_points = self.scan_wifi_networks()
        if not access_points:
            logger.warning("No WiFi networks found, falling back to IP location")
            return self._fallback_ip_location()
        
        payload = {"wifiAccessPoints": access_points}
        try:
            response = requests.post(self.MLS_URL, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                location = {
                    'latitude': data['location']['lat'],
                    'longitude': data['location']['lng'],
                    'accuracy': data.get('accuracy', 50),
                    'source': 'wifi',
                    'wifi_networks_used': len(access_points),
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                }
                location.update(self._reverse_geocode(location['latitude'], location['longitude']))
                logger.info(f"WiFi location: {location.get('city', 'Unknown')}, accuracy: {location['accuracy']}m")
                return location
            else:
                return self._fallback_ip_location()
        except Exception as e:
            logger.error(f"MLS request failed: {e}")
            return self._fallback_ip_location()
    
    def _reverse_geocode(self, lat, lon):
        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={'lat': lat, 'lon': lon, 'format': 'json', 'zoom': 10},
                headers={'User-Agent': 'RPi5-Location-Tracker/1.0'},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                address = data.get('address', {})
                return {
                    'city': address.get('city') or address.get('town') or address.get('village'),
                    'region': address.get('state') or address.get('county'),
                    'country': address.get('country_code', '').upper(),
                }
        except Exception as e:
            logger.warning(f"Reverse geocoding failed: {e}")
        return {}
    
    def _fallback_ip_location(self):
        try:
            response = requests.get('https://ipwho.is/', timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {
                    'latitude': data.get('latitude'),
                    'longitude': data.get('longitude'),
                    'city': data.get('city'),
                    'region': data.get('region'),
                    'country': data.get('country_code'),
                    'accuracy': 25000,
                    'source': 'ip_fallback',
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                }
        except Exception as e:
            logger.error(f"IP fallback failed: {e}")
        return None
    
    def update_location(self):
        location = self.get_location_from_wifi()
        if location:
            self.current_location = location
            self.location_history.append(location)
            if len(self.location_history) > 1000:
                self.location_history = self.location_history[-1000:]
            return location
        return None
    
    def get_current_location(self):
        return self.current_location
    
    def get_location_history(self, limit=100):
        return self.location_history[-limit:]
    
    def run_continuous(self, callback=None):
        logger.info(f"Starting WiFi location tracking (interval: {self.update_interval}s)")
        while True:
            try:
                location = self.update_location()
                if location and callback:
                    callback(location)
                time.sleep(self.update_interval)
            except KeyboardInterrupt:
                logger.info("Tracking stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in tracking loop: {e}")
                time.sleep(self.update_interval)


if __name__ == '__main__':
    tracker = WiFiLocationTracker(update_interval=30)
    print("Scanning WiFi networks...")
    location = tracker.update_location()
    if location:
        print(json.dumps(location, indent=2))
    else:
        print("Could not determine location")
