#!/usr/bin/env python
"""
TAAPI.io fallback provider for technical indicators
Used when HyperLiquid API is rate limited
"""

import requests
import json
import os
from datetime import datetime
import time

class TaapiProvider:
    """Fetches technical indicators from taapi.io API"""
    
    def __init__(self, api_key=None, debug=False):
        """Initialize with your taapi.io API key"""
        self.api_key = api_key
        self.base_url = "https://api.taapi.io"
        self.timeframe = "1h"  # Default timeframe
        self.debug = debug
        self.price_cache = {}  # Cache current prices to reduce API calls
        self.candle_cache = {}  # Cache candle data to reduce API calls
        self.TAAPI_LAST_RATE_LIMIT = 0
        
    def fetch_indicators_bulk(self, symbol):
        """
        Fetch most important indicators in a single bulk request using TAAPI's bulk API
        
        Args:
            symbol: The trading pair symbol (e.g., "BTC/USDT")
            
        Returns:
            Dictionary of indicator values formatted to match MarketContext expectations
        """
        if self.debug:
            print(f"Fetching bulk indicators for {symbol} from TAAPI.io...")
            
        # Ensure symbol is properly formatted
        if "/" not in symbol:
            symbol = f"{symbol}/USDT"
            
        # Extract the base asset for use in error messages
        base_asset = symbol.split('/')[0]
        
        # Initialize the result dictionary with default values
        formatted = self._initialize_formatted_data()
        
        try:
            # Set up the bulk API payload with all indicators in a single request
            payload = {
                "secret": self.api_key,
                "construct": {
                    "exchange": "binance",
                    "symbol": symbol,
                    "interval": self.timeframe,
                    "indicators": [
                        # Trend indicators
                        {"indicator": "rsi"},
                        {"indicator": "macd"},
                        {"indicator": "adx"},
                        
                        # Moving averages
                        {"indicator": "ema", "period": 20, "id": "ema20"},
                        {"indicator": "ema", "period": 50, "id": "ema50"},
                        {"indicator": "ema", "period": 200, "id": "ema200"},
                        
                        # Volatility indicators
                        {"indicator": "bbands"},
                        {"indicator": "atr"},
                        {"indicator": "volatility", "period": 14},
                        
                        # Volume indicators
                        {"indicator": "volume"},
                        
                        # Additional indicators
                        {"indicator": "mfi"},
                        {"indicator": "stoch"}
                    ]
                }
            }
            
            # Set headers
            headers = {"Content-Type": "application/json"}
            
            # Check if we need to wait for rate limit
            current_time = time.time()
            if self.TAAPI_LAST_RATE_LIMIT > 0 and current_time - self.TAAPI_LAST_RATE_LIMIT < 30:
                wait_time = 30 - (current_time - self.TAAPI_LAST_RATE_LIMIT)
                if self.debug:
                    print(f"Waiting {wait_time:.1f} seconds for TAAPI rate limit to reset...")
                time.sleep(wait_time)
                
            # Make the bulk API request
            if self.debug:
                print(f"Making bulk API request to TAAPI.io for {symbol}...")
                
            response = requests.post(
                f"{self.base_url}/bulk",
                json=payload,
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if self.debug:
                    print(f"Successfully received bulk data from TAAPI.io")
                    print(f"DEBUG: TAAPI response data: {json.dumps(data, indent=2)}")
                
                # Check for API errors even with 200 status code
                if "data" in data and len(data["data"]) > 0 and "errors" in data["data"][0]:
                    # Check if this is a rate limit or "No candles" error
                    errors = data["data"][0]["errors"]
                    if any("rate limit" in str(err).lower() for err in errors):
                        self.TAAPI_LAST_RATE_LIMIT = time.time()
                        print(f"TAAPI rate limit hit for {symbol}, pausing for 30 seconds...")
                        time.sleep(30)  # Hard pause for 30 seconds
                        return self._initialize_formatted_data()
                    elif any("no candles were found" in str(err).lower() for err in errors):
                        print(f"TAAPI couldn't find candles for {symbol}, possibly not supported")
                        self.TAAPI_LAST_RATE_LIMIT = time.time()
                        time.sleep(30)  # Hard pause anyway to avoid unnecessary repeated lookups
                        return self._initialize_formatted_data()
                        
                # Process the bulk response
                if "data" in data:
                    # CRITICAL FIX: Revert back to original response format
                    # This was previously working but our array parsing broke it
                    results = {}
                    
                    # Map each indicator to the exact key expected by the existing code
                    for item in data["data"]:
                        # Skip items with errors and no results
                        if "result" not in item or not item.get("result"):
                            continue
                            
                        indicator_id = item["id"]
                        indicator_type = item.get("indicator")
                        
                        # Create debug information
                        if self.debug:
                            print(f"DEBUG: Processing indicator: {indicator_id}, type: {indicator_type}")
                        
                        # Handle special indicators with known IDs (EMAs)
                        if indicator_id in ["ema20", "ema50", "ema200"]:
                            results[indicator_id] = item["result"]
                        # Handle standard indicators where we need their simple name
                        elif indicator_type in ["rsi", "macd", "adx", "bbands", "atr", "volatility", "volume", "mfi", "stoch"]:
                            # Store with simple name as the API endpoint expects
                            results[indicator_type] = item["result"]
                            # Add extra debug for RSI which seems especially problematic
                            if indicator_type == "rsi" and self.debug:
                                print(f"DEBUG: Storing RSI with value: {item['result']}")
                        # Anything else, use the ID as is
                        else:
                            results[indicator_id] = item["result"]
                    
                    if self.debug:
                        print(f"Final processed indicators: {list(results.keys())}")
                            
                    if self.debug:
                        print(f"Processed indicators into results dict: {list(results.keys())}")
                    
                    if self.debug:
                        print(f"Found indicators: {list(results.keys())}")
                        
                        # Print more details about the EMA values if they exist
                        if "ema20" in results:
                            print(f"DEBUG: Found ema20 in response: {results['ema20']}")
                        else:
                            print(f"DEBUG: ema20 NOT found in API response!")
                            
                        if "ema50" in results:
                            print(f"DEBUG: Found ema50 in response: {results['ema50']}")
                        else:
                            print(f"DEBUG: ema50 NOT found in API response!")
                            
                        if "ema200" in results:
                            print(f"DEBUG: Found ema200 in response: {results['ema200']}")
                        else:
                            print(f"DEBUG: ema200 NOT found in API response!")
                    
                    # RSI handling - needs to check multiple potential formats
                    rsi_value = 50  # Default value
                    
                    # Try standard format first
                    if "rsi" in results and "value" in results["rsi"]:
                        rsi_value = results["rsi"]["value"]
                        if self.debug:
                            print(f"DEBUG: Found RSI in standard format: {rsi_value}")
                            
                    # If not found yet, try other patterns that might be in the response
                    if rsi_value == 50 and self.debug:
                        print(f"DEBUG: Using default RSI value: {rsi_value}")
                        
                    formatted["rsi"] = rsi_value
                    if rsi_value > 60:
                        formatted["trend"]["direction"] = "BULLISH"
                    elif rsi_value < 40:
                        formatted["trend"]["direction"] = "BEARISH"
                        
                    if self.debug:
                        print(f"DEBUG: Final RSI value used: {rsi_value}")
                    
                    # MACD
                    if "macd" in results:
                        macd_data = results["macd"]
                        formatted["macd"] = macd_data.get("valueMACD", 0)
                        formatted["macd_signal"] = macd_data.get("valueMACDSignal", 0)
                        formatted["macd_hist"] = macd_data.get("valueMACDHist", 0)
                        
                        if self.debug and all(k in macd_data for k in ["valueMACD", "valueMACDSignal", "valueMACDHist"]):
                            print(f"DEBUG: Using MACD values from API: {macd_data['valueMACD']}, {macd_data['valueMACDSignal']}, {macd_data['valueMACDHist']}")
                        
                        # Use MACD for trend strength
                        macd = formatted["macd"]
                        macd_signal = formatted["macd_signal"]
                        
                        if macd > 0 and macd > macd_signal:
                            formatted["trend"]["direction"] = "BULLISH"
                            formatted["trend"]["strength"] = min(abs(macd) / 10, 1.0)
                        elif macd < 0 and macd < macd_signal:
                            formatted["trend"]["direction"] = "BEARISH"
                            formatted["trend"]["strength"] = min(abs(macd) / 10, 1.0)
                        
                        # Set trend_strength field
                        formatted["trend_strength"] = formatted["trend"]["strength"]
                    
                    # EMAs - use a consistent format for all moving averages
                    # Store with BOTH naming conventions to ensure compatibility
                    if "ema20" in results:
                        ema20_value = results["ema20"].get("value", 0)
                        # Use the nested format required by market_context.py for BOTH key formats
                        formatted["moving_averages"]["ema20"] = {
                            "value": {"value": ema20_value}
                        }
                        formatted["moving_averages"]["ema_20"] = {
                            "value": {"value": ema20_value}
                        }
                        if self.debug:
                            print(f"DEBUG: Using ema20 value from API: {ema20_value}")
                    if "ema50" in results:
                        ema50_value = results["ema50"].get("value", 0)
                        formatted["moving_averages"]["ema50"] = {
                            "value": {"value": ema50_value}
                        }
                        formatted["moving_averages"]["ema_50"] = {
                            "value": {"value": ema50_value}
                        }
                        if self.debug:
                            print(f"DEBUG: Using ema50 value from API: {ema50_value}")
                    if "ema200" in results:
                        ema200_value = results["ema200"].get("value", 0)
                        formatted["moving_averages"]["ema200"] = {
                            "value": {"value": ema200_value}
                        }
                        formatted["moving_averages"]["ema_200"] = {
                            "value": {"value": ema200_value}
                        }
                        if self.debug:
                            print(f"DEBUG: Using ema200 value from API: {ema200_value}")
                    
                    # Set EMA alignment based on EMA values
                    # Safely access EMA values with proper error checking
                    try:
                        # Try to get values from nested structure
                        ema20_val = formatted["moving_averages"]["ema_20"]["value"]["value"]
                        ema50_val = formatted["moving_averages"]["ema_50"]["value"]["value"]
                        ema200_val = formatted["moving_averages"]["ema_200"]["value"]["value"]
                    except (KeyError, TypeError):
                        # Fall back to defaults if access fails
                        ema20_val = 0
                        ema50_val = 0
                        ema200_val = 0
                        
                        # Add debug output
                        if self.debug:
                            print(f"Error accessing EMA values using nested structure, checking keys: {list(formatted['moving_averages'].keys())}")
                    
                    if ema20_val > 0 and ema50_val > 0 and ema200_val > 0:
                        if ema20_val > ema50_val > ema200_val:
                            formatted["trend"]["ema_alignment"] = "BULLISH"
                            formatted["trend"]["in_trend"] = True
                        elif ema20_val < ema50_val < ema200_val:
                            formatted["trend"]["ema_alignment"] = "BEARISH"
                            formatted["trend"]["in_trend"] = True
                    
                    # ADX for trend strength
                    if "adx" in results:
                        adx_value = results["adx"].get("value", 0)
                        formatted["adx"] = adx_value
                        if self.debug:
                            print(f"DEBUG: Using ADX value from API: {adx_value}")
                        
                        if adx_value > 25:
                            formatted["trend"]["in_trend"] = True
                            trend_strength = min(adx_value / 50, 1.0)
                            formatted["trend"]["strength"] = trend_strength
                            formatted["trend_strength"] = trend_strength
                            if self.debug:
                                print(f"DEBUG: Using trend strength from ADX: {trend_strength}")
                    
                    # ATR for volatility
                    if "atr" in results:
                        atr_value = results["atr"].get("value", 0)
                        formatted["volatility"]["atr"]["value"]["value"] = atr_value
                        
                        # Calculate ATR as percentage of price
                        current_price = self.get_current_price(symbol.split('/')[0])
                        if current_price > 0:
                            atr_percent = (atr_value / current_price) * 100
                            formatted["volatility"]["atr_percent"] = atr_percent
                            
                            # Set volatility level based on ATR
                            if atr_percent > 5:
                                formatted["volatility"]["level"] = "HIGH"
                                formatted["volatility"]["percentile"] = 0.8
                            elif atr_percent > 2:
                                formatted["volatility"]["level"] = "MEDIUM"
                                formatted["volatility"]["percentile"] = 0.5
                            else:
                                formatted["volatility"]["level"] = "LOW"
                                formatted["volatility"]["percentile"] = 0.2
                                
                            if self.debug:
                                print(f"DEBUG: Using ATR value: {atr_value} ({atr_percent:.2f}% of price)")
                                print(f"DEBUG: Volatility level set to {formatted['volatility']['level']}")
                    
                    # Bollinger Bands for volatility and support/resistance
                    if "bbands" in results:
                        bbands_data = results["bbands"]
                        upper = bbands_data.get("valueUpperBand", 0)
                        lower = bbands_data.get("valueLowerBand", 0)
                        middle = bbands_data.get("valueMiddleBand", 0)
                        
                        # Set the nested bbands structure
                        formatted["volatility"]["bbands"]["value"]["valueUpperBand"] = upper
                        formatted["volatility"]["bbands"]["value"]["valueLowerBand"] = lower
                        formatted["volatility"]["bbands"]["value"]["valueMiddleBand"] = middle
                        
                        if self.debug:
                            print(f"DEBUG: Using BBands values: Upper={upper}, Middle={middle}, Lower={lower}")
                    
                    # MFI for trend strength
                    if "mfi" in results:
                        mfi_value = results["mfi"].get("value", 0)
                        formatted["mfi"] = mfi_value
                        if self.debug:
                            print(f"DEBUG: Using MFI value from API: {mfi_value}")
                        
                        if mfi_value > 80:
                            formatted["trend"]["direction"] = "BEARISH"
                            trend_strength = min((mfi_value - 80) / 20, 1.0)
                            formatted["trend"]["strength"] = trend_strength
                            formatted["trend_strength"] = trend_strength
                            if self.debug:
                                print(f"DEBUG: Using trend strength from MFI: {trend_strength}")
                        elif mfi_value < 20:
                            formatted["trend"]["direction"] = "BULLISH"
                            trend_strength = min((20 - mfi_value) / 20, 1.0)
                            formatted["trend"]["strength"] = trend_strength
                            formatted["trend_strength"] = trend_strength
                            if self.debug:
                                print(f"DEBUG: Using trend strength from MFI: {trend_strength}")
                    
                    # Stochastic Oscillator for trend strength
                    if "stoch" in results:
                        stoch_data = results["stoch"]
                        stoch_k = stoch_data.get("valueK", 0)
                        stoch_d = stoch_data.get("valueD", 0)
                        formatted["stoch_k"] = stoch_k
                        formatted["stoch_d"] = stoch_d
                        if self.debug:
                            print(f"DEBUG: Using Stochastic Oscillator values from API: K={stoch_k}, D={stoch_d}")
                        
                        if stoch_k > 80 and stoch_d > 80:
                            formatted["trend"]["direction"] = "BEARISH"
                            trend_strength = min((stoch_k - 80) / 20, 1.0)
                            formatted["trend"]["strength"] = trend_strength
                            formatted["trend_strength"] = trend_strength
                            if self.debug:
                                print(f"DEBUG: Using trend strength from Stochastic Oscillator: {trend_strength}")
                        elif stoch_k < 20 and stoch_d < 20:
                            formatted["trend"]["direction"] = "BULLISH"
                            trend_strength = min((20 - stoch_k) / 20, 1.0)
                            formatted["trend"]["strength"] = trend_strength
                            formatted["trend_strength"] = trend_strength
                            if self.debug:
                                print(f"DEBUG: Using trend strength from Stochastic Oscillator: {trend_strength}")
                    
                if self.debug:
                    print(f"Successfully processed bulk data for {symbol}")
                    print(f"Trend: {formatted['trend']['direction']}, RSI: {formatted['rsi']}")
                
                return formatted
            else:
                if self.debug:
                    print(f"Error from TAAPI.io bulk API: {response.status_code} - {response.text}")
                
                # Always signal error to calling code to trigger Hyperliquid fallback
                error_msg = f"TAAPI.io API error: {response.status_code} - {response.text}"
                if response.status_code == 429 or "rate-limit" in response.text.lower():
                    error_msg = f"TAAPI.io rate limited: {response.status_code} - {response.text}"
                    self.TAAPI_LAST_RATE_LIMIT = time.time()
                    print(f"TAAPI rate limit hit for {base_asset}, pausing for 30 seconds...")
                    time.sleep(30)  # Hard pause for 30 seconds
                # Raise exception to trigger the Hyperliquid fallback in market_context.py
                raise Exception(error_msg)
                
        except Exception as e:
            if self.debug:
                print(f"Error fetching indicators for {symbol}: {e}")
            return formatted

    def _initialize_formatted_data(self):
        """Initialize the data structure with default values"""
        return {
            "volatility": {
                "level": "MEDIUM",
                "percentile": 0.5,
                "atr_percent": 0.0,
                "recent_range_percent": 0.0,
                # Add bbands in the expected nested structure
                "bbands": {
                    "value": {
                        "valueUpperBand": 0.0,
                        "valueLowerBand": 0.0,
                        "valueMiddleBand": 0.0
                    }
                },
                "atr": {
                    "value": {
                        "value": 0.0
                    }
                },
                "stddev": {
                    "value": {
                        "value": 0.0
                    }
                }
            },
            "trend": {
                "direction": "NEUTRAL",
                "strength": 0.5,
                "in_trend": False,
                "ema_alignment": "NEUTRAL"
            },
            "rsi": 50.0,
            "trend_strength": 0.5,
            "macd": 0.0,
            "macd_signal": 0.0,
            "macd_hist": 0.0,
            "adx": 0.0,
            "moving_averages": {
                # Use proper nested structure for EMAs that market_context.py expects
                "ema_20": {
                    "value": {
                        "value": 0.0
                    }
                },
                "ema_50": {
                    "value": {
                        "value": 0.0
                    }
                },
                "ema_200": {
                    "value": {
                        "value": 0.0
                    }
                },
                # Also include the alternate naming convention
                "ema20": {
                    "value": {
                        "value": 0.0
                    }
                },
                "ema50": {
                    "value": {
                        "value": 0.0
                    }
                },
                "ema200": {
                    "value": {
                        "value": 0.0
                    }
                }
            },
            "support_resistance": {
                "support_levels": [],
                "resistance_levels": []
            }
        }
        
    # No longer using individual API calls fallback
    # When bulk fails, it immediately goes to Hyperliquid in market_context.py
    
    def _fetch_single_indicator(self, indicator, symbol, params=None):
        """Fetch a single indicator from TAAPI.io"""
        try:
            # Build the base parameters
            request_params = {
                "secret": self.api_key,
                "exchange": "binance",
                "symbol": symbol,
                "interval": self.timeframe
            }
            
            # Add any additional parameters
            if params:
                request_params.update(params)
                
            # Make the request
            if self.debug:
                print(f"Fetching {indicator} for {symbol}...")
                
            response = requests.get(
                f"{self.base_url}/{indicator}",
                params=request_params
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if self.debug:
                    print(f"  {indicator} = {result}")
                    
                # Handle different response formats
                if isinstance(result, dict) and "value" in result:
                    # Most indicators return a value field
                    return result["value"]
                else:
                    # Some indicators (like MACD) return a complex object
                    return result
                    
            else:
                if self.debug:
                    print(f"  Error fetching {indicator}: {response.status_code} - {response.text}")
                    
                # Propagate rate limit errors
                if response.status_code == 429 or ("rate-limit" in response.text.lower()):
                    raise Exception(f"TAAPI.io rate limited: {response.status_code} - {response.text}")
                    
                return None
                
        except Exception as e:
            if self.debug:
                print(f"  Exception fetching {indicator}: {e}")
            return None
        
    def get_current_price(self, symbol):
        """Get the current price of a cryptocurrency"""
        # Format the symbol for TAAPI
        if "/" not in symbol:
            symbol = f"{symbol}/USDT"
            
        # Check cache first
        if symbol in self.price_cache:
            if self.debug:
                print(f"Using cached price for {symbol}: {self.price_cache[symbol]}")
            return self.price_cache[symbol]
        
        # Fetch price using TAAPI.io price endpoint
        try:
            if self.debug:
                print(f"Fetching current price for {symbol} from TAAPI.io...")
                
            # Make API request
            response = requests.get(
                f"{self.base_url}/price",
                params={
                    "secret": self.api_key,
                    "exchange": "binance",
                    "symbol": symbol,
                    "interval": self.timeframe
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                price = float(result.get("value", 0))
                
                # Cache the price
                self.price_cache[symbol] = price
                
                if self.debug:
                    print(f"Fetched price for {symbol}: {price}")
                    
                return price
            else:
                if self.debug:
                    print(f"Error fetching price: {response.status_code} - {response.text}")
                if response.status_code == 429 or "rate-limit" in response.text.lower():
                    self.TAAPI_LAST_RATE_LIMIT = time.time()
                    print(f"TAAPI rate limit hit for {symbol}, pausing for 30 seconds...")
                    time.sleep(30)  # Hard pause for 30 seconds
                return 0
        except Exception as e:
            if self.debug:
                print(f"Error fetching price: {e}")
            return 0
            
    def fetch_candles(self, symbol, interval="1h", days=14):
        """Fetch candle data from TAAPI.io to match the Hyperliquid format"""
        try:
            # Extract asset name from symbol (e.g., "BTC/USDT" -> "BTC")
            asset = symbol.split('/')[0] if '/' in symbol else symbol
            formatted_symbol = f"{asset}/USDT"
            
            # Create a cache key
            cache_key = f"{formatted_symbol}_{interval}_{days}"
            
            # Check cache first
            if cache_key in self.candle_cache:
                if self.debug:
                    print(f"Using cached candles for {formatted_symbol}")
                return self.candle_cache[cache_key]
            
            if self.debug:
                print(f"Fetching {interval} candles for {formatted_symbol} from TAAPI.io...")
            
            # Convert days to number of candles 
            # For 1h interval, 24 candles = 1 day
            backtrack = 24 * days if interval == "1h" else 24 * days // int(interval[:-1])
            
            # Make API request
            response = requests.get(
                f"{self.base_url}/candles",
                params={
                    "secret": self.api_key,
                    "exchange": "binance",
                    "symbol": formatted_symbol,
                    "interval": interval,
                    "limit": backtrack,  # Number of candles to retrieve
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                
                if self.debug:
                    print(f"Received {len(result)} candles from TAAPI.io")
                
                # Convert TAAPI.io format to match Hyperliquid format
                formatted_candles = []
                for candle in result:
                    formatted_candle = {
                        't': candle.get('timestampHuman', ''),  # Use timestamp from TAAPI
                        'o': str(candle.get('open', 0)),       # Open price
                        'h': str(candle.get('high', 0)),       # High price
                        'l': str(candle.get('low', 0)),        # Low price
                        'c': str(candle.get('close', 0)),      # Close price
                        'v': str(candle.get('volume', 0))      # Volume
                    }
                    formatted_candles.append(formatted_candle)
                
                # Sort candles by timestamp (newest last)
                formatted_candles.sort(key=lambda x: x['t'])
                
                # Cache the result
                self.candle_cache[cache_key] = formatted_candles
                
                return formatted_candles
            else:
                if self.debug:
                    print(f"Error fetching candles: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            if self.debug:
                print(f"Error fetching candle data: {e}")
            return []

# Testing function
def test_taapi_provider():
    provider = TaapiProvider(debug=True)
    
    # Test current price
    price = provider.get_current_price("BTC")
    print(f"BTC current price: {price}")
    
    # Test individual indicator fetch
    rsi = provider._fetch_single_indicator("rsi", "BTC/USDT")
    print(f"BTC RSI: {rsi}")
    
    # Test with different assets
    assets = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    
    print("\nTesting bulk indicators for multiple assets:")
    results = {}
    
    for asset in assets:
        print(f"\nTesting {asset}...")
        data = provider.fetch_indicators_bulk(asset)
        results[asset] = data
        
        if data:
            print(f"✓ Successfully retrieved data for {asset}")
            print(f"  Found categories: {list(data.keys())}")
            print(f"  RSI: {data.get('rsi')}")
            print(f"  Trend direction: {data.get('trend', {}).get('direction')}")
            print(f"  Volatility level: {data.get('volatility', {}).get('level')}")
        else:
            print(f"✗ Failed to retrieve data for {asset}")
    
    # Compare RSI values
    rsi_values = {asset: data.get('rsi', 0) for asset, data in results.items()}
    print(f"\nRSI comparison: {rsi_values}")
    
    # Check if values differ (asset-specific)
    unique_rsi_count = len(set(rsi_values.values()))
    if unique_rsi_count > 1:
        print(f"✓ Found {unique_rsi_count} different RSI values - DATA IS ASSET-SPECIFIC")
    else:
        print(f"✗ All assets have the same RSI value - DATA MAY NOT BE ASSET-SPECIFIC")
    
    print("\nTest complete")

if __name__ == "__main__":
    test_taapi_provider()
