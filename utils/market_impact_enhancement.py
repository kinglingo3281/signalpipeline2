#!/usr/bin/env python
"""
Market Impact Enhancement Module

This module extends the functionality of the cluster analysis system by:
1. Calculating market impact and absorption difficulty based on orderbook data
2. Ensuring that explanatory notes for parameters are properly included in the output

Usage:
    from market_impact_enhancement import enhance_cluster_analysis
    
    # After running identify_liquidation_clusters
    clusters = identify_liquidation_clusters(...)
    
    # After running calculate_cascade_probability 
    cascade_prob = calculate_cascade_probability(...)
    
    # Apply the enhancements
    enhanced_clusters = enhance_cluster_analysis(clusters, orderbook)
    enhanced_cascade = enhance_cascade_probability(cascade_prob, orderbook)
"""

import os
import sys
import math
import json

# Add parent directory to path to allow imports from root after moving to utils/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Define project root for consistent file paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def calculate_absorption_difficulty(price_level, size, orderbook, direction="long"):
    """
    Calculate how difficult it would be to absorb a liquidation based on orderbook depth.
    
    Args:
        price_level: The price level of the liquidation
        size: The size of the liquidation in contracts
        orderbook: Dictionary with bids and asks
        direction: "long" for long liquidation (downward), "short" for short liquidation (upward)
        
    Returns:
        Absorption difficulty score between 0.1 and 1.0
    """
    if not orderbook or not isinstance(orderbook, dict):
        return 0.5  # Default if no orderbook data
    
    # Convert size to notional value (estimate using price level)
    notional_value = size * price_level
    
    try:
        if direction == "long":
            # For long liquidations, check the bid side liquidity
            if "bids" not in orderbook or not orderbook["bids"]:
                return 0.5
                
            # Find nearby bid liquidity (within 0.5% of price level)
            nearby_liquidity = 0
            price_threshold = price_level * 0.995  # 0.5% below price level
            
            for bid_price, bid_size in orderbook["bids"]:
                if bid_price >= price_threshold:
                    nearby_liquidity += bid_size * bid_price
        else:
            # For short liquidations, check the ask side liquidity
            if "asks" not in orderbook or not orderbook["asks"]:
                return 0.5
                
            # Find nearby ask liquidity (within 0.5% of price level)
            nearby_liquidity = 0
            price_threshold = price_level * 1.005  # 0.5% above price level
            
            for ask_price, ask_size in orderbook["asks"]:
                if ask_price <= price_threshold:
                    nearby_liquidity += ask_size * ask_price
        
        # Calculate absorption difficulty
        if nearby_liquidity > 0:
            # Ratio of liquidation value to available liquidity
            absorption_difficulty = min(1.0, notional_value / nearby_liquidity)
            # Scale between 0.1 and 1.0
            return max(0.1, absorption_difficulty)
        else:
            return 0.9  # High difficulty if no nearby liquidity
    except Exception as e:
        print(f"Error calculating absorption difficulty: {e}")
        return 0.5  # Default on error


def enhance_cluster_analysis(clusters, orderbook=None):
    """
    Enhance the clusters with market impact data and ensure notes are included.
    
    Args:
        clusters: Output from identify_liquidation_clusters
        orderbook: Optional orderbook data for enhanced analysis
        
    Returns:
        Enhanced clusters with market impact and notes
    """
    if not clusters or not isinstance(clusters, dict):
        return clusters
    
    # Make a copy to avoid modifying the original data
    enhanced_clusters = clusters.copy()
    
    # Process long and short clusters
    for cluster_type in ["long_clusters", "short_clusters"]:
        if cluster_type not in enhanced_clusters:
            continue
            
        for cluster in enhanced_clusters[cluster_type]:
            # Ensure all notes are properly set
            
            # 1. Trigger probability note
            if "trigger_probability" in cluster and "trigger_probability_note" not in cluster:
                # Calculate the real value
                distance_from_price = cluster.get("distance_from_price", 0)
                current_price = clusters.get("current_price", 10000)  # Default for safety
                real_value = 0.9 - distance_from_price / current_price
                
                if real_value > 0.8:
                    cluster["trigger_probability_note"] = f"capped at 0.8, real value: {real_value:.3f}"
                else:
                    cluster["trigger_probability_note"] = "dynamic value"
            
            # 2. Dynamic threshold note
            if "dynamic_threshold_used" in cluster and "dynamic_threshold_note" not in cluster:
                threshold = cluster["dynamic_threshold_used"]
                tier = "unknown"
                if threshold == 0.05:
                    tier = "low volatility (<0.05%)"
                elif threshold == 0.10:
                    tier = "medium volatility (<0.1%)"
                elif threshold == 0.15:
                    tier = "high volatility (<0.2%)"
                elif threshold == 0.20:
                    tier = "extreme volatility (<0.5%)"
                
                cluster["dynamic_threshold_note"] = f"volatility tier: {tier}, base_threshold: {threshold}"
            
            # Calculate market impact and absorption difficulty if orderbook data is available
            if orderbook:
                price_level = cluster.get("price_level", 0)
                size = cluster.get("size", 0)
                direction = cluster.get("direction", "long")
                
                # Calculate absorption difficulty based on orderbook depth
                absorption_difficulty = calculate_absorption_difficulty(
                    price_level, 
                    size, 
                    orderbook, 
                    direction=direction
                )
                
                # Add to cluster data
                if "market_impact" not in cluster:
                    cluster["market_impact"] = {}
                
                cluster["market_impact"]["absorption_difficulty"] = absorption_difficulty
    
    return enhanced_clusters


def enhance_cascade_probability(cascade_prob, orderbook=None):
    """
    Enhance the cascade probability results with market impact data and notes.
    
    Args:
        cascade_prob: Output from calculate_cascade_probability
        orderbook: Optional orderbook data for enhanced analysis
        
    Returns:
        Enhanced cascade probability with market impact and notes
    """
    if not cascade_prob or not isinstance(cascade_prob, dict):
        return cascade_prob
    
    # Make a copy to avoid modifying the original data
    enhanced_cascade = cascade_prob.copy()
    
    # Process trigger zones
    if "trigger_zones" in enhanced_cascade:
        for zone in enhanced_cascade["trigger_zones"]:
            # Ensure proximity factor note is set
            if "proximity_factor" in zone and "proximity_factor_note" not in zone:
                price_diff_pct = zone.get("distance_pct", 0)
                proximity_factor = zone.get("proximity_factor", 1.0)
                
                if price_diff_pct > 0:
                    zone["proximity_factor_note"] = f"dynamic: {proximity_factor:.3f}"
                else:
                    zone["proximity_factor_note"] = f"default 1.0, price_diff_pct: {price_diff_pct:.6f}%"
            
            # Ensure absorption factor note is set
            if "absorption_factor" in zone and "absorption_factor_note" not in zone:
                if zone.get("absorption_factor", 0.5) != 0.5:
                    zone["absorption_factor_note"] = "dynamic from market_impact"
                else:
                    zone["absorption_factor_note"] = "default 0.5, market_impact data not available"
    
    return enhanced_cascade


def apply_enhancements_to_analysis_result(analysis_result, orderbook=None):
    """
    Apply all enhancements to a complete analysis result.
    
    Args:
        analysis_result: Complete analysis result with clusters and cascade probability
        orderbook: Optional orderbook data for enhanced analysis
        
    Returns:
        Enhanced analysis result
    """
    if not analysis_result or not isinstance(analysis_result, dict):
        return analysis_result
    
    # Make a copy to avoid modifying the original data
    enhanced_result = analysis_result.copy()
    
    # Enhance clusters if present
    if "clusters" in enhanced_result:
        enhanced_result["clusters"] = enhance_cluster_analysis(
            enhanced_result["clusters"], 
            orderbook
        )
    
    # Enhance cascade probability if present
    if "cascade" in enhanced_result:
        enhanced_result["cascade"] = enhance_cascade_probability(
            enhanced_result["cascade"], 
            orderbook
        )
    
    # Enhance landscape components if present
    if "landscape" in enhanced_result:
        landscape = enhanced_result["landscape"]
        
        # Process imbalance, cascade, and targets if they exist
        for component in ["imbalance", "cascade", "targets"]:
            if component in landscape and isinstance(landscape[component], dict):
                # Process trigger zones if they exist
                if "trigger_zones" in landscape[component]:
                    enhanced_result["landscape"][component] = enhance_cascade_probability(
                        landscape[component], 
                        orderbook
                    )
    
    return enhanced_result


# Function to integrate with run_real_enhanced_analysis.py
def apply_enhancements_before_save(result, orderbook=None):
    """
    Function to be called right before saving the JSON output.
    
    Args:
        result: The complete analysis result to be saved
        orderbook: Optional orderbook data for enhanced analysis
        
    Returns:
        Enhanced result with all notes and market impact data
    """
    enhanced_result = apply_enhancements_to_analysis_result(result, orderbook)
    print("Market impact enhancements applied successfully.")
    return enhanced_result
