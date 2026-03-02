#!/usr/bin/env python
"""
Crypto Beta Calculator
---------------------
Calculates beta coefficients for altcoins relative to BTC,
segmented by volatility regimes.
"""

import numpy as np
import pandas as pd
import os
import json
from datetime import datetime, timedelta

class CryptoBetaCalculator:
    def __init__(self, debug=False):
        self.debug = debug
        
    def calculate_beta(self, btc_prices, altcoin_prices, asset_symbol, volatility_regime=None):
        """
        Calculate regime-specific beta coefficients
        
        Args:
            btc_prices: DataFrame with BTC price data
            altcoin_prices: DataFrame with altcoin price data
            asset_symbol: Symbol of the altcoin
            volatility_regime: Current volatility regime (HIGH, MEDIUM, LOW)
            
        Returns:
            Dictionary with beta coefficients for each regime
        """
        # Initialize results
        beta_results = {
            "asset": asset_symbol,
            "timestamp": datetime.now().isoformat(),
            "regimes": {
                "HIGH": 0,
                "MEDIUM": 0,
                "LOW": 0
            },
            "current_regime": volatility_regime if volatility_regime else "MEDIUM",
            "current_beta": 0
        }
        
        try:
            # Calculate returns for both assets (using daily data for reliability)
            btc_daily = btc_prices.get("1d", pd.DataFrame())
            alt_daily = altcoin_prices.get("1d", pd.DataFrame())
            
            if btc_daily.empty or alt_daily.empty:
                if self.debug:
                    print(f"Insufficient data for beta calculation: {asset_symbol}")
                return beta_results
                
            # Merge data and calculate returns
            combined = pd.merge(
                btc_daily, 
                alt_daily,
                left_index=True, 
                right_index=True, 
                suffixes=('_btc', '_alt')
            )
            
            # Calculate returns
            combined['btc_return'] = combined['close_btc'].pct_change()
            combined['alt_return'] = combined['close_alt'].pct_change()
            combined = combined.dropna()
            
            if len(combined) < 30:
                if self.debug:
                    print(f"Insufficient data points for beta calculation: {len(combined)} < 30")
                
                # Calculate basic beta if we have at least 5 data points
                if len(combined) >= 5:
                    cov = np.cov(combined['alt_return'], combined['btc_return'])[0, 1]
                    var = np.var(combined['btc_return'])
                    beta = cov / var if var != 0 else 1.0
                    
                    # Use this as the default for all regimes
                    beta_results["regimes"]["HIGH"] = beta
                    beta_results["regimes"]["MEDIUM"] = beta
                    beta_results["regimes"]["LOW"] = beta
                    beta_results["current_beta"] = beta
                
                return beta_results
            
            # Calculate rolling volatility for segmentation
            combined['btc_volatility'] = combined['btc_return'].rolling(window=30).std()
            combined = combined.dropna()  # Remove NaN values after rolling calc
            
            # Segment data into volatility regimes
            # High: Top 30% of historical volatility
            # Medium: Middle 40%
            # Low: Bottom 30%
            high_threshold = combined['btc_volatility'].quantile(0.7)
            low_threshold = combined['btc_volatility'].quantile(0.3)
            
            high_vol_data = combined[combined['btc_volatility'] >= high_threshold]
            low_vol_data = combined[combined['btc_volatility'] <= low_threshold]
            med_vol_data = combined[(combined['btc_volatility'] > low_threshold) & 
                                   (combined['btc_volatility'] < high_threshold)]
            
            # Calculate beta for each regime
            # β = Cov(altcoin_returns, btc_returns) / Var(btc_returns)
            
            # High volatility regime
            if len(high_vol_data) >= 5:  # Ensure sufficient data
                try:
                    cov_high = np.cov(high_vol_data['alt_return'], high_vol_data['btc_return'])[0, 1]
                    var_high = np.var(high_vol_data['btc_return'])
                    beta_high = cov_high / var_high if var_high != 0 else 1.0
                    beta_results["regimes"]["HIGH"] = beta_high
                except Exception as e:
                    if self.debug:
                        print(f"Error calculating HIGH regime beta: {e}")
            
            # Medium volatility regime
            if len(med_vol_data) >= 5:
                try:
                    cov_med = np.cov(med_vol_data['alt_return'], med_vol_data['btc_return'])[0, 1]
                    var_med = np.var(med_vol_data['btc_return'])
                    beta_med = cov_med / var_med if var_med != 0 else 1.0
                    beta_results["regimes"]["MEDIUM"] = beta_med
                except Exception as e:
                    if self.debug:
                        print(f"Error calculating MEDIUM regime beta: {e}")
            
            # Low volatility regime
            if len(low_vol_data) >= 5:
                try:
                    cov_low = np.cov(low_vol_data['alt_return'], low_vol_data['btc_return'])[0, 1]
                    var_low = np.var(low_vol_data['btc_return'])
                    beta_low = cov_low / var_low if var_low != 0 else 1.0
                    beta_results["regimes"]["LOW"] = beta_low
                except Exception as e:
                    if self.debug:
                        print(f"Error calculating LOW regime beta: {e}")
            
            # Set current beta based on the specified regime
            if volatility_regime in beta_results["regimes"]:
                beta_results["current_beta"] = beta_results["regimes"][volatility_regime]
            else:
                # Default to MEDIUM regime if not specified
                beta_results["current_beta"] = beta_results["regimes"]["MEDIUM"]
                
            if self.debug:
                print(f"Calculated beta coefficients for {asset_symbol}:")
                print(f"  HIGH regime: {beta_results['regimes']['HIGH']:.3f} ({len(high_vol_data)} data points)")
                print(f"  MEDIUM regime: {beta_results['regimes']['MEDIUM']:.3f} ({len(med_vol_data)} data points)")
                print(f"  LOW regime: {beta_results['regimes']['LOW']:.3f} ({len(low_vol_data)} data points)")
                print(f"  Current regime: {beta_results['current_regime']}")
                print(f"  Current beta: {beta_results['current_beta']:.3f}")
                
        except Exception as e:
            if self.debug:
                print(f"Error calculating beta: {e}")
        
        return beta_results
    
    def cache_beta_data(self, beta_data, asset_symbol):
        """Save beta data to cache"""
        try:
            cache_dir = os.path.join("price_data", "beta_cache")
            os.makedirs(cache_dir, exist_ok=True)
            
            cache_file = os.path.join(cache_dir, f"{asset_symbol}_beta.json")
            
            with open(cache_file, 'w') as f:
                json.dump(beta_data, f, indent=2)
                
            if self.debug:
                print(f"Cached beta data for {asset_symbol}")
                
            return True
        except Exception as e:
            if self.debug:
                print(f"Error caching beta data: {e}")
            return False
            
    def load_cached_beta_data(self, asset_symbol):
        """Load beta data from cache"""
        try:
            cache_file = os.path.join("price_data", "beta_cache", f"{asset_symbol}_beta.json")
            
            if not os.path.exists(cache_file):
                return None
                
            # Check if file is not too old (less than 24 hours)
            file_age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(cache_file))
            if file_age > timedelta(hours=24):
                return None
                
            with open(cache_file, 'r') as f:
                beta_data = json.load(f)
                
            if self.debug:
                print(f"Loaded cached beta data for {asset_symbol}")
                
            return beta_data
        except Exception as e:
            if self.debug:
                print(f"Error loading cached beta data: {e}")
            return None
