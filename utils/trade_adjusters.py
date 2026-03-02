#!/usr/bin/env python
"""
Trade Parameter Adjusters
------------------------
Provides functions to adjust trade parameters based on market bias
and support/resistance levels before sending to execution.
"""

import os
import sys
import json
import glob
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime

# Add parent directory to path to allow imports from root after moving to utils/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Define project root for consistent file paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Import configuration modules with fallback for directory restructuring
try:
    # Try imports after directory restructuring
    from config.market_bias_config import market_bias_config
    MARKET_BIAS_CONFIG_AVAILABLE = True
    print("Market bias config module loaded from config/ directory")
except ImportError:
    try:
        # Fallback to original import during transition
        from market_bias_config import market_bias_config
        MARKET_BIAS_CONFIG_AVAILABLE = True
        print("Market bias config module loaded from root directory")
    except ImportError:
        MARKET_BIAS_CONFIG_AVAILABLE = False
        print("Warning: market_bias_config module not found, using default values")

try:
    # Try imports after directory restructuring
    from config.support_resistance_config import support_resistance_config
    SUPPORT_RESISTANCE_CONFIG_AVAILABLE = True
    print("Support/resistance config module loaded from config/ directory")
except ImportError:
    try:
        # Fallback to original import during transition
        from support_resistance_config import support_resistance_config
        SUPPORT_RESISTANCE_CONFIG_AVAILABLE = True
        print("Support/resistance config module loaded from root directory")
    except ImportError:
        SUPPORT_RESISTANCE_CONFIG_AVAILABLE = False
        print("Warning: support_resistance_config module not found, using default values")

# Visualization directory paths - try both root and after moving to utils/
VISUALIZATION_DIR_FROM_ROOT = os.path.join(PROJECT_ROOT, "data", "visualizations")
VISUALIZATION_DIR_ORIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "visualizations")

# Use the directory that exists, prefer root path after moving to utils/
VISUALIZATION_DIR = VISUALIZATION_DIR_FROM_ROOT if os.path.exists(VISUALIZATION_DIR_FROM_ROOT) else VISUALIZATION_DIR_ORIG

def get_timestamp_from_filename(filename):
    """Extract timestamp from filename or return None if no timestamp"""
    import re
    # Extract timestamp like 20250507_204028 from filenames
    match = re.search(r'(\d{8}_\d{6})', os.path.basename(filename))
    if match:
        return match.group(1)
    return None

def get_newest_analysis_file(asset: str) -> str:
    """Get the newest analysis file for an asset"""
    # Ensure visualization directory exists
    if not os.path.exists(VISUALIZATION_DIR):
        print(f"DEBUG SR: Visualization directory does not exist: {VISUALIZATION_DIR}")
        return ""
        
    # Find all analysis files for this asset
    pattern = f"{asset}_*enhanced_analysis_*.json"
    asset_files = glob.glob(os.path.join(VISUALIZATION_DIR, pattern))
    
    if not asset_files:
        print(f"DEBUG SR: No analysis files found for {asset} with pattern: {pattern}")
        return ""
        
    # Get the newest file by timestamp
    newest_file = max(asset_files, key=lambda x: get_timestamp_from_filename(x) or "")
    return newest_file

def get_market_bias_from_analysis(asset):
    """Get market bias from the newest analysis file for the asset"""
    # Find newest analysis file for this asset
    newest_file = get_newest_analysis_file(asset)
    
    if not newest_file:
        return "neutral", 0.0
    
    # Load the file and extract market bias info
    try:
        with open(newest_file, 'r') as f:
            analysis_data = json.load(f)
            
        # Extract market bias data
        bias_data = analysis_data.get("market_bias", {})
        
        bias = bias_data.get("bias", "NEUTRAL").upper()
        strength = bias_data.get("bias_strength", 0.0)
        
        # Convert to our format
        if bias == "BEARISH":
            return "bearish", strength
        elif bias == "BULLISH":
            return "bullish", strength
        else:
            return "neutral", 0.0
            
    except Exception as e:
        print(f"Error getting market bias for {asset}: {e}")
        return "neutral", 0.0

def identify_key_levels(asset: str, entry_price: float) -> tuple:
    """
    Identify nearby support and resistance levels for an asset.
    
    Args:
        asset: Asset symbol
        current_price: Current price of the asset
        
    Returns:
        tuple: (near_support, near_resistance, proximity_percent, level_price)
            near_support (bool): Whether price is near a support level
            near_resistance (bool): Whether price is near a resistance level
            proximity_percent (float): Proximity to the level as a percentage
            level_price (float): Price of the nearest support/resistance level
    """
    # Default return values if no key levels found
    near_support = False
    near_resistance = False
    proximity_percent = 0.0
    level_price = 0.0
    
    # Find newest analysis file for this asset
    newest_file = get_newest_analysis_file(asset)
    
    if not newest_file:
        print(f"DEBUG SR: No analysis file found for {asset}")
        return near_support, near_resistance, proximity_percent, level_price
    
    print(f"DEBUG SR: Found analysis file for {asset}: {os.path.basename(newest_file)}")
    
    # Load the file and extract S/R levels
    try:
        with open(newest_file, 'r') as f:
            analysis_data = json.load(f)
            
        # Get proximity threshold from support_resistance_config if available
        proximity_threshold = 1.0  # Default 1%
        if SUPPORT_RESISTANCE_CONFIG_AVAILABLE:
            try:
                settings = support_resistance_config.get_support_resistance_settings()
                proximity_threshold = settings.get("proximity_threshold_percent", 1.0)
                print(f"DEBUG SR: Using proximity threshold of {proximity_threshold}% from config")
            except Exception as e:
                print(f"DEBUG SR: Error getting proximity threshold from config: {e}")
            
        # Extract support/resistance data by checking various possible locations in the JSON
        sr_data = {}
        
        # Check in price_targets -> enhanced_summary -> market_context
        if "price_targets" in analysis_data and "enhanced_summary" in analysis_data["price_targets"] and \
           "market_context" in analysis_data["price_targets"]["enhanced_summary"] and \
           "support_resistance" in analysis_data["price_targets"]["enhanced_summary"]["market_context"]:
            sr_data = analysis_data["price_targets"]["enhanced_summary"]["market_context"]["support_resistance"]
            print(f"DEBUG SR: Found S/R data in price_targets->enhanced_summary->market_context")
        
        # Check in summary -> market_context 
        elif "summary" in analysis_data and "market_context" in analysis_data["summary"] and \
             "support_resistance" in analysis_data["summary"]["market_context"]:
            sr_data = analysis_data["summary"]["market_context"]["support_resistance"]
            print(f"DEBUG SR: Found S/R data in summary->market_context")
        
        # Direct in market_context
        elif "market_context" in analysis_data and "support_resistance" in analysis_data["market_context"]:
            sr_data = analysis_data["market_context"]["support_resistance"]
            print(f"DEBUG SR: Found S/R data in market_context")
        
        # Direct at root (original location)
        elif "support_resistance" in analysis_data:
            sr_data = analysis_data["support_resistance"]
            print(f"DEBUG SR: Found S/R data at root level")
        
        # Get support and resistance levels
        support_levels = sr_data.get("support_levels", [])
        resistance_levels = sr_data.get("resistance_levels", [])
        
        print(f"DEBUG SR: {asset} support levels: {support_levels}")
        print(f"DEBUG SR: {asset} resistance levels: {resistance_levels}")
        
        # ALWAYS calculate closest levels directly from arrays - this is more reliable
        closest_support = 0
        closest_resistance = 0
        
        # Find the highest support below current price
        valid_supports = [s for s in support_levels if isinstance(s, (int, float)) and s < current_price]
        if valid_supports:
            closest_support = max(valid_supports)
            print(f"DEBUG SR: Calculated closest support: {closest_support}")
        
        # Find the lowest resistance above current price
        valid_resistances = [r for r in resistance_levels if isinstance(r, (int, float)) and r > current_price]
        if valid_resistances:
            closest_resistance = min(valid_resistances)
            print(f"DEBUG SR: Calculated closest resistance: {closest_resistance}")
        
        # Check if price is near these levels (within 1%)
        if closest_support > 0:
            support_distance = (current_price - closest_support) / current_price * 100
            print(f"DEBUG SR: {asset} support distance: {support_distance:.2f}% from level {closest_support}")
            
            # Use configurable proximity threshold
            if 0 <= support_distance <= proximity_threshold:
                near_support = True
                proximity_percent = support_distance
                level_price = closest_support
                print(f"DEBUG SR: {asset} IS NEAR SUPPORT at {closest_support} (distance: {support_distance:.2f}%)")
                
        if closest_resistance > 0:
            resistance_distance = (closest_resistance - current_price) / current_price * 100
            print(f"DEBUG SR: {asset} resistance distance: {resistance_distance:.2f}% from level {closest_resistance}")
            
            # Use configurable proximity threshold
            if 0 <= resistance_distance <= proximity_threshold:
                # If both support and resistance are nearby, use the closer one
                if near_support and resistance_distance > proximity_percent:
                    # Support is closer, keep that data
                    print(f"DEBUG SR: {asset} IS NEAR BOTH SUPPORT AND RESISTANCE, but support is closer")
                    pass
                else:
                    near_support = False
                    near_resistance = True
                    proximity_percent = resistance_distance
                    level_price = closest_resistance
                    print(f"DEBUG SR: {asset} IS NEAR RESISTANCE at {closest_resistance} (distance: {resistance_distance:.2f}%)")
                    
        return near_support, near_resistance, proximity_percent, level_price
        
    except Exception as e:
        print(f"Error identifying key levels for {asset}: {e}")
        return near_support, near_resistance, proximity_percent, level_price

def apply_market_bias_adjustments(trades_df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply market bias adjustments to trade parameters.
    
    Args:
        trades_df: DataFrame containing trade data
        
    Returns:
        DataFrame: Adjusted trades DataFrame
    """
    if not MARKET_BIAS_CONFIG_AVAILABLE:
        print("Market bias configuration not available, skipping adjustments")
        return trades_df
        
    # Get market bias settings from the UI
    settings = market_bias_config.get_market_bias_settings()
    ui_bias = settings.get("bias", "neutral")
    enabled = settings.get("enabled", True)
    favorable_adj = settings.get("favorable_adjustment", 1.5) / 100  # Convert to decimal
    unfavorable_adj = settings.get("unfavorable_adjustment", 5.0) / 100  # Convert to decimal
    use_auto_bias = settings.get("use_auto_bias", False)
    
    # Skip if disabled
    if not enabled:
        return trades_df
        
    # Copy dataframe to avoid modifying the original
    adjusted_trades = trades_df.copy()
    
    # Apply adjustments based on bias
    for idx, trade in adjusted_trades.iterrows():
        asset = trade.get('asset', '')
        direction = trade.get('direction', '')
        
        # Skip if no direction or not a valid direction
        if not direction or direction not in ['LONG', 'SHORT']:
            continue
            
        # Get relevant price fields to adjust
        entry_price = float(trade.get('entry_price', 0))
        target_price = float(trade.get('target_price', 0))
        stop_price = float(trade.get('stop_price', 0))
        
        # Store original values before adjustment
        adjusted_trades.at[idx, 'orig_entry_price'] = entry_price
        adjusted_trades.at[idx, 'orig_target_price'] = target_price
        adjusted_trades.at[idx, 'orig_stop_price'] = stop_price
        
        # Skip if no valid entry price
        if entry_price <= 0:
            continue
        
        # Determine bias to use - either from UI or from analysis file
        current_bias = ui_bias
        bias_source = "manual"
        bias_strength = 1.0  # Default strength multiplier
        
        # If auto bias is enabled, get bias from analysis file
        if use_auto_bias and asset:
            analysis_bias, analysis_strength = get_market_bias_from_analysis(asset)
            current_bias = analysis_bias
            bias_source = "auto"
            # Scale adjustments by bias strength (0.3 bias strength = 30% of full adjustment)
            bias_strength = max(0.1, analysis_strength)
        
        # Skip if neutral bias
        if current_bias == "neutral":
            continue
            
        # Calculate actual adjustments
        actual_favorable_adj = favorable_adj * bias_strength
        actual_unfavorable_adj = unfavorable_adj * bias_strength
        
        # Debug the adjustment decision path
        print(f"DEBUG ADJUSTMENT: Asset={asset}, Direction={direction}, Bias={current_bias}, Will adjust? {current_bias != 'neutral'}")
        
        # Bullish market settings
        if current_bias == "bullish":
            if direction == 'LONG':
                # Make longs easier to fill (higher entry)
                old_price = entry_price
                adjusted_trades.at[idx, 'entry_price'] = entry_price * (1 + actual_favorable_adj)
                new_price = adjusted_trades.at[idx, 'entry_price']
                print(f"DEBUG APPLIED: LONG trade in BULLISH market: {asset} entry price adjusted from {old_price} to {new_price} (+{actual_favorable_adj*100:.1f}%)")
                # Add note about adjustment
                rationale = trade.get('rationale', '')
                adjusted_trades.at[idx, 'rationale'] = f"{rationale} [+Bullish bias ({bias_source}): entry raised by {actual_favorable_adj*100:.1f}%]"
            else:  # SHORT
                # Make shorts harder to fill (much higher entry)
                adjusted_trades.at[idx, 'entry_price'] = entry_price * (1 + actual_unfavorable_adj)
                # Add note about adjustment
                rationale = trade.get('rationale', '')
                adjusted_trades.at[idx, 'rationale'] = f"{rationale} [+Bullish bias ({bias_source}): entry raised by {actual_unfavorable_adj*100:.1f}%]"
                
        # Bearish market settings
        elif current_bias == "bearish":
            if direction == 'SHORT':
                # Make shorts easier to fill (lower entry)
                adjusted_trades.at[idx, 'entry_price'] = entry_price * (1 - actual_favorable_adj)
                # Add note about adjustment
                rationale = trade.get('rationale', '')
                adjusted_trades.at[idx, 'rationale'] = f"{rationale} [+Bearish bias ({bias_source}): entry lowered by {actual_favorable_adj*100:.1f}%]"
            else:  # LONG
                # Make longs harder to fill (much lower entry)
                adjusted_trades.at[idx, 'entry_price'] = entry_price * (1 - actual_unfavorable_adj)
                # Add note about adjustment
                rationale = trade.get('rationale', '')
                adjusted_trades.at[idx, 'rationale'] = f"{rationale} [+Bearish bias ({bias_source}): entry lowered by {actual_unfavorable_adj*100:.1f}%]"
    
    return adjusted_trades

def apply_support_resistance_adjustments(trades_df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply support/resistance level adjustments to trade parameters.
    
    Args:
        trades_df: DataFrame containing trade data
        
    Returns:
        DataFrame: Adjusted trades DataFrame
    """
    if not SUPPORT_RESISTANCE_CONFIG_AVAILABLE:
        print("Support/resistance configuration not available, skipping adjustments")
        return trades_df
        
    # Get support/resistance settings
    settings = support_resistance_config.get_support_resistance_settings()
    enabled = settings.get("enabled", False)  # Default to disabled for safety
    support_adj = settings.get("support_adjustment_percent", 0.5) / 100  # Convert to decimal
    resistance_adj = settings.get("resistance_adjustment_percent", 0.5) / 100  # Convert to decimal
    tp_widening = settings.get("tp_widening_percent", 15.0) / 100  # Convert to decimal
    proximity_threshold = settings.get("proximity_threshold_percent", 1.0)  # Threshold for proximity to key levels
    
    # SL adjustment factor (70% of the entry adjustment to improve R/R)
    sl_adj_factor = 0.7
    
    # Skip if disabled
    if not enabled:
        return trades_df
        
    # Copy dataframe to avoid modifying the original
    adjusted_trades = trades_df.copy()
    
    # Loop through ALL trades to ensure every trade has support/resistance data
    for idx, trade in adjusted_trades.iterrows():
        asset = trade.get('asset', '')
        direction = trade.get('direction', '')
        
        # Skip if no asset or direction
        if not asset or not direction or direction not in ['LONG', 'SHORT']:
            continue
            
        # Get relevant price fields to adjust
        entry_price = float(trade.get('entry_price', 0))
        target_price = float(trade.get('target_price', 0))
        stop_price = float(trade.get('stop_price', 0))
        
        # Always store original values before any adjustment
        # Only update if not already set (to preserve original values from market bias adjustments)
        if 'orig_entry_price' not in adjusted_trades.columns or pd.isna(adjusted_trades.at[idx, 'orig_entry_price']):
            adjusted_trades.at[idx, 'orig_entry_price'] = entry_price
        if 'orig_target_price' not in adjusted_trades.columns or pd.isna(adjusted_trades.at[idx, 'orig_target_price']):
            adjusted_trades.at[idx, 'orig_target_price'] = target_price
        if 'orig_stop_price' not in adjusted_trades.columns or pd.isna(adjusted_trades.at[idx, 'orig_stop_price']):
            adjusted_trades.at[idx, 'orig_stop_price'] = stop_price
            
        # Skip if no valid prices
        if entry_price <= 0 or target_price <= 0 or stop_price <= 0:
            continue
            
        # Check proximity to support/resistance levels
        near_support, near_resistance, proximity_percent, level_price = identify_key_levels(asset, entry_price)
        
        # Store the key level information for display - for EVERY trade
        adjusted_trades.at[idx, 'key_level_type'] = 'support' if near_support else ('resistance' if near_resistance else 'none')
        adjusted_trades.at[idx, 'key_level_price'] = level_price if (near_support or near_resistance) else 0
        adjusted_trades.at[idx, 'key_level_proximity'] = proximity_percent
        
        # Removed skip - process all trades regardless of proximity to key levels
        # This ensures all trades have proper support/resistance information in the output
        
        # Calculate original risk (distance from entry to stop)
        if direction == 'LONG':
            orig_risk = entry_price - stop_price
            orig_reward = target_price - entry_price
        else:  # SHORT
            orig_risk = stop_price - entry_price
            orig_reward = entry_price - target_price
            
        orig_rr_ratio = orig_reward / orig_risk if orig_risk > 0 else 1.0
            
        # Apply adjustments based on proximity and direction
        if direction == 'LONG':
            if near_support:
                # Near support for a long: Move entry up, widen TP, adjust SL proportionally
                new_entry = entry_price * (1 + support_adj)
                new_tp = target_price * (1 + tp_widening)
                
                # Adjust SL to maintain or improve R/R ratio
                # Use a smaller scaling factor for SL to improve R/R
                sl_adjustment = support_adj * sl_adj_factor
                new_sl = stop_price * (1 + sl_adjustment)
                
                adjusted_trades.at[idx, 'entry_price'] = new_entry
                adjusted_trades.at[idx, 'target_price'] = new_tp
                adjusted_trades.at[idx, 'stop_price'] = new_sl
                
                # Add note about adjustment
                rationale = trade.get('rationale', '')
                adjusted_trades.at[idx, 'rationale'] = f"{rationale} [+Support level adjustment: entry raised by {support_adj*100:.1f}%, TP widened by {tp_widening*100:.1f}%, SL raised by {sl_adjustment*100:.1f}%]"
                
            elif near_resistance:
                # Near resistance for a long: Move entry down, lower TP, adjust SL
                new_entry = entry_price * (1 - resistance_adj)
                
                # Lower TP as resistance will act as a cap
                tp_adjustment = resistance_adj * 1.5  # More conservative TP near resistance
                new_tp = target_price * (1 - tp_adjustment)
                
                # Lower SL too but less to maintain R/R
                sl_adjustment = resistance_adj * sl_adj_factor
                new_sl = stop_price * (1 - sl_adjustment)
                
                adjusted_trades.at[idx, 'entry_price'] = new_entry
                adjusted_trades.at[idx, 'target_price'] = new_tp
                adjusted_trades.at[idx, 'stop_price'] = new_sl
                
                # Add note about adjustment
                rationale = trade.get('rationale', '')
                adjusted_trades.at[idx, 'rationale'] = f"{rationale} [+Resistance level adjustment: entry lowered by {resistance_adj*100:.1f}%, TP lowered by {tp_adjustment*100:.1f}%, SL lowered by {sl_adjustment*100:.1f}%]"
                
        elif direction == 'SHORT':
            if near_resistance:
                # Near resistance for a short: Move entry up, widen TP (lower price), adjust SL
                new_entry = entry_price * (1 + resistance_adj)
                new_tp = target_price * (1 - tp_widening)
                
                # Adjust SL to maintain or improve R/R ratio
                sl_adjustment = resistance_adj * sl_adj_factor
                new_sl = stop_price * (1 + sl_adjustment)
                
                adjusted_trades.at[idx, 'entry_price'] = new_entry
                adjusted_trades.at[idx, 'target_price'] = new_tp
                adjusted_trades.at[idx, 'stop_price'] = new_sl
                
                # Add note about adjustment
                rationale = trade.get('rationale', '')
                adjusted_trades.at[idx, 'rationale'] = f"{rationale} [+Resistance level adjustment: entry raised by {resistance_adj*100:.1f}%, TP widened by {tp_widening*100:.1f}%, SL raised by {sl_adjustment*100:.1f}%]"
                
            elif near_support:
                # Near support for a short: Move entry down, raise TP, adjust SL
                new_entry = entry_price * (1 - support_adj)
                
                # Raise TP as support will act as a floor
                tp_adjustment = support_adj * 1.5  # More conservative TP near support
                new_tp = target_price * (1 + tp_adjustment)
                
                # Lower SL too but less to maintain R/R
                sl_adjustment = support_adj * sl_adj_factor
                new_sl = stop_price * (1 - sl_adjustment)
                
                adjusted_trades.at[idx, 'entry_price'] = new_entry
                adjusted_trades.at[idx, 'target_price'] = new_tp
                adjusted_trades.at[idx, 'stop_price'] = new_sl
                
                # Add note about adjustment
                rationale = trade.get('rationale', '')
                adjusted_trades.at[idx, 'rationale'] = f"{rationale} [+Support level adjustment: entry lowered by {support_adj*100:.1f}%, TP raised by {tp_adjustment*100:.1f}%, SL lowered by {sl_adjustment*100:.1f}%]"
    
    return adjusted_trades

def apply_all_trade_adjustments(trades_df):
    """
    Apply all available trade adjustments to the DataFrame of trades.
    This is the main entry point for the trade adjustment system.
    
    Args:
        trades_df (pd.DataFrame): DataFrame containing trades to adjust
        
    Returns:
        pd.DataFrame: Adjusted trades DataFrame
    """
    print(f"DEBUG: apply_all_trade_adjustments called with DataFrame of {len(trades_df)} rows")
    
    # Ensure we have the correct column names
    print(f"DEBUG: Columns in DataFrame: {list(trades_df.columns)}")
    
    # Store original values before any adjustments
    adjusted_trades = trades_df.copy()
    
    # Get market bias configuration
    market_bias_settings = None
    try:
        from config.market_bias_config import market_bias_config
        
        # Print config file path being used
        print(f"DEBUG: Loading market bias from config file: {market_bias_config.config_file}")
        
        # Print raw config content
        print(f"DEBUG: Raw config content: {market_bias_config.config}")
        
        # Get settings
        market_bias_settings = market_bias_config.get_market_bias_settings()
        print(f"DEBUG: Market bias settings returned from get_market_bias_settings(): {market_bias_settings}")
        
        # Extract specific values
        market_bias_enabled = market_bias_settings.get('enabled', False)
        favorable_adjustment_pct = market_bias_settings.get('favorable_adjustment', 0.0)
        unfavorable_adjustment_pct = market_bias_settings.get('unfavorable_adjustment', 0.0)
        current_bias = market_bias_settings.get('bias', 'neutral')
        
        # Convert percentages to decimal
        favorable_adjustment = favorable_adjustment_pct / 100.0
        unfavorable_adjustment = unfavorable_adjustment_pct / 100.0
        
        print(f"DEBUG: Market bias config - Enabled: {market_bias_enabled}, Bias: {current_bias}")
        print(f"DEBUG: Adjustment values - Favorable: {favorable_adjustment_pct}% ({favorable_adjustment} decimal), Unfavorable: {unfavorable_adjustment_pct}% ({unfavorable_adjustment} decimal)")
    except Exception as e:
        print(f"DEBUG: Error reading market bias config: {e}")
        market_bias_enabled = False
        favorable_adjustment = 0.0
        unfavorable_adjustment = 0.0
        current_bias = 'neutral'
    
    # Store original values for all trades first
    for idx, trade in adjusted_trades.iterrows():
        # Store original values
        entry_price = float(trade.get('entry_price', 0))
        target_price = float(trade.get('target_price', 0)) 
        stop_price = float(trade.get('stop_price', 0))
        
        # Store original values in dedicated columns
        adjusted_trades.at[idx, 'orig_entry_price'] = entry_price
        adjusted_trades.at[idx, 'orig_target_price'] = target_price
        adjusted_trades.at[idx, 'orig_stop_price'] = stop_price
    
    # Apply adjustments if enabled in config
    if market_bias_enabled and current_bias != 'neutral':
        print(f"DEBUG: APPLYING MARKET BIAS ADJUSTMENTS FROM CONFIG: {current_bias} bias, {favorable_adjustment_pct}% favorable, {unfavorable_adjustment_pct}% unfavorable")
        
        for idx, trade in adjusted_trades.iterrows():
            direction = trade.get('direction', 'UNKNOWN')
            # Normalize direction to uppercase for consistent comparison
            if isinstance(direction, str):
                direction = direction.upper()
            asset = trade.get('asset', 'UNKNOWN')
            entry_price = float(trade.get('entry_price', 0))
            
            # Determine which adjustment to apply based on bias and direction
            adjustment_pct = 0.0
            adjustment_type = ''
            
            if current_bias == 'bullish':
                if direction == 'LONG':
                    # Bullish bias + LONG trade = favorable adjustment
                    adjustment_pct = favorable_adjustment
                    adjustment_type = 'favorable'
                    print(f"DEBUG: {asset} {direction} - BULLISH FAVORABLE adjustment of {favorable_adjustment_pct}% (config value)")
                elif direction == 'SHORT':
                    # Bullish bias + SHORT trade = unfavorable adjustment
                    adjustment_pct = unfavorable_adjustment
                    adjustment_type = 'unfavorable'
                    print(f"DEBUG: {asset} {direction} - BULLISH UNFAVORABLE adjustment of {unfavorable_adjustment_pct}% (config value)")
                else:
                    # Unknown direction, skip adjustment
                    print(f"DEBUG: {asset} {direction} - UNKNOWN DIRECTION, skipping adjustment")
                    continue
            elif current_bias == 'bearish':
                if direction == 'SHORT':
                    # Bearish bias + SHORT trade = favorable adjustment
                    adjustment_pct = favorable_adjustment
                    adjustment_type = 'favorable'
                    print(f"DEBUG: {asset} {direction} - BEARISH FAVORABLE adjustment of {favorable_adjustment_pct}% (config value)")
                elif direction == 'LONG':
                    # Bearish bias + LONG trade = unfavorable adjustment
                    adjustment_pct = unfavorable_adjustment
                    adjustment_type = 'unfavorable'
                    print(f"DEBUG: {asset} {direction} - BEARISH UNFAVORABLE adjustment of {unfavorable_adjustment_pct}% (config value)")
                else:
                    # Unknown direction, skip adjustment
                    print(f"DEBUG: {asset} {direction} - UNKNOWN DIRECTION, skipping adjustment")
                    continue
            
            # Apply the adjustment to entry price
            new_entry = entry_price * (1 + adjustment_pct)
            adjusted_trades.at[idx, 'entry_price'] = new_entry
            
            # Also adjust target price (TP) by the same percentage to maintain risk/reward ratio
            target_price = float(trade.get('target_price', 0))
            if target_price > 0:
                if direction == 'LONG':
                    # For longs, increase TP by same percent
                    new_target = target_price * (1 + adjustment_pct)
                else:  # SHORT
                    # For shorts, decrease TP by same percent (since lower price is better for shorts)
                    new_target = target_price * (1 - adjustment_pct)
                adjusted_trades.at[idx, 'target_price'] = new_target
                print(f"DEBUG: Adjusted TP for {asset} {direction} trade from {target_price} to {new_target} (adjustment: {adjustment_pct*100:.1f}%)")
            else:
                print(f"DEBUG: No TP adjustment for {asset} {direction} - invalid target price: {target_price}")
            
            # Add explanation to rationale
            rationale = trade.get('rationale', '')
            adjusted_trades.at[idx, 'rationale'] = f"{rationale} [{current_bias.upper()} BIAS: entry {adjustment_type} +{adjustment_pct*100:.1f}%, TP widened by same %]"            
            
            print(f"DEBUG: Applied {adjustment_type} adjustment of {adjustment_pct*100:.1f}% to {asset} {direction} trade (original: {entry_price}, new: {new_entry})")
    else:
        print("DEBUG: Market bias adjustments DISABLED in config or set to neutral - no adjustments applied")
    
    # Original price values already stored in the forced adjustment section above
    # Log that we stored original values
    if not adjusted_trades.empty:
        first_trade = adjusted_trades.iloc[0]
        print(f"DEBUG: Original values stored for first trade: {first_trade.get('asset')} {first_trade.get('direction')}")
        print(f"DEBUG: Entry: {first_trade.get('orig_entry_price')}, TP: {first_trade.get('orig_target_price')}, SL: {first_trade.get('orig_stop_price')}")
    
    # Log that we're storing original prices
    print("DEBUG: Stored original prices for all trades before adjustments")
    
    # Check market bias settings with directory structure handling
    try:
        # Try imports after directory restructuring
        try:
            from config.market_bias_config import market_bias_config
            mb_settings = market_bias_config.get_market_bias_settings()
            print(f"DEBUG: Market bias settings from config/ directory: {mb_settings}")
        except ImportError:
            # Fallback to original import during transition
            from market_bias_config import market_bias_config
            mb_settings = market_bias_config.get_market_bias_settings()
            print(f"DEBUG: Market bias settings from root directory: {mb_settings}")
    except Exception as e:
        print(f"DEBUG: Error checking market bias settings: {e}")
    
    # Check support/resistance settings with directory structure handling
    try:
        # Try imports after directory restructuring
        try:
            from config.support_resistance_config import support_resistance_config
            sr_settings = support_resistance_config.get_support_resistance_settings()
            sr_enabled = sr_settings.get('enabled', False)
            print(f"DEBUG: Support/resistance settings from config/ directory: {sr_settings}")
        except ImportError:
            # Fallback to original import during transition
            from support_resistance_config import support_resistance_config
            sr_settings = support_resistance_config.get_support_resistance_settings()
            sr_enabled = sr_settings.get('enabled', False)
            print(f"DEBUG: Support/resistance settings from root directory: {sr_settings}")
            
        print(f"DEBUG: Support/resistance adjustments {'ENABLED' if sr_enabled else 'DISABLED'}")
    except Exception as e:
        print(f"DEBUG: Error checking support/resistance settings: {e}")
        # DEFAULT TO TRUE instead of False if there's an exception
        sr_enabled = True
        print("DEBUG: Defaulting to ENABLED support/resistance adjustments despite error")
    
    # Apply market bias adjustments first
    print("DEBUG: Applying market bias adjustments...")
    adjusted_trades = apply_market_bias_adjustments(adjusted_trades)
    
    # Then apply support/resistance adjustments if enabled
    if SUPPORT_RESISTANCE_CONFIG_AVAILABLE and sr_enabled:
        print("DEBUG: Applying support/resistance adjustments...")
        adjusted_trades = apply_support_resistance_adjustments(adjusted_trades)
    else:
        print("DEBUG: Support/resistance adjustments skipped (disabled or config unavailable)")
        
    # Ensure original columns exist and have values for display
    if not adjusted_trades.empty:
        # Make sure these columns are created even if no adjustments were applied
        if 'orig_entry_price' not in adjusted_trades.columns:
            for idx, trade in adjusted_trades.iterrows():
                adjusted_trades.at[idx, 'orig_entry_price'] = trade['entry_price']
                adjusted_trades.at[idx, 'orig_target_price'] = trade['target_price']
                adjusted_trades.at[idx, 'orig_stop_price'] = trade['stop_price']
    
    # Print a debug message to confirm price changes for the first trade
    if not adjusted_trades.empty:
        first_trade = adjusted_trades.iloc[0]
        asset = first_trade.get('asset', 'Unknown')
        direction = first_trade.get('direction', 'Unknown')
        orig_entry = first_trade.get('orig_entry_price', 0)
        new_entry = first_trade.get('entry_price', 0)
        try:
            percent_diff = ((new_entry/orig_entry)-1)*100 if orig_entry > 0 else 0
            print(f"DEBUG: {asset} {direction} - Orig Entry: {orig_entry}, New Entry: {new_entry}, Diff: {percent_diff:.1f}%")
        except Exception as e:
            print(f"DEBUG: Error calculating price difference: {e}")
        
        # Check if the columns are actually in the DataFrame
        print(f"DEBUG: Final DataFrame columns: {list(adjusted_trades.columns)}")
        if 'orig_entry_price' in adjusted_trades.columns:
            print("DEBUG: orig_entry_price column exists in final DataFrame")
        else:
            print("DEBUG: WARNING - orig_entry_price column MISSING from final DataFrame!")
    
    return adjusted_trades
