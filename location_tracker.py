#!/usr/bin/env python3
"""
Network-based location tracker for Raspberry Pi 5
Uses IP geolocation to determine approximate location
"""

import requests
import json
import time
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NetworkLocationTracker:
    def __init__(self, api_token=None, update_interval=60):
        """
        Initialize the network location tracker
        
        Args:
            api_token: Optional API token for ipinfo.io (free tier: 50k req/month)
            update_interval: Seconds between location updates
        """
        self.api_token = api_token
        self.update_interval = update_interval
        self.current_location = None
        self.location_history = []
        
    def get_public_ip(self):
        """Get the device's public IP address"""
        try:
            response = requests.get('https://api.ipify.org?format=json', timeout=10)
            response.raise_for_status()
            return response.json()['ip']
        except requests.RequestException as e:
            logger.error(f"Failed to get public IP: {e}")
            return None
    
    def get_location_from_ip(self, ip=None):
        """
        Get geolocation data from IP address using ipinfo.io
        
        Args:
            ip: IP address to lookup (None = current device IP)
        
        Returns:
            dict with location data or None on error
        """
        try:
            if ip:
                url = f"https://ipinfo.io/{ip}/json"
            else:
                url = "https://ipinfo.io/json"
            
            if self.api_token:
                url += f"?token={self.api_token}"
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Parse coordinates
            loc = data.get('loc', '0,0').split(',')
            
            location = {
                'ip': data.get('ip'),
                'city': data.get('city'),
                'region': data.get('region'),
                'country': data.get('country'),
                'latitude': float(loc[0]),
                'longitude': float(loc[1]),
                'org': data.get('org'),
                'timezone': data.get('timezone'),
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
            
            return location
            
        except requests.RequestException as e:
            logger.error(f"Failed to get location: {e}")
            return None
        except (ValueError, IndexError) as e:
            logger.error(f"Failed to parse location data: {e}")
            return None
    
    def update_location(self):
        """Update the current location"""
        location = self.get_location_from_ip()
        
        if location:
            self.current_location = location
            self.location_history.append(location)
            
            # Keep only last 1000 entries
            if len(self.location_history) > 1000:
                self.location_history = self.location_history[-1000:]
            
            logger.info(
                f"Location updated: {location['city']}, "
                f"{location['region']}, {location['country']} "
                f"({location['latitude']}, {location['longitude']})"
            )
            
            return location
        return None
    
    def get_current_location(self):
        """Get the most recent location"""
        return self.current_location
    
    def get_location_history(self, limit=100):
        """Get location history"""
        return self.location_history[-limit:]
    
    def run_continuous(self, callback=None):
        """
        Run continuous location tracking

        Args:
            callback: Optional function to call with each location update
        """
        logger.info(f"Starting continuous tracking (interval: {self.update_interval}s)")
        
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


# Alternative APIs for redundancy
class MultiSourceTracker(NetworkLocationTracker):
    """Tracker that uses multiple geolocation APIs for redundancy"""
    
    APIS = [
        {
            'name': 'ipinfo',
            'url': 'https://ipinfo.io/json',
            'parser': lambda d: {
                'latitude': float(d.get('loc', '0,0').split(',')[0]),
                'longitude': float(d.get('loc', '0,0').split(',')[1]),
                'city': d.get('city'),
                'region': d.get('region'),
                'country': d.get('country'),
            }
        },
        {
            'name': 'ip-api',
            'url': 'http://ip-api.com/json/',
            'parser': lambda d: {
                'latitude': d.get('lat'),
                'longitude': d.get('lon'),
                'city': d.get('city'),
                'region': d.get('regionName'),
                'country': d.get('countryCode'),
            }
        },
        {
            'name': 'ipwhois',
            'url': 'https://ipwho.is/',
            'parser': lambda d: {
                'latitude': d.get('latitude'),
                'longitude': d.get('longitude'),
                'city': d.get('city'),
                'region': d.get('region'),
                'country': d.get('country_code'),
            }
        }
    ]
    
    def get_location_from_ip(self, ip=None):
        """Try multiple APIs until one succeeds"""
        for api in self.APIS:
            try:
                url = api['url']
                if ip:
                    url = url.rstrip('/') + f'/{ip}'
                
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                location = api['parser'](data)
                location['ip'] = data.get('ip') or data.get('query')
                location['source'] = api['name']
                location['timestamp'] = datetime.utcnow().isoformat() + 'Z'
                
                logger.info(f"Got location from {api['name']}")
                return location
                
            except Exception as e:
                logger.warning(f"API {api['name']} failed: {e}")
                continue
        
        logger.error("All geolocation APIs failed")
        return None


if __name__ == '__main__':
    # Simple test run
    tracker = MultiSourceTracker(update_interval=30)
    
    # Get initial location
    location = tracker.update_location()
    if location:
        print(json.dumps(location, indent=2))
    
    # Run continuous tracking
    tracker.run_continuous()