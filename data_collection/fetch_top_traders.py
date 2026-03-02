"""
Script to fetch Hyperliquid top traders, cache their addresses, 
and collect their positions and open orders
"""

import os
import sys
import json
import csv
import requests
import pandas as pd
from datetime import datetime
import time
import math
import argparse
import traceback
import threading
import signal
import concurrent.futures

# Add parent directory to path to allow imports from root after moving to data_collection/
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(root_dir)
sys.path.insert(0, root_dir)  # Ensure root directory is first in path

# Also add analysis directory explicitly to path
analysis_dir = os.path.join(root_dir, 'analysis')
utils_dir = os.path.join(root_dir, 'utils')
visualization_dir = os.path.join(root_dir, 'visualization')

# Add these directories to path if they're not already there
if analysis_dir not in sys.path:
    sys.path.insert(0, analysis_dir)
if utils_dir not in sys.path:
    sys.path.insert(0, utils_dir)
if visualization_dir not in sys.path:
    sys.path.insert(0, visualization_dir)

# Define project root for consistent file paths
PROJECT_ROOT = root_dir

# Make sure necessary directories exist
os.makedirs(os.path.join(PROJECT_ROOT, "data"), exist_ok=True)
os.makedirs(os.path.join(PROJECT_ROOT, "data", "visualizations"), exist_ok=True)

# Import directly from the hyperliquid package in the activated environment
from hyperliquid.api import API
from hyperliquid.info import Info

# Cache for market data
orderbook_cache = {}

# Import our enhanced analysis modules with directory structure handling
# Make sure necessary directories exist first
os.makedirs(os.path.join(PROJECT_ROOT, "data"), exist_ok=True)
os.makedirs(os.path.join(PROJECT_ROOT, "data", "visualizations"), exist_ok=True)

# Initialize variables
ENHANCED_MODULES_AVAILABLE = False

# Create paths to specific module files
cluster_analysis_path = os.path.join(root_dir, 'analysis', 'cluster_analysis.py')
cascade_analysis_path = os.path.join(root_dir, 'analysis', 'cascade_analysis.py')
liquidation_clusters_path = os.path.join(root_dir, 'analysis', 'liquidation_clusters.py')
daily_trading_analysis_path = os.path.join(root_dir, 'analysis', 'daily_trading_analysis.py')
enhanced_heatmap_path = os.path.join(root_dir, 'visualization', 'enhanced_heatmap.py')
actionable_entry_path = os.path.join(root_dir, 'visualization', 'actionable_entry_visualization.py')
trading_view_integration_path = os.path.join(root_dir, 'visualization', 'trading_view_integration.py')
price_targeting_path = os.path.join(root_dir, 'utils', 'price_targeting.py')

# Check if required files exist
ENHANCED_MODULES_AVAILABLE = False

print("Checking for critical module files...")
for path, name in [
    (liquidation_clusters_path, "liquidation_clusters"),
    (cascade_analysis_path, "cascade_analysis"),
    (cluster_analysis_path, "cluster_analysis")
]:
    if os.path.exists(path):
        print(f"Found {name} at {path}")
    else:
        print(f"MISSING: {name} not found at {path}")

# First try the direct physical file imports if files exist
try:
    # Direct import approach - manually handle imports with importlib
    import importlib.util
    
    # First load liquidation_clusters as it's needed by other modules
    if os.path.exists(liquidation_clusters_path):
        spec = importlib.util.spec_from_file_location("liquidation_clusters", liquidation_clusters_path)
        liquidation_clusters = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(liquidation_clusters)
        sys.modules["liquidation_clusters"] = liquidation_clusters
        identify_liquidation_clusters_raw = getattr(liquidation_clusters, "identify_liquidation_clusters")
        print("Loaded liquidation_clusters.py directly")
    
    # Load cascade_analysis next as it may be needed by cluster_analysis
    if os.path.exists(cascade_analysis_path):
        spec = importlib.util.spec_from_file_location("cascade_analysis", cascade_analysis_path)
        cascade_analysis = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cascade_analysis)
        sys.modules["cascade_analysis"] = cascade_analysis
        calculate_cascade_probability = getattr(cascade_analysis, "calculate_cascade_probability")
        print("Loaded cascade_analysis.py directly")
    
    # Now load cluster_analysis which depends on the previous modules
    if os.path.exists(cluster_analysis_path):
        spec = importlib.util.spec_from_file_location("cluster_analysis", cluster_analysis_path)
        cluster_analysis = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cluster_analysis)
        sys.modules["cluster_analysis"] = cluster_analysis
        identify_liquidation_clusters = getattr(cluster_analysis, "identify_liquidation_clusters")
        optimize_target_price_ranges = getattr(cluster_analysis, "optimize_target_price_ranges")
        analyze_liquidation_landscape = getattr(cluster_analysis, "analyze_liquidation_landscape")
        calculate_range_consistency = getattr(cluster_analysis, "calculate_range_consistency")
        calculate_directional_strength = getattr(cluster_analysis, "calculate_directional_strength")
        ensure_liquidation_format = getattr(cluster_analysis, "ensure_liquidation_format")
        print("Loaded cluster_analysis.py directly")
    
    # Load other modules only if needed ones are successful
    if "liquidation_clusters" in sys.modules and "cluster_analysis" in sys.modules:
        # Load daily_trading_analysis
        if os.path.exists(daily_trading_analysis_path):
            spec = importlib.util.spec_from_file_location("daily_trading_analysis", daily_trading_analysis_path)
            daily_trading_analysis = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(daily_trading_analysis)
            sys.modules["daily_trading_analysis"] = daily_trading_analysis
            calculate_liquidation_clusters = getattr(daily_trading_analysis, "calculate_liquidation_clusters")
            print("Loaded daily_trading_analysis.py directly")
        
        # Load visualization modules
        if os.path.exists(enhanced_heatmap_path):
            spec = importlib.util.spec_from_file_location("enhanced_heatmap", enhanced_heatmap_path)
            enhanced_heatmap = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(enhanced_heatmap)
            sys.modules["enhanced_heatmap"] = enhanced_heatmap
            create_liquidation_cascade_heatmap = getattr(enhanced_heatmap, "create_liquidation_cascade_heatmap")
            print("Loaded enhanced_heatmap.py directly")
        
        if os.path.exists(actionable_entry_path):
            spec = importlib.util.spec_from_file_location("actionable_entry_visualization", actionable_entry_path)
            actionable_entry_visualization = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(actionable_entry_visualization)
            sys.modules["actionable_entry_visualization"] = actionable_entry_visualization
            create_enhanced_actionable_visualization = getattr(actionable_entry_visualization, "create_enhanced_actionable_visualization")
            print("Loaded actionable_entry_visualization.py directly")
        
        if os.path.exists(trading_view_integration_path):
            spec = importlib.util.spec_from_file_location("trading_view_integration", trading_view_integration_path)
            trading_view_integration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(trading_view_integration)
            sys.modules["trading_view_integration"] = trading_view_integration
            integrate_liquidation_with_trading_chart = getattr(trading_view_integration, "integrate_liquidation_with_trading_chart")
            TradingChartIntegration = getattr(trading_view_integration, "TradingChartIntegration")
            print("Loaded trading_view_integration.py directly")
        
        # Load price targeting
        if os.path.exists(price_targeting_path):
            spec = importlib.util.spec_from_file_location("price_targeting", price_targeting_path)
            price_targeting = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(price_targeting)
            sys.modules["price_targeting"] = price_targeting
            generate_price_targets = getattr(price_targeting, "generate_price_targets")
            generate_ta_price_targets = getattr(price_targeting, "generate_ta_price_targets")
            print("Loaded price_targeting.py directly")
        
        ENHANCED_MODULES_AVAILABLE = True
        print("Successfully imported all analysis modules directly from file locations")
    
except Exception as e:
    print(f"Error with direct file imports: {e}")
    
    # Try fallback to original imports as a last resort
    try:
        # Ensure root directory is at the start of the path
        if root_dir not in sys.path:
            sys.path.insert(0, root_dir)
        
        # Try direct imports from original locations
        from cluster_analysis import (
            identify_liquidation_clusters,
            calculate_cascade_probability,
            optimize_target_price_ranges,
            analyze_liquidation_landscape,
            calculate_range_consistency,
            calculate_directional_strength,
            ensure_liquidation_format
        )
        from daily_trading_analysis import calculate_liquidation_clusters
        from enhanced_heatmap import create_liquidation_cascade_heatmap
        from actionable_entry_visualization import create_enhanced_actionable_visualization
        from trading_view_integration import integrate_liquidation_with_trading_chart, TradingChartIntegration
        from price_targeting import generate_price_targets, generate_ta_price_targets
        
        ENHANCED_MODULES_AVAILABLE = True
        print("Enhanced analysis modules imported successfully from original locations.")
    except ImportError as e2:
        print(f"Error with original imports: {e2}")
        print("Enhanced analysis modules not available. Using base implementation.")
        ENHANCED_MODULES_AVAILABLE = False
except ImportError as e:
    # Fallback to original imports during transition
    try:
        from cluster_analysis import (
            identify_liquidation_clusters, 
            calculate_cascade_probability,
            optimize_target_price_ranges,
            analyze_liquidation_landscape,
            calculate_range_consistency,
            calculate_directional_strength,
            ensure_liquidation_format
        )
        from daily_trading_analysis import calculate_liquidation_clusters
        from enhanced_heatmap import create_liquidation_cascade_heatmap
        from actionable_entry_visualization import create_enhanced_actionable_visualization
        from trading_view_integration import integrate_liquidation_with_trading_chart, TradingChartIntegration
        
        # Track if enhanced modules are available
        ENHANCED_MODULES_AVAILABLE = True
        print("Enhanced analysis modules imported successfully from root directory.")
    except ImportError as e2:
        ENHANCED_MODULES_AVAILABLE = False
        print(f"Enhanced analysis modules not available: {e2}. Using base implementation.")

# Create data directory if it doesn't exist - with paths that work before and after moving
DATA_DIR_FROM_ROOT = os.path.join(PROJECT_ROOT, "data")
DATA_DIR_FROM_DATA_COLLECTION = os.path.join(os.path.dirname(PROJECT_ROOT), "data")

# Use the directory that exists, or create at both locations to ensure compatibility
if os.path.exists(DATA_DIR_FROM_ROOT):
    os.makedirs(DATA_DIR_FROM_ROOT, exist_ok=True)
else:
    os.makedirs(DATA_DIR_FROM_DATA_COLLECTION, exist_ok=True)

# Initialize Hyperliquid API
API_URL = "https://api.hyperliquid.xyz"
info = Info(API_URL, skip_ws=True)  # Skip WebSockets to avoid threading errors

def fetch_traders_from_source(url, source_name, limit=500):
    """
    Helper function to fetch traders from a specific source URL
    """
    print(f"Fetching top {limit} traders from {source_name}...")
    
    try:
        # Make the request
        response = requests.get(url, timeout=10)
        
        # Check if request was successful
        if response.status_code != 200:
            print(f"Error: Received status code {response.status_code} from {source_name}")
            return []
            
        # Try to parse the response as JSON
        try:
            data = response.json()
            
            # Extract traders list from the correct format
            if isinstance(data, dict) and "table_data" in data:
                traders = data["table_data"]
                print(f"Found {len(traders)} traders in {source_name} (table_data)")
            elif isinstance(data, dict) and "chart_data" in data:
                traders = data["chart_data"]
                print(f"Found {len(traders)} traders in {source_name} (chart_data)")
            elif isinstance(data, list):
                traders = data
                print(f"Found {len(traders)} traders in {source_name} (list)")
            else:
                print(f"Unexpected data format from {source_name}")
                return []
                
            # Add source information to each trader and map fields correctly
            for trader in traders:
                trader["source"] = source_name
                
                # Ensure each trader has an address field (mapped from name if needed)
                if "name" in trader and "address" not in trader:
                    trader["address"] = trader["name"]
                    
                # Ensure volume field exists (mapped from value if needed)
                if "value" in trader and "volume" not in trader:
                    trader["volume"] = trader["value"]
                    
                # Ensure rank field exists
                if "rank" not in trader:
                    trader["rank"] = 0  # This will be updated after sorting
                
            # Limit the number of traders if necessary
            return traders[:limit] if limit else traders
            
        except json.JSONDecodeError:
            print(f"Error: Response from {source_name} is not valid JSON")
            return []
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching {source_name}: {e}")
        return []

def fetch_multi_source_traders(limit_per_source=500, save_to_file=True):
    """
    Fetches traders from multiple sources and combines them
    """
    # Define the sources to fetch from - specify different limits for each
    sources = [
        {"url": "https://d2v1fiwobg9w6.cloudfront.net/largest_users_by_usd_volume", "name": "all_time_volume", "limit": 1000},
        {"url": "https://d2v1fiwobg9w6.cloudfront.net/largest_user_depositors", "name": "largest_depositors", "limit": 250},
        {"url": "https://d2v1fiwobg9w6.cloudfront.net/largest_liquidated_notional_by_user", "name": "largest_liquidated", "limit": 250},
        {"url": "https://d2v1fiwobg9w6.cloudfront.net/largest_user_trade_count", "name": "most_trades", "limit": 250},
        {"url": "https://d2v1fiwobg9w6.cloudfront.net/daily_usd_volume_by_user", "name": "daily_volume_users", "limit": 10}  # Note: only returns top 10 users
    ]
    
    # Fetch traders from all sources using ThreadPoolExecutor for parallel execution
    all_traders = []
    combined_traders = {}
    
    print(f"Fetching traders from {len(sources)} different sources...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        # Create a future for each source
        future_to_source = {executor.submit(fetch_traders_from_source, source["url"], source["name"], source["limit"]): source for source in sources}
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_source):
            source = future_to_source[future]
            try:
                traders = future.result()
                all_traders.extend(traders)
                print(f"Added {len(traders)} traders from {source['name']}")
            except Exception as e:
                print(f"Error processing {source['name']}: {e}")
    
    # Process and deduplicate traders
    for trader in all_traders:
        # Skip traders without an address
        if "address" not in trader or not trader["address"]:
            continue
            
        # Normalize the address
        address = trader["address"].lower()
        
        # Add to combined traders or update sources if already exists
        if address not in combined_traders:
            combined_traders[address] = trader
            combined_traders[address]["sources"] = [trader["source"]]
        else:
            # Add this source if not already present
            if trader["source"] not in combined_traders[address]["sources"]:
                combined_traders[address]["sources"].append(trader["source"])
    
    # Convert back to list
    unique_traders = list(combined_traders.values())
    
    # Sort by number of sources (more sources = higher ranking)
    unique_traders.sort(key=lambda x: len(x.get("sources", [])), reverse=True)
    
    print(f"\nCombined {len(all_traders)} traders from all sources into {len(unique_traders)} unique traders")
    
    # If we didn't get any traders, fallback to standard method
    if len(unique_traders) == 0:
        print("Warning: No traders found from multi-source. Falling back to standard method.")
        return fetch_top_traders_legacy(limit=1500, save_to_file=save_to_file)
    
    # Optional: Save to file
    if save_to_file:
        # Use original filename format with timestamp
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join("data", f"top_traders_{now}.json")
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        with open(filename, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "traders": unique_traders  # Just use the standard key name for compatibility
            }, f, indent=2)
            
        print(f"Saved traders data to {filename}")
    
    return unique_traders, unique_traders

def fetch_top_traders_legacy(limit=1500, save_to_file=True):
    """
    Legacy function to fetch top traders by volume only from Hyperliquid Stats API
    """
    url = "https://d2v1fiwobg9w6.cloudfront.net/largest_users_by_usd_volume"
    
    print(f"Fetching top {limit} traders by volume from {url}...")
    
    try:
        # Make the request
        response = requests.get(url, timeout=10)
        
        # Check if request was successful
        if response.status_code != 200:
            print(f"Error: Received status code {response.status_code}")
            return [], []
            
        # Try to parse the response as JSON
        try:
            data = response.json()
            if "table_data" in data:
                traders = data["table_data"]
            else:
                traders = data
                
            print(f"Found {len(traders)} traders")
            
            # Save traders data to file for later use
            if save_to_file:
                # Use original filename format for compatibility
                now = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = os.path.join("data", f"top_traders_{now}.json")
                os.makedirs(os.path.dirname(filename), exist_ok=True)
                
                with open(filename, 'w') as f:
                    json.dump({
                        "timestamp": datetime.now().isoformat(),
                        "traders": traders
                    }, f, indent=2)
                    
                print(f"Saved traders data to {filename}")
            
            # Sort traders by volume
            sorted_traders = sorted(traders, key=lambda x: float(x.get("volume", 0)), reverse=True)
            
            # Limit the number of traders if necessary
            limited_traders = sorted_traders[:limit] if limit else sorted_traders
            
            return traders, limited_traders
            
        except json.JSONDecodeError:
            print("Error: Response is not valid JSON")
            return [], []
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching traders: {e}")
        return [], []

def fetch_top_traders(limit=1500, save_to_file=True, use_multi_source=True):
    """
    Fetches the top traders by volume from Hyperliquid Stats API
    Displays their addresses and trading volumes
    Optionally saves to a file
    
    If use_multi_source is True, fetches from multiple sources instead of just volume
    """
    if use_multi_source:
        return fetch_multi_source_traders(limit_per_source=500, save_to_file=save_to_file)
    else:
        return fetch_top_traders_legacy(limit=limit, save_to_file=save_to_file)
    
    print(f"Fetching top {limit} traders by volume from {url}...")
    
    try:
        # Make the request
        response = requests.get(url, timeout=10)
        
        # Check if request was successful
        if response.status_code != 200:
            print(f"Error: Received status code {response.status_code}")
            print(f"Response: {response.text}")
            return None, None
            
        # Try to parse the response as JSON
        try:
            data = response.json()
            
            # Extract traders list from the correct format
            if isinstance(data, dict) and "table_data" in data:
                traders = data["table_data"]
                print(f"\nFound {len(traders)} traders in the table_data")
            elif isinstance(data, dict) and "chart_data" in data:
                traders = data["chart_data"]
                print(f"\nFound {len(traders)} traders in chart_data field")
            elif isinstance(data, list):
                traders = data
                print(f"\nFound {len(traders)} traders in list")
            else:
                print(f"Unexpected data format. Data keys: {data.keys() if isinstance(data, dict) else 'Not a dict'}")
                return None, None
                
            # Limit to the requested number
            traders = traders[:limit]
            
            # Format trader data into a clean format
            trader_data = []
            for i, trader in enumerate(traders):
                if isinstance(trader, dict):
                    # If each entry is a dict, extract name and value
                    address = trader.get("name", "Unknown")
                    volume = trader.get("value", 0)
                    
                    trader_data.append({
                        "rank": i+1,
                        "address": address,
                        "volume": volume
                    })
            
            # Display the traders
            print("\n=== Top Traders by Volume ===")
            print("-" * 80)
            print(f"{'Rank':<5} {'Address':<45} {'Volume (USD)':<20}")
            print("-" * 80)
            
            for trader in trader_data:
                address = trader["address"]
                
                # Format address for display (truncate if too long)
                if len(address) > 42:
                    formatted_address = f"{address[:6]}...{address[-4:]}"
                else:
                    formatted_address = address
                    
                # Print the trader info
                print(f"{trader['rank']:<5} {formatted_address:<45} ${trader['volume']:,.2f}")
                
            print("-" * 80)
            
            # Save trader data if requested
            if save_to_file:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_path = f"data/top_traders_{timestamp}.csv"
                
                # Save to CSV
                with open(file_path, "w", newline="") as csvfile:
                    fieldnames = ["rank", "address", "volume"]
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    
                    writer.writeheader()
                    writer.writerows(trader_data)
                
                print(f"Saved {len(trader_data)} traders to {file_path}")
                
                # Also save to JSON for programmatic access
                json_path = f"data/top_traders_{timestamp}.json"
                with open(json_path, "w") as jsonfile:
                    json.dump(trader_data, jsonfile, indent=2)
                    
                print(f"Saved trader data to {json_path}")
                
                return file_path, json_path
            
            return trader_data, None
            
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            print(f"Response text: {response.text[:200]}...")
            return None, None
            
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None, None

def get_latest_trader_file():
    """Returns the path to the most recent trader data file"""
    data_dir = "data"
    
    # Make sure data directory exists
    if not os.path.exists(data_dir):
        print(f"Data directory {data_dir} not found")
        return None
    
    # Look for top_traders files (original format)
    trader_files = [f for f in os.listdir(data_dir) if f.startswith("top_traders_") and f.endswith(".json")]
    
    if not trader_files:
        print("No trader data file found. Please run fetch_top_traders first.")
        return None
        
    # Get most recent file by name (they contain timestamps)
    latest_file = sorted(trader_files, reverse=True)[0]
    return os.path.join(data_dir, latest_file)

def load_trader_data(file_path=None):
    """Load trader data from JSON file"""
    if not file_path:
        file_path = get_latest_trader_file()
        
    if not file_path or not os.path.exists(file_path):
        print("No trader data file found. Please run fetch_top_traders first.")
        return []
        
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # Extract traders list
        if "traders" in data:
            traders = data["traders"]
            print(f"Loaded {len(traders)} traders from {file_path}")
            return traders
        else:
            print(f"Invalid trader data format in {file_path}")
            return []
    except Exception as e:
        print(f"Error loading trader data: {e}")
        return []

def get_user_state(address):
    """Gets user state for a specific trader using Hyperliquid SDK"""
    try:
        # Use the Info class from the SDK
        # The user_state method is defined in the Info class to call:
        # self.post("/info", {"type": "clearinghouseState", "user": address})
        user_state = info.user_state(address)
        return user_state
    except Exception as e:
        print(f"Error fetching user state for {address}: {e}")
        return None

def get_open_orders(address):
    """Gets open orders for a specific trader using Hyperliquid SDK"""
    try:
        # Use the Info class from the SDK
        # The open_orders method is defined in the Info class to call:
        # self.post("/info", {"type": "openOrders", "user": address})
        orders = info.open_orders(address)
        return orders
    except Exception as e:
        print(f"Error fetching open orders for {address}: {e}")
        return None

def process_user_positions(user_state):
    """Extracts position information from user state"""
    if not user_state or not isinstance(user_state, dict):
        return []
    
    positions = []
    asset_positions = user_state.get("assetPositions", [])
    
    for position in asset_positions:
        pos = position.get("position", {})
        
        # Skip positions with zero size
        szi = pos.get("szi")
        if szi is None or szi == "0":
            continue
            
        # Convert string values to appropriate types
        try:
            szi_float = float(szi)
            entry_px = float(pos.get("entryPx", "0"))
            liquidation_px = float(pos.get("liquidationPx", "0")) if pos.get("liquidationPx") else None
            
            position_data = {
                "coin": pos.get("coin"),
                "side": "LONG" if szi_float > 0 else "SHORT",
                "size": abs(szi_float),
                "entry_price": entry_px,
                "liquidation_price": liquidation_px
            }
            
            # Add leverage if available
            leverage = pos.get("leverage", {})
            if leverage:
                position_data["leverage_type"] = leverage.get("type")
                position_data["leverage_value"] = leverage.get("value")
                
            positions.append(position_data)
        except (ValueError, TypeError) as e:
            print(f"Error processing position: {e}")
            continue
    
    return positions

def process_open_orders(orders):
    """Extracts open order information"""
    if not orders or not isinstance(orders, list):
        return []
        
    processed_orders = []
    
    for order in orders:
        try:
            processed_order = {
                "coin": order.get("coin"),
                "side": "BUY" if order.get("side") == "B" else "SELL",
                "size": float(order.get("sz", "0")),
                "price": float(order.get("limitPx", "0")),
                "order_type": order.get("orderType")
            }
            processed_orders.append(processed_order)
        except (ValueError, TypeError) as e:
            print(f"Error processing order: {e}")
            continue
            
    return processed_orders

def batch_fetch_trader_data(trader_data, max_traders=None, max_retries=3, retry_wait=120, batch_size=5):
    """Fetch data for multiple traders in batches"""
    # If no trader data provided, try to load from file
    if not trader_data:
        print("No trader data provided, trying to load from file...")
        file_path = get_latest_trader_file()
        if file_path and os.path.exists(file_path):
            with open(file_path, 'r') as f:
                data = json.load(f)
                if "traders" in data:
                    trader_data = data["traders"]
                else:
                    print("Error: Invalid trader data format.")
                    return []
        else:
            print("Error: Could not find trader data file.")
            return []
    
    # Ensure trader_data is a list we can slice
    if not isinstance(trader_data, list):
        print("Error: Trader data is not in list format.")
        return []
    
    # Limit the number of traders if specified
    if max_traders and len(trader_data) > max_traders:
        trader_data = trader_data[:max_traders]
        
    # Import concurrent.futures for parallel processing
    import concurrent.futures
    
    # Split trader data into batches
    batches = [trader_data[i:i+batch_size] for i in range(0, len(trader_data), batch_size)]
    print(f"Fetching data for {len(trader_data)} traders in {len(batches)} batches of up to {batch_size} traders each...")
    
    all_trader_info = []
    
    # Function to process a single trader
    def process_trader(trader, trader_index, batch_size):
        if not isinstance(trader, dict) or "address" not in trader:
            print(f"Warning: Trader at index {trader_index} has invalid format. Skipping.")
            return None
            
        address = trader["address"]
        short_address = f"{address[:6]}...{address[-4:]}" if len(address) > 10 else address
        print(f"[{trader_index+1}/{batch_size}] Fetching data for {short_address}...")
        
        # Get user state with retry mechanism
        retry_count = 0
        user_state = None
        positions = []
        orders = None
        open_orders = []
        
        while retry_count < max_retries:
            try:
                # Get user state
                user_state = get_user_state(address)
                positions = process_user_positions(user_state)
                
                # Get open orders
                orders = get_open_orders(address)
                open_orders = process_open_orders(orders)
                
                # If we got here, the API calls succeeded
                break
                
            except Exception as e:
                retry_count += 1
                if retry_count >= max_retries:
                    print(f"Error fetching data for {short_address} after {max_retries} retries: {e}")
                    print(f"Skipping trader and continuing...")
                    return None
                
                print(f"Retry {retry_count}/{max_retries} after error: {e}")
                time.sleep(1)  # Wait 1 second before retrying
        
        return {
            "address": address,
            "rank": trader["rank"],
            "volume": trader["volume"],
            "positions": positions,
            "open_orders": open_orders
        }
    
    # Process each batch
    for batch_idx, batch in enumerate(batches):
        print(f"Processing batch {batch_idx+1}/{len(batches)}...")
        batch_results = []
        
        # Process all traders in the batch concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = [executor.submit(process_trader, trader, i, len(batch)) for i, trader in enumerate(batch)]
            individual_results = []
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result is not None:
                    individual_results.append(result)
        
        # Add batch results to overall results
        all_trader_info.extend(individual_results)
        
        # Pause 0.25 seconds between batches
        if batch_idx < len(batches) - 1:
            time.sleep(0.1)  # Reduced sleep between batches to 0.1s
    
    return all_trader_info

def export_positions_to_csv(trader_info):
    """Exports position data to CSV"""
    if not trader_info:
        print("No trader info to export")
        return None
        
    # Extract position data
    all_positions = []
    
    for trader in trader_info:
        address = trader["address"]
        rank = trader["rank"]
        
        for position in trader["positions"]:
            position_data = {
                "trader_address": address,
                "trader_rank": rank,
                "coin": position["coin"],
                "side": position["side"],
                "size": position["size"],
                "entry_price": position["entry_price"],
                "liquidation_price": position["liquidation_price"]
            }
            
            # Add leverage info if available
            if "leverage_type" in position:
                position_data["leverage_type"] = position["leverage_type"]
            if "leverage_value" in position:
                position_data["leverage_value"] = position["leverage_value"]
                
            all_positions.append(position_data)
    
    # Save to CSV
    if all_positions:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = f"data/trader_positions_{timestamp}.csv"
        
        # Make sure the data directory exists
        os.makedirs("data", exist_ok=True)
        
        # Convert to DataFrame and save
        df = pd.DataFrame(all_positions)
        df.to_csv(csv_path, index=False)
        
        print(f"\nExported {len(all_positions)} positions to {csv_path}")
        return csv_path
    else:
        print("No positions found to export")
        return None

def export_orders_to_csv(trader_info):
    """Exports order data to CSV"""
    if not trader_info:
        print("No trader info to export")
        return None
        
    # Extract order data
    all_orders = []
    
    for trader in trader_info:
        address = trader["address"]
        rank = trader["rank"]
        
        for order in trader["open_orders"]:
            order_data = {
                "trader_address": address,
                "trader_rank": rank,
                "coin": order["coin"],
                "side": order["side"],
                "size": order["size"],
                "price": order["price"],
                "order_type": order["order_type"]
            }
                
            all_orders.append(order_data)
    
    # Save to CSV
    if all_orders:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = f"data/trader_orders_{timestamp}.csv"
        
        # Make sure the data directory exists
        os.makedirs("data", exist_ok=True)
        
        # Convert to DataFrame and save
        df = pd.DataFrame(all_orders)
        df.to_csv(csv_path, index=False)
        
        print(f"\nExported {len(all_orders)} orders to {csv_path}")
        return csv_path
    else:
        print("No orders found to export")
        return None

def get_order_book(asset, max_age_seconds=60):
    """
    Fetch the current order book for an asset from the Hyperliquid API.
    Uses a simple cache to avoid redundant API calls.
    
    Args:
        asset (str): Asset symbol (e.g., 'BTC')
        max_age_seconds (int): Maximum age of cached data in seconds
        
    Returns:
        dict: Dictionary with 'bids' and 'asks' keys, each containing a list of dictionaries
              with 'price' and 'size' keys.
    """
    # Check cache first
    global orderbook_cache
    now = time.time()
    if asset in orderbook_cache and now - orderbook_cache[asset]["timestamp"] < max_age_seconds:
        print(f"Using cached orderbook for {asset}, age: {now - orderbook_cache[asset]["timestamp"]:.1f}s")
        return orderbook_cache[asset]["data"]
    try:
        url = "https://api.hyperliquid.xyz/info"
        payload = {
            "type": "l2Book",
            "coin": asset
        }
        
        response = requests.post(url, json=payload)
        
        if response.status_code != 200:
            print(f"Error fetching order book for {asset}: {response.status_code}")
            return None
        
        data = response.json()
        
        # The response structure has a 'levels' key that contains an array of arrays
        # The first array represents bids, the second represents asks
        # Each entry in these arrays is a dictionary with fields px (price), sz (size), and n (number of orders)
        if "levels" not in data:
            print(f"Unexpected response format for {asset} order book: {data}")
            return None
        
        levels = data["levels"]
        
        if len(levels) < 2:
            print(f"Incomplete order book data for {asset}: {levels}")
            return None
        
        # Extract bids and asks from the levels array
        bids_data = levels[0] if len(levels) > 0 else []
        asks_data = levels[1] if len(levels) > 1 else []
        
        # Process bids and asks into the expected format
        bids = []
        asks = []
        
        for bid in bids_data:
            if "px" in bid and "sz" in bid:
                # Format as dictionary with 'price' and 'size' keys
                bids.append({
                    "price": float(bid["px"]),
                    "size": float(bid["sz"])
                })
        
        for ask in asks_data:
            if "px" in ask and "sz" in ask:
                # Format as dictionary with 'price' and 'size' keys
                asks.append({
                    "price": float(ask["px"]),
                    "size": float(ask["sz"])
                })
        
        # Print some debug info
        print(f"Raw bids length: {len(bids_data)}, asks length: {len(asks_data)}")
        print(f"Processed {len(bids)} bids and {len(asks)} asks")
        
        if bids and asks:
            best_bid = max(b["price"] for b in bids)
            best_ask = min(a["price"] for a in asks)
            print(f"Best bid: {best_bid}")
            print(f"Best ask: {best_ask}")
            print(f"Mid price: {(best_bid + best_ask) / 2}")
        
        result = {
            "bids": bids,
            "asks": asks
        }
        
        # Cache the result
        orderbook_cache[asset] = {"data": result, "timestamp": time.time()}
        return result
    
    except Exception as e:
        print(f"Error fetching order book for {asset}: {e}")
        return None

def get_available_assets():
    """Gets a list of available assets from the Hyperliquid API"""
    try:
        # Use the meta endpoint to get information about available markets
        meta = info.meta()
        
        # Extract asset names from the meta information
        assets = []
        if meta and "universe" in meta:
            for coin in meta["universe"]:
                name = coin.get("name")
                if name:
                    assets.append(name)
        
        return sorted(assets)
    except Exception as e:
        print(f"Error fetching assets: {e}")
        return []

def get_top_assets_by_volume(limit=50):
    """
    Get the top assets by trading volume with robust retry logic
    """
    max_retries = 50
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Get the meta and asset contexts which includes volume information
            meta_and_asset_ctxs = info.post("/info", {"type": "metaAndAssetCtxs"})
            
            if not meta_and_asset_ctxs or len(meta_and_asset_ctxs) < 2:
                print("Failed to get meta and asset contexts")
                return []
                
            # Extract the meta data and asset contexts
            meta_data = meta_and_asset_ctxs[0]
            asset_contexts = meta_and_asset_ctxs[1]
            
            # Create a mapping of asset names to their indices
            asset_names = []
            if meta_data and "universe" in meta_data:
                for i, coin in enumerate(meta_data["universe"]):
                    asset_names.append(coin.get("name"))
            
            # Extract trading volume for each asset from the asset contexts
            asset_stats = {}
            
            for i, asset_ctx in enumerate(asset_contexts):
                if i < len(asset_names):
                    name = asset_names[i]
                    # Use dayNtlVlm (day notional volume) as the metric for ranking
                    if "dayNtlVlm" in asset_ctx:
                        try:
                            volume = float(asset_ctx["dayNtlVlm"])
                            asset_stats[name] = volume
                        except (ValueError, TypeError):
                            print(f"Invalid volume data for {name}")
                            continue
            
            if not asset_stats:
                print("No volume data found for any assets")
                return []
                
            # Sort assets by volume
            sorted_assets = sorted(asset_stats.items(), key=lambda x: x[1], reverse=True)
            
            # Get the top assets by volume
            top_assets = [asset for asset, volume in sorted_assets[:limit]]
            
            print(f"\nTop {len(top_assets)} assets by volume:")
            for i, asset in enumerate(top_assets):
                volume = asset_stats[asset]
                print(f"{i+1}. {asset}: ${volume:,.2f}")
                
            return top_assets
            
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                print(f"Error fetching top assets by volume after {max_retries} retries: {e}")
                import traceback
                traceback.print_exc()
                return []
            
            print(f"Retry {retry_count}/{max_retries} for get_top_assets_by_volume after error: {e}")
            time.sleep(1)  # Flat 1-second delay between retries

def analyze_asset_liquidations(asset, trader_info, price_step_percent=0.5):
    """
    Analyzes liquidation levels for a specific asset from the collected trader data
    """
    print(f"\nAnalyzing liquidation levels for {asset}...")
    
    # Debug: Check trader_info type
    print(f"trader_info type: {type(trader_info)}")
    if isinstance(trader_info, list) and len(trader_info) > 0:
        print(f"First trader type: {type(trader_info[0])}")
        print(f"First trader sample: {trader_info[0][:500] if isinstance(trader_info[0], str) else str(trader_info[0])[:500]}")
    
    if not trader_info:
        print(f"No trader info available for {asset}")
        return None
    
    # Extract positions for the specific asset
    asset_positions = []
    
    for trader in trader_info:
        try:
            # Handle case where trader might be a string
            if isinstance(trader, str):
                print(f"Warning: trader data is a string, skipping: {trader[:30]}...")
                continue
                
            # Check if positions exist and is a list
            if not isinstance(trader.get("positions", []), list):
                print(f"Warning: positions is not a list for trader {trader.get('address', 'unknown')}")
                continue
                
            for position in trader.get("positions", []):
                # Ensure position is a dictionary
                if not isinstance(position, dict):
                    print(f"Warning: position is not a dict: {position}")
                    continue
                if position.get("coin") == asset:
                    # Add trader info to the position
                    position_with_trader = position.copy()
                    position_with_trader["trader_address"] = trader.get("address", "unknown")
                    position_with_trader["trader_rank"] = trader.get("rank", 0)
                    asset_positions.append(position_with_trader)
        except Exception as e:
            print(f"Error processing trader data: {e}")
    
    if not asset_positions:
        print(f"No positions found for {asset}")
        return None
        
    print(f"\nAnalyzing {len(asset_positions)} positions for {asset}...")
    
    # Get current price with robust retry mechanism
    max_retries = 50
    retry_delay = 1  # Flat 1 second delay for all retries
    current_price = None
    all_mids = None
    
    for attempt in range(max_retries):
        try:
            # Configure proxy settings if needed
            if attempt > 0:
                print(f"Retry attempt {attempt+1}/{max_retries} for price data...")
                # Try to reset the session with different proxy settings
                info.session.close()
                import requests
                new_session = requests.Session()
                # Try without proxy on retry
                new_session.proxies = {}
                info.session = new_session
            
            # Get all mids using the direct POST method
            all_mids = info.post("/info", {"type": "allMids"})
            
            # The response is a dictionary with ticker as keys
            if asset in all_mids:
                current_price = float(all_mids[asset])
                print(f"Current price for {asset}: ${current_price:.2f}")
                break  # Success, exit the retry loop
            else:
                print(f"Asset {asset} not found in price data, retrying...")
        except Exception as e:
            if "Proxy Authentication Required" in str(e) or "407" in str(e):
                print(f"Proxy authentication error (attempt {attempt+1}/{max_retries}): {e}")
                # On proxy error, try to use a different connection method
                try:
                    # Try disabling proxy for the next attempt
                    import os
                    os.environ['HTTP_PROXY'] = ''
                    os.environ['HTTPS_PROXY'] = ''
                    # Use flat 1-second delay
                    import time
                    time.sleep(retry_delay)
                except:
                    pass
            else:
                print(f"Error fetching price data (attempt {attempt+1}/{max_retries}): {e}")
                # Use flat 1-second delay
                import time
                time.sleep(retry_delay)
    
    # Check if we got a valid price after all retries
    if current_price is None or current_price == 0:
        print(f"Could not find current price for {asset} after {max_retries} attempts")
        import traceback
        traceback.print_exc()
        return None
    
    # Calculate price range for liquidation analysis
    liquidation_prices = [p["liquidation_price"] for p in asset_positions if p["liquidation_price"] is not None]
    
    if not liquidation_prices:
        print(f"No liquidation prices found for {asset}")
        return None
        
    min_price = min(min(liquidation_prices) * 0.9, current_price * 0.9)
    max_price = max(max(liquidation_prices) * 1.1, current_price * 1.1)
    
    # Calculate step size
    price_range = max_price - min_price
    step_size = price_range * (price_step_percent / 100)
    
    # Create price bins
    price_bins = []
    current_price_bin = min_price
    while current_price_bin <= max_price:
        price_bins.append(current_price_bin)
        current_price_bin += step_size
        
    # Initialize liquidation bins
    long_liquidations = {price: {"value": 0, "positions": []} for price in price_bins}
    short_liquidations = {price: {"value": 0, "positions": []} for price in price_bins}
    
    # Map positions to price bins
    for position in asset_positions:
        if position["liquidation_price"] is None:
            continue
            
        # Find closest price bin
        liquidation_price = position["liquidation_price"]
        closest_bin = min(price_bins, key=lambda x: abs(x - liquidation_price))
        
        position_info = {
            "trader": position["trader_address"],
            "size": position["size"],
            "entry_price": position["entry_price"],
            "liquidation_price": liquidation_price
        }
        
        # Add to appropriate side
        if position["side"] == "LONG":
            long_liquidations[closest_bin]["value"] += position["size"]
            long_liquidations[closest_bin]["positions"].append(position_info)
        else:
            short_liquidations[closest_bin]["value"] += position["size"]
            short_liquidations[closest_bin]["positions"].append(position_info)
    
    # Calculate totals
    total_long_value = sum(bin_data["value"] for bin_data in long_liquidations.values())
    total_short_value = sum(bin_data["value"] for bin_data in short_liquidations.values())
    
    # Print results
    print(f"\nLiquidation Analysis for {asset}:")
    print(f"Total LONG liquidation value: {total_long_value:.4f}")
    print(f"Total SHORT liquidation value: {total_short_value:.4f}")
    
    # Format results
    result = {
        "asset": asset,
        "current_price": current_price,
        "price_bins": price_bins,
        "long_liquidations": long_liquidations,
        "short_liquidations": short_liquidations,
        "total_long_value": total_long_value,
        "total_short_value": total_short_value
    }
    
    return result

def analyze_orderbook_vs_liquidations(asset, liquidation_analysis, orderbook):
    """
    Compares orderbook depth against potential liquidations at different price levels
    to identify high-risk price zones
    
    Args:
        asset: Symbol for the asset being analyzed
        liquidation_analysis: Output from analyze_asset_liquidations
        orderbook: Dictionary with order book data
        
    Returns:
        Dictionary with analysis results
    """
    # Check if liquidation analysis exists
    if liquidation_analysis is None:
        print(f"  Warning: No liquidation analysis available for {asset}")
        return None
        
    # Structure of results
    results = {
        "asset": asset,
        "current_price": liquidation_analysis["current_price"],
        "bid_liquidity": {},
        "ask_liquidity": {},
        "long_risk": {},  # Liquidations that would be triggered by price drops
        "short_risk": {}, # Liquidations that would be triggered by price rises
        "high_risk_zones": {
            "long": [],   # Price zones with high long liquidation risk
            "short": []   # Price zones with high short liquidation risk
        }
    }
    
    # Extract bid/ask prices and sizes
    if not orderbook or "bids" not in orderbook or "asks" not in orderbook:
        print(f"Insufficient orderbook data for {asset}")
        return results
        
    bids = orderbook["bids"]
    asks = orderbook["asks"]
    
    # Safety check for empty lists
    if not bids or not asks:
        print(f"Empty bids or asks for {asset}")
        return results
    
    # Process bid liquidity (support, relevant for long positions)
    try:
        for bid in bids:
            results["bid_liquidity"][bid["price"]] = bid["size"]
    except Exception as e:
        print(f"Error processing bids: {e}")
        print(f"Bids data: {str(bids)[:200]}")
        
    # Process ask liquidity (resistance, relevant for short positions)
    try:
        for ask in asks:
            results["ask_liquidity"][ask["price"]] = ask["size"]
    except Exception as e:
        print(f"Error processing asks: {e}")
        print(f"Asks data: {str(asks)[:200]}")
        
    # Create sorted lists of price levels
    try:
        bid_prices = sorted(list(results["bid_liquidity"].keys()), reverse=True) if results["bid_liquidity"] else []  # Descending
        ask_prices = sorted(list(results["ask_liquidity"].keys())) if results["ask_liquidity"] else []  # Ascending
    except Exception as e:
        print(f"Error sorting price lists: {e}")
        bid_prices = []
        ask_prices = []
    
    # If we have no valid price levels, return early
    if not bid_prices and not ask_prices:
        print(f"No valid price levels found for {asset}")
        return results
        
    # Calculate cumulative liquidity at each level
    # This helps understand total available liquidity to absorb impact
    cumulative_bid_liquidity = {}
    cumulative_ask_liquidity = {}
    
    # Calculate bid cumulative liquidity from highest to lowest
    running_total = 0
    try:
        for price in bid_prices:
            running_total += results["bid_liquidity"][price]
            cumulative_bid_liquidity[price] = running_total
    except Exception as e:
        print(f"Error calculating bid cumulative liquidity: {e}")
        
    # Calculate ask cumulative liquidity from lowest to highest
    running_total = 0
    try:
        for price in ask_prices:
            running_total += results["ask_liquidity"][price]
            cumulative_ask_liquidity[price] = running_total
    except Exception as e:
        print(f"Error calculating ask cumulative liquidity: {e}")
        
    # Constants for risk analysis
    SEVERE_RISK_THRESHOLD = 0.7  # If liquidation/liquidity ratio > 0.7, severe risk
    HIGH_RISK_THRESHOLD = 0.5    # If ratio > 0.5, high risk
    MODERATE_RISK_THRESHOLD = 0.3 # If ratio > 0.3, moderate risk
    
    # Assess risk for long liquidations (downside risk)
    for price_bin in liquidation_analysis["long_liquidations"]:
        if price_bin >= liquidation_analysis["current_price"]:
            continue  # Only consider downside risk for longs
            
        # Get the liquidation details
        liquidation_value = liquidation_analysis["long_liquidations"][price_bin]["value"]
        
        if liquidation_value == 0:
            continue
            
        # Find relevant ask levels that would absorb this liquidation
        relevant_asks = [p for p in ask_prices if p <= price_bin]
        
        if not relevant_asks:
            continue
            
        # Calculate available liquidity at this price level and below
        available_liquidity = 0
        weighted_avg_price = 0
        total_weight = 0
        
        for i, ask_price in enumerate(relevant_asks[:5]):  # Consider up to 5 levels of depth
            level_liquidity = results["ask_liquidity"][ask_price]
            available_liquidity += level_liquidity
            
            # Weight price by liquidity for weighted average
            weighted_avg_price += ask_price * level_liquidity
            total_weight += level_liquidity
            
            # If we've accumulated enough liquidity to cover the liquidation, stop
            if available_liquidity >= liquidation_value * 1.5:  # 50% buffer
                break
                
        # Calculate weighted average price if we have liquidity
        if total_weight > 0:
            weighted_avg_price /= total_weight
        else:
            weighted_avg_price = price_bin
            
        # Calculate slippage as percentage from liquidation price
        slippage_pct = (price_bin - weighted_avg_price) / price_bin * 100
        
        # Calculate risk ratio
        risk_ratio = liquidation_value / available_liquidity if available_liquidity > 0 else 1
        
        # Apply risk factors based on market conditions
        # For example, if closer to current price, risk is higher
        proximity_to_current = (liquidation_analysis["current_price"] - price_bin) / liquidation_analysis["current_price"]
        proximity_factor = 1 + min(proximity_to_current * 2, 1)  # Max 2x increase for very close levels
        
        # Apply proximity factor to risk ratio
        adjusted_risk_ratio = risk_ratio * proximity_factor
        
        # Cap at 1.0 for visualization purposes
        adjusted_risk_ratio = min(adjusted_risk_ratio, 1.0)
        
        # Determine risk level
        if adjusted_risk_ratio >= SEVERE_RISK_THRESHOLD:
            risk_level = " SEVERE"
        elif adjusted_risk_ratio >= HIGH_RISK_THRESHOLD:
            risk_level = "HIGH"
        elif adjusted_risk_ratio >= MODERATE_RISK_THRESHOLD:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW"
            
        # Record this in our results
        results["long_risk"][price_bin] = {
            "liquidation_value": liquidation_value,
            "available_liquidity": available_liquidity,
            "risk_ratio": adjusted_risk_ratio,
            "risk_level": risk_level,
            "weighted_avg_price": weighted_avg_price,
            "slippage_pct": slippage_pct
        }
        
        # Flag high risk zones
        if adjusted_risk_ratio >= HIGH_RISK_THRESHOLD:
            results["high_risk_zones"]["long"].append({
                "price": price_bin,
                "risk_ratio": adjusted_risk_ratio,
                "liquidation_value": liquidation_value,
                "risk_level": risk_level
            })
    
    # Assess risk for short liquidations (upside risk)
    for price_bin in liquidation_analysis["short_liquidations"]:
        if price_bin <= liquidation_analysis["current_price"]:
            continue  # Only consider upside risk for shorts
            
        # Get the liquidation details
        liquidation_value = liquidation_analysis["short_liquidations"][price_bin]["value"]
        
        if liquidation_value == 0:
            continue
            
        # Find relevant bid levels that would absorb this liquidation
        relevant_bids = [p for p in bid_prices if p >= price_bin]
        
        if not relevant_bids:
            continue
            
        # Calculate available liquidity at this price level and above
        available_liquidity = 0
        weighted_avg_price = 0
        total_weight = 0
        
        for i, bid_price in enumerate(relevant_bids[:5]):  # Consider up to 5 levels of depth
            level_liquidity = results["bid_liquidity"][bid_price]
            available_liquidity += level_liquidity
            
            # Weight price by liquidity for weighted average
            weighted_avg_price += bid_price * level_liquidity
            total_weight += level_liquidity
            
            # If we've accumulated enough liquidity to cover the liquidation, stop
            if available_liquidity >= liquidation_value * 1.5:  # 50% buffer
                break
                
        # Calculate weighted average price if we have liquidity
        if total_weight > 0:
            weighted_avg_price /= total_weight
        else:
            weighted_avg_price = price_bin
            
        # Calculate slippage as percentage from liquidation price
        slippage_pct = (weighted_avg_price - price_bin) / price_bin * 100
        
        # Calculate risk ratio
        risk_ratio = liquidation_value / available_liquidity if available_liquidity > 0 else 1
        
        # Apply risk factors based on market conditions
        # For shorts, proximity to current price also increases risk
        proximity_to_current = (price_bin - liquidation_analysis["current_price"]) / liquidation_analysis["current_price"]
        proximity_factor = 1 + min(proximity_to_current * 2, 1)  # Max 2x increase for very close levels
        
        # Apply proximity factor to risk ratio
        adjusted_risk_ratio = risk_ratio * proximity_factor
        
        # Cap at 1.0 for visualization purposes
        adjusted_risk_ratio = min(adjusted_risk_ratio, 1.0)
        
        # Determine risk level
        if adjusted_risk_ratio >= SEVERE_RISK_THRESHOLD:
            risk_level = " SEVERE"
        elif adjusted_risk_ratio >= HIGH_RISK_THRESHOLD:
            risk_level = "HIGH"
        elif adjusted_risk_ratio >= MODERATE_RISK_THRESHOLD:
            risk_level = "MODERATE"
        else:
            risk_level = "LOW"
            
        # Record this in our results
        results["short_risk"][price_bin] = {
            "liquidation_value": liquidation_value,
            "available_liquidity": available_liquidity,
            "risk_ratio": adjusted_risk_ratio,
            "risk_level": risk_level,
            "weighted_avg_price": weighted_avg_price,
            "slippage_pct": slippage_pct
        }
        
        # Flag high risk zones
        if adjusted_risk_ratio >= HIGH_RISK_THRESHOLD:
            results["high_risk_zones"]["short"].append({
                "price": price_bin,
                "risk_ratio": adjusted_risk_ratio,
                "liquidation_value": liquidation_value,
                "risk_level": risk_level
            })
    
    # Print summary of high risk zones
    long_high_risk = results["high_risk_zones"]["long"]
    short_high_risk = results["high_risk_zones"]["short"]
    
    print("\n=== Orderbook vs Liquidations Analysis ===")
    if long_high_risk:
        print(f"High risk long liquidation zones:")
        for zone in sorted(long_high_risk, key=lambda x: x["risk_ratio"], reverse=True)[:3]:
            print(f"  - ${zone['price']:.2f}: {zone['risk_level']} (ratio: {zone['risk_ratio']:.2f}, volume: {zone['liquidation_value']:.4f})")
    else:
        print("No high risk long liquidation zones detected")
        
    if short_high_risk:
        print(f"High risk short liquidation zones:")
        for zone in sorted(short_high_risk, key=lambda x: x["risk_ratio"], reverse=True)[:3]:
            print(f"  - ${zone['price']:.2f}: {zone['risk_level']} (ratio: {zone['risk_ratio']:.2f}, volume: {zone['liquidation_value']:.4f})")
    else:
        print("No high risk short liquidation zones detected")
        
    return results

def simulate_liquidation_cascade(asset, liquidation_analysis, orderbook):
    """
    Simulate liquidation cascades based on orderbook depth and liquidation levels
    using direct calculation from orderbook data.
    
    Args:
        asset: Asset symbol
        liquidation_analysis: Output from analyze_asset_liquidations
        orderbook: Orderbook data with bids and asks
        
    Returns:
        Dictionary with cascade analysis and results
    """
    # Get current price and liquidation data
    current_price = liquidation_analysis["current_price"]
    price_bins = liquidation_analysis["price_bins"]
    long_liquidations = liquidation_analysis["long_liquidations"]
    short_liquidations = liquidation_analysis["short_liquidations"]
    
    # Debug prints
    print(f"DEBUG: long_liquidations type: {type(long_liquidations)}")
    print(f"DEBUG: short_liquidations type: {type(short_liquidations)}")
    
    # Create copies of the orderbook data that we can modify during simulation
    sim_orderbook = {
        "bids": [{"price": bid["price"], "size": bid["size"]} for bid in orderbook["bids"]],
        "asks": [{"price": ask["price"], "size": ask["size"]} for ask in orderbook["asks"]],
    }
    
    # Calculate total long and short liquidation values for market imbalance assessment
    total_long_value = liquidation_analysis.get("total_long_value", 0)
    total_short_value = liquidation_analysis.get("total_short_value", 0)
    
    # Calculate position imbalance ratio - higher means more longs than shorts
    long_short_ratio = total_long_value / total_short_value if total_short_value > 0 else float('inf')
    short_long_ratio = total_short_value / total_long_value if total_long_value > 0 else float('inf')
    
    # Function to simulate cascade in one direction
    def simulate_cascade(direction):
        # Determine which liquidations we're working with and sort price bins accordingly
        if direction == "downward":
            liquidations_by_price = long_liquidations
            sorted_price_bins = sorted(price_bins)  # Ascending prices for downward cascade
            trader_side = "sell"  # Long positions are sold when liquidated
        else:  # upward
            liquidations_by_price = short_liquidations
            sorted_price_bins = sorted(price_bins, reverse=True)  # Descending prices for upward cascade
            trader_side = "buy"  # Short positions are bought when liquidated
        
        # Starting point
        simulation_price = current_price
        processed_liquidations = set()
        cascade_steps = []
        total_value_liquidated = 0
        cumulative_price_impact = 0
        
        # We'll make a fresh copy of the orderbook for this direction
        sim_orderbook = {
            "bids": [{"price": bid["price"], "size": bid["size"]} for bid in orderbook["bids"]],
            "asks": [{"price": ask["price"], "size": ask["size"]} for ask in orderbook["asks"]],
        }
        
        # Loop through price bins in the appropriate direction
        for price_bin in sorted_price_bins:
            # Skip if the price is in the wrong direction for this cascade
            if direction == "downward" and price_bin > simulation_price:
                continue
            if direction == "upward" and price_bin < simulation_price:
                continue
                
            # Get liquidations that would be triggered at this price
            bin_liquidations = liquidations_by_price[price_bin]["value"]
            positions_affected = liquidations_by_price[price_bin]["positions"]
            
            # Skip if no liquidations
            if bin_liquidations == 0 or not positions_affected:
                continue
                
            # Check if any of these positions haven't been processed yet
            position_ids = [p.get("trader", "") + "_" + str(p.get("size", "")) for p in positions_affected]
            new_liquidations = [pos_id for pos_id in position_ids if pos_id not in processed_liquidations]
            
            if not new_liquidations:
                continue
                
            # Mark these liquidations as processed
            processed_liquidations.update(new_liquidations)
            
            # Calculate effective liquidation value (adjusting for already processed positions)
            effective_liquidation = bin_liquidations * (len(new_liquidations) / len(position_ids)) if position_ids else 0
            
            # Use our helper function to directly calculate price impact from orderbook
            execution_price, price_impact_pct, filled_levels = calculate_price_impact(
                effective_liquidation, 
                trader_side,
                simulation_price, 
                sim_orderbook
            )
            
            # Calculate absolute price impact
            absolute_impact = abs(execution_price - simulation_price)
            
            # Update simulation price for next iteration
            simulation_price = execution_price
            
            # Update cumulative impact
            cumulative_price_impact += abs(price_impact_pct / 100)
            
            # Record this step in the cascade
            cascade_steps.append({
                "price_level": price_bin,
                "liquidation_value": effective_liquidation,
                "executed_value": effective_liquidation,  # We're assuming full execution with slippage
                "unfilled_value": 0,  # Everything is filled with our model
                "initial_price": price_bin,
                "final_price": execution_price,
                "price_impact_pct": price_impact_pct,
                "positions_affected": len(new_liquidations),
                "filled_levels": filled_levels
            })
            
            total_value_liquidated += effective_liquidation
            
            # Update the orderbook for the next round of liquidations
            # We've already consumed the liquidity from this round
            if trader_side == "buy":
                # For buying, we've used up ask liquidity
                # Extract the prices and sizes from filled_levels
                for filled_level in filled_levels:
                    # Find and update this level in the orderbook
                    for i, ask in enumerate(sim_orderbook["asks"]):
                        if float(ask["price"]) == filled_level["price"]:
                            # Reduce the available size by what we filled
                            new_size = max(0, float(ask["size"]) - filled_level["size"])
                            sim_orderbook["asks"][i] = {"price": ask["price"], "size": new_size}
                            break
            else:  # sell
                # For selling, we've used up bid liquidity
                for filled_level in filled_levels:
                    for i, bid in enumerate(sim_orderbook["bids"]):
                        if float(bid["price"]) == filled_level["price"]:
                            new_size = max(0, float(bid["size"]) - filled_level["size"])
                            sim_orderbook["bids"][i] = {"price": bid["price"], "size": new_size}
                            break
        
        # Skip if no cascade was triggered
        if not cascade_steps:
            return None
            
        # Calculate total price impact
        starting_price = current_price
        ending_price = simulation_price
        total_price_impact_pct = abs((ending_price - starting_price) / starting_price * 100)
        
        # Calculate risk level considering position imbalance
        risk_level = calculate_cascade_risk_level(
            starting_price, 
            ending_price, 
            cumulative_price_impact,
            # Pass imbalance ratio - higher values indicate higher risk
            long_short_ratio if direction == "downward" else short_long_ratio
        )
        
        return {
            "direction": direction,
            "starting_price": starting_price,
            "ending_price": ending_price,
            "total_price_impact_pct": total_price_impact_pct,
            "total_liquidation_value": total_value_liquidated,
            "cascade_steps": cascade_steps,
            "risk_level": risk_level,
            "cumulative_impact": cumulative_price_impact
        }
    
    # Simulate cascades in both directions
    downward_cascade = simulate_cascade("downward")
    upward_cascade = simulate_cascade("upward")
    
    result = {
        "asset": asset,
        "current_price": current_price,
        "downward_cascade": downward_cascade,
        "upward_cascade": upward_cascade,
        "position_imbalance": {
            "total_long_value": total_long_value,
            "total_short_value": total_short_value,
            "long_short_ratio": long_short_ratio
        }
    }
    
    return result

def calculate_price_impact(size, direction, current_price, orderbook):
    """
    Calculate the price impact of executing a market order of a given size
    by walking through the actual orderbook liquidity
    
    Args:
        size: Size of the liquidation to execute
        direction: "buy" or "sell" (for short or long liquidations respectively)
        current_price: Current market price
        orderbook: The orderbook data with bids and asks
        
    Returns:
        Tuple of (execution_price, price_impact_percentage, filled_levels)
    """
    if size <= 0:
        return current_price, 0, []
    
    # Use the correct side of the orderbook based on direction
    if direction == "buy":
        # For buying (short liquidations), we walk up the asks
        book_side = sorted(orderbook["asks"], key=lambda x: x["price"])
    else:  # "sell"
        # For selling (long liquidations), we walk down the bids
        book_side = sorted(orderbook["bids"], key=lambda x: x["price"], reverse=True)
    
    remaining_size = size
    executed_size = 0
    filled_levels = []
    avg_price = 0
    weighted_sum = 0
    
    # Walk through the orderbook
    for level in book_side:
        price = float(level["price"])
        available_size = float(level["size"])
        
        if remaining_size <= available_size:
            # We can fully execute at this level
            filled_levels.append({"price": price, "size": remaining_size})
            weighted_sum += price * remaining_size
            executed_size += remaining_size
            remaining_size = 0
            break
        else:
            # Consume this level completely and continue
            filled_levels.append({"price": price, "size": available_size})
            weighted_sum += price * available_size
            executed_size += available_size
            remaining_size -= available_size
    
    # If we couldn't execute everything, apply a slippage model 
    # that increases exponentially with size
    if remaining_size > 0:
        # Base slippage starts at 5% for each unit of remaining size
        base_slippage = 0.05
        
        # Slippage increases with the percentage of liquidity consumed
        liquidity_consumed_pct = executed_size / (executed_size + remaining_size)
        
        # Increase slippage faster as we consume more liquidity
        # This creates an exponential curve - small orders have small slippage,
        # but large orders relative to available liquidity have much higher slippage
        slippage_factor = base_slippage * (1 + (liquidity_consumed_pct * 5))
        
        # Cap total slippage at 50% to avoid unrealistic prices
        additional_slippage = min(remaining_size * slippage_factor, 0.5)
        
        # Last price from orderbook, or current price if orderbook was empty
        last_price = filled_levels[-1]["price"] if filled_levels else current_price
        
        # Apply the slippage in the correct direction
        if direction == "buy":
            # Price goes up for buys
            impact_price = last_price * (1 + additional_slippage)
        else:
            # Price goes down for sells
            impact_price = last_price * (1 - additional_slippage)
            
        # Add this as a filled level for reporting purposes
        filled_levels.append({"price": impact_price, "size": remaining_size})
        weighted_sum += impact_price * remaining_size
        executed_size += remaining_size
    
    # Calculate weighted average price
    if executed_size > 0:
        avg_price = weighted_sum / executed_size
    else:
        avg_price = current_price
    
    # Calculate price impact as a percentage
    price_impact_pct = ((avg_price - current_price) / current_price) * 100
    # For sells (long liquidations), impact is negative
    if direction == "sell":
        price_impact_pct = -price_impact_pct
        
    return avg_price, price_impact_pct, filled_levels

def calculate_cascade_risk_level(starting_price, ending_price, cumulative_impact, imbalance_ratio):
    """
    Calculate the risk level of a cascade based on price impact and liquidity consumption
    """
    # Calculate percent change in price
    percent_change = abs(ending_price - starting_price) / starting_price * 100
    
    # Use more dynamic thresholds that consider both the overall market volatility
    # and the specific impact of this cascade
    
    # For Hyperliquid perps, typical volatility ranges can inform our thresholds
    if percent_change < 1:
        risk = "LOW"
    elif percent_change < 3:
        risk = "MODERATE"
    elif percent_change < 7:
        risk = "HIGH"
    else:
        risk = "SEVERE"
    
    # Consider total impact as an additional factor
    # This is more direct than before - no longer relying on arbitrary thresholds
    if cumulative_impact > 0.10:  # 10% total price impact is significant
        # Upgrade risk by one level if possible
        if risk == "LOW":
            risk = "MODERATE"
        elif risk == "MODERATE":
            risk = "HIGH"
        elif risk == "HIGH":
            risk = "SEVERE"
    
    # Adjust risk based on position imbalance
    if imbalance_ratio > 2:
        # High imbalance increases risk
        if risk == "LOW":
            risk = "MODERATE"
        elif risk == "MODERATE":
            risk = "HIGH"
        elif risk == "HIGH":
            risk = "SEVERE"
    
    return risk

def visualize_liquidation_analysis(asset, liquidation_analysis, orderbook_analysis, cascade_results=None):
    """
    Creates data for liquidation analysis without generating PNG visualizations
    
    Args:
        asset: The asset symbol
        liquidation_analysis: Output from analyze_asset_liquidations
        orderbook_analysis: Output from analyze_orderbook_vs_liquidations
        cascade_results: Optional output from simulate_liquidation_cascade
    """
    if not liquidation_analysis or not orderbook_analysis:
        print(f"Insufficient data for analysis for {asset}")
        return
        
    print(f"\nProcessing liquidation analysis data for {asset}...")
    
    # Create the data structure
    analysis_data = {
        "asset": asset,
        "current_price": liquidation_analysis["current_price"],
        "liquidation_data": liquidation_analysis,
        "orderbook_analysis": orderbook_analysis,
        "cascade_results": cascade_results
    }
    
    # Save the data to a JSON file
    try:
        # Ensure the data directory exists
        os.makedirs("data/visualizations", exist_ok=True)
        
        # Save the analysis data
        json_path = f"data/visualizations/{asset}_liquidation_analysis.json"
        with open(json_path, "w") as f:
            json.dump(analysis_data, f, indent=2)
        print(f"  Saved liquidation analysis data to {json_path}")
    except Exception as e:
        print(f"  Error saving liquidation analysis data: {e}")
    
    # Return the data for further processing
    return analysis_data

def create_cascade_visualization(asset, cascade_results, viz_dir):
    """
    Processes cascade simulation results without creating PNG visualizations
    """
    if not cascade_results:
        print(f"No cascade results to process for {asset}")
        return
        
    # Just return the data without creating visualizations
    return cascade_results

def summarize_asset_liquidity_and_positions(asset, trader_info, orderbook_analysis):
    """
    Summarizes total up and down liquidity and total short/long positions for an asset
    based on the top traders.
    
    Args:
        asset: The asset symbol
        trader_info: Information about traders, including their positions
        orderbook_analysis: Output from analyze_orderbook_vs_liquidations for liquidity data
        
    Returns:
        A dictionary containing the summary data
    """
    # Initialize counters
    total_long_positions = 0
    total_short_positions = 0
    total_long_value = 0
    total_short_value = 0
    
    # Count positions across all traders
    for trader in trader_info:
        for position in trader.get("positions", []):
            # Check if position is for the target asset
            if position.get("coin") == asset:
                # Extract size information - use "size" instead of "szi"
                size = position.get("size", 0)
                if size == 0:
                    continue
                    
                try:
                    # Get entry price using the correct key
                    entry_price = position.get("entry_price", 0)
                    
                    # Calculate position value (size * price)
                    position_value = abs(size) * entry_price
                    
                    # Determine position direction based on "side" field
                    side = position.get("side", "").upper()
                    
                    if side == "LONG":  # Long position
                        total_long_positions += 1
                        total_long_value += position_value
                    elif side == "SHORT":  # Short position
                        total_short_positions += 1
                        total_short_value += position_value
                except (ValueError, TypeError):
                    # Skip positions with invalid data
                    continue
    # Extract liquidity from orderbook analysis
    total_bid_liquidity = sum(orderbook_analysis.get("bid_liquidity", {}).values())
    total_ask_liquidity = sum(orderbook_analysis.get("ask_liquidity", {}).values())
    
    # Create summary dictionary
    summary = {
        "asset": asset,
        "total_long_positions": total_long_positions,
        "total_short_positions": total_short_positions,
        "total_long_value": total_long_value,
        "total_short_value": total_short_value,
        "total_bid_liquidity": total_bid_liquidity,
        "total_ask_liquidity": total_ask_liquidity,
        "long_short_ratio": total_long_value / total_short_value if total_short_value > 0 else float('inf'),
        "bid_ask_ratio": total_bid_liquidity / total_ask_liquidity if total_ask_liquidity > 0 else float('inf')
    }
    
    return summary

def analyze_top_assets_liquidations(trader_info, num_assets=50, num_traders=10):
    """
    Analyze liquidation levels for top assets by volume across top traders
    """
    if not trader_info:
        print("No trader info available")
        return {}
    
    # Use the first num_traders from the trader_info list
    # These are already sorted by volume from fetch_top_traders
    top_traders = trader_info[:num_traders]
    
    print(f"\nAnalyzing liquidation levels for top {len(top_traders)} traders")
    
    # Get top assets by volume
    top_assets = get_top_assets_by_volume(num_assets)
    
    if not top_assets:
        print("Failed to retrieve top assets by volume")
        return {}
    
    results = {}
    processed_assets = []
    error_assets = []
    
    print(f"\nFound {len(top_assets)} top assets to analyze")
    
    for i, asset in enumerate(top_assets):
        print(f"\n[{i+1}/{len(top_assets)}] Analyzing {asset}...")
        try:
            result = analyze_asset_liquidations(asset, top_traders)
            if result:
                # Save results to JSON file first, before any potential errors
                analysis_path = f"data/{asset}_liquidation_analysis.json"
                
                # Make sure the data directory exists
                os.makedirs("data", exist_ok=True)
                
                print(f"Attempting to save to {analysis_path}...")
                try:
                    with open(analysis_path, "w") as jsonfile:
                        # Save the FULL result data, not just a summary
                        json.dump(result, jsonfile, indent=2)
                    print(f"Successfully saved FULL liquidation analysis to {analysis_path}")
                except Exception as e:
                    print(f"ERROR saving to {analysis_path}: {e}")
                
                # Also save a summary version with timestamp for historical tracking
                summary_path = f"data/liquidation_summary_{asset}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(summary_path, "w") as jsonfile:
                    save_data = {
                        "asset": asset,
                        "current_price": result["current_price"],
                        "total_long_value": result["total_long_value"],
                        "total_short_value": result["total_short_value"],
                        "total_liquidation_value": result["total_liquidation_value"],
                        "timestamp": datetime.now().isoformat()
                    }
                    json.dump(save_data, jsonfile, indent=2)
                
                # Analyze orderbook vs liquidations
                try:
                    orderbook = get_order_book(asset)
                    if orderbook:
                        orderbook_analysis = None
                        if result is not None:
                            orderbook_analysis = analyze_orderbook_vs_liquidations(asset, result, orderbook)
                        if orderbook_analysis:
                            result["orderbook_analysis"] = orderbook_analysis
                            
                            # Update the saved JSON with orderbook analysis
                            with open(analysis_path, "w") as jsonfile:
                                json.dump(result, jsonfile, indent=2)
                            
                            # Add to results
                            results[asset] = save_data
                            processed_assets.append(asset)
                        else:
                            print(f"Skipping {asset}: No orderbook analysis available")
                            error_assets.append(asset)
                    else:
                        print(f"Skipping {asset}: No orderbook data available")
                        error_assets.append(asset)
                except Exception as e:
                    print(f"Error during orderbook analysis for {asset}: {e}")
                    import traceback
                    traceback.print_exc()
                    error_assets.append(asset)
            else:
                print(f"Skipping {asset}: No liquidation analysis available")
                error_assets.append(asset)
        except Exception as e:
            print(f"Error analyzing {asset}: {e}")
            import traceback
            traceback.print_exc()
            error_assets.append(asset)
    
    print(f"\nCompleted analysis for {len(processed_assets)} assets")
    print(f"Processed assets: {', '.join(processed_assets)}")
    
    if error_assets:
        print(f"Failed to process {len(error_assets)} assets: {', '.join(error_assets)}")
    
    return results

def export_asset_summaries_to_csv(asset_summaries):
    """
    Exports asset summaries to a CSV file with timestamp
    
    Args:
        asset_summaries: List of dictionaries with asset summary data
    """
    if not asset_summaries:
        print("No asset summaries to export.")
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = f"data/asset_summaries_{timestamp}.csv"
    
    # Create directories if they don't exist
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # Define CSV fields to export
    fields = [
        'asset',
        'current_price',
        'total_long_positions',
        'total_long_value',
        'total_short_positions',
        'total_short_value',
        'long_short_ratio',
        'total_bid_liquidity',
        'total_ask_liquidity',
        'bid_ask_ratio',
        'downward_risk_level',
        'upward_risk_level',
        'downward_impact_pct',
        'upward_impact_pct',
        'total_liquidation_value',
        'long_liquidation_value',
        'short_liquidation_value'
    ]
    
    # Write to CSV
    try:
        with open(file_path, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fields)
            writer.writeheader()
            
            for summary in asset_summaries:
                writer.writerow(summary)
                
        print(f"\nAsset summaries exported to: {file_path}")
    except Exception as e:
        print(f"Error exporting asset summaries: {e}")

def main(max_traders=1500, max_assets=50, use_enhanced=True, use_multi_source=True):
    """Main function to orchestrate the data collection and analysis"""
    # Setup console separator for better readability
    def print_section(title):
        print("\n" + "="*80)
        print(f" {title} ".center(80, "="))
        print("="*80 + "\n")
    
    print_section("LIQUIDATION ANALYSIS TOOL")
    
    # Ensure data directories exist
    data_dir = "data"
    viz_dir = os.path.join(data_dir, "visualizations")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(viz_dir, exist_ok=True)
    
    # Set the number of traders and assets to analyze
    num_traders = max_traders
    num_assets = max_assets
    
    # Step 1: Fetch top traders by volume (or multi-source if enabled)
    print_section("FETCHING TOP TRADERS")
    raw_traders, sorted_traders = fetch_top_traders(limit=max_traders, save_to_file=True, use_multi_source=use_multi_source)
    
    # Load trader data
    print("Loading trader data...")
    latest_file = get_latest_trader_file()
    
    if latest_file:
        trader_data = load_trader_data(latest_file)
        if trader_data:
            print(f"Loaded {len(trader_data)} traders for analysis.")
        else:
            print("ERROR: No valid trader data found. Using raw trader data directly.")
            trader_data = sorted_traders
            print(f"Using {len(trader_data)} traders from direct fetch.")
    else:
        print("ERROR: No trader data file found. Using raw trader data directly.")
        trader_data = sorted_traders
        print(f"Using {len(trader_data)} traders from direct fetch.")
    
    # Step 2: Fetch positions and orders for top traders
    print_section("FETCHING TRADER POSITIONS AND ORDERS")
    trader_info = batch_fetch_trader_data(trader_data, max_traders=num_traders)
    print(f"Successfully fetched data for {len(trader_info)} traders.")
    
    # Export data to CSVs
    export_positions_to_csv(trader_info)
    export_orders_to_csv(trader_info)
    
    # Step 3: Analyze liquidation levels for top assets
    print_section("ANALYZING LIQUIDATION RISK FOR TOP ASSETS")
    
    # Get the top assets by volume
    print("Getting top assets by volume...")
    top_assets = get_top_assets_by_volume(num_assets)
    
    if not top_assets:
        print("Failed to get top assets. Exiting.")
        return
    
    print(f"Top {len(top_assets)} assets by volume:")
    for asset_idx, asset in enumerate(top_assets):
        print(f"{asset_idx + 1}. {asset}")
        
    # Analyze each asset
    asset_summaries = []  # To collect all asset summaries
    
    # Ask if user wants to use enhanced analysis methods
    use_enhanced = True
    if ENHANCED_MODULES_AVAILABLE:
        use_enhanced = True
        print("Using enhanced analysis techniques with dynamic thresholds and multi-level imbalance detection.")
    
    for i, asset in enumerate(top_assets):
        print(f"\n[{i+1}/{len(top_assets)}] Analyzing {asset}...")
        
        # Step 1: Get order book data
        print(f"  Fetching order book for {asset}...")
        orderbook = get_order_book(asset)
        if not orderbook:
            print(f"  Failed to retrieve order book for {asset}. Skipping.")
            continue
        
        # Debug orderbook structure
        print(f"DEBUG - orderbook type: {type(orderbook)}")
        print(f"DEBUG - orderbook keys: {list(orderbook.keys())}")
        print(f"DEBUG - bids type: {type(orderbook['bids'])}")
        print(f"DEBUG - first bid: {orderbook['bids'][0] if orderbook['bids'] else 'None'}")
        
        # Step 2: Analyze liquidation levels
        print(f"  Analyzing liquidation levels for {asset}...")
        liquidation_analysis = analyze_asset_liquidations(asset, trader_info)
        
        # Step 3: Compare order book depth vs liquidation levels
        print(f"  Comparing order book depth vs liquidation levels...")
        
        # Analyze orderbook vs liquidations
        orderbook_analysis = None
        if liquidation_analysis is not None:
            orderbook_analysis = analyze_orderbook_vs_liquidations(
                asset, 
                liquidation_analysis, 
                orderbook
            )
        else:
            print(f"  Skipping orderbook analysis for {asset} due to missing liquidation data")
        
        # New Step: Enhanced cluster analysis if enabled
        enhanced_clusters = None
        cascade_probabilities = None
        optimized_ranges = None
        if use_enhanced and ENHANCED_MODULES_AVAILABLE:
            print(f"  Performing enhanced cluster analysis with dynamic thresholds...")
            try:
                # Extract all positions for this asset
                asset_positions = []
                for trader_data in trader_info:
                    trader_addr = trader_data.get('address', '')
                    for pos in trader_data.get('positions', []):
                        if pos.get('coin') == asset:
                            asset_positions.append(pos)
                
                # Create a DataFrame for more convenient processing
                positions_df = pd.DataFrame(asset_positions)
                
                # If positions exist, analyze them
                if not positions_df.empty:
                    # Create enhanced cluster results with our improved functions
                    # Step 1: Get enhanced clusters with dynamic thresholds
                    print("DEBUG - Before calling identify_liquidation_clusters")
                    print(f"DEBUG - liquidation_analysis keys: {liquidation_analysis.keys()}")
                    print(f"DEBUG - long_liquidations type: {type(liquidation_analysis.get('long_liquidations'))}")
                    print(f"DEBUG - short_liquidations type: {type(liquidation_analysis.get('short_liquidations'))}")
                    
                    enhanced_clusters = identify_liquidation_clusters(
                        asset,
                        liquidation_analysis,
                        orderbook=orderbook
                    )
                    
                    print(f"  Found {len(enhanced_clusters['clusters'])} liquidation clusters")
                    
                    # Step 2: Calculate cascade probability with domino density metrics
                    cascade_probabilities = calculate_cascade_probability(
                        enhanced_clusters,         # First param: clusters
                        liquidation_analysis["current_price"],  # Second param: current_price 
                        asset,                    # Third param: asset
                        debug=True                # Optional debug param
                    )
                    
                    print(f"  Cascade probability: Long: {cascade_probabilities['long_cascade']['probability']:.2f}, " +
                          f"Short: {cascade_probabilities['short_cascade']['probability']:.2f}")
                    
                    # Rest of the enhanced analysis code...
                else:
                    print("  No positions found for enhanced analysis")
            except Exception as e:
                print(f"  Error during enhanced analysis: {e}")
                print(f"  Error traceback: {traceback.format_exc()}")
                enhanced_clusters = None
                cascade_probabilities = None
                optimized_ranges = None
                # Fall back to standard analysis
        # Step 4: Simulate liquidation cascade
        print(f"  Simulating liquidation cascade scenarios...")
        cascade_results = simulate_liquidation_cascade(asset, liquidation_analysis, orderbook)
        
        # Debug information
        print(f"  DEBUG - cascade_results is None: {cascade_results is None}")
        if cascade_results is not None:
            print(f"  DEBUG - cascade_results keys: {list(cascade_results.keys())}")
            print(f"  DEBUG - downward_cascade is None: {cascade_results.get('downward_cascade') is None}")
            print(f"  DEBUG - upward_cascade is None: {cascade_results.get('upward_cascade') is None}")
            
        # Step 5: Create visualizations
        print(f"  Creating visualizations...")
        visualize_liquidation_analysis(asset, liquidation_analysis, orderbook_analysis, cascade_results)
        
        # Print summary
        print(f"\n  {asset} RISK SUMMARY:")
        
        # Default values for risk metrics
        downward_risk = "UNKNOWN"
        upward_risk = "UNKNOWN"
        down_impact = 0
        up_impact = 0
        
        # Only try to access cascade_results if it's not None
        if cascade_results is not None:
            # Use safe dictionary access with get() method and default values
            if "downward_cascade" in cascade_results:
                dc = cascade_results["downward_cascade"]
                if dc is not None:
                    downward_risk = dc.get("risk_level", "UNKNOWN")
                    down_impact = dc.get("total_price_impact_pct", 0)
            
            if "upward_cascade" in cascade_results:
                uc = cascade_results["upward_cascade"]
                if uc is not None:
                    upward_risk = uc.get("risk_level", "UNKNOWN")
                    up_impact = uc.get("total_price_impact_pct", 0)
                    
            # Adjust risk levels based on position imbalance
            position_imbalance = cascade_results.get("position_imbalance", {})
            long_short_ratio = position_imbalance.get("long_short_ratio", 1.0)
            
            # If we have significantly more shorts than longs, downward risk should be lower
            if long_short_ratio < 0.5 and downward_risk != "UNKNOWN":
                # More shorts than longs - reduce downward risk
                if downward_risk == "SEVERE":
                    downward_risk = "HIGH"
                elif downward_risk == "HIGH":
                    downward_risk = "MODERATE"
                elif downward_risk == "MODERATE":
                    downward_risk = "LOW"
                    
            # If we have significantly more longs than shorts, upward risk should be lower
            if long_short_ratio > 2.0 and upward_risk != "UNKNOWN":
                # More longs than shorts - reduce upward risk
                if upward_risk == "SEVERE":
                    upward_risk = "HIGH"
                elif upward_risk == "HIGH":
                    upward_risk = "MODERATE"
                elif upward_risk == "MODERATE":
                    upward_risk = "LOW"
        
        # Further adjust risk based on enhanced analysis if available
        if use_enhanced and enhanced_clusters is not None:
            try:
                # Access enhanced opportunity data
                if 'consolidated_imbalance' in full_analysis:
                    consolidation = full_analysis['consolidated_imbalance']
                    asset_summary['enhanced_imbalance_score'] = consolidation.get('composite_imbalance_score', 0)
                
                if 'dynamic_threshold' in enhanced_clusters:
                    asset_summary['dynamic_threshold'] = enhanced_clusters['dynamic_threshold']
                
                if enhanced_clusters.get('top_opportunity'):
                    asset_summary['top_opportunity_entry'] = enhanced_clusters['top_opportunity'].get('ideal_entry', 0)
                    asset_summary['top_opportunity_direction'] = enhanced_clusters['top_opportunity'].get('target_side', '')
                
                # Add cascade probability information if available
                if cascade_results and 'cascade_probabilities' in cascade_results:
                    probs = cascade_results['cascade_probabilities']
                    asset_summary['downward_cascade_probability'] = probs.get('long', 0)
                    asset_summary['upward_cascade_probability'] = probs.get('short', 0)
                
                # Add optimized trading range information if available
                if cascade_results and 'optimized_ranges' in cascade_results:
                    top = cascade_results['optimized_ranges'][0]
                    asset_summary['optimized_trade_side'] = top.get('trade_side', '')
                    asset_summary['optimized_entry_price'] = top.get('entry_price', 0)
                    asset_summary['optimized_target_price'] = top.get('target_price', 0)
                    asset_summary['optimized_stop_price'] = top.get('stop_price', 0)
                    asset_summary['optimized_risk_reward'] = top.get('risk_reward', 0)
                    asset_summary['optimized_quality_score'] = top.get('quality_score', 0)
            except Exception:
                # If any error occurs, continue without enhanced metrics
                pass
        
        # Print formatted risk summary
        risk_indicator = {
            "LOW": "🟢",
            "MODERATE": "🟡",
            "HIGH": "🟠",
            "SEVERE": "🔴",
            "UNKNOWN": "⚪"
        }
        
        print(f"  Downward Risk: {risk_indicator.get(downward_risk, '⚪')} {downward_risk} (Price Impact: {down_impact:.2f}%)")
        print(f"  Upward Risk: {risk_indicator.get(upward_risk, '⚪')} {upward_risk} (Price Impact: {up_impact:.2f}%)")
        
        # Generate and print the liquidity and position summary
        asset_summary = summarize_asset_liquidity_and_positions(asset, trader_info, orderbook_analysis)
        
        print(f"\n  {asset} LIQUIDITY AND POSITION SUMMARY:")
        print(f"  Total Long Positions: {asset_summary['total_long_positions']} (${asset_summary['total_long_value']:,.2f})")
        print(f"  Total Short Positions: {asset_summary['total_short_positions']} (${asset_summary['total_short_value']:,.2f})")
        print(f"  Long/Short Value Ratio: {asset_summary['long_short_ratio']:.2f}")
        print(f"  Total Bid Liquidity: ${asset_summary['total_bid_liquidity']:,.2f}")
        print(f"  Total Ask Liquidity: ${asset_summary['total_ask_liquidity']:,.2f}")
        print(f"  Bid/Ask Liquidity Ratio: {asset_summary['bid_ask_ratio']:.2f}")
        
        # Add enhanced metrics if available
        if use_enhanced and enhanced_clusters is not None:
            try:
                # Access enhanced opportunity data
                if 'top_opportunity':
                    top_opp = enhanced_clusters['top_opportunity']
                    
                    # Adjust risk based on market impact and isolation
                    if 'market_impact' in top_opp and top_opp['market_impact'] > 0.7:
                        # High market impact increases risk
                        if top_opp['direction'] == 'long' and downward_risk != "UNKNOWN":
                            # Increase downward risk
                            if downward_risk == "LOW":
                                downward_risk = "MODERATE"
                            elif downward_risk == "MODERATE":
                                downward_risk = "HIGH"
                            elif downward_risk == "HIGH":
                                downward_risk = "SEVERE"
                        
                        elif top_opp['direction'] == 'short' and upward_risk != "UNKNOWN":
                            # Increase upward risk
                            if upward_risk == "LOW":
                                upward_risk = "MODERATE"
                            elif upward_risk == "MODERATE":
                                upward_risk = "HIGH"
                            elif upward_risk == "HIGH":
                                upward_risk = "SEVERE"
            except Exception:
                # If any error occurs, continue without enhanced metrics
                pass
        
        # Print formatted risk summary
        risk_indicator = {
            "LOW": "🟢",
            "MODERATE": "🟡",
            "HIGH": "🟠",
            "SEVERE": "🔴",
            "UNKNOWN": "⚪"
        }
        
        print(f"  Downward Risk: {risk_indicator.get(downward_risk, '⚪')} {downward_risk} (Price Impact: {down_impact:.2f}%)")
        print(f"  Upward Risk: {risk_indicator.get(upward_risk, '⚪')} {upward_risk} (Price Impact: {up_impact:.2f}%)")
        
        # Generate and print the liquidity and position summary
        asset_summary = summarize_asset_liquidity_and_positions(asset, trader_info, orderbook_analysis)
        
        print(f"\n  {asset} LIQUIDITY AND POSITION SUMMARY:")
        print(f"  Total Long Positions: {asset_summary['total_long_positions']} (${asset_summary['total_long_value']:,.2f})")
        print(f"  Total Short Positions: {asset_summary['total_short_positions']} (${asset_summary['total_short_value']:,.2f})")
        print(f"  Long/Short Value Ratio: {asset_summary['long_short_ratio']:.2f}")
        print(f"  Total Bid Liquidity: ${asset_summary['total_bid_liquidity']:,.2f}")
        print(f"  Total Ask Liquidity: ${asset_summary['total_ask_liquidity']:,.2f}")
        print(f"  Bid/Ask Liquidity Ratio: {asset_summary['bid_ask_ratio']:.2f}")
        
        # Add enhanced metrics if available
        if use_enhanced and enhanced_clusters is not None:
            try:
                # Access enhanced opportunity data
                if 'consolidated_imbalance' in full_analysis:
                    consolidation = full_analysis['consolidated_imbalance']
                    asset_summary['enhanced_imbalance_score'] = consolidation.get('composite_imbalance_score', 0)
                
                if 'dynamic_threshold' in enhanced_clusters:
                    asset_summary['dynamic_threshold'] = enhanced_clusters['dynamic_threshold']
                
                if enhanced_clusters.get('top_opportunity'):
                    asset_summary['top_opportunity_entry'] = enhanced_clusters['top_opportunity'].get('ideal_entry', 0)
                    asset_summary['top_opportunity_direction'] = enhanced_clusters['top_opportunity'].get('target_side', '')
                
                # Add cascade probability information if available
                if cascade_results and 'cascade_probabilities' in cascade_results:
                    probs = cascade_results['cascade_probabilities']
                    asset_summary['downward_cascade_probability'] = probs.get('long', 0)
                    asset_summary['upward_cascade_probability'] = probs.get('short', 0)
                
                # Add optimized trading range information if available
                if cascade_results and 'optimized_ranges' in cascade_results:
                    top = cascade_results['optimized_ranges'][0]
                    asset_summary['optimized_trade_side'] = top.get('trade_side', '')
                    asset_summary['optimized_entry_price'] = top.get('entry_price', 0)
                    asset_summary['optimized_target_price'] = top.get('target_price', 0)
                    asset_summary['optimized_stop_price'] = top.get('stop_price', 0)
                    asset_summary['optimized_risk_reward'] = top.get('risk_reward', 0)
                    asset_summary['optimized_quality_score'] = top.get('quality_score', 0)
            except Exception:
                # If any error occurs, continue without enhanced metrics
                pass
        
        print("\n" + "="*80 + "\n")
        
        # Collect the asset summary
        asset_summary['asset'] = asset
        asset_summary['current_price'] = liquidation_analysis.get('current_price', 0)
        asset_summary['downward_risk_level'] = downward_risk
        asset_summary['upward_risk_level'] = upward_risk
        asset_summary['downward_impact_pct'] = down_impact
        asset_summary['upward_impact_pct'] = up_impact
        asset_summary['total_liquidation_value'] = liquidation_analysis.get('total_liquidation_value', 0)
        asset_summary['long_liquidation_value'] = liquidation_analysis.get('long_liquidation_value', 0)
        asset_summary['short_liquidation_value'] = liquidation_analysis.get('short_liquidation_value', 0)
        
        # Add to the collection of summaries
        asset_summaries.append(asset_summary)
    
    # Export all asset summaries to CSV
    print_section("EXPORTING ASSET SUMMARIES")
    export_asset_summaries_to_csv(asset_summaries)
    
    print_section("ANALYSIS COMPLETE")
    print(f"Visualizations saved to: {viz_dir}")
    print("Use the visualizations to identify high-risk assets and price levels.")
    
    if use_enhanced and ENHANCED_MODULES_AVAILABLE:
        print("\nEnhanced analysis techniques were used, providing:")
        print("- Dynamic threshold adjustment based on asset volatility")
        print("- Exponential decay weighting for proximity to current price")
        print("- Multi-level imbalance detection (near, medium, far-term)")
        print("- Liquidation density and thin spot identification")
        print("- Market impact potential based on orderbook depth")
    else:
        print("\nBase analysis techniques were used.")
        if not ENHANCED_MODULES_AVAILABLE:
            print("Enhanced modules are not available. Ensure cluster_analysis.py, daily_trading_analysis.py, and enhanced_heatmap.py exist.")
    
    # Check if data directory exists and list its contents
    print("\nChecking data directory...")
    data_dir = "data"
    if os.path.exists(data_dir):
        print(f"Data directory exists at: {os.path.abspath(data_dir)}")
        files = os.listdir(data_dir)
        print(f"Files in data directory ({len(files)} files):")
        for file in files:
            file_path = os.path.join(data_dir, file)
            file_size = os.path.getsize(file_path)
            print(f"  - {file} ({file_size} bytes)")
    else:
        print(f"Data directory does not exist at: {os.path.abspath(data_dir)}")

# Standard exit function for program termination
def exit_with_message(message="ANALYSIS COMPLETE", exit_code=0):
    print(f"\n\n==== {message} =====")
    # Use os._exit which is more forceful than sys.exit
    os._exit(exit_code)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Liquidation Analysis Tool")
    parser.add_argument("-t", "--traders", type=int, default=1500, help="Number of traders to analyze")
    parser.add_argument("-a", "--assets", type=int, default=50, help="Number of assets to analyze")
    parser.add_argument("-e", "--enhanced", action="store_true", help="Use enhanced analysis techniques")
    # Timeout argument kept for backward compatibility but no longer used
    parser.add_argument("--timeout", type=int, default=120, help="DEPRECATED: No longer used for automatic termination")
    parser.add_argument("--no-multi-source", action="store_true", help="Disable multi-source trader fetching (use only volume traders)")
    args = parser.parse_args()
    
    # Note: Automatic termination has been disabled
    print("Running without automatic termination - script will continue until complete")
    
    # Run the main function
    try:
        main(max_traders=args.traders, max_assets=args.assets, use_enhanced=args.enhanced, use_multi_source=not args.no_multi_source)
        # Exit after successful completion
        exit_with_message("ANALYSIS COMPLETE", 0)
    except Exception as e:
        print(f"Error in main function: {e}")
        traceback.print_exc()
        # Force exit with error code
        exit_with_message("SCRIPT COMPLETED WITH ERRORS", 1)
