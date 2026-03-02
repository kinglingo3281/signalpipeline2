#!/usr/bin/env python
"""
Correlation JSON Enhancer
------------------------
Enhances altcoin JSON analysis with BTC correlation data
and updates trade signals.
"""

import json
import os
from datetime import datetime

# Import the trade recommender
from btc_correlation.trade_recommender import BTCTradeRecommender

class CorrelationJSONEnhancer:
    def __init__(self, debug=False):
        self.debug = debug
        self.trade_recommender = BTCTradeRecommender(debug=debug)
        
    def enhance_json(self, original_json, correlation_data, translated_clusters, output_path=None):
        """
        Enhance altcoin JSON data with BTC correlation insights
        
        Args:
            original_json: Original altcoin analysis JSON
            correlation_data: Output from DynamicCorrelationEngine
            translated_clusters: Output from BTCClusterTranslator
            output_path: Path to save enhanced JSON (optional)
            
        Returns:
            Enhanced JSON with BTC correlation data
        """
        # Deep copy the original JSON to avoid modifying it
        enhanced_json = dict(original_json)
        
        # Only enhance if correlation threshold was met
        if not translated_clusters["metadata"]["correlation_threshold_met"]:
            # Add only correlation data without modifying trading signals
            enhanced_json["btc_correlation"] = {
                "weighted_correlation": translated_clusters["correlation"],
                "beta": translated_clusters["beta"],
                "correlation_threshold_met": False,
                "explanation": "BTC correlation below threshold, no signal enhancement applied"
            }
            
            if output_path:
                self._save_json(enhanced_json, output_path)
                
            return enhanced_json
        
        # Extract original asset clusters and current prices
        asset_clusters = original_json.get("clusters", {})
        asset_price = original_json.get("current_price", 0)
        btc_price = 0
        
        # Try to get BTC price from the correlation data
        if "btc_price" in correlation_data:
            btc_price = correlation_data["btc_price"]
            
        # Generate BTC-adjusted trade recommendations
        btc_recommendations = self.trade_recommender.generate_btc_adjusted_recommendations(
            correlation_data, 
            translated_clusters, 
            asset_clusters, 
            asset_price,
            btc_price
        )
        
        # Add BTC correlation section without modifying existing structure
        enhanced_json["btc_correlation"] = {
            "weighted_correlation": translated_clusters["correlation"],
            "beta": translated_clusters["beta"],
            "short_term_correlation": correlation_data.get("timeframes", {}).get("short", {}).get("correlation", 0),
            "medium_term_correlation": correlation_data.get("timeframes", {}).get("medium", {}).get("correlation", 0),
            "long_term_correlation": correlation_data.get("timeframes", {}).get("long", {}).get("correlation", 0),
            "translated_clusters": {
                "long_count": len(translated_clusters["long_clusters"]),
                "short_count": len(translated_clusters["short_clusters"])
            },
            "translation_quality": translated_clusters["metadata"]["translation_quality"],
            "correlation_threshold_met": True,
            "safeguards_applied": translated_clusters["metadata"]["safeguards_applied"],
            "btc_trade_recommendations": btc_recommendations
        }
        
        # Update best trades section with blended confidence scores
        self._enhance_best_trades(enhanced_json, translated_clusters)
        
        # Save enhanced JSON if output path provided
        if output_path:
            self._save_json(enhanced_json, output_path)
            
        return enhanced_json
    
    def _enhance_best_trades(self, enhanced_json, translated_clusters):
        """Helper method to enhance the best trades section"""
        # Get original best trades if they exist
        best_trades = enhanced_json.get("best_trades", [])
        
        # Get current price
        current_price = enhanced_json.get("current_price", 0)
        if current_price <= 0:
            if self.debug:
                print("Invalid current price. Cannot enhance best trades.")
            return
            
        # Get native clusters
        native_long_clusters = []
        native_short_clusters = []
        
        if "clusters" in enhanced_json:
            native_long_clusters = enhanced_json.get("clusters", {}).get("long_clusters", [])
            native_short_clusters = enhanced_json.get("clusters", {}).get("short_clusters", [])
        
        # Get translated clusters
        btc_long_clusters = translated_clusters.get("long_clusters", [])
        btc_short_clusters = translated_clusters.get("short_clusters", [])
        
        if self.debug:
            print(f"Native clusters: {len(native_long_clusters)} long, {len(native_short_clusters)} short")
            print(f"BTC-translated clusters: {len(btc_long_clusters)} long, {len(btc_short_clusters)} short")
        
        aligned_clusters = []
        
        # Check for proximity between native and BTC clusters (safeguard 3)
        # Find clusters where native and BTC clusters align (dynamically calculated proximity threshold)
        for long_cluster in native_long_clusters:
            native_price = long_cluster.get("center_price", 0)
            native_confidence = long_cluster.get("confidence", 0)  # Get native confidence if available
            if native_price <= 0:
                continue
                
            # Calculate dynamic proximity threshold based on volatility and beta
            # Lower threshold (tighter proximity required) for higher correlation
            correlation = abs(translated_clusters.get("correlation", 0))
            proximity_threshold = 0.05  # Default 5%
            if correlation > 0.7:
                proximity_threshold = 0.03  # 3% for high correlation
            elif correlation > 0.5:
                proximity_threshold = 0.04  # 4% for medium correlation
                
            # Look for nearby BTC-translated long clusters
            found_match = False
            best_match = None
            best_proximity = 1.0  # Initialize with a high value
            
            for btc_cluster in btc_long_clusters:
                btc_price = btc_cluster.get("center_price", 0)
                if btc_price <= 0:
                    continue
                    
                # Check proximity (within calculated threshold)
                price_diff_pct = abs(native_price - btc_price) / native_price
                if price_diff_pct <= proximity_threshold:
                    if not found_match or price_diff_pct < best_proximity:
                        found_match = True
                        best_match = btc_cluster
                        best_proximity = price_diff_pct
            
            if found_match:
                # Found alignment - create combined cluster
                native_confidence = long_cluster.get("confidence", 0) 
                btc_confidence = best_match.get("confidence", 0)
                
                # Higher confidence for alignment
                combined_confidence = (native_confidence * 0.7) + (btc_confidence * 0.6)
                
                aligned_clusters.append({
                    "direction": "long",
                    "center_price": (native_price + best_match["center_price"]) / 2,  # Average price
                    "native_price": native_price,
                    "btc_price": best_match["center_price"],
                    "combined_confidence": combined_confidence,
                    "native_confidence": native_confidence,
                    "btc_confidence": btc_confidence,
                    "is_aligned": True,
                    "proximity": best_proximity
                })
                
                if self.debug:
                    print(f"Found aligned LONG cluster: native={native_price:.2f}, btc={best_match['center_price']:.2f}, proximity={best_proximity:.2f}")
        
        # Similar process for short clusters
        for short_cluster in native_short_clusters:
            native_price = short_cluster.get("center_price", 0)
            native_confidence = short_cluster.get("confidence", 0)  # Get native confidence if available
            if native_price <= 0:
                continue
                
            # Calculate dynamic proximity threshold based on volatility and beta
            # Lower threshold (tighter proximity required) for higher correlation
            correlation = abs(translated_clusters.get("correlation", 0))
            proximity_threshold = 0.05  # Default 5%
            if correlation > 0.7:
                proximity_threshold = 0.03  # 3% for high correlation
            elif correlation > 0.5:
                proximity_threshold = 0.04  # 4% for medium correlation
                
            # Look for nearby BTC-translated short clusters
            found_match = False
            best_match = None
            best_proximity = 1.0  # Initialize with a high value
            
            for btc_cluster in btc_short_clusters:
                btc_price = btc_cluster.get("center_price", 0)
                if btc_price <= 0:
                    continue
                    
                # Check proximity (within calculated threshold)
                price_diff_pct = abs(native_price - btc_price) / native_price
                if price_diff_pct <= proximity_threshold:
                    if not found_match or price_diff_pct < best_proximity:
                        found_match = True
                        best_match = btc_cluster
                        best_proximity = price_diff_pct
            
            if found_match:
                # Found alignment - create combined cluster
                native_confidence = short_cluster.get("confidence", 0) 
                btc_confidence = best_match.get("confidence", 0)
                
                # Higher confidence for alignment
                combined_confidence = (native_confidence * 0.7) + (btc_confidence * 0.6)
                
                aligned_clusters.append({
                    "direction": "short",
                    "center_price": (native_price + best_match["center_price"]) / 2,  # Average price
                    "native_price": native_price,
                    "btc_price": best_match["center_price"],
                    "combined_confidence": combined_confidence,
                    "native_confidence": native_confidence,
                    "btc_confidence": btc_confidence,
                    "is_aligned": True,
                    "proximity": best_proximity
                })
                
                if self.debug:
                    print(f"Found aligned SHORT cluster: native={native_price:.2f}, btc={best_match['center_price']:.2f}, proximity={best_proximity:.2f}")
        
        # Sort aligned clusters by combined confidence
        aligned_clusters.sort(key=lambda x: x["combined_confidence"], reverse=True)
        
        # Add high-confidence BTC clusters that don't align with any native clusters
        # First, identify which BTC clusters are already aligned
        aligned_btc_prices = {
            "long": [c["btc_price"] for c in aligned_clusters if c["direction"] == "long"],
            "short": [c["btc_price"] for c in aligned_clusters if c["direction"] == "short"]
        }
        
        # Add non-aligned BTC long clusters
        for btc in btc_long_clusters:
            btc_price = btc.get("center_price", 0)
            if btc_price not in aligned_btc_prices["long"]:
                confidence = btc.get("confidence", 0)
                if confidence > 0.3:  # Only add high-confidence clusters
                    aligned_clusters.append({
                        "direction": "long",
                        "center_price": btc_price,
                        "native_price": None,
                        "btc_price": btc_price,
                        "combined_confidence": confidence * 0.6,  # Lower weight without alignment
                        "native_confidence": 0,
                        "btc_confidence": confidence,
                        "is_aligned": False,
                        "proximity": None
                    })
                    
                    if self.debug:
                        print(f"Added non-aligned BTC LONG cluster: price={btc_price:.2f}, confidence={confidence:.2f}")
        
        # Add non-aligned BTC short clusters
        for btc in btc_short_clusters:
            btc_price = btc.get("center_price", 0)
            if btc_price not in aligned_btc_prices["short"]:
                confidence = btc.get("confidence", 0)
                if confidence > 0.3:  # Only add high-confidence clusters
                    aligned_clusters.append({
                        "direction": "short",
                        "center_price": btc_price,
                        "native_price": None,
                        "btc_price": btc_price,
                        "combined_confidence": confidence * 0.6,  # Lower weight without alignment
                        "native_confidence": 0,
                        "btc_confidence": confidence,
                        "is_aligned": False,
                        "proximity": None
                    })
                    
                    if self.debug:
                        print(f"Added non-aligned BTC SHORT cluster: price={btc_price:.2f}, confidence={confidence:.2f}")
        
        # Resort all clusters by combined confidence
        aligned_clusters.sort(key=lambda x: x["combined_confidence"], reverse=True)
        
        # Create enhanced best trades section
        enhanced_best_trades = []
        
        # First add original best trades if they exist
        if best_trades:
            for trade in best_trades:
                enhanced_best_trades.append(dict(trade))
        
        # Add top aligned clusters as additional best trades
        max_trades_to_add = min(3, len(aligned_clusters))  # Add up to 3 trades
        for i, cluster in enumerate(aligned_clusters[:max_trades_to_add]):
            trade = {
                "direction": cluster["direction"],
                "entry_price": cluster["center_price"],
                "confidence": cluster["combined_confidence"],
                "is_btc_enhanced": True,
                "is_aligned": cluster["is_aligned"],
                "sources": {
                    "native": bool(cluster["native_price"]),
                    "btc_translated": bool(cluster["btc_price"])
                }
            }
            
            # Calculate target and stop prices based on direction
            if current_price > 0:
                if cluster["direction"] == "long":
                    # Long trade - target price is higher
                    risk_reward = 2.0  # Target 2:1 reward/risk ratio
                    distance = abs(current_price - cluster["center_price"])
                    trade["target_price"] = current_price + (distance * risk_reward)
                    trade["stop_price"] = cluster["center_price"] * 0.99  # 1% below entry
                else:
                    # Short trade - target price is lower
                    risk_reward = 2.0  # Target 2:1 reward/risk ratio
                    distance = abs(current_price - cluster["center_price"])
                    trade["target_price"] = current_price - (distance * risk_reward)
                    trade["stop_price"] = cluster["center_price"] * 1.01  # 1% above entry
            
            enhanced_best_trades.append(trade)
            
            if self.debug:
                print(f"Added enhanced trade: {cluster['direction']} @ {cluster['center_price']:.2f}")
        
        # Update the JSON
        enhanced_json["btc_enhanced_trades"] = enhanced_best_trades
        
        # Add explanations
        enhanced_json["btc_correlation"]["explanations"] = {
            "aligned_clusters_found": len([c for c in aligned_clusters if c["is_aligned"]]),
            "correlation_strength": "Strong" if abs(translated_clusters["correlation"]) > 0.7 else 
                                   "Medium" if abs(translated_clusters["correlation"]) > 0.5 else "Weak",
            "enhancement_quality": translated_clusters["metadata"]["translation_quality"],
            "btc_influence": f"{min(len(enhanced_best_trades), 100)}% of trades influenced by BTC analysis"
        }
        
    def _save_json(self, data, output_path):
        """Helper method to save JSON data to file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Save to file
            with open(output_path, 'w') as f:
                json.dump(data, f, indent=2)
                
            if self.debug:
                print(f"Enhanced JSON saved to {output_path}")
                
            return True
        except Exception as e:
            if self.debug:
                print(f"Error saving enhanced JSON: {e}")
            return False
