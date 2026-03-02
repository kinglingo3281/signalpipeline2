#!/usr/bin/env python
"""Market Context Module
--------------------
Provides market context data for enhanced liquidation analysis including:
- Market volatility metrics
- Trend direction and strength
- Support/resistance levels
- Market bias metrics
"""

import os
import sys
import math
import json
import random
import logging
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import time
import warnings
from typing import Dict, List, Optional, Union, Any, Tuple

# Add parent directory to path to allow imports from root after moving to utils/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Define project root for consistent file paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Rate limit tracking
HL_LAST_RATE_LIMIT = 0

# Volatility regime detection has been disabled

# Local implementation of Technical Analysis indicators using pandas directly
PANDAS_AVAILABLE = True
print("Using pandas for local technical analysis")

# Import Hyperliquid API for candles
from hyperliquid.info import Info

# Import TAAPI fallback provider
try:
    from utils.taapi_fallback import TaapiProvider
except ImportError:
    try:
        from taapi_fallback import TaapiProvider
    except ImportError:
        print("Warning: taapi_fallback module not found")
        TaapiProvider = None

# Volatility regime detection has been disabled

class TechnicalIndicatorPuller:
    def __init__(self, *args, **kwargs):
        self.debug = kwargs.get('debug', False)
        self.hl_info = Info()
        
    def fetch_candles(self, symbol, interval="1h", days=14):
        """Fetch candle data from Hyperliquid"""
        global HL_LAST_RATE_LIMIT
        
        try:
            # Extract asset name from symbol (e.g., "BTC/USDT" -> "BTC")
            asset = symbol.split('/')[0] if '/' in symbol else symbol
            
            # Set time range
            end_time = int(datetime.now().timestamp() * 1000)  # Current time in ms
            start_time = end_time - (days * 24 * 60 * 60 * 1000)  # days ago in ms
            
            # Check if we need to wait for rate limit
            current_time = time.time()
            if HL_LAST_RATE_LIMIT > 0 and current_time - HL_LAST_RATE_LIMIT < 30:
                wait_time = 30 - (current_time - HL_LAST_RATE_LIMIT)
                if self.debug:
                    print(f"Waiting {wait_time:.1f} seconds for Hyperliquid rate limit to reset...")
                time.sleep(wait_time)
            
            # Get candle data from Hyperliquid
            if self.debug:
                print(f"Fetching {interval} candles for {asset} from Hyperliquid...")
            
            try:    
                candle_data = self.hl_info.candles_snapshot(asset, interval, start_time, end_time)
                
                if not candle_data or len(candle_data) == 0:
                    if self.debug:
                        print(f"No candle data available for {asset}")
                    return []
                    
                if self.debug:
                    print(f"Received {len(candle_data)} candles from Hyperliquid API")
                    
                return candle_data
                
            except Exception as e:
                # Check if it's a rate limit error
                if '429' in str(e) or 'rate limit' in str(e).lower():
                    HL_LAST_RATE_LIMIT = time.time()
                    print(f"Hyperliquid rate limit hit for {asset}, pausing for 30 seconds...")
                    time.sleep(30)  # Hard pause for 30 seconds
                    return []  # Return empty list to trigger fallback
                else:
                    raise  # Re-raise other exceptions
            
        except Exception as e:
            if self.debug:
                print(f"Error fetching candle data: {e}")
            return []
    
    def preprocess_candles(self, candle_data):
        """Convert Hyperliquid candles to pandas DataFrame"""
        if not candle_data:
            return None
            
        # Extract OHLCV data
        data = {
            'timestamp': [],
            'open': [],
            'high': [],
            'low': [],
            'close': [],
            'volume': []
        }
        
        for candle in candle_data:
            data['timestamp'].append(candle['t'])
            data['open'].append(float(candle['o']))
            data['high'].append(float(candle['h']))
            data['low'].append(float(candle['l']))
            data['close'].append(float(candle['c']))
            data['volume'].append(float(candle['v']))
        
        # Create DataFrame
        df = pd.DataFrame(data)
        return df
        
    def calculate_indicators(self, df):
        """Calculate technical indicators using direct pandas implementation"""
        if df is None or len(df) < 20:
            return {}
            
        try:
            # Create a new DataFrame to avoid modifying the original
            result_df = df.copy()
            
            # Calculate volatility indicators
            self._calculate_bbands(result_df, 'close', 20, 2)
            self._calculate_atr(result_df, 14)
            self._calculate_stdev(result_df, 'close', 20)
            
            # Calculate trend indicators
            self._calculate_adx(result_df, 14)
            self._calculate_macd(result_df, 'close', 12, 26, 9)
            
            # Calculate EMAs
            self._calculate_ema(result_df, 'close', 20)
            self._calculate_ema(result_df, 'close', 50)
            self._calculate_ema(result_df, 'close', 200)
            
            # Calculate basic Ichimoku Cloud equivalent
            self._calculate_ichimoku(result_df)
            
            # Get the latest values (most recent candle)
            latest = result_df.iloc[-1].to_dict()
            
            return latest
            
        except Exception as e:
            print(f"Error calculating indicators: {e}")
            return {}
    
    def format_indicators(self, indicators):
        """Format indicators to match the expected structure"""
        if not indicators:
            return {}
            
        # Format the output to match the expected structure
        return {
            "volatility": {
                "atr": {"value": {"value": indicators.get('ATR_14', 0)}},
                "bbands": {"value": {
                    "valueUpperBand": indicators.get('BBU_20_2.0', 0),
                    "valueLowerBand": indicators.get('BBL_20_2.0', 0),
                    "valueMiddleBand": indicators.get('BBM_20_2.0', 0)
                }},
                "stddev": {"value": {"value": indicators.get('STDEV_20', 0)}}
            },
            "trend": {
                "adx": {"value": {"value": indicators.get('ADX_14', 25)}},  # Default 25 (neutral)
                "dmi": {"value": {
                    "plusDI": indicators.get('DMP_14', 20),  # Default neutral
                    "minusDI": indicators.get('DMN_14', 20)   # Default neutral
                }},
                "macd": {"value": {
                    "valueMACD": indicators.get('MACD_12_26_9', 0),
                    "valueMACDSignal": indicators.get('MACDs_12_26_9', 0),
                    "valueMACDHist": indicators.get('MACDh_12_26_9', 0)
                }}
            },
            "moving_averages": {
                "ema20": {"value": {"value": indicators.get('EMA_20', 0)}},
                "ema50": {"value": {"value": indicators.get('EMA_50', 0)}},
                "ema200": {"value": {"value": indicators.get('EMA_200', 0)}}
            },
            "ichimoku": {"value": {
                "tenkan": indicators.get('ISA_9', 0),
                "kijun": indicators.get('ISB_26', 0),
                "senkou_a": indicators.get('ITS_9', 0),
                "senkou_b": indicators.get('IKS_26', 0),
                "chikou": indicators.get('ICS_26', 0)
            }}
        }
        
    # Helper methods for calculating indicators
    def _calculate_ema(self, df, column, length):
        """Calculate EMA for a column"""
        df[f'EMA_{length}'] = df[column].ewm(span=length, adjust=False).mean()
    
    def _calculate_bbands(self, df, column, length, std):
        """Calculate Bollinger Bands"""
        # Middle band (SMA)
        df['BBM_20_2.0'] = df[column].rolling(window=length).mean()
        # Standard deviation
        rolling_std = df[column].rolling(window=length).std()
        # Upper and lower bands
        df['BBU_20_2.0'] = df['BBM_20_2.0'] + (rolling_std * std)
        df['BBL_20_2.0'] = df['BBM_20_2.0'] - (rolling_std * std)
    
    def _calculate_stdev(self, df, column, length):
        """Calculate Standard Deviation"""
        df['STDEV_20'] = df[column].rolling(window=length).std()
    
    def _calculate_atr(self, df, length):
        """Calculate Average True Range"""
        # True Range
        df['TR'] = np.maximum(
            np.maximum(
                df['high'] - df['low'],
                np.abs(df['high'] - df['close'].shift(1))
            ),
            np.abs(df['low'] - df['close'].shift(1))
        )
        # Average True Range
        df['ATR_14'] = df['TR'].rolling(window=length).mean()
    
    def _calculate_adx(self, df, length):
        """Calculate Average Directional Index (simplified version)"""
        # For simplicity, set a reasonable value
        df['ADX_14'] = 25  # Neutral value
        df['DMP_14'] = 20  # Neutral value
        df['DMN_14'] = 20  # Neutral value
    
    def _calculate_macd(self, df, column, fast, slow, signal):
        """Calculate MACD"""
        # Fast EMA
        fast_ema = df[column].ewm(span=fast, adjust=False).mean()
        # Slow EMA
        slow_ema = df[column].ewm(span=slow, adjust=False).mean()
        # MACD Line
        df['MACD_12_26_9'] = fast_ema - slow_ema
        # Signal Line
        df['MACDs_12_26_9'] = df['MACD_12_26_9'].ewm(span=signal, adjust=False).mean()
        # Histogram
        df['MACDh_12_26_9'] = df['MACD_12_26_9'] - df['MACDs_12_26_9']
    
    def _calculate_ichimoku(self, df):
        """Calculate basic Ichimoku Cloud equivalent"""
        # For simplicity, set reasonable values
        df['ISA_9'] = df['close'].rolling(window=9).mean()  # Tenkan-sen (Conversion Line)
        df['ISB_26'] = df['close'].rolling(window=26).mean()  # Kijun-sen (Base Line)
        # Simplified Senkou Span calculations
        df['ITS_9'] = ((df['ISA_9'] + df['ISB_26']) / 2).shift(26)  # Leading Span A
        df['IKS_26'] = df['close'].rolling(window=52).mean().shift(26)  # Leading Span B
        df['ICS_26'] = df['close'].shift(-26)  # Chikou Span (Lagging Span)
    
    def fetch_all_indicators(self, symbol):
        """Fetch and calculate all technical indicators for a symbol"""
        if not PANDAS_AVAILABLE:
            print("pandas not available, returning empty indicators")
            return {}
            
        # Fetch candle data
        candles = self.fetch_candles(symbol)
        
        # Preprocess candles
        df = self.preprocess_candles(candles)
        
        # No data available
        if df is None or len(df) < 20:
            return {}
            
        # Calculate indicators
        indicators = self.calculate_indicators(df)
        
        # Format indicators to match expected structure
        formatted = self.format_indicators(indicators)
        
        return formatted

class MarketContext:
    """Provides market context for enhanced liquidation analysis"""
    
    def __init__(self, asset, current_price, debug=False):
        """Initialize market context with asset and current price"""
        self.asset = asset
        self.current_price = current_price
        self.debug = debug
        self.taapi = TaapiProvider(debug=debug)
        self.puller = TechnicalIndicatorPuller(debug=debug)
        self.last_update = None
        self.market_data = None
        self.logger = self._setup_logger()
        
        # Initialize with default context data
        self.context_data = {
            "asset": asset,
            "current_price": current_price,
            "timestamp": datetime.now().isoformat(),
            "volatility": {
                "level": "UNKNOWN",
                "percentile": 0.0,
                "atr_percent": 0.0,
                "recent_range_percent": 0.0
            },
            "trend": {
                "direction": "NEUTRAL",
                "strength": 0.0,
                "in_trend": False,
                "ema_alignment": "NEUTRAL"
            },
            "support_resistance": {
                "support_levels": [],
                "resistance_levels": [],
                "closest_support": None,
                "closest_resistance": None
            },
            "market_bias": {
                "bias": "NEUTRAL",
                "bias_strength": 0.0,
                "price_in_range": True
            },
            "volatility_regime": {
                "classification": "NORMAL",
                "ratio": 1.0,
                "baseline_atr": 0.0,
                "regime_changed": False,
                "previous_regime": None,
                "last_updated": datetime.now().isoformat()
            }
        }
        
    def fetch_market_data(self):
        """Fetch market data from external sources with TAAPI fallback"""
        try:
            # Use TA API to get technical indicators from Hyperliquid
            indicator_puller = TechnicalIndicatorPuller(debug=self.debug)
            formatted_symbol = f"{self.asset}/USDT"
            self.ta_data = indicator_puller.fetch_all_indicators(formatted_symbol)
            
            if self.debug:
                print(f"Fetched technical data for {formatted_symbol}")
                print(f"Technical data categories: {list(self.ta_data.keys()) if self.ta_data else 'None'}")
                
            # Check if we need TAAPI fallback
            if self._needs_fallback(self.ta_data):
                if self.debug:
                    print(f"Using TAAPI fallback for {self.asset} due to missing or invalid data")
                    
                # Initialize TAAPI provider
                taapi_provider = TaapiProvider(debug=self.debug)
                
                try:
                    # Fetch data from TAAPI
                    taapi_data = taapi_provider.fetch_indicators_bulk(self.asset)
                    
                    if taapi_data:
                        if self.debug:
                            print(f"Successfully fetched TAAPI data for {self.asset}")
                            
                        # If Hyperliquid data is completely missing, use TAAPI data directly
                        if not self.ta_data:
                            self.ta_data = taapi_data
                        else:
                            # Merge data: Use TAAPI data for missing indicators
                            self._merge_indicator_data(taapi_data)
                    else:
                        if self.debug:
                            print(f"Failed to fetch TAAPI data for {self.asset}")
                except Exception as e:
                    # TAAPI rate limit handling is done internally in TaapiProvider class
                    if self.debug:
                        print(f"Error using TAAPI fallback: {e}")
            
            # Analyze the data and update context
            self._analyze_market_data()
            return True
            
        except Exception as e:
            if self.debug:
                print(f"Error fetching market data: {e}")
            try:
                # Complete fallback to TAAPI if Hyperliquid fails entirely
                if self.debug:
                    print(f"Attempting full TAAPI fallback for {self.asset}")
                
                taapi_provider = TaapiProvider(debug=self.debug)
                self.ta_data = taapi_provider.fetch_indicators_bulk(self.asset)
                
                if self.ta_data:
                    if self.debug:
                        print(f"Successfully fetched full TAAPI fallback data for {self.asset}")
                    self._analyze_market_data()
                    return True
                    
            except Exception as taapi_error:
                if self.debug:
                    print(f"TAAPI fallback also failed: {taapi_error}")
            
            # Last resort: basic analysis without external data
            self._analyze_market_data(use_external=False)
            return False
    
    def _merge_indicator_data(self, taapi_data):
        """Merge TAAPI data with existing Hyperliquid data
        
        Args:
            taapi_data (dict): Technical indicator data from TAAPI
        """
        if not taapi_data or not self.ta_data:
            return
            
        # Critical indicators to check and merge
        critical_indicators = [
            "ema20", "ema50", "ema200", "rsi", "macd", "adx", 
            "bb_upper", "bb_lower", "bb_middle", "atr", "stddev"
        ]
        
        # Replace missing or zero values in Hyperliquid data with TAAPI data
        for indicator in critical_indicators:
            if indicator not in self.ta_data or self._check_ema_value(self.ta_data.get(indicator, 0)):
                if indicator in taapi_data:
                    self.ta_data[indicator] = taapi_data[indicator]
                    if self.debug:
                        print(f"Replaced {indicator} with TAAPI data")
        
        # Handle nested structures like volatility and trend
        for category in ["volatility", "trend", "support_resistance"]:
            if category in taapi_data and (category not in self.ta_data or not self.ta_data[category]):
                self.ta_data[category] = taapi_data[category]
                if self.debug:
                    print(f"Replaced {category} with TAAPI data")
        
        # Handle moving_averages specifically since it's a nested structure
        if "moving_averages" in taapi_data and ("moving_averages" not in self.ta_data or not self.ta_data["moving_averages"]):
            self.ta_data["moving_averages"] = taapi_data["moving_averages"]
            if self.debug:
                print("Replaced moving_averages with TAAPI data")
    
    def _needs_fallback(self, data):
        """Determine if data needs fallback from TAAPI
        
        Args:
            data: Dictionary containing technical indicators
            
        Returns:
            bool: True if fallback is needed, False otherwise
        """
        # Only check for completely missing data or empty dictionary
        # This means there was likely a 429 error or candle data fetch failure
        if data is None or not data:
            if self.debug:
                print("No data available, fallback needed")
            return True
            
        # First, check if we have the main category structures
        required_categories = ["moving_averages", "trend"]
        
        for category in required_categories:
            if category not in data:
                if self.debug:
                    print(f"Missing essential category: {category}, fallback needed")
                return True
        
        # Then check for specific essential indicators in their proper nested locations
        # Remember our indicators are nested like data['moving_averages']['ema20']
        essential_indicators = [
            ("moving_averages", "ema20"),
            ("moving_averages", "ema50"),
            ("moving_averages", "ema200"),
            ("trend", "macd")
        ]
        
        # If we're missing more than half of the essential indicators, use fallback
        missing_count = 0
        for category, indicator in essential_indicators:
            if category not in data or indicator not in data[category]:
                missing_count += 1
                if self.debug:
                    print(f"DEBUG: {indicator} NOT found in data[{category}]!")
        
        # Only trigger fallback if most essential indicators are missing
        # This prevents fallback from occurring when we have at least some data
        if missing_count > len(essential_indicators) // 2:
            if self.debug:
                print(f"Missing {missing_count}/{len(essential_indicators)} essential indicators, fallback needed")
            return True
        
        # If we have most essential indicators, don't use fallback
        # Let the regular processing handle any minor missing indicators
        return False
        
    def _check_ema_value(self, value):
        """Check if EMA value is valid"""
        if isinstance(value, dict) and "value" in value:
            # Handle nested structure: value -> value -> actual_value
            if isinstance(value["value"], dict) and "value" in value["value"]:
                return value["value"]["value"] == 0
        return value == 0
        
    def _analyze_market_data(self, use_external=True):
        """Analyze market data and update context"""
        try:
            # Analyze volatility
            self._analyze_volatility(use_external=use_external)
            
            # Analyze market bias
            self._analyze_market_bias(use_external=use_external)
            
            # Analyze support and resistance levels
            self._identify_support_resistance(use_external=use_external)
            
            # Calculate market bias
            self._calculate_market_bias()
            
            return self.context_data
        
        except Exception as e:
            if self.debug:
                print(f"Error analyzing market data: {e}")
            return None
        
        return self.context_data
    
    def _setup_logger(self):
        """Setup a logger for this instance"""
        logger = logging.getLogger(f"MarketContext_{self.asset}")
        logger.setLevel(logging.INFO)
        return logger
        
    # Volatility regime functionality has been removed
    
    def _analyze_volatility(self, use_external=True):
        """Analyze market volatility"""
        vol_data = self.context_data["volatility"]
        
        # Default/fallback values
        vol_level = "MEDIUM"
        vol_percentile = 0.5
        atr_percent = 0.02  # 2% as default
        range_percent = 0.03  # 3% as default
        
        if use_external and "volatility" in self.ta_data:
            try:
                # Get ATR data
                if "atr" in self.ta_data.get("volatility", {}):
                    atr_value = self.ta_data["volatility"]["atr"]["value"]["value"]
                    atr_percent = atr_value / self.current_price
                    
                # Get Bollinger Bands width for volatility
                if "bbands" in self.ta_data.get("volatility", {}):
                    bb_data = self.ta_data["volatility"]["bbands"]["value"]
                    upper = bb_data.get("valueUpperBand", 0)
                    lower = bb_data.get("valueLowerBand", 0)
                    bb_width = (upper - lower) / self.current_price
                    
                    # Normalize BB width to a percentile (rough estimation)
                    # A narrow band (< 2% width) indicates low volatility
                    # A wide band (> 6% width) indicates high volatility
                    if bb_width < 0.02:
                        vol_level = "LOW"
                        vol_percentile = 0.25
                    elif bb_width > 0.06:
                        vol_level = "HIGH"
                        vol_percentile = 0.75
                    elif bb_width > 0.1:
                        vol_level = "EXTREME"
                        vol_percentile = 0.95
                        
                # Get standard deviation
                if "stddev" in self.ta_data.get("volatility", {}):
                    stddev = self.ta_data["volatility"]["stddev"]["value"]["value"]
                    stddev_percent = stddev / self.current_price
                    
                    # Use standard deviation to refine volatility estimate
                    if stddev_percent > 0.05:
                        vol_level = "HIGH"
                        vol_percentile = max(vol_percentile, 0.8)
                    elif stddev_percent < 0.01:
                        vol_level = "LOW"
                        vol_percentile = min(vol_percentile, 0.3)
            
            except Exception as e:
                if self.debug:
                    print(f"Error analyzing volatility: {e}")
        
        # Update volatility data
        vol_data["level"] = vol_level
        vol_data["percentile"] = vol_percentile
        vol_data["atr_percent"] = atr_percent
        vol_data["recent_range_percent"] = range_percent
        
        # Update volatility regime classification
        self.update_volatility_regime()
        
        if self.debug:
            print(f"Volatility analysis: {vol_level} ({vol_percentile:.2f})")
            print(f"Volatility regime: {self.context_data['volatility_regime']['classification']}")
            
        return vol_data
    
    def _analyze_trend(self, use_external=True):
        """Analyze market trend"""
        trend_data = self.context_data["trend"]
        
        # Default/fallback values
        direction = "NEUTRAL"
        strength = 0.5
        in_trend = False
        ema_alignment = "NEUTRAL"
        
        if use_external and self.ta_data:
            try:
                # Check ADX for trend strength
                if "adx" in self.ta_data.get("trend", {}):
                    adx_value = self.ta_data["trend"]["adx"]["value"]["value"]
                    # ADX interpretation:
                    # < 20: No trend
                    # 20-30: Weak trend
                    # 30-50: Strong trend
                    # > 50: Very strong trend
                    if adx_value < 20:
                        strength = 0.3
                        in_trend = False
                    elif adx_value < 30:
                        strength = 0.5
                        in_trend = True
                    elif adx_value < 50:
                        strength = 0.75
                        in_trend = True
                    else:
                        strength = 0.9
                        in_trend = True
                
                # Check DMI for trend direction
                if "dmi" in self.ta_data.get("trend", {}):
                    dmi_data = self.ta_data["trend"]["dmi"]["value"]
                    plus_di = dmi_data.get("plusDI", 0)
                    minus_di = dmi_data.get("minusDI", 0)
                    
                    if plus_di > minus_di:
                        direction = "BULLISH"
                    elif minus_di > plus_di:
                        direction = "BEARISH"
                    else:
                        direction = "NEUTRAL"
                
                # Check MACD for trend confirmation
                if "macd" in self.ta_data.get("trend", {}):
                    macd_data = self.ta_data["trend"]["macd"]["value"]
                    macd_line = macd_data.get("valueMACD", 0)
                    signal_line = macd_data.get("valueMACDSignal", 0)
                    
                    if macd_line > signal_line:
                        # Confirm bullish if MACD supports it
                        if direction == "BULLISH":
                            strength = min(1.0, strength + 0.1)
                        elif direction == "BEARISH":
                            # Conflicting signals
                            strength = max(0.3, strength - 0.2)
                            direction = "MIXED"
                    elif macd_line < signal_line:
                        # Confirm bearish if MACD supports it
                        if direction == "BEARISH":
                            strength = min(1.0, strength + 0.1)
                        elif direction == "BULLISH":
                            # Conflicting signals
                            strength = max(0.3, strength - 0.2)
                            direction = "MIXED"
                
                # Check moving average alignment
                ma_data = self.ta_data.get("moving_averages", {})
                ema20 = ma_data.get("ema20", {}).get("value", {}).get("value", 0)
                ema50 = ma_data.get("ema50", {}).get("value", {}).get("value", 0)
                ema200 = ma_data.get("ema200", {}).get("value", {}).get("value", 0)
                
                if ema20 and ema50 and ema200:
                    if ema20 > ema50 > ema200:
                        ema_alignment = "BULLISH"
                        if direction in ["BULLISH", "NEUTRAL"]:
                            direction = "BULLISH"
                            strength = min(1.0, strength + 0.15)
                    elif ema20 < ema50 < ema200:
                        ema_alignment = "BEARISH"
                        if direction in ["BEARISH", "NEUTRAL"]:
                            direction = "BEARISH"
                            strength = min(1.0, strength + 0.15)
                    elif ema20 > ema50 and ema50 < ema200:
                        ema_alignment = "NEUTRAL_BULLISH"
                    elif ema20 < ema50 and ema50 > ema200:
                        ema_alignment = "NEUTRAL_BEARISH"
                    else:
                        ema_alignment = "NEUTRAL"
            
            except Exception as e:
                if self.debug:
                    print(f"Error analyzing trend: {e}")
        
        # Update trend data
        trend_data["direction"] = direction
        trend_data["strength"] = strength
        trend_data["in_trend"] = in_trend
        trend_data["ema_alignment"] = ema_alignment
        
        if self.debug:
            print(f"Trend analysis: {direction} (strength: {strength:.2f}), EMA alignment: {ema_alignment}")
            
        return trend_data
    
    def _calculate_market_bias(self):
        """Calculate market bias based on trend and volatility"""
        # Get necessary data from context
        trend_data = self.context_data["trend"]
        vol_data = self.context_data["volatility"]
        sr_data = self.context_data["support_resistance"]
        
        bias_data = self.context_data["market_bias"]
        
        # Default values
        bias = "NEUTRAL"
        bias_strength = 0.5
        price_in_range = True
        
        # Determine bias based on trend and other factors
        trend_direction = trend_data["direction"]
        trend_strength = trend_data["strength"]
        ema_alignment = trend_data["ema_alignment"]
        
        if trend_direction == "BULLISH":
            bias = "BULLISH"
            bias_strength = trend_strength
        elif trend_direction == "BEARISH":
            bias = "BEARISH"
            bias_strength = trend_strength
        elif "BULLISH" in ema_alignment:
            bias = "BULLISH"
            bias_strength = 0.3
        elif "BEARISH" in ema_alignment:
            bias = "BEARISH"
            bias_strength = 0.3
            
        # Check if current price is near support/resistance
        closest_support = sr_data.get("closest_support")
        closest_resistance = sr_data.get("closest_resistance")
        
        # Update bias data
        bias_data["bias"] = bias
        bias_data["bias_strength"] = bias_strength
        bias_data["price_in_range"] = price_in_range
        
        if self.debug:
            print(f"Market bias: {bias} (strength: {bias_strength:.2f})")
            
        return bias_data
    
    def _identify_support_resistance(self, use_external=True):
        """Identify support and resistance levels"""
        sr_data = self.context_data["support_resistance"]
        
        # Default/fallback values - generate some reasonable levels based on current price
        support_levels = [
            round(self.current_price * 0.95, 2),
            round(self.current_price * 0.9, 2),
            round(self.current_price * 0.85, 2)
        ]
        
        resistance_levels = [
            round(self.current_price * 1.05, 2),
            round(self.current_price * 1.1, 2),
            round(self.current_price * 1.15, 2)
        ]
        
        if use_external and self.ta_data:
            try:
                # Use Bollinger Bands for support/resistance
                if "bbands" in self.ta_data.get("volatility", {}):
                    bb_data = self.ta_data["volatility"]["bbands"]["value"]
                    upper = bb_data.get("valueUpperBand", 0)
                    lower = bb_data.get("valueLowerBand", 0)
                    middle = bb_data.get("valueMiddleBand", 0)
                    
                    # Add these as potential levels
                    if lower < self.current_price:
                        support_levels.append(lower)
                    if upper > self.current_price:
                        resistance_levels.append(upper)
                    
                # Use EMA levels as potential support/resistance
                ma_data = self.ta_data.get("moving_averages", {})
                for ma_key, ma_info in ma_data.items():
                    if "value" in ma_info and "value" in ma_info["value"]:
                        ma_value = ma_info["value"]["value"]
                        if ma_value < self.current_price:
                            support_levels.append(ma_value)
                        else:
                            resistance_levels.append(ma_value)
                
                # Use Ichimoku cloud for additional levels
                if "ichimoku" in self.ta_data.get("trend", {}):
                    ichi_data = self.ta_data["trend"]["ichimoku"]["value"]
                    tenkan = ichi_data.get("tenkan", 0)
                    kijun = ichi_data.get("kijun", 0)
                    senkou_a = ichi_data.get("senkou_a", 0)
                    senkou_b = ichi_data.get("senkou_b", 0)
                    
                    for level in [tenkan, kijun, senkou_a, senkou_b]:
                        if level and level < self.current_price:
                            support_levels.append(level)
                        elif level and level > self.current_price:
                            resistance_levels.append(level)
            
            except Exception as e:
                if self.debug:
                    print(f"Error identifying support/resistance: {e}")
        
        # Sort and filter the levels
        support_levels = sorted(set(support_levels), reverse=True)
        resistance_levels = sorted(set(resistance_levels))
        
        # Find closest levels
        closest_support = max([s for s in support_levels if s < self.current_price], default=support_levels[0])
        closest_resistance = min([r for r in resistance_levels if r > self.current_price], default=resistance_levels[0])
        
        # Update support/resistance data
        sr_data["support_levels"] = support_levels
        sr_data["resistance_levels"] = resistance_levels
        sr_data["closest_support"] = closest_support
        sr_data["closest_resistance"] = closest_resistance
        
        if self.debug:
            print(f"Closest support: {closest_support}, Closest resistance: {closest_resistance}")
            
        return sr_data
    
    @property
    def key_levels(self):
        """Return combined support and resistance levels for use in technical analysis
        
        Returns:
            list: All support and resistance levels combined and sorted
        """
        # Use the same structure as generated by the primary Hyperliquid method
        support_levels = self.context_data["support_resistance"].get("support_levels", [])
        resistance_levels = self.context_data["support_resistance"].get("resistance_levels", [])
        
        # Fallback to reasonable levels if none exist
        if not support_levels and not resistance_levels:
            # Generate levels around current price similar to the primary method
            price = self.current_price
            support_levels = [round(price * 0.95, 2), round(price * 0.9, 2), round(price * 0.85, 2)]
            resistance_levels = [round(price * 1.05, 2), round(price * 1.1, 2), round(price * 1.15, 2)]
            
            # Update context data to match
            self.context_data["support_resistance"]["support_levels"] = support_levels
            self.context_data["support_resistance"]["resistance_levels"] = resistance_levels
        
        # Combine all levels and sort them (exactly what primary method would do)
        return sorted(list(set(support_levels + resistance_levels)))
    
    def get_volatility(self):
        """Get normalized volatility metric for use in dynamic stop loss calculation
        
        Returns:
            float: ATR as percentage of price, or standard deviation if ATR not available
        """
        # Prefer ATR as volatility metric for stop loss calculations
        atr_percent = self.context_data["volatility"].get("atr_percent", 0.02)
        
        # If ATR is too low, check if we have other volatility metrics
        if atr_percent < 0.005:
            # Fall back to other metrics if available
            bb_width = 0
            if "volatility" in self.ta_data and "bbands" in self.ta_data["volatility"]:
                bb_data = self.ta_data["volatility"]["bbands"]["value"]
                upper = bb_data.get("valueUpperBand", 0)
                lower = bb_data.get("valueLowerBand", 0)
                if upper > lower:
                    bb_width = (upper - lower) / self.current_price
            
        # Default values
        bias = "NEUTRAL"
        bias_strength = 0.5
        price_in_range = True
        
        # Determine bias based on trend and other factors
        trend_direction = trend_data["direction"]
        trend_strength = trend_data["strength"]
        ema_alignment = trend_data["ema_alignment"]
        
        if trend_direction == "BULLISH":
            bias = "BULLISH"
            bias_strength = trend_strength
        elif trend_direction == "BEARISH":
            bias = "BEARISH"
            bias_strength = trend_strength
        elif "BULLISH" in ema_alignment:
            bias = "BULLISH"
            bias_strength = 0.4
        elif "BEARISH" in ema_alignment:
            bias = "BEARISH"
            bias_strength = 0.4
        
        # Check if price is near support or resistance
        closest_support = sr_data["closest_support"]
        closest_resistance = sr_data["closest_resistance"]
        
        if closest_support and closest_resistance:
            support_distance = abs(self.current_price - closest_support) / self.current_price
            resistance_distance = abs(self.current_price - closest_resistance) / self.current_price
            
            # If very close to support, bias becomes more bullish
            if support_distance < 0.01:  # Within 1%
                if bias == "BEARISH":
                    bias = "MIXED"
                    bias_strength = max(0.2, bias_strength - 0.3)
                else:
                    bias = "BULLISH"
                    bias_strength = min(0.9, bias_strength + 0.2)
            
            # If very close to resistance, bias becomes more bearish
            if resistance_distance < 0.01:  # Within 1%
                if bias == "BULLISH":
                    bias = "MIXED"
                    bias_strength = max(0.2, bias_strength - 0.3)
                else:
                    bias = "BEARISH"
                    bias_strength = min(0.9, bias_strength + 0.2)
            
            # Check if price is far from both support and resistance
            if support_distance > 0.05 and resistance_distance > 0.05:
                price_in_range = False
        
        # Update bias data
        bias_data["bias"] = bias
        bias_data["bias_strength"] = bias_strength
        bias_data["price_in_range"] = price_in_range
        
        if self.debug:
            print(f"Market bias: {bias} (strength: {bias_strength:.2f})")
            
        return bias_data
    
    def calculate_dynamic_probability(self, cluster, current_price, direction="long"):
        """
        Calculate dynamic probability scaling for a cluster based on market context
        
        Args:
            cluster: Liquidation cluster data
            current_price: Current price of the asset
            direction: 'long' or 'short'
            
        Returns:
            Dict with adjusted probability metrics
        """
        # Get base data
        center_price = cluster.get("center_price", current_price)
        size = cluster.get("total_size", 0)
        position_count = cluster.get("position_count", 1)
        base_probability = cluster.get("trigger_probability", 0.3)  # Lower default probability
        
        # Get context data
        volatility_level = self.context_data["volatility"]["level"]
        volatility_pct = self.context_data["volatility"]["atr_percent"]
        trend_direction = self.context_data["trend"]["direction"]
        trend_strength = self.context_data["trend"]["strength"]
        market_bias = self.context_data["market_bias"]["bias"]
        
        # Calculate price distance as percentage
        price_distance = abs(center_price - current_price) / current_price
        
        # Calculate price distance in terms of ATR (volatility-adjusted distance)
        # This makes the distance more meaningful in different market conditions
        atr_distance = price_distance / max(0.005, volatility_pct)  # Avoid division by zero
        
        # Base distance factor using exponential decay with stronger decay for further positions
        # Using a much steeper decay curve for more realistic probabilities
        # Distant positions should have very low probabilities
        decay_factor = 35 + random.uniform(-5, 5)  # Add some randomness to the decay rate
        distance_factor = math.exp(-atr_distance * decay_factor)  # Steeper exponential decay
        
        # Hard cap the probability based on distance in ATR units
        # Very distant positions (>3 ATR away) should have near-zero probabilities
        if atr_distance > 3:
            distance_cap = 0.05  # Very low probability cap for distant positions
        elif atr_distance > 2:
            distance_cap = 0.15  # Low probability cap for far positions
        elif atr_distance > 1:
            distance_cap = 0.35  # Moderate probability cap
        else:
            distance_cap = 0.75  # Higher cap for nearby positions
        
        # Apply the cap to distance factor
        distance_factor = min(distance_factor, distance_cap)
        
        # Adjust for volatility with more granular scaling
        # Higher volatility makes distant levels more attainable but with diminishing returns
        if volatility_level == "EXTREME":
            volatility_multiplier = 1.5 + random.uniform(0, 0.3)
        elif volatility_level == "HIGH":
            volatility_multiplier = 1.2 + random.uniform(0, 0.2)
        elif volatility_level == "MEDIUM":
            volatility_multiplier = 1.0 + random.uniform(-0.1, 0.1) 
        else:  # LOW
            volatility_multiplier = 0.7 + random.uniform(-0.1, 0.1)
        
        # Relationship between volatility and distance - in high volatility, distance matters less
        # In low volatility, distance is more important
        if volatility_level in ["HIGH", "EXTREME"]:
            distance_weight = 0.5 - (volatility_pct * 2)  # Reduce importance of distance in high vol
            distance_weight = max(0.3, min(0.6, distance_weight))  # Bound between 0.3-0.6
        else:
            distance_weight = 0.6 + (0.1 * random.random())  # Higher weight to distance in low vol
            
        # Apply volatility adjustment to distance factor
        adjusted_distance_factor = min(0.8, distance_factor * volatility_multiplier)
        
        # Direction alignment factor - boost probability if market is trending in the right direction
        # More nuanced alignment calculation
        direction_alignment = 1.0
        if direction == "long" and center_price < current_price:  # Long liquidation when price falls
            if trend_direction == "BEARISH":
                # Bearish trend increases probability of downward price movement
                direction_alignment = 1.0 + (trend_strength * 0.3 * random.uniform(0.8, 1.2))
            elif trend_direction == "BULLISH":
                # Bullish trend decreases probability of downward price movement
                direction_alignment = 0.7 - (trend_strength * 0.2 * random.uniform(0.8, 1.2))
            else:  # NEUTRAL or MIXED
                direction_alignment = 0.9 + random.uniform(-0.1, 0.1)
        elif direction == "short" and center_price > current_price:  # Short liquidation when price rises
            if trend_direction == "BULLISH":
                # Bullish trend increases probability of upward price movement
                direction_alignment = 1.0 + (trend_strength * 0.3 * random.uniform(0.8, 1.2))
            elif trend_direction == "BEARISH":
                # Bearish trend decreases probability of upward price movement
                direction_alignment = 0.7 - (trend_strength * 0.2 * random.uniform(0.8, 1.2))
            else:  # NEUTRAL or MIXED
                direction_alignment = 0.9 + random.uniform(-0.1, 0.1)
        
        # Bound direction alignment to reasonable values
        direction_alignment = max(0.5, min(1.5, direction_alignment))
        
        # Size factor - larger liquidations are more significant but with diminishing returns
        # Log scale to prevent very large positions from dominating
        size_factor = 0.1 + min(0.5, math.log1p(size / 100) / 5)
        
        # Position diversity factor - more positions in a cluster increases likelihood
        # but with diminishing returns
        diversity_factor = min(0.25, math.log1p(position_count) / 8)
        
        # Time-of-day factor (random for now since we don't have this data)
        # Could be enhanced with actual time-based patterns if available
        time_factor = random.uniform(-0.05, 0.05)
        
        # Calculate base probability - combine factors with appropriate weights and add randomness
        random_noise = random.uniform(-0.05, 0.05)  # Small random noise component
        
        # Base probability formula with more components and randomness
        base_prob = (
            adjusted_distance_factor * distance_weight +  # Distance is key factor
            size_factor * 0.15 +                          # Size has moderate impact
            diversity_factor * 0.1 +                      # Diversity has smaller impact
            time_factor +                                 # Time factor adds small variation
            random_noise                                  # Random noise for natural variation
        ) * direction_alignment                           # Scale by direction alignment
        
        # Cap the base probability at reasonable levels
        base_prob = min(0.75, max(0.01, base_prob))
        
        # Apply a sigmoid function to create more variability in the mid-range
        # This avoids too many probabilities clustered around the extremes
        def sigmoid(x, steepness=6, midpoint=0.4):
            return 1 / (1 + math.exp(-steepness * (x - midpoint)))
        
        # Add trend persistence weighting
        trend_direction = self.context_data["trend"]["direction"]
        trend_strength = self.context_data["trend"]["strength"]
        trend_persistence = 0
        
        # Estimate trend persistence from EMA alignment
        ema_alignment = self.context_data["trend"].get("ema_alignment", "NEUTRAL")
        
        # Higher persistence when EMAs are properly aligned (stronger trends)
        if ema_alignment == "BULLISH" and trend_direction == "UP":
            trend_persistence = trend_strength * 0.8
        elif ema_alignment == "BEARISH" and trend_direction == "DOWN":
            trend_persistence = trend_strength * 0.8
        else:
            # Weaker persistence for non-aligned or mixed signals
            trend_persistence = trend_strength * 0.3
            
        # Adjust probability based on alignment with persistent trend
        persistence_factor = 0
        if (direction == "long" and trend_direction == "UP") or \
           (direction == "short" and trend_direction == "DOWN"):
            # Bonus for alignment with established trend
            persistence_factor = trend_persistence * 0.15  # Up to 15% bonus
        elif trend_persistence > 0.5:  # Only penalize counter-trend if trend is strong
            # Penalty for counter-trend when there's a persistent trend
            persistence_factor = -trend_persistence * 0.2  # Up to 20% penalty
        
        # Get the final adjusted probability
        adjusted_probability = max(0.05, min(0.95, base_prob + persistence_factor))
        
        # Calculate confidence score (0-1)
        confidence_raw = base_prob + persistence_factor
        confidence_score = max(0.05, min(0.95, confidence_raw))
        
        # Calculate confidence score - should be distinct from probability
        # Confidence represents how sure we are about the probability estimate
        
        # Confidence factors:
        # 1. Data quality - more positions = higher confidence
        data_quality = min(0.6, math.log1p(position_count) / 5)
        
        # 2. Distance clarity - very near or very far positions have higher confidence
        # than middle-distance ones (U-shaped curve)
        distance_clarity = 0.3 + 0.3 * abs((atr_distance / 5) - 0.5) * 2
        
        # 3. Trend alignment clarity - stronger trends give higher confidence in direction
        trend_clarity = 0.2 + (trend_strength * 0.4)
        
        # 4. Market consistency - how consistent the market signals are
        vol_trend_alignment = 0.5
        if (volatility_level in ["HIGH", "EXTREME"] and trend_strength > 0.6) or \
           (volatility_level in ["LOW", "MEDIUM"] and trend_strength < 0.4):
            # High volatility with strong trend or low volatility with weak trend are consistent
            vol_trend_alignment = 0.8
        
        # Combine confidence factors
        raw_confidence = (
            data_quality * 0.4 +           # Data quality is important
            distance_clarity * 0.25 +      # Distance clarity matters
            trend_clarity * 0.2 +          # Trend clarity contributes
            vol_trend_alignment * 0.15     # Market consistency helps
        )
        
        # Add slight negative correlation with probability
        # Very high probabilities should generally have lower confidence
        # Very low probabilities might actually have high confidence (e.g., confident it won't happen)
        probability_factor = 1.0 - (abs(adjusted_probability - 0.5) * 0.3)
        
        # Apply a final scaling and add small random variation
        confidence_score = raw_confidence * probability_factor * random.uniform(0.9, 1.1)
        
        # Ensure reasonable bounds
        confidence_score = min(0.85, max(0.1, confidence_score))
        
        return {
            "original_probability": base_probability,
            "adjusted_probability": adjusted_probability,
            "confidence_score": confidence_score,
            "factors": {
                "distance_factor": distance_factor,
                "volatility_multiplier": volatility_multiplier,
                "direction_alignment": direction_alignment,
                "size_factor": size_factor,
                "diversity_factor": diversity_factor, 
                "distance_weight": distance_weight
            }
        }
    
    def generate_enhanced_summary(self, clusters, cascade_data, price_targets, include_explanations=True):
        """
        Generate enhanced summary with trade explanations
        
        Args:
            clusters: Liquidation clusters data
            cascade_data: Cascade probabilities data
            price_targets: Price target data
            include_explanations: Whether to include detailed explanations
            
        Returns:
            Dict with enhanced summary data
        """
        # Extract key data
        long_cascade = cascade_data.get("long_cascade", {})
        short_cascade = cascade_data.get("short_cascade", {})
        long_cascade_prob = long_cascade.get("probability", 0)
        short_cascade_prob = short_cascade.get("probability", 0)
        dominant_direction = cascade_data.get("dominant_direction", "neutral")
        overall_risk = cascade_data.get("risk_level", "UNKNOWN")
        
        # Price target data
        primary_recommendation = price_targets.get("recommendation", {})
        long_targets = price_targets.get("long_targets", [])
        short_targets = price_targets.get("short_targets", [])
        long_ranges = [r for r in price_targets.get("ranges", []) if r.get("direction") == "long"]
        short_ranges = [r for r in price_targets.get("ranges", []) if r.get("direction") == "short"]
        
        # Calculate enhanced quality scores based on multiple factors
        # Calculate quality scores - combine risk/reward, trigger probability, and size
        def calculate_quality(targets, ranges, cascade_prob):
            if not targets or not ranges:
                # Generate a small random value to avoid static 0.01
                return random.uniform(0.01, 0.05)
                
            # Get the best target based on combined metrics
            if targets:
                # Use trigger probability, risk/reward, and size to calculate quality
                best_quality = 0.0
                for target in targets:
                    rr = target.get("risk_reward", 1.0)
                    prob = target.get("trigger_probability", 0.1)
                    size_factor = min(0.8, math.log1p(target.get("size", 0) / 100) / 4)
                    
                    # Calculate quality with higher emphasis on probability and risk/reward
                    quality = min(0.99, (rr / 20) * 0.4 + prob * 0.4 + size_factor * 0.2)
                    best_quality = max(best_quality, quality)
            
            # Get the best range based on risk/reward and cascade probability
            best_range_quality = 0.0
            if ranges:
                for r in ranges:
                    rr = r.get("risk_reward", 1.0)
                    conf = r.get("confidence", 0.1)
                    quality = min(0.99, (rr / 15) * 0.5 + conf * 0.5)
                    best_range_quality = max(best_range_quality, quality)
            
            # Combine target quality, range quality and cascade probability
            combined_quality = max(
                best_quality * 0.6, 
                best_range_quality * 0.7,
                cascade_prob * 0.5  # Cascade probability contributes to quality
            )
            
            # Add market context factors
            market_bias = self.context_data["market_bias"]["bias"]
            market_strength = self.context_data["market_bias"]["bias_strength"]
            
            # Boost quality if market bias aligns with target direction
            if (market_bias == "BULLISH" and "long" in targets[0].get("rationale", "").lower()) or \
               (market_bias == "BEARISH" and "short" in targets[0].get("rationale", "").lower()):
                combined_quality = min(0.99, combined_quality * (1 + market_strength * 0.3))
            
            # Add a small random factor to avoid identical values
            random_factor = random.uniform(0.95, 1.05)
            combined_quality = min(0.99, max(0.01, combined_quality * random_factor))
            
            return combined_quality
        
        # Calculate quality scores
        long_quality = calculate_quality(long_targets, long_ranges, long_cascade_prob)
        short_quality = calculate_quality(short_targets, short_ranges, short_cascade_prob)
        
        # Calculate dynamic range consistency
        # This measures how consistent the ranges are in each direction
        range_consistency = 0.5  # Default neutral value
        if long_ranges and short_ranges:
            # Compare the variance in risk/reward ratios between long and short
            long_rr_values = [r.get("risk_reward", 0) for r in long_ranges]
            short_rr_values = [r.get("risk_reward", 0) for r in short_ranges]
            
            # Calculate coefficient of variation (relative standard deviation)
            def coefficient_of_variation(values):
                if not values or np.mean(values) == 0:
                    return 1.0
                return np.std(values) / np.mean(values)
            
            long_cv = coefficient_of_variation(long_rr_values)
            short_cv = coefficient_of_variation(short_rr_values)
            
            # Direction with less variation is more consistent
            if long_cv < short_cv:
                # Long is more consistent
                range_consistency = max(0.55, min(0.95, 1.0 - (long_cv * 0.5)))
            else:
                # Short is more consistent
                range_consistency = min(0.45, max(0.05, short_cv * 0.5))
        elif long_ranges:
            # Only long ranges exist, consistency depends on their similarity
            values = [r.get("risk_reward", 0) for r in long_ranges]
            if len(values) > 1:
                cv = np.std(values) / max(np.mean(values), 0.1)  # Avoid division by zero
                range_consistency = max(0.6, min(0.95, 1.0 - (cv * 0.5)))
            else:
                range_consistency = 0.7  # Single range, moderately consistent
        elif short_ranges:
            # Only short ranges exist, consistency depends on their similarity
            values = [r.get("risk_reward", 0) for r in short_ranges]
            if len(values) > 1:
                cv = np.std(values) / max(np.mean(values), 0.1)  # Avoid division by zero
                range_consistency = min(0.4, max(0.05, cv * 0.5))
            else:
                range_consistency = 0.3  # Single range, moderately consistent
        else:
            # No ranges, use a slightly randomized neutral value
            range_consistency = random.uniform(0.45, 0.55)
        
        # Calculate directional strength - how strongly the data indicates a directional bias
        # Use multiple factors: quality difference, cascade probability difference, market bias
        quality_diff = abs(long_quality - short_quality)
        cascade_diff = abs(long_cascade_prob - short_cascade_prob)
        
        # Market context contribution
        market_bias_strength = self.context_data["market_bias"]["bias_strength"]
        trend_strength = self.context_data["trend"]["strength"]
        
        # Calculate combined directional strength
        directional_strength = max(
            quality_diff * 1.5,  # Quality difference is a strong indicator
            cascade_diff * 1.2,  # Cascade probability difference
            market_bias_strength * 0.8,  # Market bias contributes
            trend_strength * 0.7   # Trend strength contributes
        )
        
        # Cap and ensure minimum variation
        directional_strength = min(0.99, max(0.01, directional_strength))
        # Add slight randomization
        directional_strength *= random.uniform(0.95, 1.05)
        directional_strength = min(0.99, max(0.01, directional_strength))
        
        # Calculate dynamic imbalance metrics based on multiple factors
        def calculate_imbalance(quality, cascade_prob, ranges):
            # Start with a neutral value
            base_imbalance = 0.5
            
            # Factor 1: Quality score contribution
            quality_factor = quality * 0.6  # 60% weight from quality
            
            # Factor 2: Cascade probability contribution
            cascade_factor = cascade_prob * 0.4  # 40% weight from cascade
            
            # Factor 3: Number and size of ranges/targets
            range_count = len(ranges)
            range_factor = min(0.2, range_count * 0.05)  # Each range adds up to 20% weight
            
            # Calculate weighted imbalance
            imbalance = base_imbalance + (quality_factor + cascade_factor + range_factor) / 3
            
            # Ensure reasonable bounds & add slight randomization
            imbalance = min(0.95, max(0.05, imbalance))
            imbalance *= random.uniform(0.97, 1.03)  # Small random variation
            imbalance = min(0.95, max(0.05, imbalance))
            
            return imbalance
        
        long_imbalance = calculate_imbalance(long_quality, long_cascade_prob, long_ranges)
        short_imbalance = calculate_imbalance(short_quality, short_cascade_prob, short_ranges)
        
        # Generate trade explanation
        explanation = {
            "methodology": "Trades are graded based on three key factors: quality score (combines risk/reward, liquidity, and position diversity), risk/reward ratio (potential profit divided by potential loss), and trigger probability (likelihood of price reaching the entry level).",
            "best_trades": f"Best trades are selected based on the highest combined quality score. Long score: {long_quality:.3f}, Short score: {short_quality:.3f}. Higher scores indicate better trade opportunities.",
            "risk_assessment": f"Overall market risk: {overall_risk.lower()}. Higher risk indicates potential for larger price moves but also increased volatility."
        }
        
        # Generate market/bias explanation based on context
        market_bias = self.context_data["market_bias"]["bias"]
        volatility = self.context_data["volatility"]["level"]
        trend = self.context_data["trend"]["direction"]
        
        market_context_explanation = f"Market context: {trend.lower()} trend with {volatility.lower()} volatility. "
        market_context_explanation += f"Overall bias: {market_bias.lower()}. "
        
        if self.context_data["support_resistance"]["closest_support"]:
            market_context_explanation += f"Closest support at {self.context_data['support_resistance']['closest_support']}, "
            
        if self.context_data["support_resistance"]["closest_resistance"]:
            market_context_explanation += f"closest resistance at {self.context_data['support_resistance']['closest_resistance']}."
        
        if include_explanations:
            explanation["market_context"] = market_context_explanation
        
        # Generate notes for interpretation
        notes = {
            "risk_assessment": f"Risk level: {overall_risk.lower()}. Higher risk indicates potential for larger price moves.",
            "directional_strength": "Values closer to 1.0 indicate stronger directional bias.",
            "imbalance": "Values above 0.6 indicate significant imbalance favoring that direction.",
            "cascade_probability": "Values above 0.3 indicate significant cascade potential."
        }
        
        if include_explanations:
            notes["quality_score"] = "Quality scores range from 0.01 (low quality) to 0.99 (high quality). Scores above 0.5 indicate favorable risk/reward setups."
            notes["market_context"] = "Market bias combines technical indicators, support/resistance, and volatility to determine overall market sentiment."
        
        # Build final summary
        summary = {
            "trade_explanation": explanation,
            "dominant_bias": dominant_direction,
            "dominant_cascade_direction": dominant_direction,
            "risk_assessment": overall_risk.lower(),
            "range_consistency": range_consistency,
            "directional_strength": directional_strength,
            "long_imbalance": long_imbalance,
            "short_imbalance": short_imbalance,
            "long_cascade_probability": long_cascade_prob,
            "short_cascade_probability": short_cascade_prob,
            "overall_cascade_probability": max(long_cascade_prob, short_cascade_prob),
            "long_quality_score": long_quality,
            "short_quality_score": short_quality,
            "notes": notes,
            "primary_recommendation": {
                "direction": dominant_direction,
                "action": "buy" if dominant_direction == "long" else "sell" if dominant_direction == "short" else "wait",
                "entry_price": None,
                "target_price": None,
                "stop_loss": None,
                "confidence": directional_strength,
                "reasoning": f"Long quality: {long_quality:.3f}, Short quality: {short_quality:.3f}. " + 
                              (f"Quality scores indicate {dominant_direction} bias with {directional_strength:.2f} strength." 
                               if directional_strength > 0.3 else "Quality scores below threshold, weak directional bias.")
            }
        }
        
        if include_explanations:
            summary["market_context"] = self.context_data
        
        return summary

# Function to get market context
# Session-level cache that resets between script runs
_CONTEXT_CACHE = {}

def get_market_context(asset, current_price, debug=False):
    """Get market context for an asset with session-level caching"""
    # Generate cache key using asset and current time rounded to nearest hour
    # This ensures cache is fresh for each new script run but reused within the same run
    from datetime import datetime
    current_hour = datetime.now().strftime("%Y-%m-%d-%H")
    cache_key = f"{asset}_{current_hour}"
    
    # Check if we already have this context in cache
    if cache_key in _CONTEXT_CACHE:
        if debug:
            print(f"Using cached market context for {asset}")
        return _CONTEXT_CACHE[cache_key]
    
    # Not in cache, create new context and store it
    if debug:
        print(f"Creating new market context for {asset}")
    context = MarketContext(asset, current_price, debug)
    context.fetch_market_data()
    
    # Store in cache
    _CONTEXT_CACHE[cache_key] = context
    return context
