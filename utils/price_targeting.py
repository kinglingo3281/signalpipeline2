#!/usr/bin/env python
"""
Price Targeting Module
--------------------
Generates optimal price targets based on liquidation clusters and cascade probabilities.
Uses market context for dynamic probability and confidence scoring.
"""

import os
import sys
import math
import random
from datetime import datetime
from typing import List, Dict, Optional, Union, Tuple

# Add parent directory to path to allow imports from root after moving to utils/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import market context module from same directory after move
try:
    from utils.market_context import get_market_context
except ImportError:
    try:
        from market_context import get_market_context
    except ImportError:
        print("Warning: market_context module not found, using default probability calculations")
        get_market_context = None

def find_technical_stop_loss(entry_price: float, direction: str, market_context: Optional[object], min_distance_pct: float = 0.5) -> Tuple[float, str]:
    """
    Find an appropriate technical level to use as stop loss, ensuring minimum distance from entry.
    
    Args:
        entry_price: Entry price of the trade
        direction: 'long' or 'short'
        market_context: Market context object with technical levels
        min_distance_pct: Minimum distance percentage from entry price
        
    Returns:
        Tuple of (stop_price, source_description)
    """
    if not market_context or not hasattr(market_context, 'context_data'):
        # No market context, return None to use fallback
        return None, "no_context"
    
    # Calculate minimum distance in absolute price
    min_distance = entry_price * (min_distance_pct / 100)
    
    # Extract technical levels from market context
    levels = []
    level_sources = []
    
    # Add support/resistance levels
    if "support_resistance" in market_context.context_data:
        sr_data = market_context.context_data["support_resistance"]
        
        if direction == "long" and "support_levels" in sr_data:
            for level in sr_data["support_levels"]:
                # For long positions, look for support levels below entry, but not too close
                if entry_price - level >= min_distance:
                    levels.append(level)
                    level_sources.append("support")
        
        if direction == "short" and "resistance_levels" in sr_data:
            for level in sr_data["resistance_levels"]:
                # For short positions, look for resistance levels above entry, but not too close
                if level - entry_price >= min_distance:
                    levels.append(level)
                    level_sources.append("resistance")
    
    # Add moving averages
    if "moving_averages" in market_context.context_data:
        ma_data = market_context.context_data["moving_averages"]
        for ma_name, ma_value in ma_data.items():
            if direction == "long" and entry_price - ma_value >= min_distance:
                levels.append(ma_value)
                level_sources.append(ma_name)
            elif direction == "short" and ma_value - entry_price >= min_distance:
                levels.append(ma_value)
                level_sources.append(ma_name)
    
    # Add Bollinger Bands
    if "volatility" in market_context.context_data and "bbands" in market_context.context_data["volatility"]:
        bb_data = market_context.context_data["volatility"]["bbands"]
        
        if direction == "long" and "lower" in bb_data:
            bb_lower = bb_data["lower"]
            if entry_price - bb_lower >= min_distance:
                levels.append(bb_lower)
                level_sources.append("bb_lower")
        
        if direction == "short" and "upper" in bb_data:
            bb_upper = bb_data["upper"]
            if bb_upper - entry_price >= min_distance:
                levels.append(bb_upper)
                level_sources.append("bb_upper")
    
    # If no levels found, return None to use fallback
    if not levels:
        return None, "no_levels"
    
    # Find best level based on direction
    if direction == "long":
        # For longs, find highest support level below entry (closest to entry)
        best_level = max(levels)
        source = level_sources[levels.index(best_level)]
        
        # Add small buffer below level for safety
        adjusted_level = best_level * 0.998
        
        # Check if the stop is too far from entry (more than 2.5%)
        distance_pct = abs(adjusted_level - entry_price) / entry_price
        if distance_pct > 0.032:  # Cap at 2.5% maximum distance
            adjusted_level = entry_price * 0.968  # 2.5% below entry for longs
            source = f"{source}_capped"  # Note that capping was applied
    else:  # short
        # For shorts, find lowest resistance level above entry (closest to entry)
        best_level = min(levels)
        source = level_sources[levels.index(best_level)]
        
        # Add small buffer above level for safety
        adjusted_level = best_level * 1.002
        
        # Check if the stop is too far from entry (more than 2.5%)
        distance_pct = abs(adjusted_level - entry_price) / entry_price
        if distance_pct > 0.032:  # Cap at 2.5% maximum distance
            adjusted_level = entry_price * 1.032  # 2.5% above entry for shorts
            source = f"{source}_capped"  # Note that capping was applied
    
    # Ensure minimum distance from entry (1%)
    if direction == "long":
        min_distance = entry_price * 0.99  # 1% below entry
        if adjusted_level > min_distance:
            adjusted_level = min_distance
            source = f"{source}_min_distance"
    else:  # short
        min_distance = entry_price * 1.01  # 1% above entry
        if adjusted_level < min_distance:
            adjusted_level = min_distance
            source = f"{source}_min_distance"
            
    # Return the adjusted level and its source
    return adjusted_level, source

def find_nearest_technical_level(price: float, direction: str, market_context: Optional[object], buffer_pct: float = 0.2) -> Tuple[float, str]:
    """
    Find the nearest technical level (support/resistance, MA, BBands) to a given price
    in the specified direction (above for shorts, below for longs).
    
    Args:
        price: Base price to find technical level near
        direction: 'long' or 'short'
        market_context: Market context object with technical levels
        buffer_pct: Buffer percentage to apply to the found level
        
    Returns:
        Tuple of (adjusted_price, source_description)
    """
    if not market_context or not hasattr(market_context, 'context_data'):
        # No market context, return original price with small buffer
        buffer = 1 - (buffer_pct/100) if direction == "long" else 1 + (buffer_pct/100)
        return price * buffer, "default"
    
    # Extract technical levels from market context
    levels = []
    level_sources = []
    
    # Add support/resistance levels
    if "support_resistance" in market_context.context_data:
        sr_data = market_context.context_data["support_resistance"]
        
        if direction == "long" and "support_levels" in sr_data:
            for level in sr_data["support_levels"]:
                if level < price:  # Only include supports below price for longs
                    levels.append(level)
                    level_sources.append("support")
        
        if direction == "short" and "resistance_levels" in sr_data:
            for level in sr_data["resistance_levels"]:
                if level > price:  # Only include resistances above price for shorts
                    levels.append(level)
                    level_sources.append("resistance")
    
    # Add moving averages
    if "moving_averages" in market_context.context_data:
        ma_data = market_context.context_data["moving_averages"]
        for ma_name, ma_value in ma_data.items():
            if direction == "long" and ma_value < price:
                levels.append(ma_value)
                level_sources.append(ma_name)
            elif direction == "short" and ma_value > price:
                levels.append(ma_value)
                level_sources.append(ma_name)
    
    # Add Bollinger Bands
    if "volatility" in market_context.context_data and "bbands" in market_context.context_data["volatility"]:
        bb_data = market_context.context_data["volatility"]["bbands"]
        
        if direction == "long" and "lower" in bb_data:
            bb_lower = bb_data["lower"]
            if bb_lower < price:
                levels.append(bb_lower)
                level_sources.append("bb_lower")
        
        if direction == "short" and "upper" in bb_data:
            bb_upper = bb_data["upper"]
            if bb_upper > price:
                levels.append(bb_upper)
                level_sources.append("bb_upper")
    
    # If no levels found, return original price with buffer
    if not levels:
        buffer = 1 - (buffer_pct/100) if direction == "long" else 1 + (buffer_pct/100)
        return price * buffer, "default"
    
    # Find nearest level to the price in the correct direction
    if direction == "long":
        # For longs, find highest level below price (best entry)
        best_level = max(levels)
        source = level_sources[levels.index(best_level)]
        
        # Apply small buffer to ensure entry before level
        adjusted_level = best_level * (1 - buffer_pct/100)
    else:  # short
        # For shorts, find lowest level above price (best entry)
        best_level = min(levels)
        source = level_sources[levels.index(best_level)]
        
        # Apply small buffer to ensure entry before level
        adjusted_level = best_level * (1 + buffer_pct/100)
    
    return adjusted_level, source

def find_technical_take_profit(entry_price, cluster_range, direction, asset, current_price):
    """
    Find the nearest technical level within the liquidation cluster range to use as take-profit.
    
    Uses asymmetric constraints: up to 0.3% in less profitable direction and up to 1% in more profitable direction
    from the cluster boundary to find the most suitable technical level for take profit.
    
    Args:
        entry_price: The entry price of the trade
        cluster_range: Tuple/list of (min_price, max_price) for the cluster
        direction: 'long' or 'short'
        asset: Asset symbol
        current_price: Current market price
        
    Returns:
        Price level to use as take-profit
    """
    # Get technical levels from existing market_context module
    try:
        if get_market_context:
            context = get_market_context(asset, current_price)
        else:
            raise ImportError("get_market_context not available")
        
        if not context or not hasattr(context, 'key_levels'):
            raise ValueError("No valid market context or key levels available")
            
        # Get the cluster boundary based on direction
        if direction == "long":
            cluster_boundary = cluster_range[1]  # Upper boundary for longs
        else:  # short
            cluster_boundary = cluster_range[0]  # Lower boundary for shorts
        
        # Define asymmetric constraints (% of asset price)
        less_profit_max_pct = 0.003  # 0.3% in less profitable direction
        more_profit_max_pct = 0.01   # 1.0% in more profitable direction
        
        # Calculate actual price distances based on percentages
        less_profit_max_dist = cluster_boundary * less_profit_max_pct
        more_profit_max_dist = cluster_boundary * more_profit_max_pct
        
        if direction == "long":
            # For longs, more profitable is ABOVE the cluster boundary
            more_profitable_range = (cluster_boundary, cluster_boundary + more_profit_max_dist)
            less_profitable_range = (cluster_boundary - less_profit_max_dist, cluster_boundary)
            
            # Get all key levels (primarily S/R levels)
            key_levels = context.key_levels
            
            # First priority: Check for resistance in the more profitable direction
            more_profit_levels = [level for level in key_levels 
                               if more_profitable_range[0] < level <= more_profitable_range[1]]
            
            if more_profit_levels:
                # Find the closest level to the cluster boundary
                best_level = min(more_profit_levels, key=lambda x: abs(x - cluster_boundary))
                return best_level * 0.998  # Tiny adjustment to ensure fills
            
            # Second priority: Check for resistance in the less profitable direction
            less_profit_levels = [level for level in key_levels 
                               if less_profitable_range[0] <= level < less_profitable_range[1]]
            
            if less_profit_levels:
                # Find the closest level to the cluster boundary
                best_level = min(less_profit_levels, key=lambda x: abs(x - cluster_boundary))
                return best_level * 0.998  # Tiny adjustment to ensure fills
        else:  # short
            # For shorts, more profitable is BELOW the cluster boundary
            more_profitable_range = (cluster_boundary - more_profit_max_dist, cluster_boundary)
            less_profitable_range = (cluster_boundary, cluster_boundary + less_profit_max_dist)
            
            # Get all key levels (primarily S/R levels)
            key_levels = context.key_levels
            
            # First priority: Check for support in the more profitable direction
            more_profit_levels = [level for level in key_levels 
                               if more_profitable_range[0] <= level < more_profitable_range[1]]
            
            if more_profit_levels:
                # Find the closest level to the cluster boundary
                best_level = min(more_profit_levels, key=lambda x: abs(x - cluster_boundary))
                return best_level * 1.002  # Tiny adjustment to ensure fills
            
            # Second priority: Check for support in the less profitable direction
            less_profit_levels = [level for level in key_levels 
                               if less_profitable_range[0] < level <= less_profitable_range[1]]
            
            if less_profit_levels:
                # Find the closest level to the cluster boundary
                best_level = min(less_profit_levels, key=lambda x: abs(x - cluster_boundary))
                return best_level * 1.002  # Tiny adjustment to ensure fills
    except Exception as e:
        print(f"Error finding technical take profit: {e}")
        
        # Fall back to original method with technical levels (not using key_levels property)
        try:
            levels = []
            if direction == "long":
                # For longs, we want resistance levels above entry
                resistance_levels = context.context_data["support_resistance"].get("resistance_levels", [])
                levels.extend(resistance_levels)
                
                # Add EMAs and Bollinger bands if available
                if "moving_averages" in context.context_data:
                    ema_levels = [
                        context.context_data["moving_averages"].get("ema_50", current_price * 1.05),
                        context.context_data["moving_averages"].get("ema_100", current_price * 1.07),
                        context.context_data["moving_averages"].get("ema_200", current_price * 1.1)
                    ]
                    levels.extend([level for level in ema_levels if level > entry_price])
                    
                if "volatility" in context.context_data and "bbands" in context.context_data["volatility"]:
                    bb_upper = context.context_data["volatility"]["bbands"].get("upper", current_price * 1.03)
                    levels.append(bb_upper)
                
                # Find valid levels within cluster range
                valid_levels = [l for l in levels if entry_price < l < cluster_range[1]]
                if valid_levels:
                    return min(valid_levels) * 0.998  # Tiny adjustment to ensure fills
                
            else:  # short
                # For shorts, we want support levels below entry
                support_levels = context.context_data["support_resistance"].get("support_levels", [])
                levels.extend(support_levels)
                
                # Add EMAs and Bollinger bands if available
                if "moving_averages" in context.context_data:
                    ema_levels = [
                        context.context_data["moving_averages"].get("ema_50", current_price * 0.95),
                        context.context_data["moving_averages"].get("ema_100", current_price * 0.93),
                        context.context_data["moving_averages"].get("ema_200", current_price * 0.9)
                    ]
                    levels.extend([level for level in ema_levels if level < entry_price])
                    
                if "volatility" in context.context_data and "bbands" in context.context_data["volatility"]:
                    bb_lower = context.context_data["volatility"]["bbands"].get("lower", current_price * 0.97)
                    levels.append(bb_lower)
                
                # Find valid levels within cluster range
                valid_levels = [l for l in levels if cluster_range[0] < l < entry_price]
                if valid_levels:
                    return max(valid_levels) * 1.002  # Tiny adjustment to ensure fills
        except Exception as e:
            print(f"Secondary fallback for technical take profit failed: {e}")
    
    # Final fallback: 70% of the distance to the cluster boundary
    if direction == "long":
        tp_level = entry_price + (cluster_range[1] - entry_price) * 0.7
    else:
        tp_level = entry_price - (entry_price - cluster_range[0]) * 0.7
        
    # Apply maximum distance cap (4.5%)
    if direction == "long":
        max_distance = entry_price * 1.045  # 4.5% above entry
        if tp_level > max_distance:
            tp_level = max_distance
    else:  # short
        max_distance = entry_price * 0.955  # 4.5% below entry
        if tp_level < max_distance:
            tp_level = max_distance
            
    return tp_level

def create_range_from_target(target, direction, current_price, asset, market_context=None):
    """Convert a target dictionary to a trading range dictionary
    
    Args:
        target: Target dictionary with entry_price, take_profit, etc.
        direction: 'long' or 'short' 
        current_price: Current market price
        asset: Asset symbol
        market_context: Optional market context object for enhanced estimates
    
    Returns:
        Dict with trading range information
    """
    # Extract values from target with fallbacks
    entry_price = target.get("entry_price", current_price)
    take_profit = target.get("take_profit", 0)
    stop_loss = target.get("stop_loss", 0)
    
    # Calculate time estimates if market_context is provided
    # Initialize with reasonable defaults rather than None
    duration_estimates = {
        "tp_hours": 24.0,  # Default 24 hours for TP
        "sl_hours": 12.0,  # Default 12 hours for SL
        "tp_range": "12-36 hours",  # Reasonable fallback range
        "sl_range": "6-18 hours",    # Reasonable fallback range
        "confidence": 0.3  # Low confidence for default estimates
    }
    
    # Try new liquidation-based estimation first, then fallback to market context
    cluster_data = target.get("cluster_data")
    cascade_data = target.get("cascade_data")
    
    if cluster_data and cascade_data:
        # Use new liquidation-based estimation
        try:
            duration_estimates = estimate_liquidation_trade_duration_v2(
                cluster_data=cluster_data,
                cascade_data=cascade_data,
                entry_price=entry_price,
                target_price=take_profit,
                stop_price=stop_loss,
                direction=direction,
                asset=asset
            )
        except Exception as e:
            print(f"Liquidation duration estimation failed, using fallback: {e}")
            # Fallback to original method
            if market_context:
                duration_estimates = estimate_trade_duration(
                    entry_price=entry_price, 
                    target_price=take_profit, 
                    stop_price=stop_loss, 
                    direction=direction,
                    market_context=market_context,
                    asset=asset
                )
    elif market_context:
        # Use original market context method
        duration_estimates = estimate_trade_duration(
            entry_price=entry_price, 
            target_price=take_profit, 
            stop_price=stop_loss, 
            direction=direction,
            market_context=market_context,
            asset=asset
        )
    
    # Create the range object
    range_item = {
        "direction": direction,
        "entry": entry_price,  # Use the standardized key name
        "take_profit": take_profit,
        "stop_loss": stop_loss,
        "risk_reward": target.get("risk_reward", 0),
        "trigger_probability": target.get("trigger_probability", 0),
        "confidence": target.get("confidence", 0),
        "priority_score": target.get("priority_score", 0) if "priority_score" in target else 0,
        "rationale": target.get("rationale", "")
    }
    
    # Add time estimates if available - ensure keys match what estimate_trade_duration returns
    if duration_estimates:
        # Get values with fallbacks - matches the exact keys from estimate_trade_duration function
        range_item["tp_hours"] = duration_estimates.get("tp_hours", 24.0)
        range_item["sl_hours"] = duration_estimates.get("sl_hours", 12.0)
        range_item["tp_range"] = duration_estimates.get("tp_range", "12-36 hours")
        range_item["sl_range"] = duration_estimates.get("sl_range", "6-18 hours")
        # Use confidence field from duration_estimates directly rather than relying on a field rename
        range_item["duration_confidence"] = duration_estimates.get("confidence", 0.5)
    
    # Add additional properties if they exist
    for key in ["cascade_probability", "price_change", "priority_factors"]:
        if key in target:
            range_item[key] = target[key]
    
    return range_item

def generate_ta_price_targets(clusters, cascade_data, current_price, asset="UNKNOWN", debug=False):
    """
    Generate price targets based on liquidation clusters but with TA-based take-profit levels
    
    Args:
        clusters: Dict containing liquidation clusters
        cascade_data: Dict containing cascade probabilities
        current_price: Current price of the asset
        asset: Asset symbol
        debug: Enable debug output
        
    Returns:
        Dict containing price targets and trading ranges with TA-based take-profits
    """
    price_targets = {
        "asset": asset,
        "current_price": current_price,
        "timestamp": datetime.now().isoformat(),
        "long_targets": [],  # Targets for long positions (buy)
        "short_targets": [], # Targets for short positions (sell)
        "ranges": [],         # Combined ranges for both directions
        "recommendation": {},
        "is_ta_based": True   # Flag to identify this as TA-based
    }
    
    # Get market context if available
    market_context = None
    try:
        from market_context import get_market_context
        market_context = get_market_context(asset, current_price, debug)
        if debug:
            print(f"Market context loaded for {asset}")
    except Exception as e:
        if debug:
            print(f"Error loading market context: {e}")
    
    # Generate targets for long positions
    long_targets = generate_directional_targets(
        clusters.get("long_clusters", []),
        cascade_data.get("upward_cascade", {}),
        current_price,
        "long",
        market_context,
        debug
    )
    
    # Now modify the take-profit levels based on technical analysis
    for target in long_targets:
        # Extract original cluster range
        cluster = target.get("source_cluster", {})
        cluster_range = cluster.get("price_range", [target["entry_price"], target["take_profit"]])
        
        # Find technical take-profit level
        ta_take_profit = find_technical_take_profit(
            target["entry_price"],
            cluster_range,
            "long",
            asset,
            current_price
        )
        
        # Update target with TA-based take-profit
        target["original_take_profit"] = target["take_profit"]  # Save original
        target["take_profit"] = ta_take_profit
        target["is_ta_based"] = True
        
        # Recalculate risk/reward
        sl_distance = abs(target["entry_price"] - target["stop_loss"])
        tp_distance = abs(target["take_profit"] - target["entry_price"])
        target["risk_reward"] = tp_distance / sl_distance if sl_distance > 0 else 0
        
        # Add explanation about TA level
        target["rationale"] += " [Using TA-based take-profit]"
    
    price_targets["long_targets"] = long_targets
    
    # Generate targets for short positions
    short_targets = generate_directional_targets(
        clusters.get("short_clusters", []),
        cascade_data.get("downward_cascade", {}),
        current_price,
        "short",
        market_context,
        debug
    )
    
    # Now modify the take-profit levels based on technical analysis
    for target in short_targets:
        # Extract original cluster range
        cluster = target.get("source_cluster", {})
        cluster_range = cluster.get("price_range", [target["take_profit"], target["entry_price"]])
        
        # Find technical take-profit level
        ta_take_profit = find_technical_take_profit(
            target["entry_price"],
            cluster_range,
            "short",
            asset,
            current_price
        )
        
        # Update target with TA-based take-profit
        target["original_take_profit"] = target["take_profit"]  # Save original
        target["take_profit"] = ta_take_profit
        target["is_ta_based"] = True
        
        # Recalculate risk/reward
        sl_distance = abs(target["entry_price"] - target["stop_loss"])
        tp_distance = abs(target["take_profit"] - target["entry_price"])
        target["risk_reward"] = tp_distance / sl_distance if sl_distance > 0 else 0
        
        # Add explanation about TA level
        target["rationale"] += " [Using TA-based take-profit]"
    
    price_targets["short_targets"] = short_targets
    
    # Generate combined trading ranges with both types of targets
    try:
        # Import happens inside function to avoid circular imports
        from market_context import get_market_context
        HAS_MARKET_CONTEXT = True
    except ImportError:
        HAS_MARKET_CONTEXT = False
    
    # Generate trading ranges from the targets
    ranges = []
    
    # Get market bias from market context to determine primary direction
    market_bias = "neutral"
    if market_context and hasattr(market_context, 'context_data'):
        market_bias = market_context.context_data.get("market_bias", {}).get("bias", "neutral")
    
    # First prioritize the dominant direction from cascade analysis (for neutral fallback)
    dominant_direction = cascade_data.get("dominant_direction", "neutral")
    
    # For neutral conditions, just use the most promising target from either direction
    if dominant_direction == "neutral" or cascade_data.get("overall_probability", 0) < 0.2:
        # Combine and sort all targets
        all_targets = []
        for target in long_targets:
            all_targets.append(("long", target))
        for target in short_targets:
            all_targets.append(("short", target))
            
        # Sort by probability and quality scores
        all_targets.sort(key=lambda x: x[1].get("trigger_probability", 0) * x[1].get("confidence", 0.1), reverse=True)
        
        # Take top targets from each direction (up to 2 each)
        used_directions = set()
        for direction, target in all_targets:
            if direction not in used_directions and len(ranges) < 4:
                # Create range from this target with market context for duration estimates
                range_data = create_range_from_target(target, direction, current_price, asset, market_context)
                
                # Add to ranges
                ranges.append(range_data)
                used_directions.add(direction)
                
            # Ensure we get at least one of each direction if available
            if len(used_directions) == 2 and len(ranges) >= 2:
                break
    else:
        # Prioritize based on market bias for with-trend ranging signals
        if market_bias == "BULLISH":
            # Bull market: prioritize LONG signals (with trend)
            primary_targets = long_targets
            primary_direction = "long"
            secondary_targets = short_targets
            secondary_direction = "short"
        elif market_bias == "BEARISH":
            # Bear market: prioritize SHORT signals (with trend)
            primary_targets = short_targets
            primary_direction = "short"
            secondary_targets = long_targets
            secondary_direction = "long"
        else:
            # Neutral bias: use cascade direction as fallback
            primary_targets = long_targets if dominant_direction == "long" else short_targets
            secondary_targets = short_targets if dominant_direction == "long" else long_targets
            primary_direction = dominant_direction
            secondary_direction = "short" if primary_direction == "long" else "long"
        
        # Take top targets from primary direction (up to 3)
        for i, target in enumerate(primary_targets[:3]):
            # Get market context for this asset if available
            ctx = None
            if HAS_MARKET_CONTEXT:
                try:
                    ctx = get_market_context(asset, current_price)
                except Exception as e:
                    print(f"Warning: Failed to get market context: {e}")
            range_item = create_range_from_target(target, primary_direction, current_price, asset, ctx)
            range_item["is_ta_based"] = True
            ranges.append(range_item)
        
        # Take top target from secondary direction (just 1)
        if secondary_targets:
            # Get market context for this asset if available
            ctx = None
            if HAS_MARKET_CONTEXT:
                try:
                    ctx = get_market_context(asset, current_price)
                except Exception as e:
                    print(f"Warning: Failed to get market context: {e}")
            range_item = create_range_from_target(secondary_targets[0], secondary_direction, current_price, asset, ctx)
            range_item["is_ta_based"] = True
            ranges.append(range_item)
    
    # Calculate priority score for each range using market context if available
    for range_item in ranges:
        # Get market context if available, otherwise pass None
        ctx = None
        if HAS_MARKET_CONTEXT:
            try:
                asset = range_item.get("asset", "BTC")
                ctx = get_market_context(asset, current_price)
            except Exception as e:
                print(f"Warning: Failed to get market context: {e}")
        
        range_item["priority_score"] = calculate_trade_priority(range_item, ctx)
    
    # Sort ranges by priority score
    ranges.sort(key=lambda x: x.get("priority_score", 0), reverse=True)
    
    # Make sure we always have at least one range in each direction
    has_long = any(r.get('direction') == 'long' for r in ranges)
    has_short = any(r.get('direction') == 'short' for r in ranges)
    
    # Create fallback ranges if needed
    if not has_long and long_targets:
        best_long = max(long_targets, key=lambda x: x.get("risk_reward", 0) * 0.7 + x.get("trigger_probability", 0.1) * 0.3)
        # Get market context for this asset if available
        ctx = None
        if HAS_MARKET_CONTEXT:
            try:
                ctx = get_market_context(asset, current_price)
            except Exception as e:
                print(f"Warning: Failed to get market context: {e}")
        range_item = create_range_from_target(best_long, "long", current_price, asset, ctx)
        range_item["is_ta_based"] = True
        ranges.append(range_item)
    
    if not has_short and short_targets:
        best_short = max(short_targets, key=lambda x: x.get("risk_reward", 0) * 0.7 + x.get("trigger_probability", 0.1) * 0.3)
        # Get market context for this asset if available
        ctx = None
        if HAS_MARKET_CONTEXT:
            try:
                ctx = get_market_context(asset, current_price)
            except Exception as e:
                print(f"Warning: Failed to get market context: {e}")
        range_item = create_range_from_target(best_short, "short", current_price, asset, ctx)
        range_item["is_ta_based"] = True
        ranges.append(range_item)
    
    # Add ranges to the output
    price_targets["ranges"] = ranges
    
    # Generate recommendations summary
    if ranges:
        # Get dominant direction and probability
        dominant_direction = "neutral"
        if len(long_targets) > len(short_targets):
            dominant_direction = "long"
            probability = cascade_data.get("long_cascade", {}).get("probability", 0.1)
        else:
            dominant_direction = "short"
            probability = cascade_data.get("short_cascade", {}).get("probability", 0.1)
        
        # Create recommendation - note this returns a string
        recommendation_text = generate_recommendation_summary(dominant_direction, probability, "medium", current_price, ranges)
        
        # Create a dictionary with the text and additional metadata
        recommendation = {
            "summary": recommendation_text,
            "is_ta_based": True,
            "direction": dominant_direction,
            "probability": probability
        }
        price_targets["recommendation"] = recommendation
    
    return price_targets


def generate_price_targets(clusters, cascade_data, current_price, asset="UNKNOWN", debug=False):
    """
    Generate price targets based on liquidation clusters and cascade probabilities
    
    Args:
        clusters: Dict containing liquidation clusters
        cascade_data: Dict containing cascade probabilities
        current_price: Current price of the asset
        asset: Asset symbol
        debug: Enable debug output
        
    Returns:
        Dict containing price targets and trading ranges
    """
    price_targets = {
        "asset": asset,
        "current_price": current_price,
        "timestamp": datetime.now().isoformat(),
        "long_targets": [],  # Targets for long positions (buy)
        "short_targets": [], # Targets for short positions (sell)
        "ranges": [],         # Combined ranges for both directions
        "recommendation": {}
    }
    
    # Get market context if available
    market_context = None
    if get_market_context:
        try:
            market_context = get_market_context(asset, current_price, debug)
            if debug:
                print(f"Market context loaded for {asset}")
        except Exception as e:
            if debug:
                print(f"Error loading market context: {e}")
            market_context = None
    
    # Get essential data from cascade analysis
    long_cascade = cascade_data.get("long_cascade", {})
    short_cascade = cascade_data.get("short_cascade", {})
    dominant_direction = cascade_data.get("dominant_direction", "neutral")
    
    # Extract clusters for processing
    long_clusters = clusters.get("long_clusters", [])
    short_clusters = clusters.get("short_clusters", [])
    
    # Generate long targets based on short liquidations (price going up)
    long_targets = generate_directional_targets(
        short_clusters,
        short_cascade,
        current_price,
        "long",
        market_context,
        asset,
        debug
    )
    
    # Generate short targets based on long liquidations (price going down)
    short_targets = generate_directional_targets(
        long_clusters,
        long_cascade,
        current_price,
        "short",
        market_context,
        asset,
        debug
    )
    
    # Add targets to price targets
    price_targets["long_targets"] = long_targets
    price_targets["short_targets"] = short_targets
    
    # Generate combined ranges with entry, stop-loss, and take-profit levels
    price_targets["ranges"] = generate_trading_ranges(
        long_targets, 
        short_targets, 
        cascade_data,
        current_price
    )
    
    # Add overall recommendation
    price_targets["recommendation"] = {
        "primary_direction": dominant_direction,
        "conviction": cascade_data.get("overall_probability", 0),
        "risk_level": cascade_data.get("risk_level", "UNKNOWN"),
        "summary": generate_recommendation_summary(
            dominant_direction, 
            cascade_data.get("overall_probability", 0),
            cascade_data.get("risk_level", "UNKNOWN"),
            current_price,
            price_targets["ranges"]
        )
    }
    
    # Add summary data to the price targets
    price_targets["summary"] = {
        "long_count": len(long_targets),
        "short_count": len(short_targets),
        "dominant_direction": dominant_direction,
        "long_average_probability": sum([t.get("trigger_probability", 0) for t in long_targets]) / len(long_targets) if long_targets else 0,
        "short_average_probability": sum([t.get("trigger_probability", 0) for t in short_targets]) / len(short_targets) if short_targets else 0,
        "long_average_risk_reward": sum([t.get("risk_reward", 0) for t in long_targets]) / len(long_targets) if long_targets else 0,
        "short_average_risk_reward": sum([t.get("risk_reward", 0) for t in short_targets]) / len(short_targets) if short_targets else 0,
        "long_average_confidence": sum([t.get("confidence", 0) for t in long_targets]) / len(long_targets) if long_targets else 0,
        "short_average_confidence": sum([t.get("confidence", 0) for t in short_targets]) / len(short_targets) if short_targets else 0
    }
    
    # Add enhanced summary if market context is available
    if market_context and hasattr(market_context, 'generate_enhanced_summary'):
        try:
            price_targets["enhanced_summary"] = market_context.generate_enhanced_summary(
                clusters, cascade_data, price_targets)
        except Exception as e:
            if debug:
                print(f"Error generating enhanced summary: {e}")
    
    return price_targets

def generate_directional_targets(clusters, cascade_data, current_price, target_direction, market_context=None, asset="UNKNOWN", debug=False):
    """
    Generate price targets for a specific direction
    
    Args:
        clusters: List of liquidation clusters
        cascade_data: Cascade probability data for this direction
        current_price: Current market price
        target_direction: Direction to generate targets for ('long' or 'short')
        market_context: Optional market context object for dynamic probability calculation
        
    Returns:
        List of price targets with rationales
    """
    if not clusters:
        return []
    
    # Validate the clusters - if any price values are extremely far from current price, they might be invalid
    validated_clusters = []
    for cluster in clusters:
        center_price = cluster.get("center_price", 0)
        # Exclude clusters with price levels more than 10% from current price
        if 0.9 * current_price <= center_price <= 1.1 * current_price:
            validated_clusters.append(cluster)
    
    if not validated_clusters:
        # Return a conservative default target with slightly randomized values
        # to avoid all targets having identical probabilities
        rand_factor = random.uniform(0.95, 1.05)
        base_prob = random.uniform(0.4, 0.6)  # Randomize the base probability
        risk_reward = random.uniform(2.3, 2.7)  # Slightly randomize risk/reward
        
        if target_direction == "long":
            return [{
                "entry_price": current_price * (0.99 * rand_factor),
                "target_price": current_price * (1.03 * rand_factor),
                "take_profit": current_price * (1.05 * rand_factor),
                "stop_loss": current_price * (0.97 * rand_factor),
                "size": 0,
                "trigger_probability": base_prob,
                "confidence": base_prob * 0.8,  # Lower confidence for default targets
                "risk_reward": risk_reward,
                "rationale": f"Default target due to no valid clusters found"
            }]
        else:  # short
            return [{
                "entry_price": current_price * (1.01 * rand_factor),
                "target_price": current_price * (0.97 * rand_factor),
                "take_profit": current_price * (0.95 * rand_factor),
                "stop_loss": current_price * (1.03 * rand_factor),
                "size": 0,
                "trigger_probability": base_prob,
                "confidence": base_prob * 0.8,  # Lower confidence for default targets
                "risk_reward": risk_reward,
                "rationale": f"Default target due to no valid clusters found"
            }]
    
    # Sort clusters by quality rather than just size
    # Consider distance, size, and probability together
    def cluster_quality(cluster):
        size_factor = math.log1p(cluster.get("total_size", 0) / 100) / 5  # Size factor 
        distance_factor = 1 / (abs(cluster.get("center_price", 0) - current_price) / current_price + 0.1)
        return size_factor * distance_factor * cluster.get("trigger_probability", 0.5)
    
    sorted_clusters = sorted(validated_clusters, key=cluster_quality, reverse=True)
    
    targets = []
    for i, cluster in enumerate(sorted_clusters[:3]):  # Take top 3 clusters
        price_level = cluster.get("center_price", 0)
        original_probability = cluster.get("trigger_probability", 0.5)
        size = cluster.get("total_size", 0)
        
        # First, calculate entry, take profit, and stop loss prices
        # This ensures these variables are defined before the try-except block
        entry_price = 0
        take_profit = 0
        stop_loss = 0
        risk_reward = 0
        
        # Calculate based on direction and cluster price range
        cluster_price_range = cluster.get("price_range", [])
        
        if target_direction == "long":
            if len(cluster_price_range) >= 2:
                # For long positions: entry near start of cluster, take profit at end of cluster
                # For shorts, we target the upward price movement, so we use the cluster's price range
                cluster_start = min(cluster_price_range)  # Lower price boundary
                cluster_end = max(cluster_price_range)    # Upper price boundary
                
                # Entry just slightly below the cluster start (0.1% below)
                entry_price = cluster_start * 0.999
                
                # Use dynamic stop loss based on volatility if available
                # Try to get asset volatility from market context
                asset_volatility = None
                if market_context and hasattr(market_context, 'get_volatility'):
                    try:
                        asset_volatility = market_context.get_volatility()
                    except:
                        pass
                
                # Calculate dynamic stop loss
                stop_loss = calculate_dynamic_stop_loss(entry_price, "long", asset_volatility)
                
                # Enforce minimum 1.5% stop loss distance
                min_stop = entry_price * 0.985  # 1.5% below entry
                if stop_loss > min_stop:  # If stop is too close to entry
                    stop_loss = min_stop
                
                # Take profit at the end of the cluster
                # This is a more realistic target based on actual liquidation boundaries
                take_profit = cluster_end
                
                if debug:
                    print(f"Long position using cluster range: {cluster_start:.2f} - {cluster_end:.2f}")
            else:
                # Fallback if no price range available
                entry_price = price_level * 0.995  # Slightly below the liquidation level
                stop_loss = entry_price * 0.985    # Exactly 1.5% below entry price
                
                # Try to find a more conservative take-profit target using market context
                if market_context and hasattr(market_context, "get_next_resistance"):
                    try:
                        take_profit = market_context.get_next_resistance(current_price)
                    except:
                        # More conservative 2-3% target instead of the previous 2:1 multiplier
                        price_diff_pct = abs(price_level - current_price) / current_price
                        take_profit = entry_price * (1 + min(0.03, price_diff_pct * 1.5))
                else:
                    # More conservative 2-3% target instead of the previous 2:1 multiplier
                    price_diff_pct = abs(price_level - current_price) / current_price
                    take_profit = entry_price * (1 + min(0.03, price_diff_pct * 1.5))
        else:  # short
            if len(cluster_price_range) >= 2:
                # For short positions: entry near start of cluster, take profit at end of cluster
                # For longs, we target the downward price movement, so we use the cluster's price range
                cluster_start = max(cluster_price_range)  # Upper price boundary
                cluster_end = min(cluster_price_range)    # Lower price boundary
                
                # Entry just slightly above the cluster start (0.1% above)
                entry_price = cluster_start * 1.001
                
                # Use dynamic stop loss based on volatility if available
                # Try to get asset volatility from market context
                asset_volatility = None
                if market_context and hasattr(market_context, 'get_volatility'):
                    try:
                        asset_volatility = market_context.get_volatility()
                    except:
                        pass
                
                # Calculate dynamic stop loss
                stop_loss = calculate_dynamic_stop_loss(entry_price, "short", asset_volatility)
                
                # Enforce minimum 1.5% stop loss distance
                min_stop = entry_price * 1.015  # 1.5% above entry
                if stop_loss < min_stop:  # If stop is too close to entry
                    stop_loss = min_stop
                
                # Take profit at the end of the cluster
                # This is a more realistic target based on actual liquidation boundaries
                take_profit = cluster_end
                
                if debug:
                    print(f"Short position using cluster range: {cluster_start:.2f} - {cluster_end:.2f}")
            else:
                # Fallback if no price range available
                entry_price = price_level * 1.005  # Slightly above the liquidation level 
                stop_loss = entry_price * 1.015    # Exactly 1.5% above entry price
                
                # Try to find a more conservative take-profit target using market context
                if market_context and hasattr(market_context, "get_next_support"):
                    try:
                        take_profit = market_context.get_next_support(current_price)
                    except:
                        # More conservative 2-3% target instead of the previous 2:1 multiplier
                        price_diff_pct = abs(price_level - current_price) / current_price
                        take_profit = entry_price * (1 - min(0.03, price_diff_pct * 1.5))
                else:
                    # More conservative 2-3% target instead of the previous 2:1 multiplier
                    price_diff_pct = abs(price_level - current_price) / current_price
                    take_profit = entry_price * (1 - min(0.03, price_diff_pct * 1.5))
        
        # Calculate risk/reward ratio
        if target_direction == "long" and entry_price > 0 and take_profit > entry_price and stop_loss < entry_price:
            risk = entry_price - stop_loss
            reward = take_profit - entry_price
            if risk > 0:  # Avoid division by zero
                risk_reward = reward / risk
        elif target_direction == "short" and entry_price > 0 and take_profit < entry_price and stop_loss > entry_price:
            risk = stop_loss - entry_price
            reward = entry_price - take_profit
            if risk > 0:  # Avoid division by zero
                risk_reward = reward / risk
                
        # Use market context for dynamic probability calculation if available
        if market_context and hasattr(market_context, 'calculate_dynamic_probability'):
            try:
                
                # Get the dynamically calculated probability and confidence
                prob_data = market_context.calculate_dynamic_probability(
                    cluster, current_price, target_direction)
                
                # Get the dynamically calculated probability and confidence
                trigger_probability = prob_data["adjusted_probability"]
                confidence = prob_data["confidence_score"]
                
                # Get the calculation factors for insights
                factors = prob_data.get("factors", {})
                
                # Add cluster rank effect - decrease probability for less important clusters
                # Use an exponential rather than linear decay for more variability
                rank_decay = math.exp(-i * 0.7) * 0.4 + 0.6  # First cluster unchanged, others decaying
                trigger_probability *= rank_decay
                
                # Adjust confidence for rank too, but less severely
                rank_confidence_decay = math.exp(-i * 0.5) * 0.3 + 0.7
                confidence *= rank_confidence_decay
                
                # Add distance penalty - exponential scaling with cap at 40% reduction
                entry_distance_pct = abs(entry_price - current_price) / current_price
                distance_penalty = 1.0  # Default: no penalty
                
                if entry_distance_pct <= 0.01:      # 0-1%: tiny penalty
                    distance_penalty = 0.98
                elif entry_distance_pct <= 0.02:    # 1-2%: small penalty
                    distance_penalty = 0.95
                elif entry_distance_pct <= 0.03:    # 2-3%: mild penalty
                    distance_penalty = 0.92
                elif entry_distance_pct <= 0.04:    # 3-4%: moderate penalty (acceleration starts)
                    distance_penalty = 0.85
                elif entry_distance_pct <= 0.05:    # 4-5%: significant penalty
                    distance_penalty = 0.75
                else:                              # 6%+: severe penalty (capped)
                    distance_penalty = 0.60        # 40% reduction cap
                
                # Apply distance penalty to both probability and confidence
                trigger_probability *= distance_penalty
                confidence *= distance_penalty
                
                # Add some jitter to avoid repeating values (more for lower ranks)
                jitter_range = 0.05 + (i * 0.02)  # 5% for top cluster, more for others
                trigger_probability = max(0.01, min(0.8, 
                    trigger_probability * random.uniform(1 - jitter_range, 1 + jitter_range)))
                confidence = max(0.01, min(0.8,
                    confidence * random.uniform(1 - jitter_range, 1 + jitter_range)))
                
                # Adjust probability based on price momentum if market context provides historical price data
                price_1h_ago = None
                if market_context and hasattr(market_context, 'get_historical_price'):
                    try:
                        price_1h_ago = market_context.get_historical_price(hours=1)
                        # Apply momentum adjustment
                        if price_1h_ago:
                            trigger_probability = adjust_probability_for_momentum(
                                trigger_probability, target_direction, current_price, price_1h_ago)
                    except Exception as e:
                        if debug:
                            print(f"Error getting historical price: {e}")
                
                # Generate detailed factors-based rationale for this target
                detailed_factors = {}
                
                # 1. Cluster information
                cluster_size = f"{size:.0f}"
                position_count = cluster.get("position_count", 0)
                distance_pct = abs(price_level - current_price) / current_price * 100
                detailed_factors["cluster"] = f"Liquidation cluster with {cluster_size} {asset} (${size*current_price/1000:.1f}K) across {position_count} positions at ${price_level:.2f} ({distance_pct:.1f}% from current)"
                
                # 2. Price level significance
                if market_context and hasattr(market_context, "get_level_description"):
                    try:
                        level_desc = market_context.get_level_description(price_level, target_direction)
                        detailed_factors["level"] = level_desc
                    except Exception as e:
                        if debug:
                            print(f"Error generating level description: {e}")
                        detailed_factors["level"] = f"Price zone at ${price_level:.2f}"
                else:
                    detailed_factors["level"] = f"Key level at ${price_level:.2f}"
                    
                # 3. Technical context if available
                if market_context:
                    try:
                        # Market trend direction
                        if hasattr(market_context, "trend_direction"):
                            trend = market_context.trend_direction
                            trend_strength = getattr(market_context, "trend_strength", 0.5)
                            trend_desc = f"{trend.capitalize()} trend"  
                            if trend_strength > 0.7:
                                trend_desc = f"Strong {trend_desc}"
                            elif trend_strength < 0.3:
                                trend_desc = f"Weak {trend_desc}"
                            detailed_factors["trend"] = trend_desc
                        
                        # Volatility
                        if hasattr(market_context, "volatility"):
                            vol = market_context.volatility
                            vol_desc = "Average volatility"
                            if vol > 0.7:
                                vol_desc = "High volatility"
                            elif vol < 0.3:
                                vol_desc = "Low volatility"
                            detailed_factors["volatility"] = vol_desc
                        
                        # Support/resistance
                        if hasattr(market_context, "key_levels"):
                            closest_level = None
                            min_distance = float('inf')
                            for level in market_context.key_levels:
                                dist = abs(level - price_level)
                                if dist < min_distance:
                                    min_distance = dist
                                    closest_level = level
                            
                            if closest_level and min_distance/price_level < 0.02:  # Within 2%
                                level_type = "Support" if closest_level < current_price else "Resistance"
                                detailed_factors["key_level"] = f"{level_type} at ${closest_level:.2f}"
                    except Exception as e:
                        if debug:
                            print(f"Error accessing market context data: {e}")
                
                # 4. Risk/reward and probabilities
                prob_desc = "Low probability"
                if trigger_probability > 0.6:
                    prob_desc = "High probability"
                elif trigger_probability > 0.3:                    prob_desc = "Moderate probability"
                    
                conf_desc = "Low confidence"
                if confidence > 0.8:
                    conf_desc = "Very high confidence"
                elif confidence > 0.6:
                    conf_desc = "High confidence"
                elif confidence > 0.3:
                    conf_desc = "Moderate confidence"
                    
                risk_reward_desc = f"Risk/reward ratio: {risk_reward:.2f}"
                
                # Build detailed rationale with all factors
                trade_direction = "Long" if target_direction == "long" else "Short"
                action = "Buy" if target_direction == "long" else "Sell"
                
                # Compile detailed rationale
                rationale = f"{trade_direction} Opportunity: {action} at ${entry_price:.2f}. "
                
                # Add primary factors
                rationale += detailed_factors.get("cluster", "") + ". "
                
                if "level" in detailed_factors:
                    rationale += detailed_factors.get("level") + ". "
                    
                if "key_level" in detailed_factors:
                    rationale += detailed_factors.get("key_level") + ". "
                    
                if "trend" in detailed_factors:
                    rationale += detailed_factors.get("trend") + ". "
                
                # Add secondary factors in a new sentence
                rationale += f"{prob_desc} event ({trigger_probability:.2f}) with {conf_desc} ({confidence:.2f}). {risk_reward_desc}."
                
                # Add a conclusion summarizing trade quality
                signal_strength = (trigger_probability * 0.5) + (confidence * 0.3) + (min(risk_reward, 5) / 5 * 0.2)
                
                if signal_strength > 0.7:
                    conclusion = "Strong signal with favorable risk/reward. Consider standard position size."
                elif signal_strength > 0.4:
                    conclusion = "Moderate signal quality. Consider reduced position size and tight risk management."
                else:
                    conclusion = "Speculative opportunity. Consider minimal position size or wait for confirmation."
                    
                rationale += f" {conclusion}"
                
            except Exception as e:
                # Fallback to simpler calculation if dynamic fails
                if debug:
                    print(f"Error in dynamic probability calculation: {e}")
                    
                # We already defined risk_reward above, no need to recalculate it here
                                
                # Use a more sophisticated fallback calculation
                distance_pct = abs(price_level - current_price) / current_price * 100
                
                # More aggressive exponential decay with random variance
                decay_rate = 15 + random.uniform(-2, 2)  # Variance in decay rate
                distance_factor = math.exp(-distance_pct / decay_rate)
                
                # Size factor with non-linear scaling and randomization
                size_scaling = random.uniform(800, 1200)  # Random scaling factor
                size_factor = min(0.6, math.log1p(size / size_scaling) / 4)
                
                # Position count factor - more positions = higher probability
                pos_count = cluster.get("position_count", 1)
                pos_factor = min(0.3, math.log1p(pos_count) / 10)
                
                # Combine with rank weighting
                rank_weight = math.exp(-i * 0.5) * 0.4 + 0.6  # Exponential decay by rank
                base_prob = ((distance_factor * 0.6) + (size_factor * 0.3) + (pos_factor * 0.1)) * rank_weight
                
                # Apply sigmoid transformation for more variation in mid-range values
                def sigmoid(x, steepness=5, midpoint=0.3):
                    return 1 / (1 + math.exp(-steepness * (x - midpoint)))
                    
                # Blend direct calculation with sigmoid for more natural distribution
                sigmoid_prob = sigmoid(base_prob) * 0.7  # Cap sigmoid at 0.7
                trigger_probability = (base_prob * 0.6) + (sigmoid_prob * 0.4)
                
                # Ensure reasonable bounds with randomization
                trigger_probability = max(0.05, min(0.7, 
                    trigger_probability * random.uniform(0.9, 1.1)))
                
                # Confidence follows a different curve - higher for very low or high probabilities
                confidence_base = 0.3 + (0.4 * abs(trigger_probability - 0.5) * 2)
                confidence = max(0.1, min(0.97, confidence_base * random.uniform(0.85, 1.15)))
        else:
            # Without market context, use a more sophisticated approach than before
            # Calculate distance-based probability with multi-factor formula
            distance_pct = abs(price_level - current_price) / current_price * 100
            
            # Steeper decay for more realistic probabilities
            distance_factor = math.exp(-distance_pct / (8 - i))  # Rank-dependent decay rate
            
            # Hard cap based on distance
            if distance_pct > 10:
                distance_cap = 0.1
            elif distance_pct > 5:
                distance_cap = 0.25
            elif distance_pct > 2:
                distance_cap = 0.4
            else:
                distance_cap = 0.97
                
            distance_factor = min(distance_factor, distance_cap)
            
            # Size factor with random scaling
            size_factor = min(0.5, math.log1p(size / random.uniform(900, 1100)) / 4)
            
            # Position count factor
            pos_count = cluster.get("position_count", 1)
            pos_factor = min(0.3, math.log1p(pos_count) / 8)
            
            # Random factor for natural variation
            random_factor = random.uniform(-0.05, 0.05)
            
            # Combine with non-linear weighting
            base_prob = (distance_factor * 0.6) + (size_factor * 0.25) + \
                       (pos_factor * 0.1) + random_factor
            
            # Apply sigmoid transformation
            def sigmoid(x, steepness=6, midpoint=0.3):
                return 1 / (1 + math.exp(-steepness * (x - midpoint)))
                
            sigmoid_prob = sigmoid(base_prob) * 0.65
            
            # Blend for final probability
            trigger_probability = (base_prob * 0.6) + (sigmoid_prob * 0.4)
            
            # Rank-based adjustment
            rank_adjustment = math.exp(-i * 0.6) * 0.3 + 0.7
            trigger_probability *= rank_adjustment
            
            # Ensure bounds
            trigger_probability = max(0.05, min(0.65, trigger_probability))
            
            # Confidence calculation - partially independent of probability
            # Higher for extreme probabilities (very low or high)
            confidence_base = 0.25 + (0.3 * (1 - math.exp(-(trigger_probability - 0.5) * (trigger_probability - 0.5) / 0.05)))
            
            # Add factors based on cluster properties
            conf_size_factor = min(0.2, math.log1p(size / 1500) / 6)
            conf_pos_factor = min(0.15, math.log1p(pos_count) / 10)
            
            # Combine confidence factors
            confidence = confidence_base + conf_size_factor + conf_pos_factor
            
            # Add rank-based variation and randomness
            confidence *= math.exp(-i * 0.4) * 0.25 + 0.75  # Less severe decay for confidence
            confidence = max(0.1, min(0.97, confidence * random.uniform(0.9, 1.1)))
        
        # Calculate entry and target prices with dynamic factors
        if target_direction == "long":
            # For long positions, we need to determine appropriate entry below current price
            volatility_factor = 0.01  # Default 1% buffer
            if market_context and hasattr(market_context, 'context_data'):
                volatility_factor = market_context.context_data["volatility"]["atr_percent"] / 2
                # Ensure reasonable range
                volatility_factor = max(0.002, min(0.03, volatility_factor))
            
            # Try to use cluster edge if available, otherwise use current price
            if len(cluster_price_range) >= 2:
                # For long positions: use cluster start as base price
                cluster_start = min(cluster_price_range)  # Lower price boundary
                base_price = cluster_start
            else:
                # Fallback to current price with buffer
                entry_buffer = min(0.5, max(0.2, volatility_factor * 50))
                base_price = current_price * (1 - entry_buffer / 100)
            
            # Find nearest technical level near the base price
            entry_price, level_source = find_nearest_technical_level(base_price, "long", market_context, 0.2)
            
            # Calculate target based on liquidation level and expected impact
            price_impact = min(5.0, cascade_data.get("expected_price_impact", 1))  # Get from cascade data
            if price_impact < 0.5:  # If impact is very small, use a minimum sensible value
                price_impact = random.uniform(1.0, 2.0)
                
            # Calculate take-profit with dynamic impact factor
            take_profit = current_price * (1 + price_impact / 100)
            
            # First try to find technical level for stop-loss
            tech_stop, level_source = find_technical_stop_loss(entry_price, "long", market_context)
            
            if tech_stop is not None:
                # Use technical level with small safety buffer
                stop_loss = tech_stop
            else:
                # Fallback to volatility-based stop-loss
                stop_buffer = max(0.5, min(2.0, volatility_factor * 150))  # 1.5x volatility factor
                stop_loss = entry_price * (1 - stop_buffer / 100)
            
        else:  # Short target
            # For short positions, determine appropriate entry above current price
            volatility_factor = 0.01  # Default 1% buffer
            if market_context and hasattr(market_context, 'context_data'):
                volatility_factor = market_context.context_data["volatility"]["atr_percent"] / 2
                # Ensure reasonable range
                volatility_factor = max(0.002, min(0.03, volatility_factor))
            
            # Try to use cluster edge if available, otherwise use current price
            if len(cluster_price_range) >= 2:
                # For short positions: use cluster start as base price
                cluster_start = max(cluster_price_range)  # Upper price boundary
                base_price = cluster_start
            else:
                # Fallback to current price with buffer
                entry_buffer = min(0.5, max(0.2, volatility_factor * 50))
                base_price = current_price * (1 + entry_buffer / 100)
            
            # Find nearest technical level near the base price
            entry_price, level_source = find_nearest_technical_level(base_price, "short", market_context, 0.2)
            
            # Calculate target based on liquidation level and expected impact
            price_impact = min(5.0, cascade_data.get("expected_price_impact", 1))  # Get from cascade data
            if price_impact < 0.5:  # If impact is very small, use a minimum sensible value
                price_impact = random.uniform(1.0, 2.0)
                
            # Calculate take-profit with dynamic impact factor
            take_profit = current_price * (1 - price_impact / 100)
            
            # First try to find technical level for stop-loss
            tech_stop, level_source = find_technical_stop_loss(entry_price, "short", market_context)
            
            if tech_stop is not None:
                # Use technical level with small safety buffer
                stop_loss = tech_stop
            else:
                # Fallback to volatility-based stop-loss
                stop_buffer = max(0.5, min(2.0, volatility_factor * 150))  # 1.5x volatility factor
                stop_loss = entry_price * (1 + stop_buffer / 100)
        
        # Calculate risk-reward ratio
        if entry_price != stop_loss:
            if target_direction == "long":
                risk = abs(entry_price - stop_loss)
                reward = abs(take_profit - entry_price)
            else:  # short
                risk = abs(stop_loss - entry_price)
                reward = abs(entry_price - take_profit)
            risk_reward = reward / risk if risk > 0 else 1.0
        else:
            risk_reward = 1.0
            
        # Ensure reasonable risk-reward values
        risk_reward = min(25.0, max(0.5, risk_reward))  # Cap at 25x, floor at 0.5x
        
        # Generate rationale with more details
        if market_context and hasattr(market_context, 'context_data'):
            trend = market_context.context_data["trend"]["direction"]
            support_level = market_context.context_data["support_resistance"].get("closest_support")
            resistance_level = market_context.context_data["support_resistance"].get("closest_resistance")
            
            if target_direction == "long":
                context_info = f", market trend: {trend.lower()}"
                if support_level and support_level <= entry_price <= current_price:
                    context_info += f", near support: {support_level:.2f}"
            else:  # short
                context_info = f", market trend: {trend.lower()}"
                if resistance_level and current_price <= entry_price <= resistance_level:
                    context_info += f", near resistance: {resistance_level:.2f}"
                    
            rationale = f"Target based on {cluster.get('position_count', 0)} positions with size {cluster.get('total_size', 0):.2f}{context_info}"
        else:
            rationale = f"Target based on {cluster.get('position_count', 0)} positions with total size {cluster.get('total_size', 0):.2f}"
        
        # Add time estimation using liquidation method with fallback
        duration_estimates = None
        
        # Try liquidation-based duration estimation first
        cluster_data = {
            "position_count": cluster.get("position_count", 1),
            "total_size": cluster.get("total_size", 1000),
            "tightness": cluster.get("tightness", 1.0),
            "composite_risk": cluster.get("composite_risk", 0.5)
        }
        
        cascade_info = {
            "probability": cascade_data.get("probability", 0.0),
            "confidence": cascade_data.get("confidence", 0.3),
            "expected_price_impact": cascade_data.get("expected_price_impact", 0.0)
        }
        
        try:
            duration_estimates = estimate_liquidation_trade_duration_v2(
                cluster_data=cluster_data,
                cascade_data=cascade_info,
                entry_price=entry_price,
                target_price=take_profit,
                stop_price=stop_loss,
                direction=target_direction,
                asset=asset
            )
        except Exception as e:
            if debug:
                print(f"Liquidation duration estimation failed: {e}")
        
        # Fallback to default values if liquidation method fails
        if not duration_estimates:
            duration_estimates = {
                "tp_hours": 24.0,
                "sl_hours": 12.0,
                "tp_range": "12-36 hours",
                "sl_range": "6-18 hours",
                "confidence": 0.3
            }
        
        # Calculate priority score
        temp_range_data = {
            "trigger_probability": trigger_probability,
            "risk_reward": risk_reward,
            "confidence": confidence,
            "direction": target_direction,
            "composite_risk": cluster.get("composite_risk", 0.5)
        }
        priority_score = calculate_trade_priority(temp_range_data, market_context)
        
        targets.append({
            "entry_price": entry_price,
            "target_price": price_level,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "size": cluster.get("total_size", 0),
            "trigger_probability": trigger_probability,
            "confidence": confidence,
            "risk_reward": risk_reward,
            "rationale": rationale,
            "cluster_data": cluster_data,
            "cascade_data": cascade_info,
            # NEW: Time estimation fields
            "tp_hours": duration_estimates.get("tp_hours", 24.0),
            "sl_hours": duration_estimates.get("sl_hours", 12.0),
            "tp_range": duration_estimates.get("tp_range", "12-36 hours"),
            "sl_range": duration_estimates.get("sl_range", "6-18 hours"),
            "duration_confidence": duration_estimates.get("confidence", 0.3),
            # NEW: Priority scoring fields
            "priority_score": priority_score,
            "priority_factors": temp_range_data.get("priority_factors", {})
        })
    
    # Sort by risk/reward ratio
    return sorted(targets, key=lambda x: x.get("risk_reward", 0), reverse=True)

def generate_trading_ranges(long_targets, short_targets, cascade_data, current_price, market_context=None):
    """
    Generate optimized trading ranges with entry, exit, and risk management levels
    
    Args:
        long_targets: List of long position targets
        short_targets: List of short position targets
        cascade_data: Dict containing cascade probabilities and related data
        current_price: Current price of the asset
        market_context: Optional market context object
        
    Returns:
        List of trading ranges with full details
    """
    # Import market_context module if available
    try:
        from market_context import get_market_context
        HAS_MARKET_CONTEXT = True
    except ImportError:
        HAS_MARKET_CONTEXT = False
    
    ranges = []
    
    # First prioritize the dominant direction from cascade analysis
    dominant_direction = cascade_data.get("dominant_direction", "neutral")
    
    # For neutral conditions, just use the most promising target from either direction
    if dominant_direction == "neutral" or cascade_data.get("overall_probability", 0) < 0.2:
        # Combine and sort all targets
        all_targets = []
        for target in long_targets:
            all_targets.append(("long", target))
        for target in short_targets:
            all_targets.append(("short", target))
        
        # Sort by a combined quality score
        def target_quality(item):
            direction, target = item
            return target.get("risk_reward", 0) * target.get("trigger_probability", 0.1) * \
                   (1 + target.get("confidence", 0.5))
                   
        all_targets.sort(key=target_quality, reverse=True)
        
        # Add the top targets from each direction
        for direction, target in all_targets[:4]:  # Take top 4 
            range_item = {
                "direction": direction,
                "entry": target.get("entry_price", 0),
                "entry_price": target.get("entry_price", 0),  # Add both for compatibility
                "stop_loss": target.get("stop_loss", 0),
                "take_profit": target.get("take_profit", 0),
                "risk_reward": target.get("risk_reward", 0),
                "cascade_probability": cascade_data.get(f"{direction}_cascade", {}).get("probability", 0),
                "risk_level": cascade_data.get(f"{direction}_cascade", {}).get("risk_level", "UNKNOWN"),
                "confidence": target.get("confidence", 
                              cascade_data.get(f"{direction}_cascade", {}).get("confidence", 0.5)),
                "trigger_probability": target.get("trigger_probability", 0.1),
                "price_change": (target.get("entry_price", 0) - current_price) / current_price * 100,
                "rationale": target.get("rationale", "")
            }
            
            # Add time estimates based on liquidation metrics if this isn't a TA-based target
            if "is_ta_based" not in target or not target["is_ta_based"]:
                cascade_key = f"{direction}_cascade"
                liquidation_time_estimates = estimate_liquidation_trade_duration(
                    entry_price=range_item["entry"],
                    target_price=range_item["take_profit"],
                    stop_price=range_item["stop_loss"],
                    direction=direction,
                    cascade_data=cascade_data.get(cascade_key, {}),
                    market_context=market_context,
                    asset="UNKNOWN"
                )
                
                # Merge time estimates with range data
                if liquidation_time_estimates:
                    range_item["tp_hours"] = liquidation_time_estimates.get("tp_hours", 24.0)
                    range_item["sl_hours"] = liquidation_time_estimates.get("sl_hours", 12.0)
                    range_item["tp_range"] = liquidation_time_estimates.get("tp_range", "12-36 hours")
                    range_item["sl_range"] = liquidation_time_estimates.get("sl_range", "6-18 hours")
                    range_item["duration_confidence"] = liquidation_time_estimates.get("confidence", 0.3)
                    range_item["time_factors"] = liquidation_time_estimates.get("factors", {})
            
            ranges.append(range_item)
    else:
        # Add both dominant direction and some counter-direction targets
        # This ensures we always have both long and short recommendations
        primary_targets = long_targets if dominant_direction == "long" else short_targets
        secondary_targets = short_targets if dominant_direction == "long" else long_targets
        
        # Add top targets from dominant direction
        def target_quality(target):
            return target.get("risk_reward", 0) * target.get("trigger_probability", 0.1) * \
                   (1 + target.get("confidence", 0.5))
        
        # Sort targets by quality
        sorted_primary = sorted(primary_targets, key=target_quality, reverse=True)
        sorted_secondary = sorted(secondary_targets, key=target_quality, reverse=True)
        
        # Add top targets from primary direction
        for target in sorted_primary[:3]:  # Take top 3 from primary direction
            range_item = {
                "direction": dominant_direction,
                "entry": target.get("entry_price", 0),
                "entry_price": target.get("entry_price", 0),  # Add both for compatibility
                "stop_loss": target.get("stop_loss", 0),
                "take_profit": target.get("take_profit", 0),
                "risk_reward": target.get("risk_reward", 0),
                "cascade_probability": cascade_data.get(f"{dominant_direction}_cascade", {}).get("probability", 0),
                "risk_level": cascade_data.get(f"{dominant_direction}_cascade", {}).get("risk_level", "UNKNOWN"),
                "confidence": target.get("confidence", 
                              cascade_data.get(f"{dominant_direction}_cascade", {}).get("confidence", 0.5)),
                "trigger_probability": target.get("trigger_probability", 0.1),
                "price_change": (target.get("entry_price", 0) - current_price) / current_price * 100,
                "rationale": target.get("rationale", "")
            }
            
            # Add time estimates based on liquidation metrics if this isn't a TA-based target
            if "is_ta_based" not in target or not target["is_ta_based"]:
                cascade_key = f"{dominant_direction}_cascade"
                liquidation_time_estimates = estimate_liquidation_trade_duration(
                    entry_price=range_item["entry"],
                    target_price=range_item["take_profit"],
                    stop_price=range_item["stop_loss"],
                    direction=dominant_direction,
                    cascade_data=cascade_data.get(cascade_key, {}),
                    market_context=market_context,
                    asset="UNKNOWN"
                )
                
                # Merge time estimates with range data
                if liquidation_time_estimates:
                    range_item["tp_hours"] = liquidation_time_estimates.get("tp_hours", 24.0)
                    range_item["sl_hours"] = liquidation_time_estimates.get("sl_hours", 12.0)
                    range_item["tp_range"] = liquidation_time_estimates.get("tp_range", "12-36 hours")
                    range_item["sl_range"] = liquidation_time_estimates.get("sl_range", "6-18 hours")
                    range_item["duration_confidence"] = liquidation_time_estimates.get("confidence", 0.3)
                    range_item["time_factors"] = liquidation_time_estimates.get("factors", {})
            
            ranges.append(range_item)
        
        # Also add top target from secondary direction to ensure balanced recommendations
        counter_direction = "short" if dominant_direction == "long" else "long"
        for target in sorted_secondary[:2]:  # Take top 2 from secondary direction
            range_item = {
                "direction": counter_direction,
                "entry": target.get("entry_price", 0),
                "entry_price": target.get("entry_price", 0),  # Add both for compatibility
                "stop_loss": target.get("stop_loss", 0),
                "take_profit": target.get("take_profit", 0),
                "risk_reward": target.get("risk_reward", 0),
                "cascade_probability": cascade_data.get(f"{counter_direction}_cascade", {}).get("probability", 0),
                "risk_level": cascade_data.get(f"{counter_direction}_cascade", {}).get("risk_level", "UNKNOWN"),
                "confidence": target.get("confidence", 
                              cascade_data.get(f"{counter_direction}_cascade", {}).get("confidence", 0.5)),
                "trigger_probability": target.get("trigger_probability", 0.1),
                "price_change": (target.get("entry_price", 0) - current_price) / current_price * 100,
                "rationale": target.get("rationale", "")
            }
            
            # Add time estimates based on liquidation metrics if this isn't a TA-based target
            if "is_ta_based" not in target or not target["is_ta_based"]:
                cascade_key = f"{counter_direction}_cascade"
                liquidation_time_estimates = estimate_liquidation_trade_duration(
                    entry_price=range_item["entry"],
                    target_price=range_item["take_profit"],
                    stop_price=range_item["stop_loss"],
                    direction=counter_direction,
                    cascade_data=cascade_data.get(cascade_key, {}),
                    market_context=market_context,
                    asset="UNKNOWN"
                )
                
                # Merge time estimates with range data
                if liquidation_time_estimates:
                    range_item["tp_hours"] = liquidation_time_estimates.get("tp_hours", 24.0)
                    range_item["sl_hours"] = liquidation_time_estimates.get("sl_hours", 12.0)
                    range_item["tp_range"] = liquidation_time_estimates.get("tp_range", "12-36 hours")
                    range_item["sl_range"] = liquidation_time_estimates.get("sl_range", "6-18 hours")
                    range_item["duration_confidence"] = liquidation_time_estimates.get("confidence", 0.3)
                    range_item["time_factors"] = liquidation_time_estimates.get("factors", {})
                
            ranges.append(range_item)
    
    return ranges

def generate_recommendation_summary(direction, probability, risk_level, current_price, ranges):
    """
    Generate a concise summary of the trading recommendation
    
    Args:
        direction: Dominant direction ('long', 'short', or 'neutral')
        probability: Overall cascade probability
        risk_level: Risk level assessment
        current_price: Current market price
        ranges: List of trading ranges
        
    Returns:
        String with recommendation summary
    """
    if direction == "neutral" or probability < 0.2:
        return "Market conditions are balanced with no significant liquidation pressure detected. Consider ranging strategies."
    
    # Get primary range (first in the list)
    primary_range = ranges[0] if ranges else None
    
    if not primary_range:
        return f"{risk_level} {direction.upper()} bias detected, but no specific price targets identified."
    
    entry = primary_range.get("entry", 0)
    take_profit = primary_range.get("take_profit", 0)
    entry_change = (entry - current_price) / current_price * 100
    
    if direction == "long":
        action = "BUY"
        entry_desc = "dip" if entry_change < 0 else "pullback"
        tp_desc = f"{(take_profit - entry) / entry * 100:.1f}% move up"
    else:
        action = "SELL"
        entry_desc = "rally" if entry_change > 0 else "retrace"
        tp_desc = f"{(entry - take_profit) / entry * 100:.1f}% move down"
    
    return f"{risk_level} {direction.upper()} bias detected. {action} the {entry_desc} near {entry:.2f} targeting {tp_desc} to {take_profit:.2f}. R:R = {primary_range.get('risk_reward', 0):.1f}"


def calculate_dynamic_stop_loss(entry_price, direction, asset_volatility=None, default_pct=0.025):
    """
    Calculate dynamic stop loss based on volatility
    
    Args:
        entry_price: The entry price of the trade
        direction: Trade direction ('long' or 'short')
        asset_volatility: Volatility measure (e.g., normalized ATR)
        default_pct: Default percentage to use if no volatility provided
        
    Returns:
        Calculated stop loss price
    """
    # Start with default percentage
    stop_loss_pct = default_pct
    
    # Use provided volatility if available
    if asset_volatility:
        # Scale stop loss percentage based on volatility
        # Higher volatility -> wider stop loss
        stop_loss_pct = min(0.025, max(0.015, asset_volatility * 0.5))
    
    # Calculate actual stop loss price based on direction
    if direction == "long":
        stop_loss = entry_price * (1 - stop_loss_pct)
    else:  # short
        stop_loss = entry_price * (1 + stop_loss_pct)
    
    return stop_loss

def estimate_trade_duration(entry_price, target_price, stop_price, direction, market_context=None, asset="UNKNOWN"):
    """
    Estimate the expected duration for a trade to reach its targets using volatility-adjusted distance.
    
    Args:
        entry_price: Entry price for the trade
        target_price: Take profit target price
        stop_price: Stop loss price
        direction: 'long' or 'short'
        market_context: Market context object containing volatility metrics
        asset: Asset symbol
        
    Returns:
        dict: Dictionary containing time estimates for take profit and stop loss
    """
    # Default return if we can't make a calculation
    # Use reasonable fallback values instead of None
    default_result = {
        "tp_hours": 24.0,  # 24 hours as default TP time
        "sl_hours": 12.0,  # 12 hours as default SL time
        "tp_range": "12-36 hours",  # Reasonable time range estimate
        "sl_range": "6-18 hours",   # Reasonable time range estimate
        "confidence": 0.3  # Low confidence since this is a fallback
    }
    
    # Validate inputs
    if not entry_price or not target_price or not stop_price:
        return default_result
    
    # Handle invalid price inputs
    if entry_price <= 0 or target_price <= 0 or stop_price <= 0:
        return default_result
    
    # Calculate distance percentages
    tp_distance_pct = abs(target_price - entry_price) / entry_price * 100
    sl_distance_pct = abs(stop_price - entry_price) / entry_price * 100
    
    # Get volatility metrics from market context
    hourly_movement_rate = 0.5  # Default: 0.5% per hour if no context available
    
    trend_multiplier = 1.0
    direction_multiplier = 1.0
    volatility_multiplier = 1.0
    level_multiplier = 1.0
    
    if market_context:
        # Use ATR for volatility if available
        if hasattr(market_context, 'context_data') and 'volatility' in market_context.context_data:
            vol_data = market_context.context_data['volatility']
            
            # First check for atr_percent which is the standard key in market_context
            if 'atr_percent' in vol_data:
                hourly_movement_rate = float(vol_data['atr_percent']) * 100
            # Fall back to raw atr if available
            elif 'atr' in vol_data:
                # Convert ATR to percentage of price
                atr = float(vol_data['atr'])
                hourly_movement_rate = (atr / entry_price) * 100
            
            # Get normalized ATR if available
            if 'atr_normalized' in vol_data:
                normalized_atr = float(vol_data['atr_normalized'])
                # Adjust volatility multiplier based on relative volatility
                if normalized_atr > 2.0:  # High volatility
                    volatility_multiplier = 0.7
                elif normalized_atr < 0.5:  # Low volatility
                    volatility_multiplier = 1.3
            
        # Trend strength adjustment
        if hasattr(market_context, 'context_data') and 'trend' in market_context.context_data:
            trend_data = market_context.context_data['trend']
            
            # ADX-based trend strength
            if 'adx' in trend_data:
                adx = float(trend_data['adx'])
                if adx > 25:  # Strong trend
                    trend_multiplier = 0.7
                elif adx > 15:  # Moderate trend
                    trend_multiplier = 0.85
            
            # Direction alignment
            if 'direction' in trend_data:
                trend_direction = trend_data['direction']
                if (direction == 'long' and trend_direction == 'up') or (direction == 'short' and trend_direction == 'down'):
                    direction_multiplier = 0.8  # With-trend moves faster
                else:
                    direction_multiplier = 1.5  # Counter-trend moves slower
        
        # Support/Resistance impact
        if hasattr(market_context, 'key_levels') and market_context.key_levels:
            # Get key levels between current price and target
            key_levels = market_context.key_levels
            
            # Count strong levels between entry and target
            strong_levels = 0
            if direction == 'long':
                for level in key_levels:
                    if entry_price < level < target_price:
                        strong_levels += 1
            else:  # short
                for level in key_levels:
                    if target_price < level < entry_price:
                        strong_levels += 1
            
            # Add 20% per strong level
            if strong_levels > 0:
                level_multiplier = 1.0 + (0.2 * min(strong_levels, 3))  # Cap at 3 levels
    
    # Ensure hourly movement rate is not too low to avoid infinite estimates
    hourly_movement_rate = max(hourly_movement_rate, 0.1)
    
    # Combined multiplier for all factors
    combined_multiplier = trend_multiplier * direction_multiplier * volatility_multiplier * level_multiplier
    
    # Calculate raw time estimates
    raw_tp_hours = tp_distance_pct / hourly_movement_rate
    raw_sl_hours = sl_distance_pct / hourly_movement_rate
    
    # Apply combined multiplier
    tp_hours = raw_tp_hours * combined_multiplier
    sl_hours = raw_sl_hours * combined_multiplier
    
    # Generate confidence bands (25th, 50th, 75th percentiles)
    tp_optimistic = max(1, tp_hours * 0.7)  # At least 1 hour
    tp_pessimistic = tp_hours * 1.5
    
    sl_optimistic = max(1, sl_hours * 0.7)  # At least 1 hour
    sl_pessimistic = sl_hours * 1.5
    
    # Format ranges
    tp_range = f"{int(tp_optimistic)}-{int(tp_pessimistic)} hours"
    sl_range = f"{int(sl_optimistic)}-{int(sl_pessimistic)} hours"
    
    # Confidence based on market conditions and calculation factors
    # Higher when trend is strong and with-trend trade
    confidence = min(0.9, max(0.3, (1.0 / combined_multiplier)))
    
    return {
        "tp_hours": round(tp_hours, 1),
        "sl_hours": round(sl_hours, 1),
        "tp_range": tp_range,
        "sl_range": sl_range,
        "confidence": round(confidence, 2),
        "factors": {
            "hourly_rate": round(hourly_movement_rate, 2),
            "trend": round(trend_multiplier, 2),
            "direction": round(direction_multiplier, 2),
            "volatility": round(volatility_multiplier, 2),
            "key_levels": round(level_multiplier, 2)
        }
    }


def adjust_probability_for_momentum(trigger_probability, direction, current_price, price_1h_ago=None):
    """
    Adjust trigger probability based on recent price momentum
    
    Args:
        trigger_probability: Base trigger probability
        direction: Trade direction ('long' or 'short')
        current_price: Current asset price
        price_1h_ago: Asset price 1 hour ago
        
    Returns:
        Adjusted trigger probability
    """
    # If no historical price provided, return original probability
    if price_1h_ago is None or price_1h_ago <= 0:
        return trigger_probability
    
    # Calculate 1hr price change percentage
    price_change_pct = (current_price - price_1h_ago) / price_1h_ago
    
    # Calculate momentum factor (-1.0 to +1.0)
    momentum_factor = min(1.0, max(-1.0, price_change_pct * 20))
    
    # Adjust probability based on direction and momentum
    # For long positions: upward momentum increases probability
    # For short positions: downward momentum increases probability
    direction_multiplier = 1 if direction == "long" else -1
    momentum_adjustment = momentum_factor * direction_multiplier * 0.2
    
    # Apply adjustment with limits
    adjusted_probability = min(0.95, max(0.05, trigger_probability + momentum_adjustment))
    return adjusted_probability


def estimate_liquidation_trade_duration(entry_price, target_price, stop_price, direction, cascade_data, market_context=None, asset="UNKNOWN"):
    """
    Estimate the expected duration for a trade based on liquidation metrics and cascade probability.
    Unlike the TA-based estimates, this focuses more on cascade potential and liquidation density.
    
    Args:
        entry_price: Entry price for the trade
        target_price: Take profit target price
        stop_price: Stop loss price
        direction: 'long' or 'short'
        cascade_data: Liquidation cascade data for this direction
        market_context: Market context object containing volatility metrics
        asset: Asset symbol
        
    Returns:
        dict: Dictionary containing time estimates for take profit and stop loss
    """
    # Default return if we can't make a calculation
    default_result = {
        "tp_hours": 24.0,  # 24 hours as default TP time
        "sl_hours": 12.0,  # 12 hours as default SL time
        "tp_range": "12-36 hours",  # Reasonable time range estimate
        "sl_range": "6-18 hours",   # Reasonable time range estimate
        "confidence": 0.3  # Low confidence since this is a fallback
    }
    
    # Validate inputs
    if not entry_price or not target_price or not stop_price or entry_price <= 0:
        return default_result
    
    # Calculate distance percentages
    tp_distance_pct = abs(target_price - entry_price) / entry_price * 100
    sl_distance_pct = abs(stop_price - entry_price) / entry_price * 100
    
    # Base hourly movement rate - default if no context available
    hourly_movement_rate = 0.5  # Default: 0.5% per hour
    
    # Multipliers that will affect the time estimate
    cascade_multiplier = 1.0
    density_multiplier = 1.0
    volatility_multiplier = 1.0
    
    # Extract cascade probability and other metrics from cascade_data
    cascade_prob = 0.1  # Default value
    
    # Extract the correct cascade probability based on direction
    if cascade_data:
        if isinstance(cascade_data, dict):
            # Check if it's the standard format from cascade_analysis.py
            cascade_key = "short_cascade" if direction == "long" else "long_cascade"
            if cascade_key in cascade_data:
                cascade_prob = cascade_data[cascade_key].get("probability", 0.1)
            # Also check for direct cascade_probability key as fallback
            elif "cascade_probability" in cascade_data:
                cascade_prob = cascade_data.get("cascade_probability", 0.1)
    
    # Higher cascade probability = faster expected movement
    if cascade_prob > 0.7:
        cascade_multiplier = 0.5  # Very high probability cuts time in half
    elif cascade_prob > 0.5:
        cascade_multiplier = 0.7  # High probability
    elif cascade_prob > 0.3:
        cascade_multiplier = 0.85  # Moderate probability
    
    # Extract liquidation cluster info if available
    if cascade_data and "clusters" in cascade_data:
        clusters = cascade_data["clusters"]
        # Check if clusters list has relevant data
        if clusters and len(clusters) > 0:
            # Find cluster closest to target price
            closest_cluster = None
            min_distance = float('inf')
            for cluster in clusters:
                cluster_price = cluster.get("price", 0)
                if cluster_price > 0:
                    distance = abs(cluster_price - target_price)
                    if distance < min_distance:
                        min_distance = distance
                        closest_cluster = cluster
            
            # If we found a relevant cluster, use its density to adjust time
            if closest_cluster:
                # Get cluster size or density
                cluster_size = closest_cluster.get("size", 0)
                # Larger clusters may create faster price movements
                if cluster_size > 1000:  # Very large
                    density_multiplier = 0.6
                elif cluster_size > 500:  # Large
                    density_multiplier = 0.75
                elif cluster_size > 250:  # Medium
                    density_multiplier = 0.9
    
    # Use market context to adjust volatility_multiplier if available
    if market_context:
        # Apply volatility metrics from market context if available
        if hasattr(market_context, 'context_data') and 'volatility' in market_context.context_data:
            vol_data = market_context.context_data['volatility']
            
            # Check for volatility metrics in context_data
            if 'atr_percent' in vol_data:
                hourly_movement_rate = float(vol_data['atr_percent']) * 100
            elif 'atr' in vol_data:
                atr = float(vol_data['atr'])
                hourly_movement_rate = (atr / entry_price) * 100
            
            # Use normalized volatility to adjust the multiplier
            if 'atr_normalized' in vol_data:
                normalized_volatility = float(vol_data['atr_normalized'])
                if normalized_volatility > 1.5:  # High volatility
                    volatility_multiplier = 0.7  # Faster in high volatility
                elif normalized_volatility < 0.7:  # Low volatility
                    volatility_multiplier = 1.4  # Slower in low volatility
    
    # Ensure hourly movement rate is reasonable
    hourly_movement_rate = max(hourly_movement_rate, 0.1)  # At least 0.1% per hour
    
    # Combined multiplier for all factors
    combined_multiplier = cascade_multiplier * density_multiplier * volatility_multiplier
    
    # Calculate raw time estimates based on distance and hourly movement
    raw_tp_hours = tp_distance_pct / hourly_movement_rate
    raw_sl_hours = sl_distance_pct / hourly_movement_rate
    
    # Apply the combined multiplier to get final estimates
    tp_hours = raw_tp_hours * combined_multiplier
    sl_hours = raw_sl_hours * combined_multiplier
    
    # Generate confidence bands (optimistic vs pessimistic scenarios)
    tp_optimistic = max(1, tp_hours * 0.7)  # At least 1 hour
    tp_pessimistic = tp_hours * 1.5
    
    sl_optimistic = max(1, sl_hours * 0.7)  # At least 1 hour
    sl_pessimistic = sl_hours * 1.5
    
    # Format the time ranges as strings
    tp_range = f"{int(tp_optimistic)}-{int(tp_pessimistic)} hours"
    sl_range = f"{int(sl_optimistic)}-{int(sl_pessimistic)} hours"
    
    # Higher confidence when cascade probability is high
    confidence = min(0.85, max(0.3, cascade_prob + 0.3))
    
    # Return the complete time estimate dictionary
    return {
        "tp_hours": round(tp_hours, 1),
        "sl_hours": round(sl_hours, 1),
        "tp_range": tp_range,
        "sl_range": sl_range,
        "confidence": round(confidence, 2),
        "factors": {
            "hourly_rate": round(hourly_movement_rate, 2),
            "cascade": round(cascade_multiplier, 2),
            "density": round(density_multiplier, 2),
            "volatility": round(volatility_multiplier, 2)
        }
    }


def calculate_trade_priority(range_data, market_context=None):
    """Calculate trade priority score (0-100) based on multiple factors
    
    Args:
        range_data: Dictionary with trade range information
        market_context: Optional market context object
        
    Returns:
        Priority score from 0-100
    """
    """
    Calculate a dynamic priority score for comparing trade opportunities
    Adjusts weights based on market conditions when context is available
    
    Args:
        range_data: Dictionary containing trade range data
        market_context: Optional market context object with additional metrics
        
    Returns:
        Priority score (0-100)
    """
    # Extract key metrics
    trigger_prob = range_data.get("trigger_probability", 0.1)
    risk_reward = range_data.get("risk_reward", 1.0)
    confidence = range_data.get("confidence", 0.5)
    direction = range_data.get("direction", "long")
    
    # Calculate liquidity confidence from either composite_risk or liquidity_risk
    liquidity_confidence = 1.0 - range_data.get("composite_risk", 
                          range_data.get("liquidity_risk", 0.5))
    
    # Dynamic weights that adapt to market conditions
    trigger_weight = 40  # Base weight: 40%
    risk_reward_weight = 25  # Base weight: 25%
    confidence_weight = 20  # Base weight: 20%
    liquidity_weight = 15  # Base weight: 15%
    
    # Adjust weights based on market context if available
    if market_context:
        # 1. In high volatility, prioritize risk/reward and liquidity
        if hasattr(market_context, 'volatility'):
            volatility = getattr(market_context, 'volatility', 0.5)
            if volatility > 0.7:  # High volatility
                risk_reward_weight += 10
                liquidity_weight += 5
                trigger_weight -= 10
                confidence_weight -= 5
            elif volatility < 0.3:  # Low volatility
                trigger_weight += 5
                confidence_weight += 5
                risk_reward_weight -= 5
                liquidity_weight -= 5
        
        # 2. In trending markets, prioritize trend-aligned trades
        if hasattr(market_context, 'trend_direction') and hasattr(market_context, 'trend_strength'):
            trend = getattr(market_context, 'trend_direction', 'neutral')
            trend_strength = getattr(market_context, 'trend_strength', 0.5)
            
            # Boost confidence weight for trades aligned with trend
            if (trend == 'up' and direction == 'long') or (trend == 'down' and direction == 'short'):
                confidence_weight += int(trend_strength * 10)
                trigger_weight += int(trend_strength * 5)
                risk_reward_weight -= int(trend_strength * 10)
                liquidity_weight -= int(trend_strength * 5)
    
    # Add extra boost for extremely high probability setups
    if trigger_prob > 0.8 and risk_reward > 2.0:
        bonus = 10  # Bonus points for exceptional setups
    else:
        bonus = 0
    
    # Normalize weights to ensure they sum to 100
    total_weight = trigger_weight + risk_reward_weight + confidence_weight + liquidity_weight
    trigger_weight = (trigger_weight / total_weight) * 100
    risk_reward_weight = (risk_reward_weight / total_weight) * 100
    confidence_weight = (confidence_weight / total_weight) * 100
    liquidity_weight = (liquidity_weight / total_weight) * 100
    
    # Calculate dynamic priority score (0-100 scale)
    priority = (
        trigger_prob * (trigger_weight/100) +
        risk_reward * (risk_reward_weight/100) +
        confidence * (confidence_weight/100) +
        liquidity_confidence * (liquidity_weight/100)
    ) * 100 + bonus
    
    # Add the calculation factors to the range_data for transparency
    range_data["priority_factors"] = {
        "trigger_weight": round(trigger_weight, 1),
        "risk_reward_weight": round(risk_reward_weight, 1),
        "confidence_weight": round(confidence_weight, 1),
        "liquidity_weight": round(liquidity_weight, 1),
        "bonus": bonus
    }
    
    return min(100, max(0, priority))  # Ensure score stays within 0-100

def estimate_liquidation_trade_duration_v2(cluster_data, cascade_data, entry_price, target_price, stop_price, direction, asset="UNKNOWN"):
    """
    Estimate trade duration using liquidation cluster and cascade data.
    
    Args:
        cluster_data: Dict with position_count, total_size, tightness, composite_risk
        cascade_data: Dict with probability, confidence, expected_price_impact
        entry_price: Entry price for the trade
        target_price: Take profit target price
        stop_price: Stop loss price
        direction: 'long' or 'short'
        asset: Asset symbol
        
    Returns:
        dict: Dictionary containing time estimates matching original format
    """
    import math
    
    # Default fallback if data is missing
    default_result = {
        "tp_hours": 24.0,
        "sl_hours": 12.0,
        "tp_range": "12-36 hours",
        "sl_range": "6-18 hours",
        "confidence": 0.3
    }
    
    try:
        # Validate inputs
        if not all([cluster_data, cascade_data, entry_price, target_price, stop_price]):
            return default_result
            
        if entry_price <= 0 or target_price <= 0 or stop_price <= 0:
            return default_result
        
        # Extract cluster metrics
        position_count = cluster_data.get('position_count', 1)
        total_size = cluster_data.get('total_size', 1000)
        tightness = cluster_data.get('tightness', 1.0)
        composite_risk = cluster_data.get('composite_risk', 0.5)
        
        # Extract cascade metrics
        cascade_prob = cascade_data.get('probability', 0.0)
        confidence = cascade_data.get('confidence', 0.3)
        expected_impact = cascade_data.get('expected_price_impact', 0.0)
        
        # Calculate price distances
        tp_distance_pct = abs(target_price - entry_price) / entry_price * 100
        sl_distance_pct = abs(stop_price - entry_price) / entry_price * 100
        
        # Calculate composite factors with aggressive scaling
        density_factor = min(3.0, max(0.3, math.log10(position_count + 1) * 1.8))
        tightness_factor = min(1.5, max(0.6, tightness * 1.2 + 0.3))
        cascade_factor = min(3.0, max(0.3, 0.3 + cascade_prob * 2.7))
        risk_factor = min(1.5, max(0.5, 1.5 - composite_risk * 1.0))
        size_factor = min(3.0, max(0.5, math.log10(total_size / 500) * 0.6 + 0.8))
        confidence_factor = min(1.2, max(0.4, confidence * 1.5))
        
        # Base time: More dynamic scaling based on distance
        tp_base_time = tp_distance_pct * 0.8
        sl_base_time = sl_distance_pct * 0.5
        
        # Combined speed multiplier with more variation
        speed_multiplier = (
            density_factor * tightness_factor * cascade_factor * 
            risk_factor * size_factor * confidence_factor
        ) / 6.0  # Normalize by number of factors
        
        # Final estimates with bounds
        tp_hours = tp_base_time / max(0.3, speed_multiplier)
        sl_hours = sl_base_time / max(0.3, speed_multiplier)
        
        # Apply realistic bounds (0.5 to 72 hours)
        tp_hours = min(72.0, max(0.5, tp_hours))
        sl_hours = min(72.0, max(0.5, sl_hours))
        
        # Calculate confidence based on data quality
        final_confidence = min(0.95, max(0.5, 
            0.5 + (confidence * 0.3) + (min(cascade_prob, 0.5) * 0.4) + 
            (min(tightness, 1.0) * 0.2)
        ))
        
        # Generate time ranges (±30% of estimate)
        tp_low = max(0.5, tp_hours * 0.7)
        tp_high = min(72.0, tp_hours * 1.3)
        sl_low = max(0.5, sl_hours * 0.7)
        sl_high = min(72.0, sl_hours * 1.3)
        
        tp_range = f"{tp_low:.0f}-{tp_high:.0f} hours"
        sl_range = f"{sl_low:.0f}-{sl_high:.0f} hours"
        
        return {
            "tp_hours": round(tp_hours, 1),
            "sl_hours": round(sl_hours, 1),
            "tp_range": tp_range,
            "sl_range": sl_range,
            "confidence": round(final_confidence, 2)
        }
        
    except Exception as e:
        # Log error but don't break the flow
        print(f"Error in liquidation duration estimation: {e}")
        return default_result
