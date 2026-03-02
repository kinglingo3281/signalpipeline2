#!/usr/bin/env python
"""
Market Alignment Module
---------------------
Detects alignment between trade directions and market bias
to apply tiered confidence thresholds.
"""

import json
import os
import sys
import logging

# Add parent directory to path to allow imports from root after moving to utils/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Define project root for consistent file paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("market_alignment")

def load_config():
    """Load configuration from tracker/config.json"""
    # When in utils/, need to look in parent dir + tracker/config.json
    # When in root, need to look in ./tracker/config.json
    # Try both paths to handle both scenarios
    
    # Path when in utils/ directory
    config_path_from_utils = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tracker", "config.json")
    
    # Original path when in root directory
    config_path_from_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracker", "config.json")
    
    try:
        # Try from utils/ directory first
        if os.path.exists(config_path_from_utils):
            with open(config_path_from_utils, "r") as f:
                config = json.load(f)
            return config
        # Then try from root directory
        elif os.path.exists(config_path_from_root):
            with open(config_path_from_root, "r") as f:
                config = json.load(f)
            return config
        else:
            logger.warning("Could not find config file in either path")
            return {"confidence_thresholds": {"aligned": 0.2, "neutral": 0.3, "counter_trend": 0.4, "enable_tiered_thresholds": True}}
    except Exception as e:
        logger.warning(f"Could not load config file: {e}")
        return {"confidence_thresholds": {"aligned": 0.2, "neutral": 0.3, "counter_trend": 0.4, "enable_tiered_thresholds": True}}

def get_alignment_classification(direction, market_bias):
    """
    Determine the alignment between a trade direction and market bias
    
    Args:
        direction: 'long' or 'short'
        market_bias: 'BULLISH', 'BEARISH', or 'NEUTRAL' (or None)
    
    Returns:
        str: 'aligned', 'counter_trend', or 'neutral'
    """
    # Handle None or empty string cases
    if market_bias is None or not market_bias or market_bias.upper() == "NEUTRAL":
        return "neutral"
    
    # Normalize inputs for consistent comparison
    direction_norm = direction.lower() if direction else ""
    bias_norm = market_bias.upper() if market_bias else ""
    
    # Check for variations of bullish terminology
    is_bullish = any(term in bias_norm for term in ["BULLISH", "BULL"])
    is_bearish = any(term in bias_norm for term in ["BEARISH", "BEAR"])
        
    if direction_norm == "long" and is_bullish:
        return "aligned"
    elif direction_norm == "short" and is_bearish:
        return "aligned"
    elif direction_norm == "long" and is_bearish:
        return "counter_trend"
    elif direction_norm == "short" and is_bullish:
        return "counter_trend"
    
    return "neutral"  # Default fallback

def get_confidence_threshold(direction, market_bias, trend_strength=None):
    """
    Get the minimum confidence threshold based on alignment with market bias and trend strength
    
    Args:
        direction: 'long' or 'short'
        market_bias: 'BULLISH', 'BEARISH', or 'NEUTRAL'
        trend_strength: Optional float (0-1) indicating the strength of the current trend
    
    Returns:
        float: The minimum confidence threshold
    """
    # Load config to get thresholds
    config = load_config()
    thresholds = config.get("confidence_thresholds", {})
    enabled = thresholds.get("enable_tiered_thresholds", True)
    
    if not enabled:
        return 0.2  # Default minimum threshold if tiered system is disabled
    
    # Get alignment classification
    alignment = get_alignment_classification(direction, market_bias)
    
    # Get base threshold for this alignment
    base_threshold = 0.2  # Default fallback
    if alignment == "aligned":
        base_threshold = thresholds.get("aligned", 0.2)
    elif alignment == "neutral":
        base_threshold = thresholds.get("neutral", 0.3)
    elif alignment == "counter_trend":
        base_threshold = thresholds.get("counter_trend", 0.4)
    
    # Apply trend strength multiplier if provided and enabled
    trend_config = thresholds.get("trend_strength", {})
    if trend_strength is not None and trend_config.get("enable", True):
        # Only apply multiplier to counter-trend trades
        if alignment == "counter_trend":
            # Get the strong trend threshold and max multiplier from config
            strong_threshold = trend_config.get("strong_threshold", 0.7)
            max_multiplier = trend_config.get("max_multiplier", 1.5)
            
            # Calculate multiplier based on how much trend_strength exceeds the threshold
            if trend_strength >= strong_threshold:
                # Scale from 1.0 (at threshold) to max_multiplier (at trend_strength=1.0)
                strength_scale = (trend_strength - strong_threshold) / (1.0 - strong_threshold)
                multiplier = 1.0 + (strength_scale * (max_multiplier - 1.0))
                
                # Apply multiplier to base threshold, capped at 0.5 to avoid extreme filtering
                adjusted_threshold = min(0.5, base_threshold * multiplier)
                
                # Log the adjustment if significant
                if adjusted_threshold > base_threshold + 0.05:
                    logger.info(f"Adjusting {alignment} confidence threshold from {base_threshold:.2f} to {adjusted_threshold:.2f} due to strong trend ({trend_strength:.2f})")
                
                return adjusted_threshold
    
    return base_threshold
