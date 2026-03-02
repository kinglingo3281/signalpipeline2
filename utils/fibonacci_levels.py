#!/usr/bin/env python
"""
Fibonacci Retracement Calculator
-------------------------------
Calculates Fibonacci retracement levels for crypto assets using 125 weekly candles in linear mode.
Caches results to avoid recalculation and API rate limits.
Uses TAAPI's construct API for efficient batch processing.
"""

import os
import sys
import json
import time
import requests
from datetime import datetime

# Add parent directory to path to allow imports from root after moving to analysis/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import from hyperliquid package
from hyperliquid.info import Info

# Constants
# Define paths that will work both before and after moving to analysis/ directory
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR_FROM_ROOT = os.path.join(PROJECT_ROOT, "data", "fibonacci_cache")
CACHE_DIR_FROM_ANALYSIS = os.path.join(os.path.dirname(PROJECT_ROOT), "data", "fibonacci_cache")

# Use the directory that exists, or default to the from-root path
CACHE_DIR = CACHE_DIR_FROM_ROOT if os.path.exists(CACHE_DIR_FROM_ROOT) else CACHE_DIR_FROM_ANALYSIS

CACHE_EXPIRY_HOURS = 24  # Refresh once a day (24 hours)
FIBONACCI_LEVELS = [0.236, 0.382, 0.5, 0.618, 0.786]
TAAPI_SECRET = os.getenv("TAAPI_SECRET", "")

# Make sure cache directory exists
os.makedirs(CACHE_DIR, exist_ok=True)

def get_fibonacci_levels(asset, force_refresh=False):
    """Get Fibonacci retracement levels for an asset with improved caching.
    
    Args:
        asset: Asset symbol (e.g., BTC, ETH)
        force_refresh: If True, force recalculation
        
    Returns:
        Dictionary of Fibonacci levels or None if calculation failed
    """
    # Completely override force_refresh by checking global refresh flag
    global_refresh_file = os.path.join(CACHE_DIR, "last_refresh.txt")
    
    # Check if the global refresh flag exists and is recent (< 24 hours old)
    if os.path.exists(global_refresh_file):
        try:
            with open(global_refresh_file, 'r') as f:
                last_refresh = datetime.fromisoformat(f.read().strip())
                hours_since_refresh = (datetime.now() - last_refresh).total_seconds() / 3600
                
                # If we refreshed in the last 24 hours, ignore the force_refresh parameter
                if hours_since_refresh < 24:
                    print(f"FIBDEBUG: OVERRIDE - Using cached data for {asset} regardless of force_refresh parameter. Last global refresh: {hours_since_refresh:.1f} hours ago")
                    force_refresh = False
                else:
                    print(f"FIBDEBUG: Global refresh file is too old ({hours_since_refresh:.1f} hours)")
        except Exception as e:
            print(f"FIBDEBUG: Error reading global refresh file: {e}")
    else:
        print(f"FIBDEBUG: No global refresh file found")
        
    print(f"FIBDEBUG: get_fibonacci_levels processing {asset}, final force_refresh={force_refresh}")
    
    # Compute cache file path
    cache_file = os.path.join(CACHE_DIR, f"{asset}_fibonacci.json")
    
    # Check if we have a recent cached version
    if not force_refresh and os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cached_data = json.load(f)
                
            # Check if cache has expired
            timestamp = cached_data.get("timestamp", "")
            if timestamp:
                # Parse timestamp
                cached_time = datetime.strptime(timestamp, "%Y%m%d_%H%M%S")
                hours_elapsed = (datetime.now() - cached_time).total_seconds() / 3600
                
                if hours_elapsed < CACHE_EXPIRY_HOURS:
                    # Cache is still valid
                    return cached_data
                    
            print(f"Cache has expired for {asset}")
        except Exception as e:
            print(f"Error reading cache: {e}")
            
    # Calculate new values
    print(f"Refreshing Fibonacci levels for {asset}...")
    fibonacci_data = calculate_fibonacci_levels(asset)
    
    # Save to cache if calculation succeeded
    if fibonacci_data and fibonacci_data.get("levels"):
        try:
            with open(cache_file, 'w') as f:
                json.dump(fibonacci_data, f, indent=4)
                
            # Update global refresh timestamp if this was a forced refresh
            if force_refresh:
                global_refresh_file = os.path.join(CACHE_DIR, "last_refresh.txt")
                try:
                    with open(global_refresh_file, 'w') as f:
                        f.write(datetime.now().isoformat())
                    print(f"FIBDEBUG: Updated global refresh timestamp for {asset}")
                except Exception as e:
                    print(f"FIBDEBUG: Error updating global refresh timestamp: {e}")
                    
        except Exception as e:
            print(f"Error saving to cache: {e}")
            
    return fibonacci_data

def calculate_fibonacci_levels(asset):
    """Calculate Fibonacci retracement levels for an asset using TAAPI's bulk API.
    
    Uses the construct/bulk API to efficiently fetch all Fibonacci levels in a single request.
    Prioritizes gateio exchange and falls back to binance if needed.
    Uses 125 weekly candles with linear chart mode as recommended.
    
    Args:
        asset: Asset symbol (e.g., BTC, ETH)
        
    Returns:
        Dictionary with Fibonacci data including levels, trend, and current price
    """
    print(f"Calculating Fibonacci levels for {asset}...")
    
    # Construct API URL for batch processing
    construct_url = "https://api.taapi.io/bulk"
    
    # Build construct for gateio (primary exchange)
    construct_data = {
        "secret": TAAPI_SECRET,
        "construct": [
            # Uptrend constructs
            *[
                {
                    "exchange": "gateio",
                    "symbol": f"{asset}/USDT",
                    "interval": "1w",  # Weekly candles as recommended
                    "indicators": [
                        {
                            "indicator": "fibonacciretracement",
                            "trend": "uptrend",
                            "period": 125,  # 125 candles 
                            "retracement": level,
                            "backtracks": 0,
                            "chartType": "linear"  # Linear mode as recommended
                        }
                    ]
                } for level in FIBONACCI_LEVELS
            ],
            # Downtrend constructs
            *[
                {
                    "exchange": "gateio",
                    "symbol": f"{asset}/USDT",
                    "interval": "1w",  # Weekly candles as recommended
                    "indicators": [
                        {
                            "indicator": "fibonacciretracement",
                            "trend": "downtrend",
                            "period": 125,  # 125 candles 
                            "retracement": level,
                            "backtracks": 0,
                            "chartType": "linear"  # Linear mode as recommended
                        }
                    ]
                } for level in FIBONACCI_LEVELS
            ]
        ]
    }
    
    # Binance fallback construct (in case gateio doesn't have the asset)
    construct_data_fallback = {
        "secret": TAAPI_SECRET,
        "construct": [
            # Uptrend constructs - Binance fallback
            *[
                {
                    "exchange": "binance",
                    "symbol": f"{asset}/USDT",
                    "interval": "1w",  # Weekly candles as recommended
                    "indicators": [
                        {
                            "indicator": "fibonacciretracement",
                            "trend": "uptrend",
                            "period": 125,  # 125 candles 
                            "retracement": level,
                            "backtracks": 0,
                            "chartType": "linear"  # Linear mode as recommended
                        }
                    ]
                } for level in FIBONACCI_LEVELS
            ],
            # Downtrend constructs - Binance fallback
            *[
                {
                    "exchange": "binance",
                    "symbol": f"{asset}/USDT",
                    "interval": "1w",  # Weekly candles as recommended
                    "indicators": [
                        {
                            "indicator": "fibonacciretracement",
                            "trend": "downtrend",
                            "period": 125,  # 125 candles 
                            "retracement": level,
                            "backtracks": 0,
                            "chartType": "linear"  # Linear mode as recommended
                        }
                    ]
                } for level in FIBONACCI_LEVELS
            ]
        ]
    }
    
    # Process API responses
    uptrend_levels = {}
    downtrend_levels = {}
    
    try:
        # Make batch request to TAAPI using gateio first
        response = requests.post(construct_url, json=construct_data)
        
        # If GateIO fails, try Binance as fallback
        if response.status_code != 200 or 'error' in response.text.lower():
            print(f"Trying Binance as fallback for {asset}...")
            response = requests.post(construct_url, json=construct_data_fallback)
        
        if response.status_code == 200:
            data = response.json()
            
            # Process the results
            if 'data' in data:
                for item in data['data']:
                    # Skip items with errors
                    if 'errors' in item and item['errors']:
                        continue  
                    
                    # Extract indicator ID details
                    id_parts = item['id'].split('_')
                    
                    # Need enough parts to extract info
                    if len(id_parts) >= 5:
                        # Determine trend type and level
                        trend_type = ""
                        for part in id_parts:
                            if part.lower() in ["uptrend", "downtrend"]:
                                trend_type = part.lower()
                                break
                                
                        # Find which Fibonacci level this is
                        level = None
                        for fib_level in FIBONACCI_LEVELS:
                            if str(fib_level) in item['id']:
                                level = str(fib_level)
                                break
                        
                        # Skip if level or trend not identified
                        if not level or not trend_type:
                            continue
                            
                        # Extract the Fibonacci level value
                        value = 0
                        if 'result' in item and 'value' in item['result']:
                            value = float(item['result']['value'])
                        
                        # Store in the appropriate dictionary
                        if 'uptrend' in trend_type:
                            uptrend_levels[level] = value
                        elif 'downtrend' in trend_type:
                            downtrend_levels[level] = value
        else:
            print(f"Error from TAAPI: {response.status_code} - {response.text}")
            
        # Don't try to fetch current price from Hyperliquid - focus on TAAPI for Fibonacci levels
        # The current price isn't essential for the Fibonacci calculation itself
        current_price = 0
        
        # We already got successful Fibonacci levels from TAAPI, so we can proceed
        # The more important part is the Fibonacci levels themselves, not the current price
        if len(uptrend_levels) > 0 or len(downtrend_levels) > 0:
            print(f"Successfully got Fibonacci levels for {asset} from TAAPI")
        else:
            print(f"Warning: No Fibonacci levels found for {asset}")
        
        # Detect trend based on which levels are closer to current price
        trend = "uptrend"  # Default to uptrend
        
        if current_price > 0 and uptrend_levels and downtrend_levels:
            # Calculate average distance to levels
            uptrend_dists = [abs(current_price - level) / current_price 
                            for level in uptrend_levels.values() if level > 0]
            downtrend_dists = [abs(current_price - level) / current_price 
                              for level in downtrend_levels.values() if level > 0]
            
            # Average distances
            uptrend_distance = sum(uptrend_dists) / len(uptrend_dists) if uptrend_dists else float('inf')
            downtrend_distance = sum(downtrend_dists) / len(downtrend_dists) if downtrend_dists else float('inf')
            
            # Determine trend based on distance
            trend = "uptrend" if uptrend_distance <= downtrend_distance else "downtrend"
        
        # Select the appropriate levels based on the trend
        levels = uptrend_levels if trend == "uptrend" else downtrend_levels
        
        # Log success and return data
        print(f"Successfully calculated Fibonacci levels for {asset}. Found {len(levels)} levels. Trend: {trend}.")
        return {
            "asset": asset,
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "levels": levels,
            "trend": trend,
            "current_price": current_price
        }
    except Exception as e:
        print(f"Error calculating Fibonacci levels: {e}")
        return {
            "asset": asset,
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "levels": {},
            "trend": "uptrend",
            "current_price": 0
        }

def refresh_all_fibonacci_levels(assets=None):
    """Refresh Fibonacci levels for all specified assets or all cached assets"""
    if not assets:
        # If no assets specified, refresh all cached ones
        assets = []
        for filename in os.listdir(CACHE_DIR):
            if filename.endswith("_fibonacci.json"):
                asset = filename.split("_fibonacci.json")[0]
                assets.append(asset)
                
        # If still no assets, get them from data directory
        if not assets:
            # Define paths that will work both before and after moving to analysis/ directory
            vis_dir_from_root = os.path.join(PROJECT_ROOT, "data", "visualizations")
            vis_dir_from_analysis = os.path.join(os.path.dirname(PROJECT_ROOT), "data", "visualizations")
            
            # Use the directory that exists
            visualizations_dir = vis_dir_from_root if os.path.exists(vis_dir_from_root) else vis_dir_from_analysis
            
            if os.path.exists(visualizations_dir):
                for filename in os.listdir(visualizations_dir):
                    if "_enhanced_analysis_" in filename:
                        asset = filename.split("_enhanced_analysis_")[0]
                        if asset not in assets:
                            assets.append(asset)
            else:
                print(f"Warning: Visualizations directory not found at {visualizations_dir}")
    
    # Check global refresh timestamp first
    global_refresh_file = os.path.join(CACHE_DIR, "last_refresh.txt")
    needs_refresh = True
    
    if os.path.exists(global_refresh_file):
        try:
            with open(global_refresh_file, 'r') as f:
                last_refresh = datetime.fromisoformat(f.read().strip())
                hours_since_refresh = (datetime.now() - last_refresh).total_seconds() / 3600
                
                if hours_since_refresh < 24:
                    print(f"FIBDEBUG: Global refresh is recent ({hours_since_refresh:.1f} hours ago), skipping forced refresh")
                    needs_refresh = False
        except Exception as e:
            print(f"FIBDEBUG: Error reading global refresh timestamp: {e}")
    
    # Refresh each asset
    results = {}
    for asset in assets:
        if needs_refresh:
            print(f"Refreshing Fibonacci levels for {asset}...")
        else:
            print(f"Using cached Fibonacci levels for {asset}...")
        # Only force refresh if global timestamp indicates it's needed
        data = get_fibonacci_levels(asset, force_refresh=needs_refresh)
        results[asset] = data
        
    return results

if __name__ == "__main__":
    # If run directly, refresh all fibonacci levels
    assets = None
    if len(sys.argv) > 1:
        assets = sys.argv[1:]
    
    refresh_all_fibonacci_levels(assets)
