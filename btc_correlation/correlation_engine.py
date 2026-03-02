#!/usr/bin/env python
"""
Dynamic Correlation Engine
--------------------------
Calculates correlation between BTC and altcoins across multiple timeframes
with dynamic weighting based on market conditions.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import os
import json

class DynamicCorrelationEngine:
    def __init__(self, debug=False):
        self.debug = debug
        
    def calculate_correlation(self, btc_prices, altcoin_prices, asset_symbol):
        """
        Calculate multi-timeframe correlation with dynamic weighting
        
        Args:
            btc_prices: DataFrame with BTC OHLCV data across timeframes
            altcoin_prices: DataFrame with altcoin OHLCV data across timeframes
            asset_symbol: Symbol of the altcoin
            
        Returns:
            Dictionary with correlation metrics
        """
        # Initialize results dictionary
        correlation = {
            "asset": asset_symbol,
            "timestamp": datetime.now().isoformat(),
            "timeframes": {},
            "weighted_correlation": 0,
            "current_regime": "UNKNOWN"
        }
        
        try:
            # Calculate correlations for each timeframe
            # Short-term: 24h rolling window (1h candles)
            correlation["timeframes"]["short"] = self._calculate_timeframe_correlation(
                btc_prices.get("1h", pd.DataFrame()), 
                altcoin_prices.get("1h", pd.DataFrame()),
                24  # 24 hours (1h candles)
            )
            
            # Medium-term: 42 periods (4h candles)
            correlation["timeframes"]["medium"] = self._calculate_timeframe_correlation(
                btc_prices.get("4h", pd.DataFrame()), 
                altcoin_prices.get("4h", pd.DataFrame()),
                42  # 42 periods (4h candles)
            )
            
            # Long-term: 30 periods (daily candles)
            correlation["timeframes"]["long"] = self._calculate_timeframe_correlation(
                btc_prices.get("1d", pd.DataFrame()), 
                altcoin_prices.get("1d", pd.DataFrame()),
                30  # 30 periods (daily candles)
            )
            
            # Detect volatility regime
            correlation["current_regime"] = self._detect_volatility_regime(btc_prices.get("1d", pd.DataFrame()))
            
            # Calculate weighted correlation
            if all(correlation["timeframes"][tf].get("sample_size", 0) > 0 for tf in ["short", "medium", "long"]):
                # Apply exponential decay weighting to recent data
                # Weights: 0.5 * short + 0.3 * medium + 0.2 * long
                short_corr = correlation["timeframes"]["short"].get("correlation", 0)
                medium_corr = correlation["timeframes"]["medium"].get("correlation", 0)
                long_corr = correlation["timeframes"]["long"].get("correlation", 0)
                
                short_weight = 0.5
                medium_weight = 0.3
                long_weight = 0.2
                
                correlation["weighted_correlation"] = (
                    short_weight * short_corr +
                    medium_weight * medium_corr +
                    long_weight * long_corr
                )
                
                if self.debug:
                    print(f"Calculated weighted correlation for {asset_symbol}: {correlation['weighted_correlation']:.3f}")
                    print(f"  Short-term: {short_corr:.3f} (weight: {short_weight})")
                    print(f"  Medium-term: {medium_corr:.3f} (weight: {medium_weight})")
                    print(f"  Long-term: {long_corr:.3f} (weight: {long_weight})")
                    print(f"  Current regime: {correlation['current_regime']}")
        
        except Exception as e:
            if self.debug:
                print(f"Error calculating correlation: {e}")
        
        return correlation
    
    def _calculate_timeframe_correlation(self, btc_data, altcoin_data, periods):
        """Calculate correlation for a specific timeframe"""
        if btc_data.empty or altcoin_data.empty:
            return {"correlation": 0, "sample_size": 0}
        
        # Align data and calculate returns
        try:
            # Ensure data is aligned by timestamp
            combined = pd.merge(
                btc_data, 
                altcoin_data,
                left_index=True, 
                right_index=True, 
                suffixes=('_btc', '_alt')
            )
            
            # Take only the closing prices and calculate returns
            btc_returns = combined['close_btc'].pct_change().dropna()
            alt_returns = combined['close_alt'].pct_change().dropna()
            
            # Take only the last 'periods' number of data points
            btc_returns = btc_returns.tail(periods)
            alt_returns = alt_returns.tail(periods)
            
            # Apply exponential decay weighting to recent data
            # More recent data points have higher weights
            alphas = np.exp(np.linspace(-3, 0, len(btc_returns)))
            weights = alphas / alphas.sum()
            
            # Calculate weighted correlation
            if len(btc_returns) >= 3:  # Need at least 3 points for meaningful correlation
                # Standard correlation
                correlation = btc_returns.corr(alt_returns)
                
                # Weighted correlation (for future enhancement)
                # weighted_correlation = np.corrcoef(
                #     btc_returns * weights, 
                #     alt_returns * weights
                # )[0, 1]
                
                return {
                    "correlation": correlation,
                    "sample_size": len(btc_returns)
                }
            else:
                return {"correlation": 0, "sample_size": len(btc_returns)}
                
        except Exception as e:
            if self.debug:
                print(f"Error calculating timeframe correlation: {e}")
            return {"correlation": 0, "sample_size": 0}
    
    def _detect_volatility_regime(self, price_data):
        """Detect volatility regime based on historical data"""
        if price_data.empty:
            return "MEDIUM"
        
        try:
            # Calculate daily returns
            returns = price_data['close'].pct_change().dropna()
            
            # Calculate rolling volatility (standard deviation of returns)
            current_vol = returns.rolling(window=30).std().iloc[-1] if len(returns) >= 30 else returns.std()
            
            # Get historic volatility percentiles
            if len(returns) >= 90:  # Need sufficient history
                # Calculate the 30th and 70th percentiles of historic volatility
                vol_30_percentile = returns.rolling(window=30).std().quantile(0.3)
                vol_70_percentile = returns.rolling(window=30).std().quantile(0.7)
                
                # Determine regime based on historical percentiles
                if current_vol > vol_70_percentile:
                    return "HIGH"
                elif current_vol < vol_30_percentile:
                    return "LOW"
                else:
                    return "MEDIUM"
            else:
                # Not enough data to determine percentiles
                return "MEDIUM"
                
        except Exception as e:
            if self.debug:
                print(f"Error detecting volatility regime: {e}")
            return "MEDIUM"
            
    def cache_correlation_data(self, correlation_data, asset_symbol):
        """Save correlation data to cache"""
        try:
            cache_dir = os.path.join("price_data", "correlation_cache")
            os.makedirs(cache_dir, exist_ok=True)
            
            cache_file = os.path.join(cache_dir, f"{asset_symbol}_correlation.json")
            
            with open(cache_file, 'w') as f:
                json.dump(correlation_data, f, indent=2)
                
            if self.debug:
                print(f"Cached correlation data for {asset_symbol}")
                
            return True
        except Exception as e:
            if self.debug:
                print(f"Error caching correlation data: {e}")
            return False
            
    def load_cached_correlation_data(self, asset_symbol):
        """Load correlation data from cache"""
        try:
            cache_file = os.path.join("price_data", "correlation_cache", f"{asset_symbol}_correlation.json")
            
            if not os.path.exists(cache_file):
                return None
                
            # Check if file is not too old (less than 12 hours)
            file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_file))
            if file_age > timedelta(hours=12):
                return None
                
            with open(cache_file, 'r') as f:
                correlation_data = json.load(f)
                
            if self.debug:
                print(f"Loaded cached correlation data for {asset_symbol}")
                
            return correlation_data
        except Exception as e:
            if self.debug:
                print(f"Error loading cached correlation data: {e}")
            return None
