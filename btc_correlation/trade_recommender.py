#!/usr/bin/env python
"""
BTC Trade Recommender
--------------------
Generates trading recommendations based on BTC correlation analysis.
Combines BTC influence with asset-specific clusters for enhanced trade signals.
"""

import math
import json
import random
from datetime import datetime

class BTCTradeRecommender:
    """
    Generates BTC-adjusted trade recommendations by analyzing 
    the relationship between BTC movements and altcoin liquidations
    """
    
    def __init__(self, debug=False):
        self.debug = debug
        
    def generate_btc_adjusted_recommendations(self, correlation_data, translated_clusters, 
                                             asset_clusters, asset_price, btc_price):
        """
        Generate BTC-adjusted trade recommendations
        
        Args:
            correlation_data: Correlation analysis data
            translated_clusters: BTC-translated liquidation clusters
            asset_clusters: Native asset liquidation clusters
            asset_price: Current asset price
            btc_price: Current BTC price
            
        Returns:
            Dict with BTC-adjusted trade recommendations
        """
        if self.debug:
            print("Generating BTC-adjusted trade recommendations...")
            
        # Extract key metrics
        correlation = translated_clusters.get("correlation", 0)
        beta = translated_clusters.get("beta", 0)
        
        # Extract clusters
        btc_long_clusters = translated_clusters.get("long_clusters", [])
        btc_short_clusters = translated_clusters.get("short_clusters", [])
        
        # Extract native clusters if available
        native_long_clusters = []
        native_short_clusters = []
        
        if isinstance(asset_clusters, dict):
            native_long_clusters = asset_clusters.get("long_clusters", [])
            native_short_clusters = asset_clusters.get("short_clusters", [])
        
        # Determine if correlation is strong enough to make BTC-based recommendations
        correlation_strength = abs(correlation)
        CORRELATION_THRESHOLD = 0.3  # Minimum correlation to consider BTC influence
        
        if correlation_strength < CORRELATION_THRESHOLD:
            # BTC correlation too weak to make reliable recommendations
            return {
                "status": "weak_correlation",
                "message": f"BTC correlation ({correlation:.2f}) below threshold for reliable recommendations",
                "btc_recommendations": []
            }
            
        # Calculate BTC influence weight based on correlation strength
        # Higher correlation = higher weight for BTC signals
        btc_influence_weight = min(0.8, correlation_strength * 1.2)
        
        if self.debug:
            print(f"BTC influence weight: {btc_influence_weight:.2f}")
            
        # Generate BTC-specific recommendations
        btc_recommendations = []
        
        # Combine native and BTC-translated clusters to identify aligned signals
        aligned_signals = self._identify_aligned_signals(
            translated_clusters, 
            native_long_clusters, 
            native_short_clusters,
            asset_price
        )
        
        if self.debug:
            print(f"Found {len(aligned_signals)} aligned signals")
            
        # Generate recommendations from aligned signals
        for signal in aligned_signals:
            direction = signal.get("direction", "neutral")
            price_level = signal.get("price_level", asset_price)
            btc_confidence = signal.get("btc_confidence", 0)
            native_confidence = signal.get("native_confidence", 0)
            
            # Skip invalid signals
            if direction not in ["long", "short"] or price_level <= 0:
                continue
                
            # Calculate blended confidence based on BTC influence weight
            blended_confidence = (btc_confidence * btc_influence_weight) + \
                               (native_confidence * (1 - btc_influence_weight))
            
            # Only include high-confidence signals
            if blended_confidence < 0.3:
                continue
                
            # Determine BTC condition that would trigger this signal
            btc_trigger_price = self._calculate_btc_trigger_price(
                direction, 
                btc_price, 
                beta, 
                price_level, 
                asset_price
            )
            
            # Calculate profit targets and stop losses
            take_profit, stop_loss = self._calculate_risk_parameters(
                direction, 
                price_level, 
                asset_price, 
                correlation_strength
            )
            
            recommendation = {
                "direction": direction,
                "price_level": price_level,
                "confidence": blended_confidence,
                "btc_influence": btc_influence_weight,
                "btc_trigger_price": btc_trigger_price,
                "take_profit": take_profit,
                "stop_loss": stop_loss,
                "is_aligned": signal.get("is_aligned", False),
                "alignment_strength": signal.get("alignment_strength", 0),
                "rationale": self._generate_rationale(
                    direction, 
                    correlation, 
                    beta, 
                    price_level, 
                    btc_trigger_price, 
                    btc_price
                )
            }
            
            btc_recommendations.append(recommendation)
        
        # Sort by confidence
        btc_recommendations.sort(key=lambda x: x.get("confidence", 0), reverse=True)
        
        # Take top 3 recommendations only
        top_recommendations = btc_recommendations[:3]
        
        # Add meta information
        result = {
            "status": "success",
            "correlation": correlation,
            "beta": beta,
            "btc_influence_weight": btc_influence_weight,
            "aligned_signals_count": len(aligned_signals),
            "btc_recommendations": top_recommendations,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        return result
    
    def _identify_aligned_signals(self, translated_clusters, native_long_clusters, native_short_clusters, current_price):
        """
        Identify signals where native and BTC-translated clusters align
        
        Args:
            translated_clusters: BTC-translated liquidation clusters
            native_long_clusters: Native long liquidation clusters
            native_short_clusters: Native short liquidation clusters
            current_price: Current asset price
            
        Returns:
            List of aligned signals
        """
        # Extract BTC-translated clusters
        btc_long_clusters = translated_clusters.get("long_clusters", [])
        btc_short_clusters = translated_clusters.get("short_clusters", [])
        
        # Get correlation metrics
        correlation = translated_clusters.get("correlation", 0)
        correlation_abs = abs(correlation)
        
        # Dynamic proximity threshold based on correlation strength
        proximity_threshold = 0.05  # Default 5%
        if correlation_abs > 0.7:
            proximity_threshold = 0.025  # Higher correlation = tighter threshold
        elif correlation_abs > 0.5:
            proximity_threshold = 0.035
            
        aligned_signals = []
        
        # Check for alignment between native and BTC long clusters
        for native in native_long_clusters:
            native_price = native.get("center_price", 0)
            if native_price <= 0:
                continue
                
            # Look for nearby BTC cluster
            for btc in btc_long_clusters:
                btc_price = btc.get("center_price", 0)
                if btc_price <= 0:
                    continue
                    
                # Check proximity
                price_diff_pct = abs(native_price - btc_price) / native_price
                if price_diff_pct <= proximity_threshold:
                    # Calculate alignment strength inversely proportional to distance
                    alignment_strength = 1 - (price_diff_pct / proximity_threshold)
                    
                    # Combine confidences
                    native_conf = native.get("confidence", 0.5)
                    btc_conf = btc.get("confidence", 0.5)
                    
                    aligned_signals.append({
                        "direction": "long",
                        "price_level": (native_price + btc_price) / 2,  # Average
                        "native_price": native_price,
                        "btc_price": btc_price,
                        "native_confidence": native_conf,
                        "btc_confidence": btc_conf,
                        "is_aligned": True,
                        "alignment_strength": alignment_strength
                    })
        
        # Repeat for short clusters
        for native in native_short_clusters:
            native_price = native.get("center_price", 0)
            if native_price <= 0:
                continue
                
            # Look for nearby BTC cluster
            for btc in btc_short_clusters:
                btc_price = btc.get("center_price", 0)
                if btc_price <= 0:
                    continue
                    
                # Check proximity
                price_diff_pct = abs(native_price - btc_price) / native_price
                if price_diff_pct <= proximity_threshold:
                    # Calculate alignment strength inversely proportional to distance
                    alignment_strength = 1 - (price_diff_pct / proximity_threshold)
                    
                    # Combine confidences
                    native_conf = native.get("confidence", 0.5)
                    btc_conf = btc.get("confidence", 0.5)
                    
                    aligned_signals.append({
                        "direction": "short",
                        "price_level": (native_price + btc_price) / 2,  # Average
                        "native_price": native_price,
                        "btc_price": btc_price,
                        "native_confidence": native_conf,
                        "btc_confidence": btc_conf,
                        "is_aligned": True,
                        "alignment_strength": alignment_strength
                    })
        
        # Add strong BTC signals without corresponding native cluster
        # Important for identifying BTC-driven moves not yet visible in native clusters
        
        # First identify which BTC clusters are already aligned
        aligned_btc_prices = {
            "long": [s["btc_price"] for s in aligned_signals if s["direction"] == "long"],
            "short": [s["btc_price"] for s in aligned_signals if s["direction"] == "short"]
        }
        
        # Add strong BTC long signals without alignment
        for btc in btc_long_clusters:
            btc_price = btc.get("center_price", 0)
            confidence = btc.get("confidence", 0)
            
            # Skip if already aligned or low confidence
            if btc_price in aligned_btc_prices["long"] or confidence < 0.5:
                continue
                
            aligned_signals.append({
                "direction": "long",
                "price_level": btc_price,
                "native_price": None,
                "btc_price": btc_price,
                "native_confidence": 0,
                "btc_confidence": confidence,
                "is_aligned": False,
                "alignment_strength": 0
            })
            
        # Add strong BTC short signals without alignment
        for btc in btc_short_clusters:
            btc_price = btc.get("center_price", 0)
            confidence = btc.get("confidence", 0)
            
            # Skip if already aligned or low confidence
            if btc_price in aligned_btc_prices["short"] or confidence < 0.5:
                continue
                
            aligned_signals.append({
                "direction": "short",
                "price_level": btc_price,
                "native_price": None,
                "btc_price": btc_price,
                "native_confidence": 0,
                "btc_confidence": confidence,
                "is_aligned": False,
                "alignment_strength": 0
            })
            
        return aligned_signals
    
    def _calculate_btc_trigger_price(self, direction, btc_price, beta, target_price, current_price):
        """
        Calculate the BTC price that would trigger the signal
        
        Args:
            direction: Trade direction ('long' or 'short')
            btc_price: Current BTC price
            beta: Beta coefficient
            target_price: Target price level
            current_price: Current asset price
            
        Returns:
            BTC price that would trigger this signal
        """
        if btc_price <= 0 or beta == 0:
            return None
            
        price_change_pct = (target_price / current_price) - 1
        
        # Factor in direction
        if direction == "short" and price_change_pct > 0:
            price_change_pct = -price_change_pct
        elif direction == "long" and price_change_pct < 0:
            price_change_pct = -price_change_pct
            
        # Calculate required BTC move based on beta
        # If beta = 2, then BTC needs to move half as much to cause the asset move
        btc_change_pct = price_change_pct / beta
        
        # Calculate BTC trigger price
        btc_trigger = btc_price * (1 + btc_change_pct)
        
        return btc_trigger
    
    def _calculate_risk_parameters(self, direction, price_level, current_price, correlation_strength):
        """
        Calculate take profit and stop loss levels based on direction and correlation
        
        Args:
            direction: Trade direction ('long' or 'short')
            price_level: Entry price level
            current_price: Current asset price
            correlation_strength: Strength of BTC correlation
            
        Returns:
            Tuple of (take_profit, stop_loss)
        """
        # Base risk/reward ratio - adjust based on correlation strength
        # Higher correlation = more aggressive targets due to higher confidence
        risk_reward = 2.0 + (correlation_strength * 0.5)  # 2.0 to 2.5
        
        # Calculate price distance
        distance = abs(price_level - current_price)
        
        if direction == "long":
            # Long trade - buy low, sell high
            take_profit = current_price + (distance * risk_reward)
            stop_loss = price_level * 0.99  # 1% below entry
        else:
            # Short trade - sell high, buy low
            take_profit = current_price - (distance * risk_reward)
            stop_loss = price_level * 1.01  # 1% above entry
            
        return take_profit, stop_loss
    
    def _generate_rationale(self, direction, correlation, beta, price_level, btc_trigger, btc_price):
        """
        Generate descriptive rationale for the trade recommendation
        
        Args:
            direction: Trade direction ('long' or 'short')
            correlation: BTC correlation coefficient
            beta: Beta coefficient
            price_level: Target price level
            btc_trigger: BTC trigger price
            btc_price: Current BTC price
            
        Returns:
            String with trade rationale
        """
        direction_text = "bullish" if direction == "long" else "bearish"
        correlation_text = "strong" if abs(correlation) > 0.7 else "moderate" if abs(correlation) > 0.5 else "weak"
        
        rationale = f"BTC-influenced {direction_text} opportunity with {correlation_text} correlation ({correlation:.2f})."
        
        # Add specifics on BTC trigger
        if btc_trigger and btc_price:
            btc_move_pct = (btc_trigger / btc_price - 1) * 100
            if abs(btc_move_pct) < 20:  # Only show reasonable moves
                move_text = "rise" if btc_move_pct > 0 else "fall"
                rationale += f" A BTC {move_text} to ${btc_trigger:,.0f} (±{abs(btc_move_pct):.1f}%) could trigger this setup."
                
        # Add beta explanation if available
        if beta:
            beta_desc = "amplifies" if beta > 1 else "dampens"
            rationale += f" Beta of {beta:.2f} {beta_desc} BTC movements."
            
        return rationale
