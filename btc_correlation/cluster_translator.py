#!/usr/bin/env python
"""
BTC Cluster Translator
---------------------
Translates BTC liquidation clusters to equivalent altcoin price levels
based on correlation strength and beta coefficients.
"""

import math
import os
import json
from datetime import datetime

class BTCClusterTranslator:
    def __init__(self, debug=False):
        self.debug = debug
        
    def translate_clusters(self, btc_clusters, correlation_data, beta_data, 
                           btc_current_price, altcoin_current_price, altcoin_symbol):
        """
        Translate BTC clusters to altcoin price levels
        
        Args:
            btc_clusters: Dictionary containing BTC liquidation clusters
            correlation_data: Output from DynamicCorrelationEngine
            beta_data: Output from CryptoBetaCalculator
            btc_current_price: Current BTC price
            altcoin_current_price: Current altcoin price
            altcoin_symbol: Symbol of the altcoin
            
        Returns:
            Dictionary with translated clusters and metadata
        """
        # Initialize results
        translated_results = {
            "altcoin": altcoin_symbol,
            "btc_current_price": btc_current_price,
            "altcoin_current_price": altcoin_current_price,
            "correlation": correlation_data.get("weighted_correlation", 0),
            "beta": beta_data.get("current_beta", 1.0),
            "long_clusters": [],
            "short_clusters": [],
            "metadata": {
                "translation_quality": 0,
                "correlation_threshold_met": False,
                "safeguards_applied": []
            }
        }
        
        # Extract correlation and beta values
        correlation = correlation_data.get("weighted_correlation", 0)
        beta = beta_data.get("current_beta", 1.0)
        
        # Apply correlation threshold filter (safeguard 1)
        # Only translate when correlation exceeds threshold
        correlation_threshold = 0.5  # Can be adjusted to 0.5-0.7 range
        
        if abs(correlation) < correlation_threshold:
            translated_results["metadata"]["correlation_threshold_met"] = False
            translated_results["metadata"]["safeguards_applied"].append(
                f"Correlation threshold filter: correlation {correlation:.2f} below threshold {correlation_threshold}"
            )
            if self.debug:
                print(f"Correlation ({correlation:.2f}) below threshold ({correlation_threshold}) for {altcoin_symbol}. Skipping translation.")
            return translated_results
        
        translated_results["metadata"]["correlation_threshold_met"] = True
        
        # Cap maximum weight to 40% of native clusters (safeguard 2)
        max_btc_weight = 0.4
        translated_results["metadata"]["safeguards_applied"].append(
            f"Dynamic weight cap: maximum BTC weight set to {max_btc_weight}"
        )
        
        # Process BTC long clusters (which would become liquidations if price drops)
        if "long_clusters" in btc_clusters:
            for cluster in btc_clusters["long_clusters"]:
                self._translate_cluster(
                    cluster, "long", btc_current_price, altcoin_current_price,
                    beta, correlation, max_btc_weight, translated_results
                )
            
        # Process BTC short clusters (which would become liquidations if price rises)
        if "short_clusters" in btc_clusters:
            for cluster in btc_clusters["short_clusters"]:
                self._translate_cluster(
                    cluster, "short", btc_current_price, altcoin_current_price,
                    beta, correlation, max_btc_weight, translated_results
                )
        
        # Calculate translation quality based on correlation and number of translated clusters
        total_clusters = len(translated_results["long_clusters"]) + len(translated_results["short_clusters"])
        if total_clusters > 0:
            # Quality is based on correlation and number of clusters translated
            quality = (abs(correlation) ** 2) * min(1.0, total_clusters / 5)
            translated_results["metadata"]["translation_quality"] = quality
            
            if self.debug:
                print(f"Translated {total_clusters} clusters for {altcoin_symbol}")
                print(f"  Long clusters: {len(translated_results['long_clusters'])}")
                print(f"  Short clusters: {len(translated_results['short_clusters'])}")
                print(f"  Translation quality: {quality:.3f}")
        else:
            if self.debug:
                print(f"No clusters translated for {altcoin_symbol}")
        
        return translated_results
    
    def _translate_cluster(self, cluster, direction, btc_current_price, altcoin_current_price,
                          beta, correlation, max_btc_weight, translated_results):
        """Helper method to translate an individual BTC cluster"""
        try:
            # Extract cluster data
            center_price = cluster.get("center_price", 0)
            cluster_size = cluster.get("total_size", 0)
            
            # Skip if invalid data
            if center_price <= 0 or cluster_size <= 0:
                if self.debug:
                    print(f"Skipping invalid cluster: center_price={center_price}, size={cluster_size}")
                return
                
            # Calculate percent distance from current BTC price
            pct_change_btc = (center_price - btc_current_price) / btc_current_price
            
            # Apply beta to get expected altcoin price
            expected_altcoin_price = altcoin_current_price * (1 + (pct_change_btc * beta))
            
            # Calculate absolute distance for distance decay
            distance_factor = abs(pct_change_btc)
            
            # Apply exponential decay for distant clusters (part of safeguard 2)
            distance_penalty = math.exp(-4 * distance_factor)
            
            # Calculate confidence: correlation * cluster_size / distance
            # Avoid division by zero
            distance_divisor = max(0.01, distance_factor)
            raw_confidence = abs(correlation) * cluster_size / distance_divisor
            
            # Apply cap: min(confidence, max_btc_weight * cluster_size) (safeguard 2)
            capped_confidence = min(raw_confidence, max_btc_weight * cluster_size)
            
            # Apply correlation^2 for influence scaling (safeguard 4)
            weighted_confidence = capped_confidence * (correlation ** 2)
            
            # Skip if confidence is too low
            if weighted_confidence < 0.1:
                if self.debug:
                    print(f"Skipping low confidence cluster: {weighted_confidence:.3f} < 0.1")
                return
                
            # Create translated cluster
            translated_cluster = {
                "center_price": expected_altcoin_price,
                "direction": direction,
                "total_size": cluster_size * abs(correlation),  # Scale size by correlation
                "confidence": weighted_confidence,
                "distance_from_current": distance_factor,
                "btc_source_price": center_price,
                "translated_from_btc": True
            }
            
            # Add cluster to appropriate list
            if direction == "long":
                translated_results["long_clusters"].append(translated_cluster)
            else:
                translated_results["short_clusters"].append(translated_cluster)
                
            # Track safeguard application
            safeguards = []
            if distance_penalty < 0.8:
                safeguards.append(f"Distance decay: {distance_penalty:.2f}")
            if capped_confidence < raw_confidence:
                safeguards.append(f"Weight cap: {capped_confidence:.2f} (raw: {raw_confidence:.2f})")
            
            if safeguards and not any(s in translated_results["metadata"]["safeguards_applied"] for s in safeguards):
                translated_results["metadata"]["safeguards_applied"].extend(safeguards)
                
            if self.debug:
                print(f"Translated {direction} cluster:")
                print(f"  BTC price: {center_price} -> Altcoin price: {expected_altcoin_price:.3f}")
                print(f"  Distance factor: {distance_factor:.3f}")
                print(f"  Confidence: {weighted_confidence:.3f}")
                if safeguards:
                    print(f"  Applied safeguards: {', '.join(safeguards)}")
                
        except Exception as e:
            if self.debug:
                print(f"Error translating cluster: {e}")
                
    def cache_translated_clusters(self, translated_clusters, altcoin_symbol):
        """Save translated clusters to cache"""
        try:
            cache_dir = os.path.join("price_data", "translated_clusters")
            os.makedirs(cache_dir, exist_ok=True)
            
            cache_file = os.path.join(cache_dir, f"{altcoin_symbol}_translated_clusters.json")
            
            with open(cache_file, 'w') as f:
                json.dump(translated_clusters, f, indent=2)
                
            if self.debug:
                print(f"Cached translated clusters for {altcoin_symbol}")
                
            return True
        except Exception as e:
            if self.debug:
                print(f"Error caching translated clusters: {e}")
            return False
            
    def load_cached_translated_clusters(self, altcoin_symbol):
        """Load translated clusters from cache"""
        try:
            cache_file = os.path.join("price_data", "translated_clusters", f"{altcoin_symbol}_translated_clusters.json")
            
            if not os.path.exists(cache_file):
                return None
                
            # Translated clusters should always be fresh - max 1 hour old
            file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_file))
            if file_age.total_seconds() > 3600:  # 1 hour in seconds
                return None
                
            with open(cache_file, 'r') as f:
                translated_clusters = json.load(f)
                
            if self.debug:
                print(f"Loaded cached translated clusters for {altcoin_symbol}")
                
            return translated_clusters
        except Exception as e:
            if self.debug:
                print(f"Error loading cached translated clusters: {e}")
            return None
