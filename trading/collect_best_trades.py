#!/usr/bin/env python
"""
Collect Best Trades
------------------
Scans all analyzed assets, collects their best trade recommendations,
and outputs a consolidated list of top trades sorted by confidence.

This script can be run independently to test signal generation functionality
before integrating it into the main batch workflow.
"""

import os
import re
import sys
import json
import time
import locale
import fnmatch
import argparse
import math
import pandas as pd
from datetime import datetime, timedelta
from collections import defaultdict
# Import for webhook functionality
import requests

# Add parent directory to path to allow imports from root after moving to trading/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Define project root for consistent file paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Import time estimation function from utils directory
from utils.price_targeting import estimate_liquidation_trade_duration
# Import Hyperliquid API for position checking
from hyperliquid.info import Info
from hyperliquid.utils.constants import MAINNET_API_URL

# Import trade adjustment functionality from utils directory
try:
    from utils.trade_adjusters import apply_all_trade_adjustments
    TRADE_ADJUSTERS_AVAILABLE = True
except ImportError:
    try:
        from trade_adjusters import apply_all_trade_adjustments
        TRADE_ADJUSTERS_AVAILABLE = True
    except ImportError:
        TRADE_ADJUSTERS_AVAILABLE = False
        print("Warning: trade_adjusters module not found, trade adjustments disabled")

# Import adaptive trading system from trading directory
try:
    from trading.adaptive_trading import adjust_confidence, adaptive_system
    ADAPTIVE_TRADING_AVAILABLE = True
    print("Adaptive trading system loaded successfully")
except ImportError:
    try:
        from adaptive_trading import adjust_confidence, adaptive_system
        ADAPTIVE_TRADING_AVAILABLE = True
        print("Adaptive trading system loaded successfully")
    except ImportError:
        ADAPTIVE_TRADING_AVAILABLE = False
        print("Warning: Adaptive trading system not available, using standard confidence scores")
VOLATILITY_REGIME_AVAILABLE = False

# Hardcoded user configuration for position checking
USER_CONFIG = {
    "account_address": "0x8A391469043eB1E30F78f94D6f9B7E1196c0eFB1"
}

# Import risk/reward configuration from config directory
try:
    # Try imports after directory restructuring
    from config.risk_reward_config import risk_reward_config
    RISK_REWARD_CONFIG_AVAILABLE = True
    print("Risk/reward config module loaded from config/ directory")
except ImportError:
    try:
        # Fallback to original import during transition
        from risk_reward_config import risk_reward_config
        RISK_REWARD_CONFIG_AVAILABLE = True
        print("Risk/reward config module loaded from root directory")
    except ImportError:
        RISK_REWARD_CONFIG_AVAILABLE = False
        print("Warning: risk_reward_config module not found, using default values")

# Import trade adjustment functionality from utils directory
try:
    from utils.trade_adjusters import apply_all_trade_adjustments
    TRADE_ADJUSTERS_AVAILABLE = True
    print("Trade adjusters loaded successfully")
except ImportError:
    try:
        from trade_adjusters import apply_all_trade_adjustments
        TRADE_ADJUSTERS_AVAILABLE = True
        print("Trade adjusters loaded successfully")
    except ImportError:
        TRADE_ADJUSTERS_AVAILABLE = False
        print("Warning: trade_adjusters module not found, using raw trade parameters")

def get_user_positions_and_recent_activity(user_address):
    """Get user's active positions, open orders, and recent filled orders
    
    Returns:
        tuple: (positions_set, open_orders_set, recent_fills_set)
    """
    try:
        # Connect to API
        info = Info(MAINNET_API_URL, skip_ws=True)
        
        # Initialize tracking structures
        positions_set = set()
        open_orders_set = set()
        recent_fills_set = set()
        # Dictionary to track last trade profitability per asset
        # Format: {asset: (timestamp, was_profitable)}
        asset_last_trades = {}
        
        # Get user state for active positions
        user_state = info.user_state(user_address)
        if user_state:
            asset_positions = user_state.get("assetPositions", [])
            for position in asset_positions:
                pos_data = position.get('position', {})
                coin = pos_data.get('coin', '')
                size = float(pos_data.get('szi', 0))
                
                if coin and size != 0:  # Active position
                    positions_set.add(coin)
        
        # Get open orders
        open_orders = info.open_orders(user_address)
        if open_orders:
            for order in open_orders:
                coin = order.get('coin', '')
                if coin:  # Any open order (entry or exit)
                    open_orders_set.add(coin)
        
        # Get recent filled orders (looking back 6 hours to track unprofitable trades)
        six_hours_ago = int((datetime.now() - timedelta(hours=6)).timestamp() * 1000)
        user_fills = info.user_fills(user_address)
        
        if user_fills:
            # Sort fills by time (newest first) to easily find most recent per asset
            sorted_fills = sorted(user_fills, key=lambda x: int(x.get('time', 0)), reverse=True)
            processed_coins = set()
            
            for fill in sorted_fills:
                coin = fill.get('coin', '')
                timestamp = int(fill.get('time', 0))
                pnl = float(fill.get('closedPnl', 0))
                
                # Skip if this coin's most recent trade already processed
                if not coin or coin in processed_coins:
                    continue
                    
                # Mark as processed so we only check most recent trade
                processed_coins.add(coin)
                
                # Store information about last trade
                was_profitable = (pnl > 0)
                asset_last_trades[coin] = (timestamp, was_profitable)
                
                # Add to recent fills set if unprofitable and within cooldown period
                # or has any activity in last 10 minutes (to prevent trading during active price movement)
                ten_minutes_ago = int((datetime.now() - timedelta(minutes=10)).timestamp() * 1000)
                
                if (not was_profitable and timestamp >= six_hours_ago) or timestamp >= ten_minutes_ago:
                    recent_fills_set.add(coin)
        
        return positions_set, open_orders_set, recent_fills_set, asset_last_trades
    
    except Exception as e:
        print(f"Error fetching user data: {e}")
        return set(), set(), set(), {}

def get_assets_to_exclude():
    """Get the set of assets that should be excluded from recommendations"""
    try:
        user_address = USER_CONFIG["account_address"]
        positions_set, open_orders_set, recent_fills_set, asset_last_trades = get_user_positions_and_recent_activity(user_address)
        
        # Combine all assets that should be excluded
        excluded_assets = positions_set | open_orders_set | recent_fills_set
        
        # Collect cooldown detail information for logging purposes only
        # We no longer exclude assets based on cooldowns - we'll handle that with
        # confidence reduction in collect_ta_based_trades instead
        cooldown_details = []
        
        if ADAPTIVE_TRADING_AVAILABLE:
            # Check all assets for both long and short direction cooldowns (for logging only)
            assets_to_check = set()
            
            # Add all assets from recent fills
            for coin in asset_last_trades.keys():
                assets_to_check.add(coin)
                
            # Also add any assets that might be in the adaptive system but not in recent fills
            if hasattr(adaptive_system, 'performance_data') and 'trade_history' in adaptive_system.performance_data:
                for pair_key in adaptive_system.performance_data['trade_history'].keys():
                    if '_' in pair_key:  # Should be in format 'ASSET_direction'
                        asset = pair_key.split('_')[0]
                        assets_to_check.add(asset)
            
            # Check each asset for cooldowns in both directions (for logging only)
            for asset in assets_to_check:
                for direction in ['long', 'short']:
                    in_cooldown, reason = adaptive_system.get_cooldown_status(asset, direction)
                    if in_cooldown:
                        # Note: We no longer add to cooldown_assets
                        cooldown_details.append(f"{asset}-{direction}: {reason}")
        
        # We no longer exclude assets based on cooldowns
        # (removed line: excluded_assets |= cooldown_assets)
        
        # Print summary of exclusions (if any)
        if excluded_assets:
            print(f"\nFiltering out {len(excluded_assets)} assets with positions/orders/recent activity:")
            print(", ".join(sorted(excluded_assets)))
            
            # Provide more detailed breakdown
            if positions_set:
                print(f"  - Active positions: {', '.join(sorted(positions_set))}")
            if open_orders_set:
                print(f"  - Open orders: {', '.join(sorted(open_orders_set))}")
            if recent_fills_set:
                print(f"  - Recent activity: {', '.join(sorted(recent_fills_set))}")
                
                # Show additional details about cooldown reasons
                current_time_ms = int(datetime.now().timestamp() * 1000)
                unprofitable_details = []
                recent_details = []
                
                for coin in sorted(recent_fills_set):
                    if coin in asset_last_trades:
                        timestamp, was_profitable = asset_last_trades[coin]
                        hours_ago = (current_time_ms - timestamp) / (1000 * 60 * 60)
                        
                        if not was_profitable:
                            hours_remaining = max(0, 6 - hours_ago)
                            if hours_remaining > 0:
                                unprofitable_details.append(f"{coin} ({hours_ago:.1f}h ago, {hours_remaining:.1f}h remaining)")
                        else:
                            recent_details.append(f"{coin} (profitable but recent activity)")
                
                if unprofitable_details:
                    print(f"    Unprofitable trades: {', '.join(unprofitable_details)}")
                if recent_details:
                    print(f"    Very recent activity: {', '.join(recent_details)}")
            
            # Show adaptive cooldown details if any
            if cooldown_details:
                print(f"  - Adaptive cooldowns:")
                for detail in cooldown_details:
                    print(f"    {detail}")
        
        return excluded_assets
    except Exception as e:
        print(f"Error getting assets to exclude: {e}")
        return set()

# Reuse functions from enhanced_visualization.py for consistency

def get_data_directory(data_subdir="data/visualizations"):
    """Get the data directory with fallback paths for pre/post move scenarios"""
    possible_paths = [
        os.path.join(PROJECT_ROOT, data_subdir),  # After move using PROJECT_ROOT
        os.path.join(os.path.dirname(os.path.abspath(__file__)), data_subdir),  # Current directory
        data_subdir  # Relative path as fallback
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # If no valid path found, return default and ensure it exists
    default_path = os.path.join(PROJECT_ROOT, data_subdir)
    os.makedirs(default_path, exist_ok=True)
    return default_path

def find_trade_signal_files(data_dir="data/sim_trades"):
    """Find all trade signal files, sorted by timestamp (newest first)"""
    try:
        actual_dir = get_data_directory(data_dir)
        files = [f for f in os.listdir(actual_dir) if f.startswith("trade_signals_") and f.endswith(".json")]
        files = sorted(files, reverse=True)
        files = [os.path.join(actual_dir, f) for f in files]
        return files
    except FileNotFoundError:
        print(f"Warning: Directory {actual_dir} not found")
        return []

def load_trade_signals_from_file(filepath):
    """Load trade signals from a trade signal file"""
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
            
        # Extract trades from the file
        trades = []
        if isinstance(data, list):
            for trade_obj in data:
                if isinstance(trade_obj, dict) and 'raw_data' in trade_obj:
                    raw_data = trade_obj['raw_data']
                    # Ensure all required fields are present
                    if all(key in raw_data for key in ['asset', 'direction', 'entry_price', 'target_price', 'stop_price']):
                        trades.append(raw_data)
        
        return trades
    except Exception as e:
        print(f"Error loading trade signals from {filepath}: {e}")
        return []

def find_analysis_files(asset, data_dir="data/visualizations", include_btc_correlation=False):
    """Find all enhanced analysis files for an asset, sorted by timestamp (newest first)"""
    import re
    files = []
    try:
        actual_dir = get_data_directory(data_dir)
        if not os.path.exists(actual_dir):
            return files
        
        # Pattern to match timestamped files: {ASSET}_enhanced_analysis_{TIMESTAMP}.json
        pattern = re.compile(f"{asset}_enhanced_analysis_\\d{{8}}_\\d{{6}}\\.json$")
        
        # Find all matching files
        for filename in os.listdir(actual_dir):
            if pattern.match(filename):
                files.append(os.path.join(actual_dir, filename))
        
        # Sort by timestamp (newest first) using existing get_timestamp_from_filename
        files = sorted(files, key=get_timestamp_from_filename, reverse=True)
        return files
    except Exception as e:
        print(f"Error finding analysis files for {asset}: {e}")
        return []

def get_sr_data_for_asset(asset, data_dir="data/visualizations"):
    """Get support/resistance data directly from the newest file for an asset"""
    sr_file_pattern = f"sr_{asset}_*.json"
    sr_files = []
    
    try:
        actual_dir = get_data_directory(data_dir)
        for filename in os.listdir(actual_dir):
            if fnmatch.fnmatch(filename, sr_file_pattern):
                sr_files.append(os.path.join(actual_dir, filename))
    except FileNotFoundError:
        print(f"Warning: Directory {actual_dir} not found")
        return []

    if not sr_files:
        print(f"No analysis files found for {asset}")
        return [], []
    
    newest_file = sr_files[0]
    # Get the newest file for this asset
    
    try:
        # Load the file
        with open(newest_file, 'r') as f:
            analysis_data = json.load(f)
        
        # Try to get support/resistance data using multiple methods
        support_levels = []
        resistance_levels = []
        
        # Try to find where support/resistance data is stored in this file
        sr_data = None
        
        # Try to find common locations for S/R data
        if "market_context" in analysis_data and "support_resistance" in analysis_data["market_context"]:
            sr_data = analysis_data["market_context"]["support_resistance"]
        elif "price_targets" in analysis_data and "enhanced_summary" in analysis_data["price_targets"]:
            if "market_context" in analysis_data["price_targets"]["enhanced_summary"]:
                if "support_resistance" in analysis_data["price_targets"]["enhanced_summary"]["market_context"]:
                    sr_data = analysis_data["price_targets"]["enhanced_summary"]["market_context"]["support_resistance"]
                    
        # Extract support/resistance data if found
        if sr_data is not None:
            support_levels = sr_data.get("support_levels", [])
            resistance_levels = sr_data.get("resistance_levels", [])
            # Successfully found S/R data
        
        # If helper function didn't find anything, search directly in common paths
        if not support_levels and not resistance_levels:
            # Try direct paths
            if "support_resistance" in analysis_data:
                support_levels = analysis_data["support_resistance"].get("support_levels", [])
                resistance_levels = analysis_data["support_resistance"].get("resistance_levels", [])
                # Found S/R data at root level
            
            # Try in price_targets path
            elif "price_targets" in analysis_data and "enhanced_summary" in analysis_data["price_targets"]:
                summary = analysis_data["price_targets"]["enhanced_summary"]
                if "market_context" in summary and "support_resistance" in summary["market_context"]:
                    sr_data = summary["market_context"]["support_resistance"]
                    support_levels = sr_data.get("support_levels", [])
                    resistance_levels = sr_data.get("resistance_levels", [])
                    # Found S/R data in price_targets path
        
        # Ensure we have proper lists
        if not isinstance(support_levels, list):
            support_levels = []
        if not isinstance(resistance_levels, list):
            resistance_levels = []
            
        # Filter out non-numeric values
        support_levels = [float(level) for level in support_levels if isinstance(level, (int, float, str)) and str(level).replace('.', '', 1).isdigit()]
        resistance_levels = [float(level) for level in resistance_levels if isinstance(level, (int, float, str)) and str(level).replace('.', '', 1).isdigit()]
        
        # Sort the levels
        support_levels.sort()
        resistance_levels.sort()
        
        # Return the processed support and resistance levels
        return support_levels, resistance_levels
    except Exception as e:
        print(f"Error getting S/R data for {asset}: {e}")
    
    return [], []

def get_timestamp_from_filename(filename):
    """Extract timestamp from filename or return None if no timestamp"""
    match = re.search(r"(\d{8}_\d{6})\.json$", filename)
    if match:
        return match.group(1)
    return None

def format_timestamp(timestamp_str):
    """Format timestamp string to a readable date/time"""
    if not timestamp_str:
        return "Unknown"
    
    try:
        # Handle our custom timestamp format (YYYYMMDD_HHMMSS)
        if isinstance(timestamp_str, str) and re.match(r"\d{8}_\d{6}", timestamp_str):
            dt = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
            return dt.strftime("%Y-%m-%d %H:%M:%S"), dt
        
        # Default format attempt
        return timestamp_str, None
    except:
        return timestamp_str, None

def load_enhanced_analysis(file_path):
    """Load enhanced analysis data from a specific file"""
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Error loading {file_path}: {e}")
        return None

def is_recent_file(file_path, max_hours_old=5):
    """Check if a file is recent (within specified hours)"""
    timestamp_str = get_timestamp_from_filename(file_path)
    if not timestamp_str:
        return False
    
    _, timestamp_dt = format_timestamp(timestamp_str)
    if not timestamp_dt:
        return False
    
    # Check if the timestamp is within the specified hours
    cutoff_time = datetime.now() - timedelta(hours=max_hours_old)
    return timestamp_dt > cutoff_time

def extract_trades_from_file(file_path, asset):
    """Extract trade recommendations from a file"""
    try:
        # Load data from JSON file
        with open(file_path, 'r') as f:
            data = json.load(f)
            
        # Extract market bias info if present
        market_bias = "neutral"
        bias_strength = 0.0
        if "market_bias" in data:
            market_bias = data["market_bias"].get("bias", "neutral").lower()
            bias_strength = data["market_bias"].get("bias_strength", 0.0)
            
        # Extract support/resistance levels if present
        support_levels = []
        resistance_levels = []
        # Try using the helper function first
        sr_data = get_sr_data(data)
        if sr_data:
            support_levels = sr_data.get("support_levels", [])
            resistance_levels = sr_data.get("resistance_levels", [])
            # Successfully extracted S/R levels using helper function
        # Fall back to direct access if helper function didn't find anything
        elif "support_resistance" in data:
            support_levels = data["support_resistance"].get("support_levels", [])
            resistance_levels = data["support_resistance"].get("resistance_levels", [])
            # Extracted S/R levels directly
        # Ensure we have the right format
        if not isinstance(support_levels, list):
            support_levels = []
        if not isinstance(resistance_levels, list):
            resistance_levels = []
            
        # Get current price and ensure it's valid
        current_price = data.get("current_price", 0)
        if current_price <= 0:
            print(f"Warning: Invalid current price for {asset}: {current_price}")
            return []
    except Exception as e:
        print(f"Error loading file {file_path}: {e}")
        return []
        
    # Get the timestamp
    timestamp_str = get_timestamp_from_filename(file_path)
    formatted_time, _ = format_timestamp(timestamp_str)
    
    trades = []
    
    # 1. FIRST PRIORITY: Get trades from ta_price_targets.ranges (this is where time data is stored)
    if "ta_price_targets" in data and "ranges" in data["ta_price_targets"] and data["ta_price_targets"]["ranges"]:
        ranges = data["ta_price_targets"]["ranges"]
        source = "TA Range"
        
        # Split into long and short trades
        long_ranges = [r for r in ranges if r.get("direction") == "long"]
        short_ranges = [r for r in ranges if r.get("direction") == "short"]
        
        # Get best long trade (highest confidence)
        if long_ranges:
            best_long = sorted(long_ranges, key=lambda x: x.get("confidence", 0), reverse=True)[0]
            
            entry_price = best_long.get("entry_price", best_long.get("entry", 0))
            if entry_price > 0:
                trade = {
                    "direction": "long",
                    "entry_price": entry_price,
                    "target_price": best_long.get("take_profit", 0),
                    "stop_price": best_long.get("stop_loss", 0),
                    "current_price": current_price,
                    "confidence": best_long.get("confidence", 0.5),
                    "source": source,
                    "asset": asset,
                    "risk_reward": best_long.get("risk_reward", 0),
                    "profit_potential": best_long.get("profit_potential", 0),
                    "rationale": best_long.get("rationale", ""),
                    "formatted_time": formatted_time,
                    # Extract time estimates from range object
                    "tp_hours": best_long.get("tp_hours", 0),
                    "sl_hours": best_long.get("sl_hours", 0),
                    "tp_range": best_long.get("tp_range", ""),
                    "sl_range": best_long.get("sl_range", ""),
                    "duration_confidence": best_long.get("duration_confidence", 0.5)
                }
                
                # Validate the trade
                if trade["entry_price"] > 0 and trade["target_price"] > 0 and trade["stop_price"] > 0:
                    trades.append(trade)
        
        # Get best short trade (highest confidence)
        if short_ranges:
            best_short = sorted(short_ranges, key=lambda x: x.get("confidence", 0), reverse=True)[0]
            
            entry_price = best_short.get("entry_price", best_short.get("entry", 0))
            if entry_price > 0:
                trade = {
                    "direction": "short",
                    "entry_price": entry_price,
                    "target_price": best_short.get("take_profit", 0),
                    "stop_price": best_short.get("stop_loss", 0),
                    "current_price": current_price,
                    "confidence": best_short.get("confidence", 0.5),
                    "source": source,
                    "asset": asset,
                    "risk_reward": best_short.get("risk_reward", 0),
                    "profit_potential": best_short.get("profit_potential", 0),
                    "rationale": best_short.get("rationale", ""),
                    "formatted_time": formatted_time,
                    # Extract time estimates from range object
                    "tp_hours": best_short.get("tp_hours", 0),
                    "sl_hours": best_short.get("sl_hours", 0),
                    "tp_range": best_short.get("tp_range", ""),
                    "sl_range": best_short.get("sl_range", ""),
                    "duration_confidence": best_short.get("duration_confidence", 0.5)
                }
                
                # Validate the trade
                if trade["entry_price"] > 0 and trade["target_price"] > 0 and trade["stop_price"] > 0:
                    trades.append(trade)
    
    # 2. SECOND PRIORITY: Check price_targets.ranges
    elif "price_targets" in data and "ranges" in data["price_targets"] and data["price_targets"]["ranges"]:
        ranges = data["price_targets"]["ranges"]
        source = "Range"
        
        # Split into long and short trades
        long_ranges = [r for r in ranges if r.get("direction") == "long"]
        short_ranges = [r for r in ranges if r.get("direction") == "short"]
        
        # Get best long trade (highest confidence)
        if long_ranges:
            best_long = sorted(long_ranges, key=lambda x: x.get("confidence", 0), reverse=True)[0]
            
            entry_price = best_long.get("entry_price", best_long.get("entry", 0))
            if entry_price > 0:
                trade = {
                    "direction": "long",
                    "entry_price": entry_price,
                    "target_price": best_long.get("take_profit", 0),
                    "stop_price": best_long.get("stop_loss", 0),
                    "current_price": current_price,
                    "confidence": best_long.get("confidence", 0.5),
                    "source": source,
                    "asset": asset,
                    "risk_reward": best_long.get("risk_reward", 0),
                    "profit_potential": best_long.get("profit_potential", 0),
                    "rationale": best_long.get("rationale", ""),
                    "formatted_time": formatted_time,
                    # Extract time estimates from range object
                    "tp_hours": best_long.get("tp_hours", 0),
                    "sl_hours": best_long.get("sl_hours", 0),
                    "tp_range": best_long.get("tp_range", ""),
                    "sl_range": best_long.get("sl_range", ""),
                    "duration_confidence": best_long.get("duration_confidence", 0.5)
                }
                
                # Validate the trade
                if trade["entry_price"] > 0 and trade["target_price"] > 0 and trade["stop_price"] > 0:
                    trades.append(trade)
        
        # Get best short trade (highest confidence)
        if short_ranges:
            best_short = sorted(short_ranges, key=lambda x: x.get("confidence", 0), reverse=True)[0]
            
            entry_price = best_short.get("entry_price", best_short.get("entry", 0))
            if entry_price > 0:
                trade = {
                    "direction": "short",
                    "entry_price": entry_price,
                    "target_price": best_short.get("take_profit", 0),
                    "stop_price": best_short.get("stop_loss", 0),
                    "current_price": current_price,
                    "confidence": best_short.get("confidence", 0.5),
                    "source": source,
                    "asset": asset,
                    "risk_reward": best_short.get("risk_reward", 0),
                    "profit_potential": best_short.get("profit_potential", 0),
                    "rationale": best_short.get("rationale", ""),
                    "formatted_time": formatted_time,
                    # Extract time estimates from range object
                    "tp_hours": best_short.get("tp_hours", 0),
                    "sl_hours": best_short.get("sl_hours", 0),
                    "tp_range": best_short.get("tp_range", ""),
                    "sl_range": best_short.get("sl_range", ""),
                    "duration_confidence": best_short.get("duration_confidence", 0.5)
                }
                
                # Validate the trade
                if trade["entry_price"] > 0 and trade["target_price"] > 0 and trade["stop_price"] > 0:
                    trades.append(trade)
    
    # 2. SECOND PRIORITY: Check long_targets and short_targets arrays
    elif "price_targets" in data and ("long_targets" in data["price_targets"] or "short_targets" in data["price_targets"]):
        # Process long targets
        if "long_targets" in data["price_targets"] and data["price_targets"]["long_targets"]:
            long_targets = data["price_targets"]["long_targets"]
            source = "Long Target"
            
            for target in long_targets:
                entry_price = target.get("entry_price", 0)
                if entry_price <= 0:
                    continue
                    
                trade = {
                    "direction": "long",
                    "entry_price": entry_price,
                    "target_price": target.get("take_profit", 0),
                    "stop_price": target.get("stop_loss", 0),
                    "confidence": target.get("confidence", 0),
                    "trigger_probability": target.get("trigger_probability", 0),
                    "risk_reward": target.get("risk_reward", 0),
                    "size": target.get("size", 0),
                    "rationale": target.get("rationale", ""),
                    "source": source,
                    "current_price": current_price,
                    "asset": asset,
                    "formatted_time": formatted_time,
                    # Extract time estimates if available
                    "tp_hours": 0,
                    "sl_hours": 0,
                    "tp_range": "",
                    "sl_range": "",
                    "duration_confidence": 0.5
                }
                
                # Look for time estimates in 'ranges' that match this target
                if "ranges" in data["price_targets"]:
                    for range_item in data["price_targets"]["ranges"]:
                        if range_item.get("direction") == "long" and abs(range_item.get("entry", 0) - entry_price) < 0.00001:
                            # Found matching range, extract time data
                            trade["tp_hours"] = range_item.get("tp_hours", 0)
                            trade["sl_hours"] = range_item.get("sl_hours", 0)
                            trade["tp_range"] = range_item.get("tp_range", "")
                            trade["sl_range"] = range_item.get("sl_range", "")
                            trade["duration_confidence"] = range_item.get("duration_confidence", 0.5)
                            break
                trades.append(trade)
        
        # Process short targets
        if "short_targets" in data["price_targets"] and data["price_targets"]["short_targets"]:
            short_targets = data["price_targets"]["short_targets"]
            source = "Short Target"
            
            for target in short_targets:
                entry_price = target.get("entry_price", 0)
                if entry_price <= 0:
                    continue
                    
                trade = {
                    "direction": "short",
                    "entry_price": entry_price,
                    "target_price": target.get("take_profit", 0),
                    "stop_price": target.get("stop_loss", 0),
                    "confidence": target.get("confidence", 0),
                    "trigger_probability": target.get("trigger_probability", 0),
                    "risk_reward": target.get("risk_reward", 0),
                    "size": target.get("size", 0),
                    "rationale": target.get("rationale", ""),
                    "source": source,
                    "current_price": current_price,
                    "asset": asset,
                    "formatted_time": formatted_time,
                    # Extract time estimates if available
                    "tp_hours": 0,
                    "sl_hours": 0,
                    "tp_range": "",
                    "sl_range": "",
                    "duration_confidence": 0.5
                }
                
                # Look for time estimates in 'ranges' that match this target
                if "ranges" in data["price_targets"]:
                    for range_item in data["price_targets"]["ranges"]:
                        if range_item.get("direction") == "short" and abs(range_item.get("entry", 0) - entry_price) < 0.00001:
                            # Found matching range, extract time data
                            trade["tp_hours"] = range_item.get("tp_hours", 0)
                            trade["sl_hours"] = range_item.get("sl_hours", 0)
                            trade["tp_range"] = range_item.get("tp_range", "")
                            trade["sl_range"] = range_item.get("sl_range", "")
                            trade["duration_confidence"] = range_item.get("duration_confidence", 0.5)
                            break
                trades.append(trade)
    
    # 3. THIRD PRIORITY: Check summary.primary_recommendation if we still have no trades
    elif "summary" in data and "primary_recommendation" in data["summary"]:
        rec = data["summary"]["primary_recommendation"]
        direction = rec.get("direction")
        
        # Only use if we have a direction and confidence
        if direction and rec.get("confidence", 0) > 0:
            # We might not have specific price levels, so estimate based on current price
            source = "Primary Recommendation"
            confidence = rec.get("confidence", 0)
            
            # Use explicit values if available
            entry_price = rec.get("entry_price")
            target_price = rec.get("target_price")
            stop_loss = rec.get("stop_loss")
            
            # For missing values, make reasonable estimates
            if not entry_price or entry_price <= 0:
                # Use current price as fallback
                entry_price = current_price
            
            if not target_price or target_price <= 0:
                # Estimate target price based on direction and confidence
                if direction.lower() == "long":
                    target_price = entry_price * (1 + 0.02 * confidence)  # 2% per 0.1 confidence
                else:
                    target_price = entry_price * (1 - 0.02 * confidence)  # 2% per 0.1 confidence
            
            if not stop_loss or stop_loss <= 0:
                # Estimate stop loss
                if direction.lower() == "long":
                    stop_loss = entry_price * 0.98  # 2% below entry
                else:
                    stop_loss = entry_price * 1.02  # 2% above entry
            
            # Initialize time-related fields with default values
            tp_hours = rec.get("tp_hours", 0)
            sl_hours = rec.get("sl_hours", 0)
            tp_range = rec.get("tp_range", "")
            sl_range = rec.get("sl_range", "")
            duration_confidence = rec.get("duration_confidence", 0.5)
            
            # Check in ta_price_targets.ranges - THIS IS THE MAIN LOCATION FOR TIME DATA
            if "ta_price_targets" in data and "ranges" in data["ta_price_targets"] and data["ta_price_targets"]["ranges"]:
                for range_item in data["ta_price_targets"]["ranges"]:
                    if range_item.get("direction") == direction.lower():
                        # Use range values from ta_price_targets
                        tp_hours = range_item.get("tp_hours", tp_hours)
                        sl_hours = range_item.get("sl_hours", sl_hours)
                        tp_range = range_item.get("tp_range", tp_range)
                        sl_range = range_item.get("sl_range", sl_range)
                        duration_confidence = range_item.get("duration_confidence", duration_confidence)
                        break
            
            # Fallback 1: Check price_targets.ranges
            if not tp_range and "price_targets" in data and "ranges" in data["price_targets"] and data["price_targets"]["ranges"]:
                for range_item in data["price_targets"]["ranges"]:
                    if range_item.get("direction") == direction.lower():
                        tp_hours = range_item.get("tp_hours", tp_hours)
                        sl_hours = range_item.get("sl_hours", sl_hours)
                        tp_range = range_item.get("tp_range", tp_range)
                        sl_range = range_item.get("sl_range", sl_range)
                        duration_confidence = range_item.get("duration_confidence", duration_confidence)
                        break
                        
            # Fallback 2: Check summary.ranges
            if not tp_range and "summary" in data and "ranges" in data["summary"]:
                for range_item in data["summary"]["ranges"]:
                    if range_item.get("direction") == direction.lower():
                        tp_hours = range_item.get("tp_hours", tp_hours)
                        sl_hours = range_item.get("sl_hours", sl_hours)
                        tp_range = range_item.get("tp_range", tp_range)
                        sl_range = range_item.get("sl_range", sl_range)
                        duration_confidence = range_item.get("duration_confidence", duration_confidence)
                        break
                        
            trade = {
                "direction": direction,
                "entry_price": entry_price,
                "target_price": target_price,
                "stop_price": stop_loss,
                "confidence": confidence,
                "rationale": rec.get("reasoning", ""),
                "source": source,
                "current_price": current_price,
                "asset": asset,
                "formatted_time": formatted_time,
                # Add time range fields
                "tp_hours": tp_hours,
                "sl_hours": sl_hours,
                "tp_range": tp_range,
                "sl_range": sl_range,
                "duration_confidence": duration_confidence
            }
            trades.append(trade)
    
    # If we couldn't find any trades through the standard paths, return empty
    if not trades:
        return []
    
    # Add asset and timestamp info to all trades
    timestamp_str = get_timestamp_from_filename(file_path)
    formatted_time, _ = format_timestamp(timestamp_str) if timestamp_str else ("Unknown", None)
    
    # Further process each trade to add derived metrics
    for trade in trades:
        # Add support/resistance data to each trade
        if not "support_levels" in trade and len(support_levels) > 0:
            trade["support_levels"] = support_levels
        if not "resistance_levels" in trade and len(resistance_levels) > 0:
            trade["resistance_levels"] = resistance_levels
        # Calculate potential profit percentage
        entry_price = trade.get("entry_price", 0)
        target_price = trade.get("target_price", 0)
        stop_price = trade.get("stop_price", 0)
        
        # Skip invalid trades
        if not entry_price or entry_price <= 0:
            continue
            
        # Add asset and timestamp if not already present
        trade["asset"] = asset
        trade["timestamp"] = formatted_time
        trade["current_price"] = current_price
            
        # Calculate profit and risk percentages
        if entry_price and target_price and trade.get("direction"):
            if trade["direction"].lower() == "long":
                profit_pct = ((target_price / entry_price) - 1) * 100 if entry_price else 0
                risk_pct = ((entry_price / stop_price) - 1) * 100 if stop_price and stop_price > 0 else 0
            else:  # short
                profit_pct = ((entry_price / target_price) - 1) * 100 if target_price else 0
                risk_pct = ((stop_price / entry_price) - 1) * 100 if stop_price and stop_price > 0 else 0
        else:
            profit_pct = 0
            risk_pct = 0
        
        # Add calculated metrics
        trade["profit_potential"] = profit_pct
        trade["risk_pct"] = risk_pct
        
        # Use provided risk/reward or calculate it
        if "risk_reward" not in trade or not trade["risk_reward"]:
            trade["risk_reward"] = abs(profit_pct / risk_pct) if risk_pct else 0
            
        # Calculate entry distance from current price
        trade["entry_distance"] = abs((entry_price / current_price - 1) * 100) if current_price > 0 else 0
        
        # Ensure direction is uppercase
        if "direction" in trade:
            trade["direction"] = trade["direction"].upper()
        
    # Filter out any trades with invalid values
    valid_trades = []
    for trade in trades:
        # Basic validation
        if trade.get("entry_price", 0) <= 0 or trade.get("target_price", 0) <= 0:
            continue
            
        # Make sure profit calculation is reasonable
        if abs(trade.get("profit_potential", 0)) > 100:
            continue
            
        # Ensure non-negative risk_reward
        if trade.get("risk_reward", 0) < 0:
            continue
            
        valid_trades.append(trade)
    
    return valid_trades

def get_available_assets(data_dir="data/sim_trades"):
    """Get a list of all available assets with trade signal files"""
    assets = set()
    try:
        # Get the actual directory using fallback paths
        actual_dir = get_data_directory(data_dir)
        files = os.listdir(actual_dir)
        for filename in files:
            if filename.endswith("_liquidation_analysis.json"):
                asset = filename.split("_liquidation_analysis.json")[0]
                assets.add(asset)
        return sorted(list(assets))
    except Exception as e:
        print(f"Error listing assets: {e}")
        return []

def collect_best_trades(max_hours_old=5, top_n=25, min_confidence=0.5, min_risk_reward=1.0,
                         data_dir="data/visualizations", output_file=None, include_rationale=True):
    # Use data directory with fallback paths
    actual_dir = get_data_directory(data_dir)
    """
    Collect the best trades from all assets with recent analysis files
    
    Args:
        max_hours_old: Maximum age of files to consider (in hours)
        top_n: Number of top trades to return
        min_confidence: Minimum confidence score to include a trade
        min_risk_reward: Minimum risk/reward ratio to include a trade
        data_dir: Directory containing analysis files
        output_file: Optional path to save results as CSV
        include_rationale: Whether to include reasoning in the output
        
    Returns:
        Pandas DataFrame with top trades
    """
    print(f"Collecting best trades from analyses less than {max_hours_old} hours old...")
    
    # Get all available assets
    assets = get_available_assets(data_dir)
    if not assets:
        print(f"No assets found in {data_dir}")
        return pd.DataFrame()
    
    print(f"Found {len(assets)} assets with analysis files")
    
    # Collect all trades
    all_trades = []
    recent_asset_count = 0
    
    for asset in assets:
        # Get the newest file for this asset
        files = find_analysis_files(asset, data_dir)
        if not files:
            continue
        
        newest_file = files[0]  # First file is newest due to sorting
        
        # Check if the file is recent enough
        if not is_recent_file(newest_file, max_hours_old):
            continue
            
        recent_asset_count += 1
        
        # Extract trades from this file
        asset_trades = extract_trades_from_file(newest_file, asset)
        if asset_trades:
            all_trades.extend(asset_trades)
            print(f"Found {len(asset_trades)} trades for {asset}")
    
    print(f"Processed {recent_asset_count} assets with recent analysis files")
    
    if not all_trades:
        print("No qualifying trades found")
        return pd.DataFrame()
    
    # Convert to DataFrame
    trades_df = pd.DataFrame(all_trades)
    
    # Apply adaptive confidence adjustment if available
    if ADAPTIVE_TRADING_AVAILABLE:
        print("Applying adaptive confidence adjustments based on historical performance...")
        all_trades_count = len(trades_df)
        adjusted_trades = []
        
        for _, trade in trades_df.iterrows():
            # Skip if the asset is in cooldown for this direction
            asset = trade["asset"]
            direction = trade["direction"]
            in_cooldown, reason = adaptive_system.get_cooldown_status(asset, direction)
            
            # IMPORTANT: Also check for direction-wide cooldown (after 3+ consecutive losses in that direction)
            in_dir_cooldown, dir_reason = adaptive_system.get_direction_cooldown_status(direction)
            if in_dir_cooldown:
                in_cooldown = True
                reason = dir_reason  # Use the direction cooldown reason
            
            # Convert to dictionary for adjustment
            adjusted_trade = trade.to_dict()
            
            # Apply confidence adjustment if not in cooldown
            if not in_cooldown:
                adjusted_trade = adjust_confidence(adjusted_trade)
                # Add original confidence for reference
                if "original_confidence" not in adjusted_trade:
                    adjusted_trade["original_confidence"] = trade["confidence"]
            else:
                # If in cooldown, add reason and set low confidence
                adjusted_trade["original_confidence"] = trade["confidence"]
                adjusted_trade["confidence"] = 0.1  # Very low confidence for cooldown trades
                adjusted_trade["cooldown_reason"] = reason
                
            adjusted_trades.append(adjusted_trade)
        
        # Convert back to DataFrame
        trades_df = pd.DataFrame(adjusted_trades)
        
        # Add info about adjustments
        print(f"Adjusted confidence scores for {all_trades_count} trades based on historical performance")
    
    # Apply filters
    trades_df = trades_df[trades_df["confidence"] >= min_confidence]
    trades_df = trades_df[trades_df["risk_reward"] >= min_risk_reward]
    
    # Apply additional validation
    trades_df = trades_df[(trades_df["entry_price"] > 0) & (trades_df["target_price"] > 0) & (trades_df["stop_price"] > 0)]
    
    # Apply additional filters if needed
    if not trades_df.empty:
        # Sort directly by confidence as requested
        trades_df = trades_df.sort_values(by="confidence", ascending=False)
        
        # Add a more detailed summary if requested
        if include_rationale and not trades_df.empty:
            print("\nTOP TRADE DETAILS:")
            for i, (_, trade) in enumerate(trades_df.head(min(3, len(trades_df))).iterrows()):
                print(f"\n{i+1}. {trade['asset']} {trade['direction']} @ {trade['entry_price']}")
                if trade['rationale']:
                    print(f"   Rationale: {trade['rationale']}")
    
    # Take only the best trade per asset (highest confidence)
    if not trades_df.empty:
        print(f"Filtering to select only the best trade per asset...")
        # Group by asset and get the highest confidence trade for each
        trades_df = trades_df.loc[trades_df.groupby('asset')['confidence'].idxmax()]
        
        # Sort again by confidence
        trades_df = trades_df.sort_values(by="confidence", ascending=False)
        print(f"After filtering, {len(trades_df)} unique assets have trades")
    
    # Take top 25 trades
    top_trades = trades_df.head(top_n)
    
    # Save to CSV if requested
    if output_file:
        top_trades.to_csv(output_file, index=False)
        print(f"Saved top {len(top_trades)} trades to {output_file} (one best trade per asset, {top_n} total)")
    
    return top_trades

def format_trade_signal(trade):
    """Format a trade recommendation in the requested signal format"""
    # Extract trade details using direct dictionary access for core fields
    # as the original system expected
    asset = trade["asset"]
    direction = trade["direction"].lower()
    entry_price = trade["entry_price"]
    current_price = trade["current_price"]
    target_price = trade["target_price"]
    stop_price = trade["stop_price"]
    
    # Calculate percentages
    if direction == "long":
        sl_percent = abs((entry_price - stop_price) / entry_price * 100)
        tp_percent = abs((target_price - entry_price) / entry_price * 100)
    else:  # short
        sl_percent = abs((stop_price - entry_price) / entry_price * 100)
        tp_percent = abs((entry_price - target_price) / entry_price * 100)
    
    # Calculate position size based on $1000 example balance with 5x leverage
    # This uses approximately 20% of available balance per trade
    position_size = round(200 / entry_price, 2)  # $200 value (20% of $1000)
    
    # Format prices based on magnitude
    def format_price_clean(price):
        if price >= 1000:
            return f"{price:.0f}"
        elif price >= 100:
            return f"{price:.1f}"
        elif price >= 10:
            return f"{price:.2f}"
        elif price >= 1:
            return f"{price:.3f}"
        elif price >= 0.1:
            return f"{price:.4f}"
        elif price >= 0.01:
            return f"{price:.5f}"
        elif price >= 0.001:
            return f"{price:.6f}"
        else:
            return f"{price:.8f}"
    
    # Start with the basic trade signal
    signal = f"""{direction.upper()} {asset}/USDT
- Entry: {format_price_clean(entry_price)}
- SL: {format_price_clean(stop_price)} {sl_percent:.2f}%
- TP: {format_price_clean(target_price)} {tp_percent:.2f}%
+ Price when signal is generated: {format_price_clean(current_price)}"""
    
    # Add time estimates if available - use safer .get() method for optional fields
    if "tp_range" in trade and trade["tp_range"]:
        signal += f"\n+ Estimated time to TP: {trade['tp_range']}"
    if "sl_range" in trade and trade["sl_range"]:
        signal += f"\n+ Estimated time to SL: {trade['sl_range']}"
    
    # Add PVP command and example balance
    signal += f"\n\nPVP:\n/limit {direction.lower()} {asset} 5x {format_price_clean(entry_price)} {position_size}\nExample Balance: 1000.00\n⚠️ ORDER EXPIRY: CANCEL IF UNFILLED WITHIN 6 HOURS ⚠️"
    
    return signal

def print_trade_table(trades, max_age_hours=None, sort_by="confidence"):
    """Print a formatted table of trade signals"""
    if trades.empty:
        print("No trade signals available")
        return

    # Create a copy to avoid modifying the original
    display_df = trades.copy()
    
    # Initialize S/R cache for all assets in this table to avoid redundant lookups
    sr_cache = {}
    for idx, row in display_df.iterrows():
        asset = row['asset']
        if asset not in sr_cache:
            support_levels, resistance_levels = get_sr_data_for_asset(asset)
            sr_cache[asset] = {
                'support': support_levels,
                'resistance': resistance_levels
            }
            
    # Add S/R adjustment indicator to direction column if applicable
    for idx, row in display_df.iterrows():
        if row.get("sr_adjusted", False):
            key_level_type = row.get("key_level_type", "")
            level_price = row.get("key_level_price", 0)
            level_indicator = f"S:{level_price:.2f}" if key_level_type == "support" else f"R:{level_price:.2f}"
            display_df.at[idx, "direction"] = f"{row['direction']} ({level_indicator})"
        
    # Check for original price columns
    orig_cols = ['orig_entry_price', 'orig_target_price', 'orig_stop_price']
    
    # Round numeric columns
    def format_price(price):
        """Format price with appropriate decimal places"""
        # Handle NaN, None, and invalid values
        if price is None or (isinstance(price, float) and (math.isnan(price) or math.isinf(price))):
            return "N/A"
            
        try:
            price_float = float(price)
            if price_float < 0.1:
                return f"{price_float:.6f}"
            elif price_float < 1:
                return f"{price_float:.4f}"
            elif price_float < 100:
                return f"{price_float:.2f}"
            else:
                return f"{int(price_float)}"
        except (ValueError, TypeError):
            return "N/A"
    
    # Check if this is a BTC correlation table
    is_btc_table = 'btc_correlation' in display_df.columns
    
    # Check if we have adaptive confidence adjustments
    has_adaptive = 'original_confidence' in display_df.columns
    
    # Print header with adjustments and original values
    print("\n" + "=" * 230)
    if is_btc_table and has_adaptive:
        print(f"{'Asset':<6} {'Side':<6} {'Entry':<10} {'TP':<10} {'SL':<10} {'R/R':<6} {'Conf':<6} {'Adj':<6} {'Mult':<6} {'Source':<8} {'BTC Corr':<8} {'Time to TP':<17} {'Time to SL':<17} {'Date':<19} | {'Adjustment Details':<80}")
    elif is_btc_table:
        print(f"{'Asset':<6} {'Side':<6} {'Entry':<10} {'TP':<10} {'SL':<10} {'R/R':<6} {'Conf':<6} {'Source':<8} {'BTC Corr':<8} {'Est Time':<10} {'Date':<16} {'Adjustment Details':<80}")
    elif has_adaptive:
        print(f"{'Asset':<6} {'Side':<6} {'Entry':<10} {'TP':<10} {'SL':<10} {'R/R':<6} {'Conf':<6} {'Adj':<6} {'Mult':<6} {'Source':<8} {'Est Time':<10} {'Date':<16} {'Adjustment Details':<80}")
    else:
        print(f"{'Asset':<6} {'Side':<6} {'Entry':<10} {'TP':<10} {'SL':<10} {'R/R':<6} {'Conf':<6} {'Source':<8} {'Est Time':<10} {'Date':<16} {'Adjustment Details':<80}")
    print("-" * 160)
    
    # Print rows
    for _, row in display_df.iterrows():
        asset = row['asset']
        direction = row['direction'].upper()[:4]  # LONG or SHOR
        entry = format_price(row['entry_price'])
        tp = format_price(row['target_price'])
        sl = format_price(row['stop_price'])
        rr = f"{row['risk_reward']:.2f}"
        conf = f"{row['confidence']:.2f}"
        source = row['source'][:7]
        date = row.get('formatted_time', '---')
        
        # Get support/resistance data for this asset if not already in cache
        if asset not in sr_cache:
            # Get S/R data directly from file
            support_levels, resistance_levels = get_sr_data_for_asset(asset)
            sr_cache[asset] = {
                'support': support_levels,
                'resistance': resistance_levels
            }
            # S/R data loaded successfully for this asset
        # Handle tuple format if present (returned by format_timestamp)
        if isinstance(date, tuple) and len(date) > 0:
            date = date[0]
        if isinstance(date, str) and len(date) > 16:
            date = date[:16]
        
        # Format time estimates
        tp_time = row.get('tp_hours', 0)
        sl_time = row.get('sl_hours', 0)
        duration_conf = row.get('duration_confidence', 0)
        
        # Create a concise time estimate string
        est_time = "N/A"
        if tp_time > 0:
            conf_str = f" ({int(duration_conf*100)}%)" if duration_conf > 0 else ""
            est_time = f"{tp_time:.1f}h{conf_str}"
        
        # Get range strings if available
        tp_range = row.get('tp_range', '')
        if tp_range:
            est_time = tp_range
        
        # Format with colors (using ANSI escape codes)
        direction_color = "\033[32m" if direction == "LONG" else "\033[31m"  # Green for long, red for short
        reset_color = "\033[0m"
        
        # Get adaptive trading info if available
        orig_conf = ""
        mult = ""
        if 'original_confidence' in row:
            orig_conf = f"{row.get('original_confidence', 0):.2f}"
            mult_val = row.get('confidence_multiplier', 1.0)
            mult = f"{mult_val:.2f}"
            
            # Change color if in cooldown
            if 'cooldown_reason' in row:
                conf = f"\033[33m{conf}\033[0m"  # Yellow for cooldown
        
        # Use stored original price values if available, otherwise
        # Get original prices if available (from S/R adjustments)
        orig_entry_price = row.get('orig_entry_price', row['entry_price'])
        orig_tp_price = row.get('orig_target_price', row['target_price'])
        orig_sl_price = row.get('orig_stop_price', row['stop_price'])
        
        # Create a detailed adjustment summary string with original prices
        epsilon = 0.0000001
        
        # Format for original values and adjustments
        entry_adj = ""
        tp_adj = ""
        sl_adj = ""
        
        # Format original entry and adjustment
        entry_pct = 0
        entry_dir = ""
        if abs(orig_entry_price - row['entry_price']) > epsilon:
            entry_pct = abs((row['entry_price'] / orig_entry_price - 1) * 100)
            entry_dir = "+" if row['entry_price'] > orig_entry_price else "-"
            entry_adj = f"ADJ: {entry_dir}{entry_pct:.1f}%"
        
        # Format original TP and adjustment
        tp_pct = 0
        tp_dir = ""
        if abs(orig_tp_price - row['target_price']) > epsilon:
            tp_pct = abs((row['target_price'] / orig_tp_price - 1) * 100)
            tp_dir = "+" if row['target_price'] > orig_tp_price else "-"
            tp_adj = f"ADJ: {tp_dir}{tp_pct:.1f}%"
        
        # Format original SL and adjustment
        sl_pct = 0
        sl_dir = ""
        if abs(orig_sl_price - row['stop_price']) > epsilon:
            sl_pct = abs((row['stop_price'] / orig_sl_price - 1) * 100)
            sl_dir = "+" if row['stop_price'] > orig_sl_price else "-"
            sl_adj = f"ADJ: {sl_dir}{sl_pct:.1f}%"
        
        # Get key level information if available
        key_level_type = row.get('key_level_type', 'none')
        key_level_price = row.get('key_level_price', 0)
        key_level_proximity = row.get('key_level_proximity', 0)
        
        # Get market bias information
        market_bias = row.get('market_bias', 'neutral')
        bias_strength = row.get('market_bias_strength', 0)
        
        # Get support/resistance levels from cache
        cached_sr = sr_cache.get(asset, {'support': [], 'resistance': []})
        support_levels = cached_sr['support']
        resistance_levels = cached_sr['resistance']
        
        # Create level information string
        level_info = ""
        
        # Always show support/resistance levels from cache when available
        if support_levels or resistance_levels:
            # Format support levels (up to 3)
            sup_str = ", ".join([f"{s:.2f}" for s in support_levels[:3]]) if support_levels else "none"
            # Format resistance levels (up to 3)
            res_str = ", ".join([f"{r:.2f}" for r in resistance_levels[:3]]) if resistance_levels else "none"
            level_info = f"Sup: {sup_str} | Res: {res_str} | "
        
        
        # Add adjustment info if this trade was adjusted
        if row.get("sr_adjusted", False):
            # Ensure level_type is a string before calling capitalize()
            level_type_raw = row.get("key_level_type", "")
            if isinstance(level_type_raw, (int, float)):
                level_type = str(level_type_raw)
            else:
                level_type = level_type_raw.capitalize() if level_type_raw else ""
            level_price = row.get("key_level_price", 0)
            proximity = row.get("key_level_proximity", 0)
            
            # Add colored adjustment indicator
            level_color = "\033[32m" if level_type.lower() == "support" else "\033[31m"  # Green for support, red for resistance
            level_info += f"{level_color}Adjusted to {level_type}\033[0m at {format_price(level_price)} | "
            
            # Add percentage of adjustment
            if orig_entry_price != row['entry_price']:
                entry_adjust_pct = abs((row['entry_price'] / orig_entry_price - 1) * 100)
                level_info += f"Entry adj: {entry_adjust_pct:.2f}% | "
        else:
            level_info = f"S/R: None | "
        
        # Add market bias info if available
        if market_bias != 'neutral' and bias_strength > 0:
            bias_display = market_bias.capitalize()
            level_info += f"Bias: {bias_display} ({bias_strength:.2f}) | "
        
        # Create the complete adjustment summary
        adj_summary = level_info
        adj_summary += f"Entry: {orig_entry_price:.4f} {entry_adj if entry_adj else '(no adj)'} | "
        adj_summary += f"SL: {orig_sl_price:.4f} {sl_adj if sl_adj else '(no adj)'} | "
        adj_summary += f"TP: {orig_tp_price:.4f} {tp_adj if tp_adj else '(no adj)'}"
        
        # If truly no adjustments were made and no key levels
        if not entry_adj and not tp_adj and not sl_adj and not level_info:
            adj_summary = "No adjustments made to original values"
        
        # Get BTC correlation if available
        btc_corr = f"{row.get('btc_correlation', 0):.2f}" if 'btc_correlation' in row else ""
        
        # Print the row with appropriate columns in the new format
        if is_btc_table and has_adaptive:
            print(f"{asset:<6} {direction_color}{direction:<6}{reset_color} {entry:<10} {tp:<10} {sl:<10} {rr:<6} {conf:<6} {orig_conf:<6} {mult:<6} {source:<8} {btc_corr:<8} {est_time:<17} {date:<19} {adj_summary:<80}")
        elif is_btc_table:
            print(f"{asset:<6} {direction_color}{direction:<6}{reset_color} {entry:<10} {tp:<10} {sl:<10} {rr:<6} {conf:<6} {source:<8} {btc_corr:<8} {est_time:<10} {date:<16} {adj_summary:<80}")
        elif has_adaptive:
            print(f"{asset:<6} {direction_color}{direction:<6}{reset_color} {entry:<10} {tp:<10} {sl:<10} {rr:<6} {conf:<6} {orig_conf:<6} {mult:<6} {source:<8} {est_time:<10} {date:<16} {adj_summary:<80}")
        else:
            print(f"{asset:<6} {direction_color}{direction:<6}{reset_color} {entry:<10} {tp:<10} {sl:<10} {rr:<6} {conf:<6} {source:<8} {est_time:<10} {date:<16} {adj_summary:<80}")
    
    print("=" * 160)
    
    # If rationales are included, print them below the table
    if 'rationale' in display_df.columns and any(display_df['rationale']):
        print("\nDetailed Trade Rationales:")
        print("-" * 110)
        for i, (_, row) in enumerate(display_df.iterrows()):
            if row.get('rationale'):
                # Add BTC correlation info to rationale if available
                btc_info = ""
                if 'btc_correlation' in row and row['btc_correlation'] > 0:
                    btc_info = f" [BTC Correlation: {row['btc_correlation']:.2f}, Beta: {row.get('beta', 0):.2f}]"
                
                print(f"[{i+1}] {row['asset']} {row['direction'].upper()}{btc_info}: {row['rationale']}")
        print("-" * 110)
def save_trade_signals(trades_df, output_file):
    """Save trade signals to a text file"""
    if trades_df.empty:
        print("No trades to save")
        return False
    
    try:
        with open(output_file, 'w') as f:
            # Convert DataFrame rows to dictionaries
            trade_dicts = trades_df.to_dict('records')
            
            # Write each trade signal
            for i, trade in enumerate(trade_dicts, 1):
                f.write(f"SIGNAL #{i}:\n")
                f.write("=" * 30 + "\n")
                f.write(format_trade_signal(trade) + "\n")
                f.write("=" * 30 + "\n\n")
        
        print(f"Trade signals saved to {output_file}")
        return True
    except Exception as e:
        print(f"Error saving trade signals: {e}")
        return False


def format_sim_trade_signal(trade, signal_type):
    """Format a trade signal in the sim_trades format"""
    # Extract data from the trade dictionary - use direct dictionary access for core fields
    # and .get() for optional fields, matching the original code style
    asset = trade["asset"]
    direction = trade["direction"].lower()
    entry_price = float(trade["entry_price"])  # Ensure float for calculations
    target_price = float(trade["target_price"])
    stop_price = float(trade["stop_price"])
    current_price = float(trade.get("current_price", entry_price))  # Default to entry price if not available
    
    # Get optional fields with fallbacks
    risk_reward = float(trade.get("risk_reward", 1.0))
    confidence = float(trade.get("confidence", 0.5)) * 100  # Convert to percentage
    
    # Standard trade type is T2 Scalping, could be customized later
    trade_type = "T2 Scalping"
    
    # Calculate SL and TP percentages (distance from entry price)
    if direction == "long":
        sl_pct = ((stop_price - entry_price) / entry_price) * 100
        tp_pct = ((target_price - entry_price) / entry_price) * 100
    else:  # short
        sl_pct = ((entry_price - stop_price) / entry_price) * -100  # Negative for shorts
        tp_pct = ((entry_price - target_price) / entry_price) * 100
    
    # Format the title
    title = f"{direction.capitalize()} {trade_type}_{asset}/USDT"
    
    # Format the entry, SL, TP with percentages
    entry_str = f"- Entry: {entry_price:.4f}"
    sl_str = f"- SL: {stop_price:.4f} {abs(sl_pct):.2f}%"
    tp_str = f"- TP: {target_price:.4f} {abs(tp_pct):.2f}%"
    
    # Add current price and signal type
    current_price_str = f"+ Price when signal is generated: {current_price:.4f}"
    signal_type_str = f"+ Signal Type: {signal_type}"
    
    # Add time estimates - always include them with proper fallbacks
    time_estimates = {}
    
    # Get duration confidence if available
    duration_conf = trade.get("duration_confidence", 0.5) 
    conf_str = f" ({int(duration_conf*100)}% confidence)" if duration_conf > 0 else ""
    
    # Check for tp_range first (formatted string)
    if "tp_range" in trade and trade["tp_range"]:
        time_estimates["tp_time"] = f"+ Time to TP: {trade['tp_range']}{conf_str}"
    # Fall back to tp_hours (numeric value) if available
    elif "tp_hours" in trade and trade["tp_hours"]:
        time_estimates["tp_time"] = f"+ Time to TP: ~{trade['tp_hours']:.1f} hours{conf_str}"
    # Always include some estimate
    else:
        time_estimates["tp_time"] = "+ Time to TP: 12-36 hours (estimate)"
    
    # Same for stop loss time estimates
    if "sl_range" in trade and trade["sl_range"]:
        time_estimates["sl_time"] = f"+ Time to SL: {trade['sl_range']}{conf_str}"
    elif "sl_hours" in trade and trade["sl_hours"]:
        time_estimates["sl_time"] = f"+ Time to SL: ~{trade['sl_hours']:.1f} hours{conf_str}"
    else:
        time_estimates["sl_time"] = "+ Time to SL: 6-18 hours (estimate)"
    
    # Add confidence score 
    confidence_str = f"+ Confidence: {confidence:.1f}%"
    
    # Add BTC correlation if available
    btc_corr_str = ""
    if "btc_correlation" in trade and trade["btc_correlation"] > 0:
        btc_correlation = float(trade["btc_correlation"])
        btc_corr_str = f"+ BTC Correlation: {btc_correlation:.2f}"
    
    # Combine into formatted signal
    formatted_signal = {
        "title": title,
        "entry": entry_str,
        "sl": sl_str,
        "tp": tp_str,
        "current_price": current_price_str,
        "signal_type": signal_type_str,
        "confidence": confidence_str,
        "btc_correlation": btc_corr_str if btc_corr_str else None,
        "raw_data": {
            "asset": asset,
            "direction": direction,
            "entry_price": entry_price,
            "target_price": target_price,
            "stop_price": stop_price,
            "current_price": current_price,
            "signal_type": signal_type,
            "tp_hours": trade.get("tp_hours", 0),
            "sl_hours": trade.get("sl_hours", 0),
            "tp_range": trade.get("tp_range", ""),
            "sl_range": trade.get("sl_range", ""),
            "duration_confidence": trade.get("duration_confidence", 0.5)
        }
    }
    
    # Add time estimates if available
    if time_estimates:
        for key, value in time_estimates.items():
            formatted_signal[key] = value
    
    # Remove None values
    formatted_signal = {k: v for k, v in formatted_signal.items() if v is not None}
    
    return formatted_signal

def send_webhook(signals, webhook_url):
    """
    Send trade signals to a webhook
    
    Args:
        signals: List of formatted trade signal strings
        webhook_url: URL to send the webhook to
    
    Returns:
        Success status and response information
    """
    try:
        # Prepare the payload
        payload = {
            "signals": signals,
            "timestamp": datetime.now().isoformat(),
            "source": "analysis-pipeline",
            "type": "trade_signals"
        }
        
        # Send the webhook
        response = requests.post(
            webhook_url,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "AnalysisPipeline/1.0"
            },
            timeout=10
        )
        
        # Check if the request was successful
        if response.status_code == 200:
            print(f"Successfully sent {len(signals)} signals to webhook")
            return True, response.text
        else:
            print(f"Failed to send signals to webhook: {response.status_code}")
            return False, f"Status code: {response.status_code}, Response: {response.text}"
    
    except Exception as e:
        print(f"Error sending webhook: {e}")
        return False, str(e)

def get_newest_file_per_asset(files):
    """Returns only the newest file for each asset from a list of files"""
    if not files:
        return []
    
    # Group files by asset
    asset_files = {}
    for file_path in files:
        asset = get_asset_from_filename(file_path)
        if asset not in asset_files:
            asset_files[asset] = []
        asset_files[asset].append(file_path)
    
    # Get newest file for each asset
    newest_files = []
    for asset, files in asset_files.items():
        # Sort by timestamp (newest first)
        sorted_files = sorted(files, key=get_timestamp_from_filename, reverse=True)
        if sorted_files:
            newest_files.append(sorted_files[0])
    
    return newest_files

def collect_pure_liquidation_trades(max_hours_old=5, top_n=10, min_confidence=0.3, min_risk_reward=1.0,
                              data_dir="data/visualizations", include_rationale=True, min_sl_percent=1.0):
    # Use data directory with fallback paths
    actual_dir = get_data_directory(data_dir)
    """Collect trade recommendations based solely on liquidation clusters without TA enhancements"""
    all_trades = []
    assets = get_available_assets(data_dir)
    processed_assets = set()  # Track which assets we've already processed
    
    for asset in assets:
        if asset in processed_assets:
            continue  # Skip if we've already processed this asset
            
        processed_assets.add(asset)
        
        # Get all analysis files for this asset
        all_files = find_analysis_files(asset, data_dir)
        
        # Filter out old files
        recent_files = [f for f in all_files if is_recent_file(f, max_hours_old)]
        if not recent_files:
            continue
            
        # Sort by timestamp (newest first)
        newest_file = sorted(recent_files, key=get_timestamp_from_filename, reverse=True)[0]
        
        # Load data from newest file only
        data = load_enhanced_analysis(newest_file)
        if not data:
            continue
            
        # We only want trades from the "ranges" section which come directly from liquidation clusters
        if "price_targets" not in data or "ranges" not in data["price_targets"]:
            continue
            
        # Get current price
        current_price = data.get("current_price", 0)
        if current_price <= 0:
            continue
        
        # Get timestamp info
        timestamp_str = get_timestamp_from_filename(newest_file)
        formatted_time_tuple = format_timestamp(timestamp_str)
        formatted_time = formatted_time_tuple[0] if isinstance(formatted_time_tuple, tuple) else formatted_time_tuple
        
        # Look at liquidation clusters for cascade information
        cascade_data = None
        orderbook_data = None
        if "cascade_probabilities" in data:
            cascade_data = data["cascade_probabilities"]
        if "orderbook_analysis" in data:
            orderbook_data = data["orderbook_analysis"]
        
        # Extract pure liquidation-based trades from ranges
        ranges = data["price_targets"]["ranges"]
        for trade in ranges:
            direction = trade.get("direction", "")
            if not direction or direction not in ["long", "short"]:
                continue
                
            entry_price = trade.get("entry_price", 0)
            target_price = trade.get("take_profit", 0)
            stop_price = trade.get("stop_loss", 0)
            confidence = trade.get("confidence", 0)
            risk_reward = trade.get("risk_reward", 0)
            
            # Only validate that prices are valid
            if entry_price <= 0 or target_price <= 0 or stop_price <= 0:
                continue
                
            # Validate direction for sanity check
            if direction == "long" and target_price <= entry_price:
                continue
            if direction == "short" and target_price >= entry_price:
                continue
                
            # Create enhanced rationale with cascade information
            rationale = "Target based on liquidation cascade potential"  
            
            # Add position count and size if available
            if "cluster_size" in trade:
                rationale = f"Target based on {trade.get('position_count', 0)} positions with size {trade.get('cluster_size', 0):.2f}"
            
            # Add cascade information if available
            if cascade_data:
                cascade_direction = "long" if direction == "short" else "short"
                cascade_prob = cascade_data.get(f"{cascade_direction}_cascade", {}).get("probability", 0)
                if cascade_prob > 0:
                    cascade_from = cascade_data.get(f"{cascade_direction}_cascade", {}).get("start_price", 0)
                    cascade_to = cascade_data.get(f"{cascade_direction}_cascade", {}).get("end_price", 0)
                    if cascade_from > 0 and cascade_to > 0:
                        rationale += f", expecting cascade from {cascade_from:.2f} to {cascade_to:.2f} (prob: {cascade_prob:.2f})"
            
            # Add orderbook liquidity vs cluster size info if available
            if orderbook_data:
                liquidity_direction = "bids" if direction == "long" else "asks"
                liquidity = orderbook_data.get(f"total_{liquidity_direction}_within_5pct", 0)
                cluster_size = trade.get("cluster_size", 0)
                if liquidity > 0 and cluster_size > 0:
                    ratio = cluster_size / liquidity
                    rationale += f", orderbook liquidity: {liquidity:.2f} vs cluster size: {cluster_size:.2f} (ratio: {ratio:.2f})"
            
            # Add source designation
            rationale += " [Pure Liquidation Analysis]"
            
            # Extract time estimate fields from the range dict if present (do NOT recalculate here)
            tp_hours = trade.get("tp_hours", 0)
            sl_hours = trade.get("sl_hours", 0)
            tp_range = trade.get("tp_range", "")
            sl_range = trade.get("sl_range", "")
            duration_confidence = trade.get("duration_confidence", 0.5)
            # Create the trade dict
            trade_data = {
                "asset": asset,
                "direction": direction,
                "entry_price": entry_price,
                "target_price": target_price,
                "stop_price": stop_price,
                "risk_reward": risk_reward,
                "confidence": confidence,
                "source": "Pure Liq",
                "timestamp": timestamp_str,
                "formatted_time": formatted_time,
                "profit_potential": abs(target_price - entry_price) / entry_price,
                "rationale": rationale if include_rationale else "",
                "current_price": current_price,
                # Time estimate fields (passed through from analysis file)
                "tp_hours": tp_hours,
                "sl_hours": sl_hours,
                "tp_range": tp_range,
                "sl_range": sl_range,
                "duration_confidence": duration_confidence
            }
            all_trades.append(trade_data)
    
    # Convert to DataFrame
    if not all_trades:
        return pd.DataFrame()
        
    df = pd.DataFrame(all_trades)
    
    # Apply support/resistance price adjustments
    if not df.empty:
        df = apply_sr_price_adjustments(df)
    
    # Apply adaptive confidence adjustment if available
    if ADAPTIVE_TRADING_AVAILABLE and not df.empty:
        print("Applying adaptive confidence adjustments to Pure Liquidation trades...")
        all_trades_count = len(df)
        adjusted_trades = []
        
        for _, trade in df.iterrows():
            # Skip if the asset is in cooldown for this direction
            asset = trade["asset"]
            direction = trade["direction"]
            in_cooldown, reason = adaptive_system.get_cooldown_status(asset, direction)
            
            # CRITICAL FIX: Check for direction-wide cooldown
            in_direction_cooldown, direction_reason = adaptive_system.get_direction_cooldown_status(direction)
            
            # Convert to dictionary for adjustment
            adjusted_trade = trade.to_dict()
            
            # Apply confidence adjustment if not in cooldown
            if not in_cooldown:
                adjusted_trade = adjust_confidence(adjusted_trade)
                # Add original confidence for reference
                if "original_confidence" not in adjusted_trade:
                    adjusted_trade["original_confidence"] = trade["confidence"]
            else:
                # If in cooldown, add reason and set low confidence
                adjusted_trade["original_confidence"] = trade["confidence"]
                adjusted_trade["confidence"] = 0.1  # Very low confidence for cooldown trades
                adjusted_trade["cooldown_reason"] = reason
                
            adjusted_trades.append(adjusted_trade)
        
        # Convert back to DataFrame
        df = pd.DataFrame(adjusted_trades)
        
        # Add info about adjustments
        print(f"Adjusted confidence scores for {all_trades_count} Pure Liquidation trades based on historical performance")
    
    # Apply dynamic confidence thresholds based on market alignment
    if not df.empty:
        # Create a filtered DataFrame
        filtered_rows = []
        filtered_out_count = 0
        aligned_count = counter_trend_count = neutral_count = 0
        
        for _, row in df.iterrows():
            # Extract market bias from trade data if available
            market_bias = None
            try:
                if "market_context" in row and isinstance(row["market_context"], str):
                    # Extract from market context string format: "... Overall bias: bullish. ..."
                    context_parts = row["market_context"].split("Overall bias:")
                    if len(context_parts) > 1:
                        bias_part = context_parts[1].split(".")[0].strip().upper()
                        market_bias = bias_part
            except Exception as e:
                print(f"Error extracting market bias: {e}")
            
            # Get dynamic threshold based on direction and market bias
            direction = row["direction"]
            threshold = get_confidence_threshold(direction, market_bias)
            
            # Apply volatility regime confidence modifier if available
            if VOLATILITY_REGIME_AVAILABLE and "volatility_regime" in row:
                volatility_regime = row["volatility_regime"]
                volatility_modifier = get_confidence_modifier(row["asset"], volatility_regime)
                # Apply modifier to confidence (row confidence is already adjusted value)
                orig_confidence = row["confidence"]
                adjusted_confidence = orig_confidence * volatility_modifier
                
                if volatility_modifier < 1.0:
                    print(f"{row['asset']} {direction} - Volatility regime {volatility_regime}: Confidence adjusted from {orig_confidence:.2f} to {adjusted_confidence:.2f}")
                    
                # Update row with adjusted confidence
                row["confidence"] = adjusted_confidence
                row["volatility_modifier"] = volatility_modifier
            
            # Track counts for logging
            alignment = "neutral"
            if market_bias:
                if (direction == "long" and market_bias == "BULLISH") or \
                   (direction == "short" and market_bias == "BEARISH"):
                    alignment = "aligned"
                    aligned_count += 1
                elif (direction == "long" and market_bias == "BEARISH") or \
                     (direction == "short" and market_bias == "BULLISH"):
                    alignment = "counter_trend"
                    counter_trend_count += 1
                else:
                    neutral_count += 1
            else:
                neutral_count += 1
            
            # Filter based on dynamic threshold
            if row["confidence"] >= threshold and row["risk_reward"] >= min_risk_reward:
                filtered_rows.append(row)
            else:
                filtered_out_count += 1
        
        # Create new filtered DataFrame
        if filtered_rows:
            df = pd.DataFrame(filtered_rows)
        else:
            df = pd.DataFrame()
        
        # Log alignment statistics
        print(f"Pure Liquidation trade alignment: {aligned_count} aligned, {counter_trend_count} counter-trend, {neutral_count} neutral")
        print(f"Filtered out {filtered_out_count} Pure Liquidation trades based on dynamic confidence thresholds")
    
    # Apply additional validation
    if not df.empty:
        df = df[(df["entry_price"] > 0) & (df["target_price"] > 0) & (df["stop_price"] > 0)]
        
        # Only sort if the DataFrame is not empty
        if not df.empty:
            # Sort by confidence
            df = df.sort_values(by="confidence", ascending=False)
            
            # Take top N
            df = df.head(top_n)
    
            # Take one trade per asset (best trade only)
            df = df.loc[df.groupby('asset')["confidence"].idxmax()]
        
            # Sort again
            df = df.sort_values(by="confidence", ascending=False)
            
            # Take top N
            df = df.head(top_n)
    
    return df

# Import market alignment module for dynamic confidence thresholds
try:
    from market_alignment import get_confidence_threshold
    from trend_strength_helper import extract_trend_strength
except ImportError:
    # Fallback if modules not available
    def get_confidence_threshold(direction, market_bias, trend_strength=None):
        return 0.3
    def extract_trend_strength(row):
        return None

# Volatility regime detection has been removed

def apply_sr_price_adjustments(trades_df):
    """Adjust trade prices based on nearest support/resistance or fibonacci levels"""
    # Skip if empty
    if trades_df.empty:
        return trades_df
        
    # Load S/R config settings
    try:
        from support_resistance_config import SupportResistanceConfig
        sr_config = SupportResistanceConfig()
        settings = sr_config.get_support_resistance_settings()
        fibonacci_settings = sr_config.get_fibonacci_settings()
        
        # Skip if disabled
        if not settings.get("enabled", False):
            return trades_df
            
        # Get adjustment percentages
        support_adj_pct = settings.get("support_adjustment_percent", 1.0) / 100
        resistance_adj_pct = settings.get("resistance_adjustment_percent", 2.5) / 100
        tp_widening_pct = settings.get("tp_widening_percent", 1.0) / 100
        proximity_threshold = settings.get("proximity_threshold_percent", 1.0) / 100
        use_fibonacci = fibonacci_settings.get("use_fibonacci", True)
    except Exception as e:
        print(f"Error loading support/resistance config: {e} - skipping adjustments")
        return trades_df
    
    # Process each trade
    adjusted_count = 0
    
    # Create a cache for fibonacci data to avoid recalculating for each trade
    fibonacci_cache = {}
    
    # Check if we should skip Fibonacci refreshing based on last refresh time
    fib_refresh_needed = True
    fib_timestamp_file = os.path.join("data", "fibonacci_cache", "last_refresh.txt")
    
    print("\n*** FIBONACCI REFRESH DEBUG ***")
    print(f"Checking timestamp file: {fib_timestamp_file}")
    
    if os.path.exists(fib_timestamp_file):
        print(f"Timestamp file exists: {fib_timestamp_file}")
        try:
            with open(fib_timestamp_file, 'r') as f:
                timestamp_content = f.read().strip()
                print(f"Timestamp content: {timestamp_content}")
                last_refresh = datetime.fromisoformat(timestamp_content)
                hours_since_refresh = (datetime.now() - last_refresh).total_seconds() / 3600
                
                print(f"Hours since last refresh: {hours_since_refresh:.1f}")
                # Only refresh once every 24 hours
                if hours_since_refresh < 24:
                    fib_refresh_needed = False
                    print(f">>> DECISION: Skipping Fibonacci refresh (last refresh: {hours_since_refresh:.1f} hours ago)")
                else:
                    print(f">>> DECISION: Refresh needed (last refresh: {hours_since_refresh:.1f} hours ago)")
        except Exception as e:
            print(f"Error reading Fibonacci timestamp file: {e}")
    else:
        print(f"Timestamp file does not exist, will create it")
    
    # If refresh is needed, update the timestamp file
    if fib_refresh_needed:
        try:
            os.makedirs(os.path.dirname(fib_timestamp_file), exist_ok=True)
            with open(fib_timestamp_file, 'w') as f:
                now = datetime.now().isoformat()
                f.write(now)
                print(f"Updated timestamp file with: {now}")
            print("INITIALIZING FIBONACCI LEVELS\nThis might take a moment for first run...")
        except Exception as e:
            print(f"Error writing Fibonacci timestamp file: {e}")
    
    print(f"Final fib_refresh_needed value: {fib_refresh_needed}")
    print("*** END FIBONACCI REFRESH DEBUG ***\n")
    
    for idx, row in trades_df.iterrows():
        asset = row["asset"]
        direction = row["direction"].upper()
        entry_price = float(row["entry_price"])
        tp_price = float(row["target_price"])
        sl_price = float(row["stop_price"])
        
        # Store original values
        trades_df.at[idx, "orig_entry_price"] = entry_price
        trades_df.at[idx, "orig_target_price"] = tp_price
        trades_df.at[idx, "orig_stop_price"] = sl_price
        
        # First check for Fibonacci levels if enabled
        if use_fibonacci:
            # Get fibonacci levels for this asset
            if asset not in fibonacci_cache:
                try:
                    from fibonacci_levels import get_fibonacci_levels
                    
                    # Only force refresh if global refresh is needed
                    print(f"Getting Fibonacci levels for {asset}, force_refresh={fib_refresh_needed}")
                    fibonacci_cache[asset] = get_fibonacci_levels(asset, force_refresh=fib_refresh_needed)
                except Exception as e:
                    print(f"Error fetching fibonacci levels for {asset}: {e}")
                    fibonacci_cache[asset] = None
            
            fibonacci_data = fibonacci_cache[asset]
            
            # Check if we have valid fibonacci data
            if fibonacci_data and "levels" in fibonacci_data and fibonacci_data["levels"]:
                levels = fibonacci_data["levels"]
                trend = fibonacci_data["trend"]
                
                # Find closest fibonacci level (within proximity threshold)
                closest_level = None
                closest_distance_pct = float('inf')
                closest_level_price = 0
                
                for level_key, level_price in levels.items():
                    level_price = float(level_price)
                    distance_pct = abs(level_price - entry_price) / entry_price
                    
                    if distance_pct < proximity_threshold and distance_pct < closest_distance_pct:
                        closest_level = level_key
                        closest_distance_pct = distance_pct
                        closest_level_price = level_price
                
                # Apply adjustments based on closest level, direction, and trend
                if closest_level:
                    level_value = float(closest_level)  # 0.236, 0.382, etc.
                    
                    # Determine if the level is support or resistance based on trend and direction
                    if direction == "LONG":
                        # For long trades:
                        if trend == "uptrend":
                            # In uptrend, lower levels are support, higher are resistance
                            is_support = level_value <= 0.382  # 0.236 and 0.382 act as support in uptrend
                        else:  # downtrend
                            # In downtrend, higher levels are resistance, lower are support
                            is_support = level_value <= 0.236  # Only 0.236 acts as support in downtrend
                    else:  # SHORT
                        # For short trades:
                        if trend == "uptrend":
                            # In uptrend, higher levels are resistance
                            is_support = level_value <= 0.236  # Only 0.236 acts as support in uptrend
                        else:  # downtrend
                            # In downtrend, lower levels are support, higher are resistance
                            is_support = level_value <= 0.382  # 0.236 and 0.382 act as support in downtrend
                    
                    # Calculate new entry price based on fibonacci level
                    if direction == "LONG":
                        if is_support:
                            # Level is support, adjust entry up slightly for better entry near support
                            new_entry = closest_level_price * (1 + support_adj_pct)
                            # Don't move entry up above current entry
                            new_entry = min(new_entry, entry_price)
                        else:
                            # Level is resistance, adjust entry down away from resistance
                            new_entry = closest_level_price * (1 - resistance_adj_pct)
                            # Don't move entry above the level price
                            new_entry = min(new_entry, closest_level_price)
                    else:  # SHORT
                        if is_support:
                            # Level is support, adjust entry up away from support
                            new_entry = closest_level_price * (1 + support_adj_pct) 
                            # Don't move entry below the level price
                            new_entry = max(new_entry, closest_level_price)
                        else:
                            # Level is resistance, adjust entry down slightly for better entry near resistance
                            new_entry = closest_level_price * (1 - resistance_adj_pct)
                            # Don't move entry down below current entry
                            new_entry = max(new_entry, entry_price)
                    
                    # Calculate relative TP move
                    if direction == "LONG":
                        tp_distance_pct = (tp_price - entry_price) / entry_price
                        new_tp = new_entry * (1 + tp_distance_pct * (1 + tp_widening_pct))
                    else:  # SHORT
                        tp_distance_pct = (entry_price - tp_price) / entry_price
                        new_tp = new_entry * (1 - tp_distance_pct * (1 + tp_widening_pct))
                    
                    # Update values
                    trades_df.at[idx, "entry_price"] = new_entry
                    trades_df.at[idx, "target_price"] = new_tp
                    # Keep stop loss the same
                    
                    # Record adjustment details
                    trades_df.at[idx, "sr_adjusted"] = True
                    trades_df.at[idx, "key_level_type"] = f"fib_{closest_level}"
                    trades_df.at[idx, "key_level_price"] = closest_level_price
                    trades_df.at[idx, "key_level_proximity"] = closest_distance_pct * 100
                    trades_df.at[idx, "fibonacci_level"] = closest_level
                    trades_df.at[idx, "fibonacci_trend"] = trend
                    trades_df.at[idx, "fibonacci_is_support"] = is_support
                    adjusted_count += 1
                    continue  # Skip traditional S/R if Fibonacci adjustment was applied
                
        # Fall back to traditional support/resistance if fibonacci not enabled or no levels found
        # Get support/resistance levels already in the row or get fresh ones
        support_levels = row.get("support_levels", [])
        resistance_levels = row.get("resistance_levels", [])
        
        # If levels aren't in row, get them directly
        if not support_levels or not resistance_levels:
            support_levels, resistance_levels = get_sr_data_for_asset(asset)
        
        # Convert to float if needed
        support_levels = [float(s) for s in support_levels if isinstance(s, (int, float, str)) and str(s).replace('.', '', 1).isdigit()]
        resistance_levels = [float(r) for r in resistance_levels if isinstance(r, (int, float, str)) and str(r).replace('.', '', 1).isdigit()]
        
        # Apply adjustments based on direction
        if direction == "LONG":
            # Find nearest support below entry price
            valid_supports = [s for s in support_levels if s < entry_price]
            if valid_supports:
                nearest_support = max(valid_supports)
                # Set entry to support + adjustment
                new_entry = nearest_support * (1 + support_adj_pct)
                
                # Calculate relative TP move
                tp_distance_pct = (tp_price - entry_price) / entry_price
                new_tp = new_entry * (1 + tp_distance_pct * (1 + tp_widening_pct))
                
                # Update values
                trades_df.at[idx, "entry_price"] = new_entry
                trades_df.at[idx, "target_price"] = new_tp
                # Keep stop loss the same
                
                # Record adjustment details
                trades_df.at[idx, "sr_adjusted"] = True
                trades_df.at[idx, "key_level_type"] = "support"
                trades_df.at[idx, "key_level_price"] = nearest_support
                trades_df.at[idx, "key_level_proximity"] = (entry_price - nearest_support) / entry_price * 100
                adjusted_count += 1
        
        elif direction == "SHORT":
            # Find nearest resistance above entry price
            valid_resistances = [r for r in resistance_levels if r > entry_price]
            if valid_resistances:
                nearest_resistance = min(valid_resistances)
                # Set entry to resistance - adjustment
                new_entry = nearest_resistance * (1 - resistance_adj_pct)
                
                # Calculate relative TP move
                tp_distance_pct = (entry_price - tp_price) / entry_price
                new_tp = new_entry * (1 - tp_distance_pct * (1 + tp_widening_pct))
                
                # Update values
                trades_df.at[idx, "entry_price"] = new_entry
                trades_df.at[idx, "target_price"] = new_tp
                # Keep stop loss the same
                
                # Record adjustment details
                trades_df.at[idx, "sr_adjusted"] = True
                trades_df.at[idx, "key_level_type"] = "resistance"
                trades_df.at[idx, "key_level_price"] = nearest_resistance
                trades_df.at[idx, "key_level_proximity"] = (nearest_resistance - entry_price) / entry_price * 100
                adjusted_count += 1
    
    # Recalculate risk/reward with new prices
    for idx, row in trades_df.iterrows():
        if "sr_adjusted" in row and row["sr_adjusted"]:
            # Recalculate risk/reward
            entry = float(row["entry_price"])
            tp = float(row["target_price"])
            sl = float(row["stop_price"])
            
            if row["direction"] == "LONG":
                profit_pct = ((tp / entry) - 1) * 100
                risk_pct = ((entry / sl) - 1) * 100 if sl > 0 else 0
            else:  # SHORT
                profit_pct = ((entry / tp) - 1) * 100 if tp > 0 else 0
                risk_pct = ((sl / entry) - 1) * 100 if sl > 0 and entry > 0 else 0
            
            # Update values
            if risk_pct > 0:
                trades_df.at[idx, "risk_reward"] = profit_pct / risk_pct
            trades_df.at[idx, "profit_potential"] = profit_pct
    
    return trades_df

def get_sr_data_for_asset(asset, data_dir="data/visualizations"):
    """Get support/resistance data for a specific asset"""
    # Use absolute path construction like in test_sr_expanded.py
    analysis_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), data_dir)
    asset_files = []
    
    if os.path.exists(analysis_dir):
        for file in os.listdir(analysis_dir):
            if fnmatch.fnmatch(file, f"*{asset}*enhanced_analysis*.json"):
                asset_files.append(os.path.join(analysis_dir, file))
    
    if not asset_files:
        return [], []  # No files found
    
    # Try to sort by timestamp from filename first (like in test_sr_expanded.py)
    timestamped_files = [(f, get_timestamp_from_filename(f)) for f in asset_files]
    valid_timestamped = [(f, ts) for f, ts in timestamped_files if ts]
    
    if valid_timestamped:
        # Sort by timestamp (newest first)
        newest_file = sorted(valid_timestamped, key=lambda x: x[1], reverse=True)[0][0]
    else:
        # Fallback to file modification time
        newest_file = sorted(asset_files, key=os.path.getmtime, reverse=True)[0]
    
    try:
        with open(newest_file, "r") as f:
            analysis_data = json.load(f)
        support, resistance = get_sr_data(analysis_data)
        return support, resistance
    except Exception as e:
        print(f"Error loading S/R data for {asset}: {str(e)}")
        return [], []

def get_sr_data(analysis_data):
    """Extract support/resistance data from the nested JSON structure"""
    support_levels = []
    resistance_levels = []
    
    # Helper function to extract levels with key name flexibility
    def extract_sr_levels(sr_data):
        # Try "support_levels" and "resistance_levels" first (used in test_sr_expanded.py)
        s_levels = sr_data.get("support_levels", [])
        r_levels = sr_data.get("resistance_levels", [])
        
        # If empty, try "support" and "resistance" as fallback
        if not s_levels:
            s_levels = sr_data.get("support", [])
        if not r_levels:
            r_levels = sr_data.get("resistance", [])
            
        return s_levels, r_levels
    
    # Check primary path in enhanced_summary
    if "price_targets" in analysis_data and "enhanced_summary" in analysis_data["price_targets"] and \
       "market_context" in analysis_data["price_targets"]["enhanced_summary"] and \
       "support_resistance" in analysis_data["price_targets"]["enhanced_summary"]["market_context"]:
        sr_data = analysis_data["price_targets"]["enhanced_summary"]["market_context"]["support_resistance"]
        support_levels, resistance_levels = extract_sr_levels(sr_data)
        if support_levels or resistance_levels:
            return support_levels, resistance_levels
    
    # Check direct support_resistance object
    if "support_resistance" in analysis_data:
        sr_data = analysis_data["support_resistance"]
        support_levels, resistance_levels = extract_sr_levels(sr_data)
        if support_levels or resistance_levels:
            return support_levels, resistance_levels
    
    # Check in market_context
    if "market_context" in analysis_data and "support_resistance" in analysis_data["market_context"]:
        sr_data = analysis_data["market_context"]["support_resistance"]
        support_levels, resistance_levels = extract_sr_levels(sr_data)
        if support_levels or resistance_levels:
            return support_levels, resistance_levels
    
    # Check other common paths
    if "summary" in analysis_data and "market_context" in analysis_data["summary"] and \
       "support_resistance" in analysis_data["summary"]["market_context"]:
        sr_data = analysis_data["summary"]["market_context"]["support_resistance"]
        support_levels, resistance_levels = extract_sr_levels(sr_data)
        if support_levels or resistance_levels:
            return support_levels, resistance_levels
    
    return [], []

def collect_ta_based_trades(max_hours_old=5, top_n=10, min_confidence=0.3, min_risk_reward=1.0,
                            data_dir="data/visualizations", include_rationale=True, min_sl_percent=0.1):
    """Collect the top TA-based trade recommendations from the newest files only, filtered by volatility regime conditions"""
    
    # CRITICAL DEBUG: Check direction cooldown status at the start
    if ADAPTIVE_TRADING_AVAILABLE:
        print("\n===== DIRECTION COOLDOWN STATUS CHECK =====")
        in_short_cooldown, short_reason = adaptive_system.get_direction_cooldown_status("short")
        in_long_cooldown, long_reason = adaptive_system.get_direction_cooldown_status("long")
        print(f"SHORT direction cooldown: {in_short_cooldown} - {short_reason or 'No reason'}") 
        print(f"LONG direction cooldown: {in_long_cooldown} - {long_reason or 'No reason'}") 
        print("==========================================\n")
    
    all_trades = []
    assets = get_available_assets(data_dir)
    processed_assets = set()  # Track which assets we've already processed
    
    # Get assets to exclude (those with positions, orders, or recent activity)
    assets_to_exclude = get_assets_to_exclude()
    
    for asset in assets:
        if asset in processed_assets:
            continue  # Skip if we've already processed this asset
            
        # Skip assets with existing positions, orders, or recent activity
        if asset in assets_to_exclude:
            continue
            
        processed_assets.add(asset)
        
        # Get all analysis files for this asset
        all_files = find_analysis_files(asset, data_dir)
        
        # Filter out old files
        recent_files = [f for f in all_files if is_recent_file(f, max_hours_old)]
        if not recent_files:
            continue
            
        # Sort by timestamp (newest first)
        newest_file = sorted(recent_files, key=get_timestamp_from_filename, reverse=True)[0]
        
        # Load data from newest file only
        data = load_enhanced_analysis(newest_file)
        if not data:
            continue
            
        # Volatility regime cooldown check removed
                
        # Check if we have TA-based trades
        if "ta_price_targets" not in data:
            continue
            
        # Get current price
        current_price = data.get("current_price", 0)
        if current_price <= 0:
            continue
        
        # Get timestamp info
        timestamp_str = get_timestamp_from_filename(newest_file)
        formatted_time_tuple = format_timestamp(timestamp_str)
        formatted_time = formatted_time_tuple[0] if isinstance(formatted_time_tuple, tuple) else formatted_time_tuple
        
        # Only look in ta_price_targets to avoid duplicates
        source_label = "TA-Based"
        asset_trades = []
        
        # Extract time range data from ta_price_targets.ranges
        time_range_data = {
            "long": {},
            "short": {}
        }
        
        # Look for time range data in ta_price_targets.ranges
        if "ranges" in data["ta_price_targets"]:
            ranges = data["ta_price_targets"]["ranges"]
            for range_item in ranges:
                direction = range_item.get("direction", "").lower()
                if direction in ["long", "short"]:
                    time_range_data[direction] = {
                        "tp_hours": range_item.get("tp_hours", 0),
                        "sl_hours": range_item.get("sl_hours", 0),
                        "tp_range": range_item.get("tp_range", ""),
                        "sl_range": range_item.get("sl_range", ""),
                        "duration_confidence": range_item.get("duration_confidence", 0.5)
                    }
        
        # Get best long TA-based trade - allow multiple high confidence trades
        long_targets = data["ta_price_targets"].get("long_targets", [])
        if long_targets:
            # Filter valid targets and sort by confidence
            valid_longs = []
            for target in long_targets:
                direction = "long"
                entry_price = target.get("entry_price", 0)
                target_price = target.get("take_profit", target.get("target_price", 0))
                stop_price = target.get("stop_loss", 0)
                confidence = target.get("confidence", 0)
                risk_reward = target.get("risk_reward", 0)
                
                # Only validate that prices are valid but don't filter on confidence or risk/reward
                if entry_price <= 0 or target_price <= 0 or stop_price <= 0:
                    continue
                if target_price <= entry_price:  # Validate direction
                    continue
                    
                # Skip trades with stop loss less than 1.00% away from entry
                min_distance_pct = 0.015  # 1.5% minimum
                sl_distance_pct = abs(entry_price - stop_price) / entry_price
                if sl_distance_pct < min_distance_pct:  # Stop too close to entry
                    continue
                    
                # Fix risk/reward if needed
                if risk_reward > 20 or risk_reward < 0.5:
                    sl_distance = abs(entry_price - stop_price)
                    tp_distance = abs(target_price - entry_price)
                    if sl_distance > 0:
                        risk_reward = tp_distance / sl_distance
                    else:
                        continue
                
                # Calculate and validate stop loss distance as percentage
                entry_price = float(target["entry_price"])
                stop_price = float(target["stop_loss"])
                if entry_price > 0 and stop_price > 0:
                    sl_percent = (entry_price - stop_price) / entry_price * 100
                    
                    # Skip trades with stop loss too close to entry
                    if sl_percent < min_sl_percent:
                        print(f"Skipping {target['asset']} {target['direction']} - Stop loss too close: {sl_percent:.2f}% (min: {min_sl_percent:.2f}%)")
                        continue
                
                valid_longs.append({
                    "target": target,
                    "entry_price": entry_price,
                    "target_price": target_price,
                    "stop_price": stop_price,
                    "confidence": confidence,
                    "risk_reward": risk_reward
                })
            
            # Get best long trades by confidence
            if valid_longs:
                best_longs = sorted(valid_longs, key=lambda x: x["confidence"], reverse=True)
                for best_long in best_longs:
                    target = best_long["target"]
                    
                    trade_data = {
                        "asset": asset,
                        "direction": "long",
                        "entry_price": best_long["entry_price"],
                        "target_price": best_long["target_price"],
                        "stop_price": best_long["stop_price"],
                        "risk_reward": best_long["risk_reward"],
                        "confidence": best_long["confidence"],
                        "source": source_label,
                        "timestamp": timestamp_str,
                        "formatted_time": formatted_time,
                        "profit_potential": abs(best_long["target_price"] - best_long["entry_price"]) / best_long["entry_price"],
                        "rationale": target.get("rationale", "TA-based recommendation") if include_rationale else "",
                        "current_price": current_price,
                        # Add time-related fields from ta_price_targets.ranges
                        "tp_hours": time_range_data["long"].get("tp_hours", target.get("tp_hours", 0)),
                        "sl_hours": time_range_data["long"].get("sl_hours", target.get("sl_hours", 0)),
                        "tp_range": time_range_data["long"].get("tp_range", target.get("tp_range", "")),
                        "sl_range": time_range_data["long"].get("sl_range", target.get("sl_range", "")),
                        "duration_confidence": time_range_data["long"].get("duration_confidence", target.get("duration_confidence", 0.5)),
                    }
                    asset_trades.append(trade_data)
        
        # Get best short TA-based trade - allow multiple high confidence trades
        short_targets = data["ta_price_targets"].get("short_targets", [])
        # CRITICAL FIX: Check for direction-wide cooldown before processing ANY shorts
        if ADAPTIVE_TRADING_AVAILABLE:
            in_short_cooldown, short_reason = adaptive_system.get_direction_cooldown_status("short")
            if in_short_cooldown:
                print(f"SKIPPING ALL SHORTS for {asset} - Direction-wide cooldown: {short_reason}")
                short_targets = []  # Clear all short targets when direction is in cooldown
                
        if short_targets:
            # Filter valid targets and sort by confidence
            valid_shorts = []
            for target in short_targets:
                direction = "short"
                entry_price = target.get("entry_price", 0)
                target_price = target.get("take_profit", target.get("target_price", 0))
                stop_price = target.get("stop_loss", 0)
                confidence = target.get("confidence", 0)
                risk_reward = target.get("risk_reward", 0)
                
                # Only validate that prices are valid but don't filter on confidence or risk/reward
                if entry_price <= 0 or target_price <= 0 or stop_price <= 0:
                    continue
                if target_price >= entry_price:  # Validate direction
                    continue
                    
                # Skip trades with stop loss less than 1.00% away from entry
                min_distance_pct = 0.015  # 1.5% minimum
                sl_distance_pct = abs(stop_price - entry_price) / entry_price
                if sl_distance_pct < min_distance_pct:  # Stop too close to entry
                    continue
                    
                # Fix risk/reward if needed
                if risk_reward > 20 or risk_reward < 0.5:
                    sl_distance = abs(entry_price - stop_price)
                    tp_distance = abs(entry_price - target_price)
                    if sl_distance > 0:
                        risk_reward = tp_distance / sl_distance
                    else:
                        continue
                
                # Calculate and validate stop loss distance as percentage
                entry_price = float(target["entry_price"])
                stop_price = float(target["stop_loss"])
                if entry_price > 0 and stop_price > 0:
                    sl_percent = (stop_price - entry_price) / entry_price * 100
                    
                    # Skip trades with stop loss too close to entry
                    if sl_percent < min_sl_percent:
                        print(f"Skipping {target['asset']} {target['direction']} - Stop loss too close: {sl_percent:.2f}% (min: {min_sl_percent:.2f}%)")
                        continue
                
                valid_shorts.append({
                    "target": target,
                    "entry_price": entry_price,
                    "target_price": target_price,
                    "stop_price": stop_price,
                    "confidence": confidence,
                    "risk_reward": risk_reward
                })
            
            # Get best short trades by confidence
            if valid_shorts:
                best_shorts = sorted(valid_shorts, key=lambda x: x["confidence"], reverse=True)
                for best_short in best_shorts:
                    target = best_short["target"]
                    
                    trade_data = {
                        "asset": asset,
                        "direction": "short",
                        "entry_price": best_short["entry_price"],
                        "target_price": best_short["target_price"],
                        "stop_price": best_short["stop_price"],
                        "risk_reward": best_short["risk_reward"],
                        "confidence": best_short["confidence"],
                        "source": source_label,
                        "timestamp": timestamp_str,
                        "formatted_time": formatted_time,
                        "profit_potential": abs(best_short["entry_price"] - best_short["target_price"]) / best_short["entry_price"],
                        "rationale": target.get("rationale", "TA-based recommendation") if include_rationale else "",
                        "current_price": current_price,
                        # Add time-related fields from ta_price_targets.ranges
                        "tp_hours": time_range_data["short"].get("tp_hours", target.get("tp_hours", 0)),
                        "sl_hours": time_range_data["short"].get("sl_hours", target.get("sl_hours", 0)),
                        "tp_range": time_range_data["short"].get("tp_range", target.get("tp_range", "")),
                        "sl_range": time_range_data["short"].get("sl_range", target.get("sl_range", "")),
                        "duration_confidence": time_range_data["short"].get("duration_confidence", target.get("duration_confidence", 0.5)),
                        # Add volatility regime data
                        "volatility_regime": data.get("volatility_regime", {}).get("classification", "NORMAL") if "volatility_regime" in data else "NORMAL"
                    }
                    asset_trades.append(trade_data)
        
        # Only add the highest confidence trade for this asset
        if len(asset_trades) > 1:
            # Sort by confidence and take only the highest confidence trade
            highest_conf_trade = sorted(asset_trades, key=lambda x: x["confidence"], reverse=True)[0]
            all_trades.append(highest_conf_trade)
        elif len(asset_trades) == 1:
            all_trades.append(asset_trades[0])
    
    # Create DataFrame and sort by confidence
    if not all_trades:
        return pd.DataFrame()
        
    df = pd.DataFrame(all_trades)
    
    # Apply support/resistance price adjustments
    if not df.empty:
        df = apply_sr_price_adjustments(df)
    
    # Apply adaptive confidence adjustment if available
    if ADAPTIVE_TRADING_AVAILABLE and not df.empty:
        print("Applying adaptive confidence adjustments to TA-based trades...")
        all_trades_count = len(df)
        adjusted_trades = []
        
        for _, trade in df.iterrows():
            # Skip if the asset is in cooldown for this direction
            asset = trade["asset"]
            direction = trade["direction"]
            in_cooldown, reason = adaptive_system.get_cooldown_status(asset, direction)
            
            # CRITICAL FIX: Also check for direction-wide cooldown
            in_direction_cooldown, direction_reason = adaptive_system.get_direction_cooldown_status(direction)
            
            # Convert to dictionary for adjustment
            adjusted_trade = trade.to_dict()
            
            # Apply confidence adjustment if not in cooldown
            if not in_cooldown and not in_direction_cooldown:
                adjusted_trade = adjust_confidence(adjusted_trade)
                # Add original confidence for reference
                if "original_confidence" not in adjusted_trade:
                    adjusted_trade["original_confidence"] = trade["confidence"]
            else:
                # If in cooldown, add reason and set low confidence
                adjusted_trade["original_confidence"] = trade["confidence"]
                adjusted_trade["confidence"] = 0.1  # Very low confidence for cooldown trades
                adjusted_trade["cooldown_reason"] = reason
                
            adjusted_trades.append(adjusted_trade)
        
        # Convert back to DataFrame
        df = pd.DataFrame(adjusted_trades)
        
        # Add info about adjustments
        print(f"Adjusted confidence scores for {all_trades_count} TA-based trades based on historical performance")
    
    # Sort by confidence
    if not df.empty:
        df = df.sort_values(by="confidence", ascending=False)
    
    # Apply dynamic confidence thresholds based on market alignment
    if not df.empty:
        # Create a filtered DataFrame
        filtered_rows = []
        filtered_out_count = 0
        aligned_count = counter_trend_count = neutral_count = 0
        
        for _, row in df.iterrows():
            # Extract market bias from trade data if available
            market_bias = None
            try:
                if "market_context" in row and isinstance(row["market_context"], str):
                    # Extract from market context string format: "... Overall bias: bullish. ..."
                    context_parts = row["market_context"].split("Overall bias:")
                    if len(context_parts) > 1:
                        bias_part = context_parts[1].split(".")[0].strip().upper()
                        market_bias = bias_part
            except Exception as e:
                print(f"Error extracting market bias: {e}")
            
            # Get dynamic threshold based on direction and market bias
            direction = row["direction"]
            threshold = get_confidence_threshold(direction, market_bias)
            
            # Apply volatility regime confidence modifier if available
            if VOLATILITY_REGIME_AVAILABLE and "volatility_regime" in row:
                volatility_regime = row["volatility_regime"]
                volatility_modifier = get_confidence_modifier(row["asset"], volatility_regime)
                # Apply modifier to confidence (row confidence is already adjusted value)
                orig_confidence = row["confidence"]
                adjusted_confidence = orig_confidence * volatility_modifier
                
                if volatility_modifier < 1.0:
                    print(f"{row['asset']} {direction} - Volatility regime {volatility_regime}: Confidence adjusted from {orig_confidence:.2f} to {adjusted_confidence:.2f}")
                    
                # Update row with adjusted confidence
                row["confidence"] = adjusted_confidence
                row["volatility_modifier"] = volatility_modifier
            
            # Track counts for logging
            alignment = "neutral"
            if market_bias:
                if (direction == "long" and market_bias == "BULLISH") or \
                   (direction == "short" and market_bias == "BEARISH"):
                    alignment = "aligned"
                    aligned_count += 1
                elif (direction == "long" and market_bias == "BEARISH") or \
                     (direction == "short" and market_bias == "BULLISH"):
                    alignment = "counter_trend"
                    counter_trend_count += 1
                else:
                    neutral_count += 1
            else:
                neutral_count += 1
            
            # Filter based on dynamic threshold
            if row["confidence"] >= threshold and row["risk_reward"] >= min_risk_reward:
                filtered_rows.append(row)
            else:
                filtered_out_count += 1
        
        # Create new filtered DataFrame
        if filtered_rows:
            df = pd.DataFrame(filtered_rows)
            # Sort by confidence and limit to top_n
            df = df.sort_values(by="confidence", ascending=False)
            df = df.head(top_n)
        else:
            df = pd.DataFrame()
        
        # Log alignment statistics
        print(f"Trade alignment: {aligned_count} aligned, {counter_trend_count} counter-trend, {neutral_count} neutral")
        print(f"Filtered out {filtered_out_count} trades based on dynamic confidence thresholds")
    
    # CRITICAL: Apply trade adjustments if available
    print(f"***** DEBUG: About to check for trade adjusters. TRADE_ADJUSTERS_AVAILABLE={TRADE_ADJUSTERS_AVAILABLE}, df has {len(df) if not df.empty else 0} rows *****")
    if TRADE_ADJUSTERS_AVAILABLE and not df.empty:
        try:
            print("***** DEBUG: Starting trade parameter adjustments... *****")
            # Trace price of first trade before adjustment
            if len(df) > 0:
                first_trade = df.iloc[0]
                print(f"***** DEBUG: Trade before adjustment - Asset: {first_trade.get('asset')}, Entry: {first_trade.get('entry_price')}, TP: {first_trade.get('target_price')}, SL: {first_trade.get('stop_price')} *****")
            
            # Get market bias from config to pass explicitly
            try:
                from config.market_bias_config import market_bias_config
                market_bias_settings = market_bias_config.get_market_bias_settings()
                market_bias = market_bias_settings.get('bias', 'neutral')
                print(f"***** DEBUG: Current market bias from config: {market_bias} *****")
            except Exception as e:
                print(f"***** DEBUG: Error getting market bias: {e} *****")
                market_bias = 'neutral'
            
            # Force the current_bias value in all trades for testing
            for idx in df.index:
                df.at[idx, 'current_bias'] = market_bias
                df.at[idx, 'bias_source'] = 'config'
            print(f"***** DEBUG: Added current_bias={market_bias} to all trades before adjustment *****")
            
            # Apply adjustments with more debugging
            print("***** CALLING apply_all_trade_adjustments NOW *****")
            df = apply_all_trade_adjustments(df)
            
            # Trace price after adjustment
            if len(df) > 0:
                first_trade = df.iloc[0]
                print(f"***** DEBUG: Trade after adjustment - Asset: {first_trade.get('asset')}, Entry: {first_trade.get('entry_price')}, TP: {first_trade.get('target_price')}, SL: {first_trade.get('stop_price')} *****")
                print(f"***** DEBUG: Original prices stored - Entry: {first_trade.get('orig_entry_price', 'NOT STORED')}, TP: {first_trade.get('orig_target_price', 'NOT STORED')}, SL: {first_trade.get('orig_stop_price', 'NOT STORED')} *****")
                
                # Calculate adjustment percentage for verification
                orig_entry = float(first_trade.get('orig_entry_price', 0))
                new_entry = float(first_trade.get('entry_price', 0))
                if orig_entry > 0:
                    pct_diff = ((new_entry/orig_entry)-1)*100
                    print(f"***** DEBUG: First trade adjustment percentage: {pct_diff:.2f}% *****")
            
            print("***** DEBUG: Trade adjustments applied to all qualifying trades *****")
        except Exception as e:
            print(f"DEBUG: Error applying trade adjustments: {e}")
            import traceback
            traceback.print_exc()
    
    return df

def collect_btc_correlation_trades(max_hours_old=5, top_n=10, min_confidence=0.3, min_risk_reward=1.0,
                                 data_dir="data/visualizations", include_rationale=True, min_sl_percent=1.0):
    """Collect the top BTC correlation trade recommendations from the newest files only"""
    all_trades = []
    assets = get_available_assets(data_dir)
    processed_assets = set()  # Track which assets we've already processed
    
    # Try both data directories
    for source_dir in [data_dir, "data/btc_correlation"]:
        for asset in assets:
            if asset in processed_assets:
                continue  # Skip if we've already processed this asset
                
            processed_assets.add(asset)
            
            # Get all BTC correlation files for this asset
            try:
                if source_dir == "data/btc_correlation":
                    # For BTC correlation directory, use direct file matching
                    import glob
                    file_pattern = os.path.join(source_dir, f"{asset}_btc_correlation_*.json")
                    all_files = glob.glob(file_pattern)
                else:
                    # For visualization directory, use standard logic
                    all_files = find_analysis_files(asset, source_dir)
            except Exception as e:
                print(f"Error finding files for {asset} in {source_dir}: {e}")
                continue
            
            # Filter out old files
            recent_files = []
            for f in all_files:
                try:
                    if is_recent_file(f, max_hours_old):
                        recent_files.append(f)
                except Exception:
                    # Skip files with timestamp issues
                    pass
                    
            if not recent_files:
                continue
                
            # Sort by timestamp (newest first)
            try:
                newest_file = sorted(recent_files, key=get_timestamp_from_filename, reverse=True)[0]
            except Exception as e:
                print(f"Error sorting files for {asset}: {e}")
                continue
            
            # Load data from newest file only
            try:
                data = load_enhanced_analysis(newest_file)
            except Exception:
                # This could be a direct BTC correlation file, try loading directly
                try:
                    with open(newest_file, 'r') as f:
                        data = json.load(f)
                        # Add market bias and support/resistance data to each trade
                        for trade in data["btc_enhanced_trades"]:
                            trade['market_bias'] = data.get("market_bias", "")
                            trade['market_bias_strength'] = data.get("bias_strength", 0)
                            trade['support_levels'] = data.get("support_levels", [])
                            trade['resistance_levels'] = data.get("resistance_levels", [])
                except Exception as e:
                    print(f"Error loading {newest_file}: {e}")
                    continue
            
            if not data:
                continue
                
            # Check if we have BTC correlation trades
            if "btc_enhanced_trades" not in data or not data["btc_enhanced_trades"]:
                continue
                
            btc_trades = data["btc_enhanced_trades"]
            
            # Get current price (may not be available in BTC correlation files)
            current_price = data.get("current_price", 1.0)  # Default to 1.0 if not available
            
            # Process each BTC trade
            for trade in btc_trades:
                # Extract data
                direction = trade.get("direction", "")
                entry_price = trade.get("entry_price", 0)
                target_price = trade.get("target_price", 0)
                stop_price = trade.get("stop_loss", trade.get("stop_price", 0))
                confidence = trade.get("confidence", 0)
                
                # Skip invalid entries
                if not direction or entry_price <= 0:
                    continue
                    
                # For BTC correlation trades, target_price might be unreasonably high
                # Check if target_price is more than 50% away from entry_price (highly unlikely)
                price_diff_pct = abs(target_price - entry_price) / entry_price
                if price_diff_pct > 0.5:  # More than 50% move
                    # Create a more reasonable target (5-10% move)
                    if direction == "long":
                        target_price = entry_price * 1.07  # 7% upside
                    else:  # short
                        target_price = entry_price * 0.93  # 7% downside
                
                # Similarly, fix stop_price if it's unreasonable
                stop_diff_pct = abs(stop_price - entry_price) / entry_price
                if stop_diff_pct > 0.2 or stop_diff_pct < 0.002:  # More than 20% or less than 0.2%
                    # Create a more reasonable stop (1-2% away)
                    if direction == "long":
                        stop_price = entry_price * 0.99  # 1% downside
                    else:  # short
                        stop_price = entry_price * 1.01  # 1% upside
                
                # Check if stop is in the wrong direction
                if (direction == "long" and stop_price > entry_price) or \
                   (direction == "short" and stop_price < entry_price):
                    # Fix stop direction
                    if direction == "long":
                        stop_price = entry_price * 0.99  # 1% downside
                    else:  # short
                        stop_price = entry_price * 1.01  # 1% upside
                
                # Validate confidence score (often extremely high in BTC correlation trades)
                if confidence > 1.0:
                    # Map any confidence over 1.0 to the 0.6-0.9 range (higher = better but realistic)
                    confidence = 0.6 + min(0.3, (confidence - 1.0) / 100.0)
                
                # Calculate risk/reward with validated prices
                sl_distance = abs(entry_price - stop_price)
                tp_distance = abs(target_price - entry_price)
                if sl_distance > 0:
                    risk_reward = tp_distance / sl_distance
                else:
                    continue  # Invalid trade
                
                # Validate risk/reward is reasonable
                if risk_reward > 20 or risk_reward < 0.5:
                    risk_reward = min(max(risk_reward, 1.5), 4.0)  # Cap between 1.5 and 4.0
                
                # Skip low confidence/RR trades
                if confidence < min_confidence or risk_reward < min_risk_reward:
                    continue
                
                # Calculate and validate stop loss distance as percentage
                entry_price = float(trade["entry_price"])
                stop_price = float(trade["stop_price"])
                if entry_price > 0 and stop_price > 0:
                    if trade["direction"].lower() == "long":
                        sl_percent = (entry_price - stop_price) / entry_price * 100
                    else:  # short
                        sl_percent = (stop_price - entry_price) / entry_price * 100
                    
                    # Skip trades with stop loss too close to entry
                    if sl_percent < min_sl_percent:
                        print(f"Skipping {asset} {trade['direction']} - Stop loss too close: {sl_percent:.2f}% (min: {min_sl_percent:.2f}%)")
                        continue
                
                # Extract BTC correlation metrics
                btc_correlation = 0
                btc_influence = 0
                beta = 0
                
                # Look for BTC correlation data in various places
                if "btc_correlation" in data:
                    btc_corr_data = data["btc_correlation"]
                    btc_correlation = btc_corr_data.get("weighted_correlation", 0)
                    beta = btc_corr_data.get("beta", 0)
                    
                    # Extract influence from explanation if available
                    explanation = btc_corr_data.get("explanations", {})
                    btc_influence_text = explanation.get("btc_influence", "")
                    if btc_influence_text and "%" in btc_influence_text:
                        try:
                            # Extract number from text like "3% of trades influenced by BTC analysis"
                            btc_influence = float(btc_influence_text.split("%")[0])/100
                        except ValueError:
                            pass
                # BTC correlation could also be directly in the data
                elif "weighted_correlation" in data:
                    btc_correlation = data.get("weighted_correlation", 0)
                    beta = data.get("beta", 0)
                
                # Create trade dict with BTC-specific fields
                trade_data = {
                    "asset": asset,
                    "direction": direction,
                    "entry_price": entry_price,
                    "target_price": target_price,
                    "stop_price": stop_price,
                    "risk_reward": risk_reward,
                    "confidence": confidence,
                    "source": "BTC Corr",
                    "timestamp": get_timestamp_from_filename(newest_file),
                    "formatted_time": format_timestamp(get_timestamp_from_filename(newest_file))[0],
                    "profit_potential": abs(target_price - entry_price) / entry_price if direction == "long" else abs(entry_price - target_price) / entry_price,
                    "btc_correlation": btc_correlation,
                    "btc_influence": btc_influence,
                    "beta": beta,
                    "rationale": trade.get("rationale", "BTC correlation-based recommendation") if include_rationale else ""
                }
                all_trades.append(trade_data)
    
    # Create DataFrame and sort by confidence
    if not all_trades:
        return pd.DataFrame()
        
    df = pd.DataFrame(all_trades)
    # Sort directly by confidence as requested
    df = df.sort_values('confidence', ascending=False).head(top_n).reset_index(drop=True)
    
    # Apply trade adjustments if available
    if TRADE_ADJUSTERS_AVAILABLE and not df.empty:
        try:
            print("Applying trade parameter adjustments to BTC correlation trades...")
            df = apply_all_trade_adjustments(df)
            print("Trade adjustments applied to all qualifying BTC correlation trades")
        except Exception as e:
            print(f"Error applying trade adjustments to BTC correlation trades: {e}")
    
    return df

def main():
    """Main function to run the trade collection process silently and display trades"""
    # Set default values without parsing command line
    args = {
        "num_trades": 10,
        "max_age": 24.0,
        "min_confidence": 0.2,
        "min_risk_reward": 1.37,  # Updated minimum risk/reward threshold
        "data_dir": "data/visualizations",
        "include_rationale": True,
        "min_sl_percent": 1.0     # Minimum stop loss distance as percentage
    }
    
    # Initialize fibonacci levels for all assets to ensure they're cached
    try:
        print("\n" + "=" * 80)
        print("INITIALIZING FIBONACCI LEVELS")
        print("This might take a moment for first run...")
        
        # Get list of available assets
        assets = get_available_assets(args["data_dir"])
        
        # Import fibonacci calculator
        from utils.fibonacci_levels import refresh_all_fibonacci_levels
        
        # Only refresh if we haven't done so within 24 hours
        refresh_all_fibonacci_levels(assets)
        
        print("Fibonacci levels updated")
        print("=" * 80)
    except Exception as e:
        print(f"Error initializing Fibonacci levels: {e}")
        print("Will calculate on-demand instead")
        print("=" * 80)
    
    # Print info about position filtering
    print("\n" + "=" * 80)
    print("POSITION FILTERING ACTIVE")
    print("Excluding assets with positions, open orders, or activity in last 3 hours")
    print("=" * 80)
    
    # Create sim_trades directory
    sim_trades_dir = os.path.join(PROJECT_ROOT, "data", "sim_trades")
    os.makedirs(sim_trades_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_output = os.path.join(sim_trades_dir, f"trade_signals_{timestamp}.json")
    
    # Temporarily allow debug output to help diagnose S/R data extraction issues
    # original_stdout = sys.stdout
    # sys.stdout = open(os.devnull, 'w')
    original_stdout = sys.stdout  # Just define it but don't redirect
    
    try:
        # Collect TA-based trades - apply adaptive adjustment and min confidence filtering
        ta_trades = collect_ta_based_trades(
            max_hours_old=args["max_age"],
            top_n=25,  # Get top 25 TA trades
            min_confidence=0.2,  # Apply minimum confidence to filter out cooldown trades
            min_risk_reward=0,  # No risk/reward filtering yet
            data_dir=args["data_dir"],
            include_rationale=args["include_rationale"],
            min_sl_percent=args["min_sl_percent"]
        )
        
        # Collect pure liquidation trades
        pure_liq_trades = collect_pure_liquidation_trades(
            max_hours_old=args["max_age"],
            top_n=10,  # Get top 10 pure liquidation trades
            min_confidence=0,  # No confidence filtering
            min_risk_reward=0,  # No risk/reward filtering
            data_dir=args["data_dir"],
            include_rationale=args["include_rationale"],
            min_sl_percent=args["min_sl_percent"]
        )
        
        # Collect BTC correlation trades
        btc_trades = collect_btc_correlation_trades(
            max_hours_old=args["max_age"],
            top_n=10,  # Always get top 10
            min_confidence=max(0.4, args["min_confidence"]),
            min_risk_reward=args["min_risk_reward"],
            data_dir=args["data_dir"],
            include_rationale=args["include_rationale"],
            min_sl_percent=args["min_sl_percent"]
        )
        
        # Create a list to hold all formatted trade signals (TA trades only)
        all_signals = []
        
        # Get risk/reward filter settings from configuration if available
        min_risk_reward_threshold = 1.37  # Default value
        max_risk_reward_threshold = 10.0  # Default max value
        risk_reward_filtering_enabled = True  # Default is enabled
        
        if RISK_REWARD_CONFIG_AVAILABLE:
            try:
                # Get settings from config
                settings = risk_reward_config.get_risk_reward_settings()
                min_risk_reward_threshold = settings.get("min_risk_reward", 1.37)
                max_risk_reward_threshold = settings.get("max_risk_reward", 10.0)
                risk_reward_filtering_enabled = settings.get("enabled", True)
            except Exception as e:
                print(f"Error getting risk/reward settings: {e}")
                # Use defaults if there's an error
        
        # Ensure risk_reward column exists
        if 'risk_reward' not in ta_trades.columns:
            print("Warning: risk_reward column is missing, calculating it from trade parameters...")
            # Calculate risk_reward if we have the necessary columns
            if all(col in ta_trades.columns for col in ['entry_price', 'target_price', 'stop_price']):
                ta_trades['risk_reward'] = ta_trades.apply(
                    lambda row: abs(row['target_price'] - row['entry_price']) / 
                                abs(row['entry_price'] - row['stop_price']) 
                                if abs(row['entry_price'] - row['stop_price']) > 0 else 1.5, 
                    axis=1
                )
            else:
                # Add default value if we can't calculate it
                print("Cannot calculate risk_reward - missing required columns")
                ta_trades['risk_reward'] = 1.5
        
        # Apply risk/reward filters
        if risk_reward_filtering_enabled:
            filtered_ta_trades = ta_trades[
                (ta_trades['risk_reward'] >= min_risk_reward_threshold) &
                (ta_trades['risk_reward'] <= max_risk_reward_threshold)
            ].copy()
        else:
            # If filtering is disabled, keep all trades
            filtered_ta_trades = ta_trades.copy()
        
        # Log how many trades were filtered out
        original_count = len(ta_trades)
        filtered_count = len(filtered_ta_trades)
        filtered_out = original_count - filtered_count
        
        # Apply trade parameter adjustments if available
        if TRADE_ADJUSTERS_AVAILABLE:
            try:
                # Apply all registered trade adjustments
                pre_adjustment_count = len(filtered_ta_trades)
                filtered_ta_trades = apply_all_trade_adjustments(filtered_ta_trades)
                post_adjustment_count = len(filtered_ta_trades)
                
                # Log adjustment results
                if pre_adjustment_count != post_adjustment_count:
                    print(f"Trade adjusters modified trade count from {pre_adjustment_count} to {post_adjustment_count}")
                else:
                    print(f"Trade adjusters applied to {pre_adjustment_count} trades with parameters modified")
            except Exception as e:
                print(f"Error applying trade adjustments: {e}")
                # Continue with unadjusted trades if there's an error
        
        # Add TA-based trades - use direct DataFrame access instead of iterrows() to get adjusted values
        for idx in range(len(filtered_ta_trades)):
            row = filtered_ta_trades.iloc[idx]
            signal = format_sim_trade_signal(row, "TA-Based")
            all_signals.append(signal)
        
        # Write to JSON file
        with open(json_output, 'w') as f:
            json.dump(all_signals, f, indent=2)
    
    finally:
        # We're not redirecting stdout anymore, so nothing to restore
        # if sys.stdout != original_stdout:
        #     sys.stdout.close()
        #     sys.stdout = original_stdout
        pass
    
    # Display the TA-based trades
    print("\n" + "=" * 80)
    if risk_reward_filtering_enabled:
        print(f"TOP 25 TA-BASED TRADE RECOMMENDATIONS (R/R {min_risk_reward_threshold:.2f} - {max_risk_reward_threshold:.2f})")
    else:
        print("TOP 25 TA-BASED TRADE RECOMMENDATIONS (R/R FILTERING DISABLED)")
    print("=" * 80)
    
    if filtered_count > 0:
        if risk_reward_filtering_enabled:
            print(f"Risk/Reward Filter: MIN={min_risk_reward_threshold:.2f}, MAX={max_risk_reward_threshold:.2f}, ENABLED=Yes")
            print(f"Filtered out {filtered_out} trades based on risk/reward range")
        else:
            print("Risk/Reward Filter: DISABLED (showing all trades)")
        print_trade_table(filtered_ta_trades)
    else:
        print(f"No qualifying TA-based trades found with R/R >= {min_risk_reward_threshold}")
    
    # Display the pure liquidation trades
    print("\n" + "=" * 80)
    print("TOP 10 PURE LIQUIDATION RECOMMENDATIONS")
    print("=" * 80)
    if not pure_liq_trades.empty:
        print_trade_table(pure_liq_trades)
    else:
        print("No qualifying pure liquidation trades found")
    
    print("\n" + "=" * 80)
    print("TOP 10 BTC CORRELATION RECOMMENDATIONS")
    print("=" * 80)
    if not btc_trades.empty:
        print_trade_table(btc_trades)
    else:
        print("No qualifying BTC correlation trades found")
        
    # Display the JSON file path at the end
    print("\n" + "=" * 80)
    print(f"JSON file created: {json_output}")
    print("=" * 80)

if __name__ == "__main__":
    # Create data directory if it doesn't exist
    # Create both a relative data directory and a PROJECT_ROOT-based one
    os.makedirs("data", exist_ok=True)
    os.makedirs(os.path.join(PROJECT_ROOT, "data"), exist_ok=True)
    os.makedirs(os.path.join(PROJECT_ROOT, "data", "visualizations"), exist_ok=True)
    
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

