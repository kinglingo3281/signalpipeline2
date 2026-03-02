#!/usr/bin/env python
"""
Cascade Analysis Module
----------------------
Calculates cascade probabilities and identifies critical thresholds.
"""

import os
import sys
from datetime import datetime

# Add parent directory to path to allow imports from root after moving to analysis/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Define project root for consistent file path handling
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def calculate_cascade_probability(clusters, current_price, asset="UNKNOWN", debug=False):
    """
    Calculate the probability of cascading liquidations based on identified clusters
    
    Args:
        clusters: Dict containing liquidation clusters
        current_price: Current price of the asset
        asset: Asset symbol
        debug: Enable debug output
        
    Returns:
        Dict containing cascade probabilities and details
    """
    cascade = {
        "asset": asset,
        "current_price": current_price,
        "timestamp": datetime.now().isoformat(),
        "long_cascade": {
            "probability": 0.0,
            "risk_level": "LOW",
            "critical_threshold": None,
            "expected_price_impact": 0.0,
            "confidence": 0.0
        },
        "short_cascade": {
            "probability": 0.0,
            "risk_level": "LOW",
            "critical_threshold": None,
            "expected_price_impact": 0.0,
            "confidence": 0.0
        }
    }
    
    # Maximum realistic price impact as percentage of current price
    max_price_impact_percentage = 5.0
    
    # Process long liquidation clusters (price going down)
    if long_clusters := clusters.get("long_clusters", []):
        # First, filter out any clusters with unrealistic price levels
        valid_clusters = []
        for cluster in long_clusters:
            center_price = cluster.get("center_price", 0)
            # Only include clusters within 50% of current price
            if 0.5 * current_price <= center_price <= 1.5 * current_price:
                valid_clusters.append(cluster)
                
        if debug and len(valid_clusters) < len(long_clusters):
            print(f"Filtered out {len(long_clusters) - len(valid_clusters)} long clusters with unrealistic prices")
        
        # Sort clusters by total size (largest first)
        sorted_clusters = sorted(valid_clusters, key=lambda x: x.get("total_size", 0), reverse=True)
        
        # Estimate cascade probability based on cluster sizes and proximity
        total_size = sum(cluster.get("total_size", 0) for cluster in valid_clusters)
        total_proximity_weighted_size = 0
        
        # Find closest significant cluster for critical threshold
        closest_significant_cluster = None
        min_distance = float('inf')
        
        for cluster in sorted_clusters:
            size = cluster.get("total_size", 0)
            center_price = cluster.get("center_price", 0)
            
            # Calculate distance as a percentage of current price
            distance_pct = (current_price - center_price) / current_price * 100 if center_price > 0 else 0
            
            if debug:
                print(f"LONG CLUSTER: Size: {size}, Center: {center_price}, Distance: {distance_pct:.2f}%")
            
            # Skip clusters that are above current price (not relevant for long liquidations)
            if center_price >= current_price:
                continue
                
            # Consider distance factor - closer clusters have more impact
            # Use a more conservative proximity factor that decreases with distance
            proximity_factor = max(0.01, 1 / (1 + abs(distance_pct) / 3)) 
            proximity_weighted_size = size * proximity_factor
            total_proximity_weighted_size += proximity_weighted_size
            
            # Track closest significant cluster (for critical threshold)
            # A cluster is significant if it's at least 5% of total liquidation size
            if abs(distance_pct) < min_distance and size > total_size * 0.05:  
                min_distance = abs(distance_pct)
                closest_significant_cluster = cluster
        
        # Calculate cascade probability based on size and proximity
        # Normalize by a factor to keep probabilities in a realistic range
        size_factor = min(0.8, total_size / 10000) # Cap at 0.8
        proximity_factor = min(0.9, total_proximity_weighted_size / (total_size + 1)) # Avoid division by zero
        
        # Combine factors with appropriate weights
        cascade_prob = min(0.95, size_factor * 0.4 + proximity_factor * 0.6)
        
        # Determine risk level - more conservative thresholds
        risk_level = "LOW"
        if cascade_prob > 0.7:
            risk_level = "SEVERE"
        elif cascade_prob > 0.5:
            risk_level = "HIGH"
        elif cascade_prob > 0.25:
            risk_level = "MEDIUM"
        
        # Calculate expected price impact as a percentage of current price
        # This should be realistic - even severe liquidations rarely move price more than a few percent
        expected_impact = min(max_price_impact_percentage, cascade_prob * 2.0 + size_factor * 3.0)
        
        # Set critical threshold based on closest significant cluster
        critical_threshold = closest_significant_cluster.get("center_price") if closest_significant_cluster else None
        
        # Calculate confidence based on cluster quality and sample size
        confidence = min(0.9, 0.3 + (0.7 * min(1.0, len(valid_clusters) / 5)))
        
        # Update cascade data
        cascade["long_cascade"] = {
            "probability": cascade_prob,
            "risk_level": risk_level,
            "critical_threshold": critical_threshold,
            "expected_price_impact": expected_impact,
            "confidence": confidence
        }
    
    # Process short liquidation clusters (price going up)
    if short_clusters := clusters.get("short_clusters", []):
        # First, filter out any clusters with unrealistic price levels
        valid_clusters = []
        for cluster in short_clusters:
            center_price = cluster.get("center_price", 0)
            # Only include clusters within 50% of current price
            if 0.5 * current_price <= center_price <= 1.5 * current_price:
                valid_clusters.append(cluster)
                
        if debug and len(valid_clusters) < len(short_clusters):
            print(f"Filtered out {len(short_clusters) - len(valid_clusters)} short clusters with unrealistic prices")
        
        # Sort clusters by total size (largest first)
        sorted_clusters = sorted(valid_clusters, key=lambda x: x.get("total_size", 0), reverse=True)
        
        # Estimate cascade probability based on cluster sizes and proximity
        total_size = sum(cluster.get("total_size", 0) for cluster in valid_clusters)
        total_proximity_weighted_size = 0
        
        # Find closest significant cluster for critical threshold
        closest_significant_cluster = None
        min_distance = float('inf')
        
        for cluster in sorted_clusters:
            size = cluster.get("total_size", 0)
            center_price = cluster.get("center_price", 0)
            
            # Calculate distance as a percentage of current price
            distance_pct = (center_price - current_price) / current_price * 100 if center_price > 0 else 0
            
            if debug:
                print(f"SHORT CLUSTER: Size: {size}, Center: {center_price}, Distance: {distance_pct:.2f}%")
            
            # Skip clusters that are below current price (not relevant for short liquidations)
            if center_price <= current_price:
                continue
                
            # Consider distance factor - closer clusters have more impact
            # Use a more conservative proximity factor that decreases with distance
            proximity_factor = max(0.01, 1 / (1 + abs(distance_pct) / 3))
            proximity_weighted_size = size * proximity_factor
            total_proximity_weighted_size += proximity_weighted_size
            
            # Track closest significant cluster (for critical threshold)
            # A cluster is significant if it's at least 5% of total liquidation size
            if abs(distance_pct) < min_distance and size > total_size * 0.05:  
                min_distance = abs(distance_pct)
                closest_significant_cluster = cluster
        
        # Calculate cascade probability based on size and proximity
        # Normalize by a factor to keep probabilities in a realistic range
        size_factor = min(0.8, total_size / 10000) # Cap at 0.8
        proximity_factor = min(0.9, total_proximity_weighted_size / (total_size + 1)) # Avoid division by zero
        
        # Combine factors with appropriate weights
        cascade_prob = min(0.95, size_factor * 0.4 + proximity_factor * 0.6)
        
        # Determine risk level - more conservative thresholds
        risk_level = "LOW"
        if cascade_prob > 0.7:
            risk_level = "SEVERE"
        elif cascade_prob > 0.5:
            risk_level = "HIGH"
        elif cascade_prob > 0.25:
            risk_level = "MEDIUM"
        
        # Calculate expected price impact as a percentage of current price
        # This should be realistic - even severe liquidations rarely move price more than a few percent
        expected_impact = min(max_price_impact_percentage, cascade_prob * 2.0 + size_factor * 3.0)
        
        # Set critical threshold based on closest significant cluster
        critical_threshold = closest_significant_cluster.get("center_price") if closest_significant_cluster else None
        
        # Calculate confidence based on cluster quality and sample size
        confidence = min(0.9, 0.3 + (0.7 * min(1.0, len(valid_clusters) / 5)))
        
        # Update cascade data
        cascade["short_cascade"] = {
            "probability": cascade_prob,
            "risk_level": risk_level,
            "critical_threshold": critical_threshold,
            "expected_price_impact": expected_impact,
            "confidence": confidence
        }
    
    return cascade

def simulate_cascade_paths(clusters, current_price):
    """
    Simulate possible cascade paths to predict price trajectories
    
    Args:
        clusters: Dictionary with long and short clusters
        current_price: Current market price
        
    Returns:
        Dictionary with possible cascade paths and their probabilities
    """
    paths = {
        "upward": [],   # Paths for upward price movement
        "downward": []  # Paths for downward price movement
    }
    
    # Sort long and short clusters by price
    long_clusters = sorted(clusters.get("long_clusters", []), key=lambda x: x["center_price"])
    short_clusters = sorted(clusters.get("short_clusters", []), key=lambda x: x["center_price"], reverse=True)
    
    # Simulate downward paths (long liquidations)
    if long_clusters:
        path = {
            "starting_price": current_price,
            "steps": [],
            "cumulative_impact": 0,
            "probability": 0.5  # Default probability
        }
        
        current_step_price = current_price
        cumulative_impact = 0
        cumulative_prob = 1.0
        
        for i, cluster in enumerate(long_clusters):
            # Only include clusters above the current price (must be hit to trigger)
            if cluster["center_price"] <= current_step_price:
                continue
                
            # Calculate impact of this cluster
            step_impact = min(5.0, cluster["total_size"] / 1000) if cluster["total_size"] > 0 else 0
            cumulative_impact += step_impact
            
            # Update current price after liquidation
            next_price = current_step_price * (1 - step_impact / 100)
            
            # Calculate probability of this step (declining with each step)
            step_prob = cluster.get("trigger_probability", 0.5) * (0.8 ** i)
            cumulative_prob *= step_prob
            
            # Add step to path
            path["steps"].append({
                "price_level": cluster["center_price"],
                "next_price": next_price,
                "impact": step_impact,
                "probability": step_prob
            })
            
            current_step_price = next_price
        
        # Finalize path
        if path["steps"]:
            path["ending_price"] = current_step_price
            path["cumulative_impact"] = cumulative_impact
            path["probability"] = min(0.95, cumulative_prob)
            paths["downward"].append(path)
    
    # Simulate upward paths (short liquidations)
    if short_clusters:
        path = {
            "starting_price": current_price,
            "steps": [],
            "cumulative_impact": 0,
            "probability": 0.5  # Default probability
        }
        
        current_step_price = current_price
        cumulative_impact = 0
        cumulative_prob = 1.0
        
        for i, cluster in enumerate(short_clusters):
            # Only include clusters below the current price (must be hit to trigger)
            if cluster["center_price"] >= current_step_price:
                continue
                
            # Calculate impact of this cluster
            step_impact = min(5.0, cluster["total_size"] / 1000) if cluster["total_size"] > 0 else 0
            cumulative_impact += step_impact
            
            # Update current price after liquidation
            next_price = current_step_price * (1 + step_impact / 100)
            
            # Calculate probability of this step (declining with each step)
            step_prob = cluster.get("trigger_probability", 0.5) * (0.8 ** i)
            cumulative_prob *= step_prob
            
            # Add step to path
            path["steps"].append({
                "price_level": cluster["center_price"],
                "next_price": next_price,
                "impact": step_impact,
                "probability": step_prob
            })
            
            current_step_price = next_price
        
        # Finalize path
        if path["steps"]:
            path["ending_price"] = current_step_price
            path["cumulative_impact"] = cumulative_impact
            path["probability"] = min(0.95, cumulative_prob)
            paths["upward"].append(path)
    
    return paths
