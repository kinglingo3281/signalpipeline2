#!/usr/bin/env python
"""
Risk Analyzer Module
------------------
Integrates orderbook depth data with liquidation clusters to create
composite risk scores and dynamic stop loss recommendations.
"""

import os
import sys
import math
import numpy as np
from datetime import datetime

# Add parent directory to path to allow imports from root after moving to analysis/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Define project root for consistent file path handling
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class RiskAnalyzer:
    """Analyzes trading risk by combining orderbook and liquidation data"""
    
    def __init__(self, debug=False):
        self.debug = debug
    
    def calculate_composite_risk_scores(self, clusters, orderbook_analysis, current_price, asset="UNKNOWN"):
        """
        Calculate composite risk scores by integrating orderbook depth with liquidation clusters
        
        Args:
            clusters: Dict containing liquidation clusters
            orderbook_analysis: Dict containing orderbook analysis data
            current_price: Current price of the asset
            asset: Asset symbol
            
        Returns:
            Dict containing enhanced clusters with composite risk scores
        """
        if not clusters or not orderbook_analysis:
            if self.debug:
                print(f"Missing data for risk analysis: clusters={bool(clusters)}, orderbook={bool(orderbook_analysis)}")
            return clusters
            
        # Make a deep copy of clusters to avoid modifying the original
        enhanced_clusters = {
            "asset": clusters.get("asset", asset),
            "current_price": clusters.get("current_price", current_price),
            "timestamp": datetime.now().isoformat(),
            "long_clusters": [],
            "short_clusters": [],
            "metadata": clusters.get("metadata", {})
        }
        
        # Extract data we need from orderbook
        bid_liquidity = orderbook_analysis.get("bid_liquidity", {})
        ask_liquidity = orderbook_analysis.get("ask_liquidity", {})
        long_risk = orderbook_analysis.get("long_risk", {})
        short_risk = orderbook_analysis.get("short_risk", {})
        high_risk_zones = orderbook_analysis.get("high_risk_zones", {"long": [], "short": []})
        
        # Process long clusters
        long_clusters = clusters.get("long_clusters", [])
        for cluster in long_clusters:
            # Get cluster price - check various field names that might be used
            price_level = cluster.get("price_level", 
                         cluster.get("center_price", 
                         cluster.get("liquidation_price", 0)))
            
            # Skip invalid clusters
            if price_level == 0:
                continue
                
            # Create enhanced cluster with original data
            enhanced_cluster = dict(cluster)
            
            # Calculate orderbook risk for this cluster
            orderbook_risk = self._calculate_orderbook_risk(
                price_level, 
                long_risk, 
                high_risk_zones.get("long", []),
                "long"
            )
            
            # Calculate liquidity absorption risk
            liquidity_risk = self._calculate_liquidity_absorption_risk(
                price_level,
                enhanced_cluster.get("size", enhanced_cluster.get("total_size", 0)),
                bid_liquidity, 
                "long"
            )
            
            # Calculate composite risk score
            composite_risk = self._calculate_composite_risk(
                orderbook_risk,
                liquidity_risk,
                price_level,
                current_price
            )
            
            # Add risk metrics to enhanced cluster
            enhanced_cluster["orderbook_risk"] = orderbook_risk
            enhanced_cluster["liquidity_risk"] = liquidity_risk
            enhanced_cluster["composite_risk"] = composite_risk
            
            # Add dynamic stop loss recommendation
            enhanced_cluster["dynamic_stop_loss"] = self._calculate_dynamic_stop_loss(
                price_level, 
                current_price, 
                composite_risk,
                "long",
                bid_liquidity
            )
            
            enhanced_clusters["long_clusters"].append(enhanced_cluster)
        
        # Process short clusters
        short_clusters = clusters.get("short_clusters", [])
        for cluster in short_clusters:
            # Get cluster price - check various field names that might be used
            price_level = cluster.get("price_level", 
                         cluster.get("center_price", 
                         cluster.get("liquidation_price", 0)))
            
            # Skip invalid clusters
            if price_level == 0:
                continue
                
            # Create enhanced cluster with original data
            enhanced_cluster = dict(cluster)
            
            # Calculate orderbook risk for this cluster
            orderbook_risk = self._calculate_orderbook_risk(
                price_level, 
                short_risk, 
                high_risk_zones.get("short", []),
                "short"
            )
            
            # Calculate liquidity absorption risk
            liquidity_risk = self._calculate_liquidity_absorption_risk(
                price_level,
                enhanced_cluster.get("size", enhanced_cluster.get("total_size", 0)),
                ask_liquidity, 
                "short"
            )
            
            # Calculate composite risk score
            composite_risk = self._calculate_composite_risk(
                orderbook_risk,
                liquidity_risk,
                price_level,
                current_price
            )
            
            # Add risk metrics to enhanced cluster
            enhanced_cluster["orderbook_risk"] = orderbook_risk
            enhanced_cluster["liquidity_risk"] = liquidity_risk
            enhanced_cluster["composite_risk"] = composite_risk
            
            # Add dynamic stop loss recommendation
            enhanced_cluster["dynamic_stop_loss"] = self._calculate_dynamic_stop_loss(
                price_level, 
                current_price, 
                composite_risk,
                "short",
                ask_liquidity
            )
            
            enhanced_clusters["short_clusters"].append(enhanced_cluster)
            
        # Add metadata
        enhanced_clusters["metadata"]["has_enhanced_risk"] = True
        enhanced_clusters["metadata"]["risk_analysis_version"] = "1.0"
        
        return enhanced_clusters
    
    def _calculate_orderbook_risk(self, price_level, risk_data, high_risk_zones, direction):
        """Calculate orderbook risk based on pre-calculated risk data"""
        # Default risk values
        risk_score = 0.1  # Base risk score
        
        # Check if the price level matches any known risk zones
        for zone in high_risk_zones:
            zone_price = zone.get("price", 0)
            if abs(price_level - zone_price) / price_level < 0.01:  # Within 1% of the risk zone
                risk_score = max(risk_score, zone.get("risk_score", 0))
                
        # Check direct risk data if available
        str_price = str(price_level)
        if str_price in risk_data:
            zone_data = risk_data[str_price]
            risk_score = max(risk_score, zone_data.get("risk_score", 0))
        
        # Normalize to 0-1 range
        return min(max(risk_score, 0), 1)
    
    def _calculate_liquidity_absorption_risk(self, price_level, cluster_size, liquidity_data, direction):
        """Calculate risk based on how much liquidity is available to absorb this cluster"""
        if cluster_size <= 0:
            return 0.1  # Minimal risk for zero-size clusters
            
        # Find nearby liquidity levels
        nearby_liquidity = 0
        price_tolerance = 0.01  # Look within 1% of price
        
        for price_str, size in liquidity_data.items():
            try:
                price = float(price_str)
                if abs(price - price_level) / price_level <= price_tolerance:
                    nearby_liquidity += size
            except (ValueError, TypeError):
                continue
        
        # Calculate absorption ratio
        if nearby_liquidity > 0:
            absorption_ratio = min(cluster_size / nearby_liquidity, 10)  # Cap at 10x
            # Transform to 0-1 risk score (higher ratio = higher risk)
            # 0.2 = low risk (lots of liquidity)
            # 0.5 = medium risk (roughly equal)
            # 0.8+ = high risk (little liquidity)
            risk_score = 0.2 + (min(absorption_ratio, 2) / 2 * 0.6)
        else:
            # No liquidity found nearby - high risk
            risk_score = 0.9
            
        return risk_score
    
    def _calculate_composite_risk(self, orderbook_risk, liquidity_risk, price_level, current_price):
        """Calculate composite risk score combining multiple risk factors"""
        # Calculate price distance factor (closer to current price = higher risk)
        price_distance_pct = abs(price_level - current_price) / current_price
        distance_factor = math.exp(-5 * price_distance_pct)  # Exponential decay with distance
        
        # Weighted average of risk components
        composite_risk = (
            orderbook_risk * 0.4 +       # 40% weight to orderbook risk
            liquidity_risk * 0.4 +       # 40% weight to liquidity absorption risk
            distance_factor * 0.2        # 20% weight to price proximity
        )
        
        return composite_risk
    
    def _calculate_dynamic_stop_loss(self, price_level, current_price, risk_score, direction, liquidity_data):
        """Calculate dynamic stop loss based on risk and liquidity distribution"""
        # Start with a default stop loss percentage based on risk
        base_stop_pct = 0.02  # Default 2% stop loss
        
        # Adjust based on risk score - higher risk means wider stop
        risk_adjustment = 0.01 + (risk_score * 0.05)  # 1-6% range based on risk
        
        # Find significant liquidity levels that could serve as natural stop loss points
        liquidity_levels = []
        for price_str, size in liquidity_data.items():
            try:
                price = float(price_str)
                # Only consider levels between current price and target
                if direction == "long":
                    if price < current_price and price > price_level:
                        liquidity_levels.append((price, size))
                else:  # Short direction
                    if price > current_price and price < price_level:
                        liquidity_levels.append((price, size))
            except (ValueError, TypeError):
                continue
                
        # Sort liquidity levels by size (largest first)
        liquidity_levels.sort(key=lambda x: x[1], reverse=True)
        
        # Find best stop loss candidate
        if liquidity_levels:
            # Take largest liquidity level as potential stop loss point
            stop_price = liquidity_levels[0][0]
            
            # Calculate corresponding percentage
            if direction == "long":
                stop_pct = (current_price - stop_price) / current_price
            else:
                stop_pct = (stop_price - current_price) / current_price
                
            # If this natural level is too aggressive, fall back to risk-based calculation
            if stop_pct < 0.015:  # Minimum 1.5% stop loss
                stop_pct = risk_adjustment
            
            # Cap maximum stop loss percentage
            stop_pct = min(stop_pct, 0.1)  # Maximum 10% stop loss
        else:
            # No significant liquidity levels found, use risk-based approach
            stop_pct = max(0.015, risk_adjustment)  # Ensure minimum 1.5% stop
            
        # Calculate final stop loss price
        if direction == "long":
            stop_price = current_price * (1 - stop_pct)
        else:
            stop_price = current_price * (1 + stop_pct)
            
        return {
            "price": stop_price,
            "percentage": stop_pct,
            "risk_based": not bool(liquidity_levels),
            "explanation": f"{'Risk' if not liquidity_levels else 'Liquidity'}-based stop loss at {stop_pct:.2%} from entry"
        }
    
    def generate_risk_enhanced_trade_recommendations(self, price_targets, enhanced_clusters, orderbook_analysis):
        """
        Generate enhanced trade recommendations that incorporate risk analysis
        
        Args:
            price_targets: Original price targets from price_targeting module
            enhanced_clusters: Clusters with composite risk scores
            orderbook_analysis: Orderbook analysis data
            
        Returns:
            Enhanced price targets with risk-adjusted stops and risk metrics
        """
        if not price_targets or not enhanced_clusters:
            return price_targets
            
        # Make a copy of the price targets to avoid modifying the original
        enhanced_targets = dict(price_targets)
        
        # Enhance long targets
        long_targets = enhanced_targets.get("long_targets", [])
        for target in long_targets:
            # Find matching cluster if any
            target_price = target.get("target_price", 0)
            
            matching_cluster = None
            for cluster in enhanced_clusters.get("short_clusters", []):
                cluster_price = cluster.get("price_level", cluster.get("center_price", 0))
                if abs(cluster_price - target_price) / target_price < 0.03:  # Within 3%
                    matching_cluster = cluster
                    break
            
            if matching_cluster:
                # Add risk metrics from the cluster
                target["orderbook_risk"] = matching_cluster.get("orderbook_risk", 0)
                target["liquidity_risk"] = matching_cluster.get("liquidity_risk", 0)
                target["composite_risk"] = matching_cluster.get("composite_risk", 0)
                
                # Update stop loss if dynamic stop is available
                if "dynamic_stop_loss" in matching_cluster:
                    dynamic_stop = matching_cluster["dynamic_stop_loss"]
                    
                    # Only use dynamic stop if it's more conservative than the original
                    current_stop = target.get("stop_loss", 0)
                    dynamic_price = dynamic_stop.get("price", 0)
                    entry_price = target.get("entry_price", 0)
                    
                    if dynamic_price > 0 and (current_stop == 0 or dynamic_price > current_stop):
                        # Check for minimum distance requirement
                        min_distance_pct = 0.015  # 1.5% minimum
                        if entry_price > 0:
                            min_stop_price = entry_price * (1 - min_distance_pct)
                            # Ensure stop is at least 1.5% away from entry
                            if dynamic_price > min_stop_price:  # If too close to entry
                                dynamic_price = min_stop_price
                                dynamic_stop["explanation"] = f"Enforced 1.5% minimum stop distance"
                                
                        target["stop_loss"] = dynamic_price
                        target["stop_loss_explanation"] = dynamic_stop.get("explanation", "Dynamic stop loss")
                        
                        # Recalculate risk/reward
                        entry_price = target.get("entry_price", 0)
                        take_profit = target.get("take_profit", 0)
                        
                        if entry_price > 0 and take_profit > 0 and dynamic_price > 0:
                            # Long: entry < stop < take profit
                            risk = entry_price - dynamic_price
                            reward = take_profit - entry_price
                            
                            if risk > 0:  # Avoid division by zero
                                target["risk_reward"] = reward / risk
                
        # Enhance short targets
        short_targets = enhanced_targets.get("short_targets", [])
        for target in short_targets:
            # Find matching cluster if any
            target_price = target.get("target_price", 0)
            
            matching_cluster = None
            for cluster in enhanced_clusters.get("long_clusters", []):
                cluster_price = cluster.get("price_level", cluster.get("center_price", 0))
                if abs(cluster_price - target_price) / target_price < 0.03:  # Within 3%
                    matching_cluster = cluster
                    break
            
            if matching_cluster:
                # Add risk metrics from the cluster
                target["orderbook_risk"] = matching_cluster.get("orderbook_risk", 0)
                target["liquidity_risk"] = matching_cluster.get("liquidity_risk", 0)
                target["composite_risk"] = matching_cluster.get("composite_risk", 0)
                
                # Update stop loss if dynamic stop is available
                if "dynamic_stop_loss" in matching_cluster:
                    dynamic_stop = matching_cluster["dynamic_stop_loss"]
                    
                    # Only use dynamic stop if it's more conservative than the original
                    current_stop = target.get("stop_loss", 0)
                    dynamic_price = dynamic_stop.get("price", 0)
                    entry_price = target.get("entry_price", 0)
                    
                    if dynamic_price > 0 and (current_stop == 0 or dynamic_price < current_stop):
                        # Check for minimum distance requirement
                        min_distance_pct = 0.015  # 1.5% minimum
                        if entry_price > 0:
                            min_stop_price = entry_price * (1 + min_distance_pct)
                            # Ensure stop is at least 1.5% away from entry
                            if dynamic_price < min_stop_price:  # If too close to entry
                                dynamic_price = min_stop_price
                                dynamic_stop["explanation"] = f"Enforced 1.5% minimum stop distance"
                                
                        target["stop_loss"] = dynamic_price
                        target["stop_loss_explanation"] = dynamic_stop.get("explanation", "Dynamic stop loss")
                        
                        # Recalculate risk/reward
                        entry_price = target.get("entry_price", 0)
                        take_profit = target.get("take_profit", 0)
                        
                        if entry_price > 0 and take_profit > 0 and dynamic_price > 0:
                            # Short: entry > stop > take profit
                            risk = dynamic_price - entry_price
                            reward = entry_price - take_profit
                            
                            if risk > 0:  # Avoid division by zero
                                target["risk_reward"] = reward / risk
        
        # Add risk metadata
        if "summary" not in enhanced_targets:
            enhanced_targets["summary"] = {}
            
        enhanced_targets["summary"]["has_risk_enhancement"] = True
        enhanced_targets["summary"]["long_average_risk"] = sum([t.get("composite_risk", 0) for t in long_targets]) / len(long_targets) if long_targets else 0
        enhanced_targets["summary"]["short_average_risk"] = sum([t.get("composite_risk", 0) for t in short_targets]) / len(short_targets) if short_targets else 0
        
        return enhanced_targets
