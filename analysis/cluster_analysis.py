#!/usr/bin/env python
"""
Cluster Analysis Module (Bridge)
-------------------------------
Bridge module that re-exports functions from our enhanced analysis modules
to maintain compatibility with auto_liquidation_analysis.py
"""

import os
import sys

# Add parent directory to path to allow imports from root after moving to analysis/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Define project root for consistent file path handling
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Make sure our own directory is in the path
analysis_dir = os.path.dirname(os.path.abspath(__file__))
if analysis_dir not in sys.path:
    sys.path.append(analysis_dir)

# Import from our cascade analysis module
try:
    # First try absolute import with package
    from analysis.cascade_analysis import calculate_cascade_probability as cascade_probability_original
except ImportError:
    # Then try direct import from same directory
    from cascade_analysis import calculate_cascade_probability as cascade_probability_original

# Import from liquidation clusters module
try:
    # First try absolute import with package
    from analysis.liquidation_clusters import identify_liquidation_clusters as identify_clusters_function
except ImportError:
    # Then try direct import from same directory
    from liquidation_clusters import identify_liquidation_clusters as identify_clusters_function

# Import from enhanced liquidation analysis
try:
    # First try absolute import with package
    from analysis.enhanced_liquidation_analysis import EnhancedLiquidationAnalysis
except ImportError:
    # Then try direct import from same directory
    from enhanced_liquidation_analysis import EnhancedLiquidationAnalysis

# Import from price targeting with fallback options
try:
    # First try with utils package
    from utils.price_targeting import generate_price_targets
except ImportError:
    # If that fails, try direct import (pre-refactoring location)
    try:
        from price_targeting import generate_price_targets
    except ImportError:
        # Define a stub function if all imports fail
        print("Warning: Could not import price_targeting module, using stub function")
        def generate_price_targets(*args, **kwargs):
            return {"error": "price_targeting module not available"}

# Bridge functions that auto_liquidation_analysis.py is looking for

def identify_liquidation_clusters(asset, liquidation_analysis, orderbook=None):
    """Bridge to our enhanced liquidation cluster identification"""
    # Extract the current price from liquidation analysis
    current_price = liquidation_analysis.get('current_price', 0)
    
    # Extract positions in the format needed for the identify_clusters_function
    positions = {
        "long": [],
        "short": []
    }
    
    # Check if we have long/short liquidations in the expected format
    if 'long_liquidations' in liquidation_analysis:
        for price_key, data in liquidation_analysis['long_liquidations'].items():
            if isinstance(data, dict) and 'positions' in data and isinstance(data['positions'], list):
                for pos in data['positions']:
                    positions["long"].append({
                        "price": float(pos.get("liquidation_price", price_key)),
                        "size": float(pos.get("size", 0)),
                        "trader": pos.get("trader", "unknown")
                    })
                    
    if 'short_liquidations' in liquidation_analysis:
        for price_key, data in liquidation_analysis['short_liquidations'].items():
            if isinstance(data, dict) and 'positions' in data and isinstance(data['positions'], list):
                for pos in data['positions']:
                    positions["short"].append({
                        "price": float(pos.get("liquidation_price", price_key)),
                        "size": float(pos.get("size", 0)),
                        "trader": pos.get("trader", "unknown")
                    })
    
    # Call the actual identify_liquidation_clusters function that our modules use
    debug_mode = False  # Set to true if you want debug output
    clusters = identify_clusters_function(positions, current_price, asset, debug_mode)
    
    # Return in the format expected by auto_liquidation_analysis
    return {
        'asset': asset,
        'clusters': clusters.get('clusters', []),
        'long_clusters': clusters.get('long_clusters', []),
        'short_clusters': clusters.get('short_clusters', []),
        'current_price': current_price
    }

def analyze_liquidation_landscape(asset, liquidation_analysis, orderbook=None):
    """Bridge to our enhanced landscape analysis"""
    # Create an instance of our enhanced analysis
    analyzer = EnhancedLiquidationAnalysis(asset=asset)
    
    # Use data from the passed liquidation analysis
    analyzer.current_price = liquidation_analysis.get('current_price', 0)
    
    # Return basic landscape analysis
    return {
        'asset': asset,
        'current_price': analyzer.current_price,
        'long_liquidity': liquidation_analysis.get('long_liquidity', 0),
        'short_liquidity': liquidation_analysis.get('short_liquidity', 0),
        'long_position_count': len(liquidation_analysis.get('long_positions', [])),
        'short_position_count': len(liquidation_analysis.get('short_positions', []))
    }

def calculate_cascade_probability(asset, liquidation_analysis, enhanced_clusters=None, orderbook=None):
    """Bridge function to handle the orderbook parameter that fetch_top_traders.py passes"""
    # Extract the current price from liquidation_analysis
    current_price = liquidation_analysis.get('current_price', 0)
    
    # Call the original function from cascade_analysis.py without the orderbook parameter
    cascade_results = cascade_probability_original(enhanced_clusters, current_price, asset)
    
    # Adapt the structure to what fetch_top_traders.py expects
    adapted_results = {
        "asset": asset,
        "current_price": current_price,
        "cascade_probability": {
            "long": cascade_results.get("long_cascade", {}).get("probability", 0.0),
            "short": cascade_results.get("short_cascade", {}).get("probability", 0.0)
        },
        "risk_level": {
            "long": cascade_results.get("long_cascade", {}).get("risk_level", "LOW"),
            "short": cascade_results.get("short_cascade", {}).get("risk_level", "LOW")
        },
        "critical_threshold": {
            "long": cascade_results.get("long_cascade", {}).get("critical_threshold", None),
            "short": cascade_results.get("short_cascade", {}).get("critical_threshold", None)
        },
        "expected_price_impact": {
            "long": cascade_results.get("long_cascade", {}).get("expected_price_impact", 0.0),
            "short": cascade_results.get("short_cascade", {}).get("expected_price_impact", 0.0)
        },
        # Preserve the original structure for backward compatibility
        "long_cascade": cascade_results.get("long_cascade", {}),
        "short_cascade": cascade_results.get("short_cascade", {})
    }
    
    return adapted_results

def optimize_target_price_ranges(asset, liquidation_analysis, clusters, cascade_probabilities, orderbook=None):
    """Bridge to our price targeting module"""
    current_price = liquidation_analysis.get('current_price', 0)
    
    # Get price targets using our module
    price_targets = generate_price_targets(
        clusters,
        cascade_probabilities,
        current_price,
        asset=asset
    )
    
    # Return in expected format
    return price_targets

def calculate_range_consistency(clusters, current_price):
    """Calculate the consistency of liquidation ranges"""
    # Basic implementation to satisfy the import
    if not clusters:
        return 0.5
    
    range_consistency = 0.0
    
    # Get all clusters
    all_clusters = []
    if 'long_clusters' in clusters:
        all_clusters.extend(clusters['long_clusters'])
    if 'short_clusters' in clusters:
        all_clusters.extend(clusters['short_clusters'])
    
    if not all_clusters:
        return 0.5
    
    # Calculate consistency based on cluster sizes and distances
    sizes = [cluster.get('size', 0) for cluster in all_clusters]
    
    if not sizes or sum(sizes) == 0:
        return 0.5
    
    # Higher consistency when cluster sizes are more evenly distributed
    # and when clusters are closer to current price
    largest_size = max(sizes) if sizes else 0
    if largest_size > 0:
        size_ratio = sum(sizes) / (len(sizes) * largest_size)
        range_consistency = size_ratio
    else:
        range_consistency = 0.5
    
    return min(0.95, max(0.05, range_consistency))

def calculate_directional_strength(clusters, cascade_probabilities):
    """Calculate the directional strength of the market"""
    # Basic implementation to satisfy the import
    if not clusters or not cascade_probabilities:
        return 0.3
    
    # Get probabilities
    long_prob = cascade_probabilities.get('long_cascade', {}).get('probability', 0)
    short_prob = cascade_probabilities.get('short_cascade', {}).get('probability', 0)
    
    # Calculate imbalance between long and short probabilities
    total_prob = long_prob + short_prob
    if total_prob < 0.1:
        return 0.3  # Low overall probability = low directional strength
    
    # Calculate imbalance - higher means stronger direction
    imbalance = abs(long_prob - short_prob) / max(0.1, total_prob)
    
    # Scale to a reasonable range
    directional_strength = 0.3 + (imbalance * 0.6)
    
    return min(0.95, max(0.05, directional_strength))

def ensure_liquidation_format(liquidation_data):
    """Ensure liquidation data is in the expected format"""
    # Simple passthrough function to satisfy the import
    return liquidation_data
