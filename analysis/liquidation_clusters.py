#!/usr/bin/env python
"""
Liquidation Clustering Module
----------------------------
Identifies clusters of liquidation positions and analyzes their properties.
"""

import os
import sys
import math
from datetime import datetime

# Add parent directory to path to allow imports from root after moving to analysis/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Define project root for consistent file path handling
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def identify_liquidation_clusters(positions, current_price, asset="UNKNOWN", debug=False, orderbook_data=None):
    """
    Identify clusters of liquidation positions using density-based approach
    
    Args:
        positions: Dictionary with 'long' and 'short' position lists
        current_price: Current market price
        asset: Asset symbol
        debug: Whether to include debug information
        orderbook_data: Optional orderbook depth data for evaluating market impact
        
    Returns:
        Dictionary with identified clusters and metadata
    """
    # Initialize result structure
    clusters = {
        "asset": asset,
        "current_price": current_price,
        "timestamp": datetime.now().isoformat(),
        "long_clusters": [],
        "short_clusters": []
    }
    
    # Process long positions
    long_clusters = find_clusters(positions["long"], current_price, direction="long", debug=debug, orderbook_data=orderbook_data)
    clusters["long_clusters"] = long_clusters
    
    # Process short positions
    short_clusters = find_clusters(positions["short"], current_price, direction="short", debug=debug, orderbook_data=orderbook_data)
    clusters["short_clusters"] = short_clusters
    
    # Calculate metadata about the clusters
    clusters["metadata"] = {
        "long_count": len(long_clusters),
        "short_count": len(short_clusters),
        "total_count": len(long_clusters) + len(short_clusters),
        "price_range": {
            "min": min([current_price * 0.5] + 
                     [c["center_price"] for c in long_clusters] + 
                     [c["center_price"] for c in short_clusters]),
            "max": max([current_price * 1.5] + 
                     [c["center_price"] for c in long_clusters] + 
                     [c["center_price"] for c in short_clusters])
        }
    }
    
    return clusters

def find_clusters(positions, current_price, direction="long", debug=False, orderbook_data=None):
    """
    Find clusters in a set of positions
    
    Args:
        positions: List of position dictionaries
        current_price: Current market price
        direction: 'long' or 'short'
        debug: Whether to include debug information
        orderbook_data: Optional orderbook depth data for assessing market impact
        
    Returns:
        List of cluster dictionaries
    """
    if not positions:
        return []
        
    # Sort positions by price
    positions.sort(key=lambda x: x["price"])
    
    # Parameters for clustering
    min_cluster_size = 2  # Minimum positions to form a cluster
    price_threshold_pct = 2.0  # % of current price to consider as same cluster
    price_threshold = current_price * price_threshold_pct / 100
    
    # Parameters for size-based filtering
    min_cluster_size_usd = 100  # Minimum total size for any valid cluster
    min_single_position_size = 500  # Default minimum for single positions, may be adjusted dynamically
    
    if debug:
        print(f"Using price threshold of {price_threshold} ({price_threshold_pct}% of {current_price})")
    
    # Initialize clusters
    clusters = []
    
    if not positions:
        return clusters
        
    current_cluster = {
        "positions": [positions[0]],
        "center_price": positions[0]["price"],
        "total_size": positions[0]["size"],
        "price_range": [positions[0]["price"], positions[0]["price"]]
    }
    
    # Group positions into clusters based on price proximity
    for pos in positions[1:]:
        # If this position is close enough to the current cluster's center
        if abs(pos["price"] - current_cluster["center_price"]) <= price_threshold:
            # Add to current cluster
            current_cluster["positions"].append(pos)
            current_cluster["total_size"] += pos["size"]
            
            # Update price range
            current_cluster["price_range"][0] = min(current_cluster["price_range"][0], pos["price"])
            current_cluster["price_range"][1] = max(current_cluster["price_range"][1], pos["price"])
            
            # Recalculate center as weighted average
            total_weight = sum(p["size"] for p in current_cluster["positions"])
            current_cluster["center_price"] = sum(p["price"] * p["size"] for p in current_cluster["positions"]) / total_weight
        else:
            # Determine if cluster meets our criteria to be included
            should_include = False
            
            # Criteria 1: Has enough positions (traditional clustering)
            if len(current_cluster["positions"]) >= min_cluster_size and current_cluster["total_size"] >= min_cluster_size_usd:
                should_include = True
            # Criteria 2: Single position with significant market impact potential
            elif len(current_cluster["positions"]) == 1:
                # Check if it meets minimum size
                if current_cluster["total_size"] >= min_single_position_size:
                    # Determine dynamic threshold if orderbook data is available
                    if orderbook_data:
                        try:
                            # Evaluate position against liquidity at this price level
                            position_price = current_cluster["center_price"]
                            
                            # For longs (looking at bids)
                            if direction == "long":
                                if "bid_liquidity" in orderbook_data:
                                    # Find closest price level
                                    liquidity_levels = orderbook_data["bid_liquidity"]
                                    closest_level = min(liquidity_levels.keys(), 
                                                      key=lambda x: abs(float(x) - position_price))
                                    level_liquidity = liquidity_levels[closest_level]
                                    
                                    # If position is at least 5% of liquidity, it's significant
                                    if current_cluster["total_size"] >= level_liquidity * 0.05:
                                        should_include = True
                                        if debug:
                                            print(f"Single position {current_cluster['total_size']} at {position_price} is significant (≥5% of {level_liquidity} liquidity)")
                            # For shorts (looking at asks)
                            else:  # direction == "short"
                                if "ask_liquidity" in orderbook_data:
                                    # Find closest price level
                                    liquidity_levels = orderbook_data["ask_liquidity"]
                                    closest_level = min(liquidity_levels.keys(), 
                                                      key=lambda x: abs(float(x) - position_price))
                                    level_liquidity = liquidity_levels[closest_level]
                                    
                                    # If position is at least 5% of liquidity, it's significant
                                    if current_cluster["total_size"] >= level_liquidity * 0.05:
                                        should_include = True
                                        if debug:
                                            print(f"Single position {current_cluster['total_size']} at {position_price} is significant (≥5% of {level_liquidity} liquidity)")
                        except Exception as e:
                            if debug:
                                print(f"Error evaluating single position liquidity impact: {e}")
                    
                    # As a fallback, we'll still include extremely large positions that would likely impact any market
                    # This is just a safety net for when orderbook data isn't available or has issues
                    if current_cluster["total_size"] >= min_single_position_size * 10:  # 5000$+
                        should_include = True
                        if debug:
                            print(f"Including very large single position: {current_cluster['total_size']} (≥{min_single_position_size * 10})")
            
            # Include the cluster if it meets our criteria
            if should_include:
                finalize_cluster(current_cluster, current_price, direction, positions, debug)
                clusters.append(current_cluster)
            
            # Start a new cluster with this position
            current_cluster = {
                "positions": [pos],
                "center_price": pos["price"],
                "total_size": pos["size"],
                "price_range": [pos["price"], pos["price"]]
            }
    
    # Determine if the last cluster meets our criteria to be included
    should_include = False
    
    # Criteria 1: Has enough positions (traditional clustering)
    if len(current_cluster["positions"]) >= min_cluster_size and current_cluster["total_size"] >= min_cluster_size_usd:
        should_include = True
    # Criteria 2: Single position with significant market impact potential
    elif len(current_cluster["positions"]) == 1:
        # Check if it meets minimum size
        if current_cluster["total_size"] >= min_single_position_size:
            # Determine dynamic threshold if orderbook data is available
            if orderbook_data:
                try:
                    # Evaluate position against liquidity at this price level
                    position_price = current_cluster["center_price"]
                    
                    # For longs (looking at bids)
                    if direction == "long":
                        if "bid_liquidity" in orderbook_data:
                            # Find closest price level
                            liquidity_levels = orderbook_data["bid_liquidity"]
                            closest_level = min(liquidity_levels.keys(), 
                                              key=lambda x: abs(float(x) - position_price))
                            level_liquidity = liquidity_levels[closest_level]
                            
                            # If position is at least 5% of liquidity, it's significant
                            if current_cluster["total_size"] >= level_liquidity * 0.05:
                                should_include = True
                                if debug:
                                    print(f"Single position {current_cluster['total_size']} at {position_price} is significant (≥5% of {level_liquidity} liquidity)")
                    # For shorts (looking at asks)
                    else:  # direction == "short"
                        if "ask_liquidity" in orderbook_data:
                            # Find closest price level
                            liquidity_levels = orderbook_data["ask_liquidity"]
                            closest_level = min(liquidity_levels.keys(), 
                                              key=lambda x: abs(float(x) - position_price))
                            level_liquidity = liquidity_levels[closest_level]
                            
                            # If position is at least 5% of liquidity, it's significant
                            if current_cluster["total_size"] >= level_liquidity * 0.05:
                                should_include = True
                                if debug:
                                    print(f"Single position {current_cluster['total_size']} at {position_price} is significant (≥5% of {level_liquidity} liquidity)")
                except Exception as e:
                    if debug:
                        print(f"Error evaluating single position liquidity impact: {e}")
            
            # As a fallback, we'll still include extremely large positions that would likely impact any market
            # This is just a safety net for when orderbook data isn't available or has issues
            if current_cluster["total_size"] >= min_single_position_size * 10:  # 5000$+
                should_include = True
                if debug:
                    print(f"Including very large single position: {current_cluster['total_size']} (≥{min_single_position_size * 10})")
    
    # Include the cluster if it meets our criteria
    if should_include:
        finalize_cluster(current_cluster, current_price, direction, positions, debug)
        clusters.append(current_cluster)
    
    # Sort clusters by total size (largest first)
    clusters.sort(key=lambda x: x["total_size"], reverse=True)
    
    return clusters

def finalize_cluster(cluster, current_price, direction, all_positions, debug=False):
    """
    Calculate additional metrics for a cluster
    
    Args:
        cluster: Cluster dictionary to finalize
        current_price: Current market price
        direction: 'long' or 'short'
        all_positions: All positions for relative size calculation
        debug: Whether to include debug information
        
    Returns:
        Updated cluster dictionary
    """
    # Calculate distance from current price as percentage
    price_distance_pct = (cluster["center_price"] - current_price) / current_price * 100
    cluster["price_distance_pct"] = price_distance_pct
    
    # Calculate relative size compared to largest known position
    max_size = max([p["size"] for p in all_positions]) if all_positions else 1
    cluster["relative_size"] = min(1.0, cluster["total_size"] / max_size)
    
    # Calculate tightness of the cluster (lower = tighter)
    price_range = cluster["price_range"][1] - cluster["price_range"][0]
    cluster["tightness"] = 1.0 - min(1.0, price_range / (current_price * 0.05))
    
    # Calculate trigger probability based on distance from current price
    # For long positions (triggered on price drop), closer = higher probability
    # For short positions (triggered on price rise), closer = higher probability
    if direction == "long":
        # Long positions get liquidated when price drops
        # If price is already below liquidation price, probability is high
        if cluster["center_price"] >= current_price:
            # Price needs to drop to trigger
            price_change_needed = (cluster["center_price"] - current_price) / current_price
            # Higher price change needed = lower probability
            trigger_prob = max(0.05, min(0.95, 1.0 - 10 * price_change_needed))
        else:
            # Price already below liquidation point
            trigger_prob = 0.95
    else:
        # Short positions get liquidated when price rises
        # If price is already above liquidation price, probability is high
        if cluster["center_price"] <= current_price:
            # Price needs to rise to trigger
            price_change_needed = (current_price - cluster["center_price"]) / current_price
            # Higher price change needed = lower probability
            trigger_prob = max(0.05, min(0.95, 1.0 - 10 * price_change_needed))
        else:
            # Price already above liquidation point
            trigger_prob = 0.95
            
    cluster["trigger_probability"] = trigger_prob
    cluster["direction"] = direction
    cluster["position_count"] = len(cluster["positions"])
    
    # Remove positions from final output to reduce size
    if not debug:
        cluster.pop("positions", None)
        
    return cluster
