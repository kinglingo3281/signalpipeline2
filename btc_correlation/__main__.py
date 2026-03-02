#!/usr/bin/env python
"""
BTC Correlation Analysis Main Module
-----------------------------------
Provides a unified interface for the BTC correlation analysis pipeline.
This module coordinates:
1. Price data collection
2. Correlation calculation
3. Beta calculation
4. Cluster translation
5. JSON enhancement
"""

import os
import sys
import json
import pandas as pd
from datetime import datetime

# Ensure package directory is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import correlation components
from btc_correlation.correlation_engine import DynamicCorrelationEngine
from btc_correlation.beta_calculator import CryptoBetaCalculator
from btc_correlation.cluster_translator import BTCClusterTranslator
from btc_correlation.json_enhancer import CorrelationJSONEnhancer

# Import price data collector
from price_data.price_collector import PriceCollector

class BTCCorrelationAnalysis:
    """Main class for BTC correlation analysis"""
    
    def __init__(self, debug=False):
        self.debug = debug
        
        # Initialize components
        self.price_collector = PriceCollector(debug=debug)
        self.correlation_engine = DynamicCorrelationEngine(debug=debug)
        self.beta_calculator = CryptoBetaCalculator(debug=debug)
        self.cluster_translator = BTCClusterTranslator(debug=debug)
        self.json_enhancer = CorrelationJSONEnhancer(debug=debug)
        
        # Create data directories if they don't exist
        os.makedirs("data/btc_correlation", exist_ok=True)
        
    def run_analysis(self, altcoin_symbol, btc_clusters=None, altcoin_json=None):
        """
        Run the complete BTC correlation analysis pipeline
        
        Args:
            altcoin_symbol: Symbol of the altcoin to analyze
            btc_clusters: BTC liquidation clusters (optional, will be loaded from file if not provided)
            altcoin_json: Original altcoin JSON analysis (optional, will be loaded from file if not provided)
            
        Returns:
            Dict with enhanced JSON including BTC correlation data
        """
        if self.debug:
            print(f"\nRunning BTC correlation analysis for {altcoin_symbol}")
        
        # Step 1: Collect price data
        if self.debug:
            print("Step 1: Collecting price data...")
        
        try:
            # Fetch BTC price data
            btc_prices = self.price_collector.fetch_ohlcv_data("BTC", timeframes=["1h", "4h", "1d"])
            
            # Fetch altcoin price data
            altcoin_prices = self.price_collector.fetch_ohlcv_data(altcoin_symbol, timeframes=["1h", "4h", "1d"])
            
            # Get current prices
            btc_current_price = btc_prices.get("1h", pd.DataFrame()).iloc[-1].get("close", 0) if "1h" in btc_prices and not btc_prices["1h"].empty else 0
            altcoin_current_price = altcoin_prices.get("1h", pd.DataFrame()).iloc[-1].get("close", 0) if "1h" in altcoin_prices and not altcoin_prices["1h"].empty else 0
            
            if self.debug:
                print(f"  BTC current price: {btc_current_price}")
                print(f"  {altcoin_symbol} current price: {altcoin_current_price}")
        except Exception as e:
            if self.debug:
                print(f"Error collecting price data: {e}")
            return None
            
        # Step 2: Calculate correlation
        if self.debug:
            print("\nStep 2: Calculating correlation...")
            
        try:
            # Check for cached correlation data first
            correlation_data = self.correlation_engine.load_cached_correlation_data(altcoin_symbol)
            
            if not correlation_data:
                # Calculate correlation across timeframes
                correlation_data = self.correlation_engine.calculate_correlation(
                    btc_prices,
                    altcoin_prices,
                    altcoin_symbol
                )
                
                # Cache the correlation data
                self.correlation_engine.cache_correlation_data(correlation_data, altcoin_symbol)
                
            weighted_correlation = correlation_data.get("weighted_correlation", 0)
            current_regime = correlation_data.get("current_regime", "MEDIUM")
            
            if self.debug:
                print(f"  Weighted correlation: {weighted_correlation:.3f}")
                print(f"  Current volatility regime: {current_regime}")
        except Exception as e:
            if self.debug:
                print(f"Error calculating correlation: {e}")
            return None
            
        # Step 3: Calculate beta coefficients
        if self.debug:
            print("\nStep 3: Calculating beta coefficients...")
            
        try:
            # Check for cached beta data first
            beta_data = self.beta_calculator.load_cached_beta_data(altcoin_symbol)
            
            if not beta_data:
                # Calculate beta coefficients
                beta_data = self.beta_calculator.calculate_beta(
                    btc_prices,
                    altcoin_prices,
                    altcoin_symbol,
                    current_regime
                )
                
                # Cache the beta data
                self.beta_calculator.cache_beta_data(beta_data, altcoin_symbol)
                
            current_beta = beta_data.get("current_beta", 1.0)
            
            if self.debug:
                print(f"  Current beta: {current_beta:.3f}")
                print(f"  Regime-specific betas:")
                for regime, beta in beta_data.get("regimes", {}).items():
                    print(f"    {regime}: {beta:.3f}")
        except Exception as e:
            if self.debug:
                print(f"Error calculating beta coefficients: {e}")
            return None
            
        # Step 4: Load BTC clusters if not provided
        if btc_clusters is None:
            if self.debug:
                print("\nStep 4: Loading BTC clusters...")
                
            try:
                # Look for the most recent BTC enhanced analysis file
                import glob
                btc_files = glob.glob(os.path.join("data", "visualizations", "BTC_enhanced_analysis_*.json"))
                
                if btc_files:
                    # Get the most recent file by creation time
                    btc_file = max(btc_files, key=os.path.getctime)
                    if self.debug:
                        print(f"  Using latest BTC enhanced analysis file: {os.path.basename(btc_file)}")
                else:
                    # If no enhanced files found, try legacy paths
                    btc_file = os.path.join("data", "visualizations", "BTC_liquidation_analysis.json")
                    
                    if not os.path.exists(btc_file):
                        if self.debug:
                            print(f"  BTC clusters file not found at {btc_file}")
                        # Try alternative locations
                        alt_btc_file = os.path.join("data", "BTC_liquidation_analysis.json")
                        if os.path.exists(alt_btc_file):
                            btc_file = alt_btc_file
                        else:
                            if self.debug:
                                print("  No BTC clusters found. Cannot proceed with translation.")
                            return None
                        
                with open(btc_file, 'r') as f:
                    btc_data = json.load(f)
                    
                # Extract clusters from the file
                if "clusters" in btc_data:
                    btc_clusters = btc_data["clusters"]
                elif "liquidation_data" in btc_data:
                    # Different structure - need to construct clusters
                    liq_data = btc_data["liquidation_data"]
                    btc_clusters = {
                        "asset": "BTC",
                        "current_price": liq_data.get("current_price", btc_current_price),
                        "long_clusters": [],
                        "short_clusters": []
                    }
                    
                    # Try to extract clusters from liquidation_data
                    if self.debug:
                        print("  Constructing BTC clusters from liquidation data...")
                        
                    # Extract long liquidation clusters
                    if "long_liquidations" in liq_data:
                        for liq in liq_data["long_liquidations"]:
                            if isinstance(liq, dict) and "price" in liq and "size" in liq:
                                btc_clusters["long_clusters"].append({
                                    "center_price": liq["price"],
                                    "total_size": liq["size"],
                                    "direction": "long"
                                })
                                
                    # Extract short liquidation clusters
                    if "short_liquidations" in liq_data:
                        for liq in liq_data["short_liquidations"]:
                            if isinstance(liq, dict) and "price" in liq and "size" in liq:
                                btc_clusters["short_clusters"].append({
                                    "center_price": liq["price"],
                                    "total_size": liq["size"],
                                    "direction": "short"
                                })
                
                if not btc_clusters:
                    if self.debug:
                        print("  No BTC clusters found in data files.")
                    return None
                    
                if self.debug:
                    print(f"  Loaded BTC clusters:")
                    print(f"    Long clusters: {len(btc_clusters.get('long_clusters', []))}")
                    print(f"    Short clusters: {len(btc_clusters.get('short_clusters', []))}")
            except Exception as e:
                if self.debug:
                    print(f"Error loading BTC clusters: {e}")
                return None
                
        # Step 5: Translate BTC clusters to altcoin price levels
        if self.debug:
            print("\nStep 5: Translating BTC clusters...")
            
        try:
            # Check for cached translated clusters first
            translated_clusters = self.cluster_translator.load_cached_translated_clusters(altcoin_symbol)
            
            if not translated_clusters:
                # Translate BTC clusters to altcoin price levels
                translated_clusters = self.cluster_translator.translate_clusters(
                    btc_clusters,
                    correlation_data,
                    beta_data,
                    btc_current_price,
                    altcoin_current_price,
                    altcoin_symbol
                )
                
                # Cache the translated clusters
                self.cluster_translator.cache_translated_clusters(translated_clusters, altcoin_symbol)
                
            if self.debug:
                print(f"  Translated clusters:")
                print(f"    Long clusters: {len(translated_clusters.get('long_clusters', []))}")
                print(f"    Short clusters: {len(translated_clusters.get('short_clusters', []))}")
                print(f"    Translation quality: {translated_clusters.get('metadata', {}).get('translation_quality', 0):.3f}")
                print(f"    Correlation threshold met: {translated_clusters.get('metadata', {}).get('correlation_threshold_met', False)}")
                
            if not translated_clusters.get("metadata", {}).get("correlation_threshold_met", False):
                if self.debug:
                    print("  Correlation threshold not met. Skipping JSON enhancement.")
                return {
                    "status": "correlation_below_threshold",
                    "correlation": weighted_correlation,
                    "beta": current_beta,
                    "altcoin": altcoin_symbol
                }
        except Exception as e:
            if self.debug:
                print(f"Error translating BTC clusters: {e}")
            return None
            
        # Step 6: Enhance altcoin JSON with BTC correlation data
        if self.debug:
            print("\nStep 6: Enhancing altcoin JSON...")
            
        try:
            # Load altcoin JSON if not provided
            if altcoin_json is None:
                # Try to load altcoin JSON from the standard location
                altcoin_file = os.path.join("data", "visualizations", f"{altcoin_symbol}_liquidation_analysis.json")
                
                if not os.path.exists(altcoin_file):
                    if self.debug:
                        print(f"  Altcoin JSON file not found at {altcoin_file}")
                    # Try alternative locations
                    alt_file = os.path.join("data", f"{altcoin_symbol}_liquidation_analysis.json")
                    if os.path.exists(alt_file):
                        altcoin_file = alt_file
                    else:
                        if self.debug:
                            print("  No altcoin JSON found. Cannot enhance.")
                        return None
                        
                with open(altcoin_file, 'r') as f:
                    altcoin_json = json.load(f)
            
            # Create output path
            output_dir = os.path.join("data", "btc_correlation")
            os.makedirs(output_dir, exist_ok=True)
            
            # Add timestamp to output filename
            current_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(output_dir, f"{altcoin_symbol}_btc_correlation_{current_timestamp}.json")
            
            # Enhance altcoin JSON with BTC correlation data
            enhanced_json = self.json_enhancer.enhance_json(
                altcoin_json,
                correlation_data,
                translated_clusters,
                output_file
            )
            
            if self.debug:
                print(f"  Enhanced JSON saved to {output_file}")
                
            return {
                "status": "success",
                "correlation": weighted_correlation,
                "beta": current_beta,
                "altcoin": altcoin_symbol,
                "enhanced_json": enhanced_json
            }
        except Exception as e:
            if self.debug:
                print(f"Error enhancing altcoin JSON: {e}")
            return None


def main():
    """Run BTC correlation analysis from command line"""
    import argparse
    
    parser = argparse.ArgumentParser(description="BTC Correlation Analysis")
    parser.add_argument("--asset", "-a", type=str, help="Altcoin symbol to analyze")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug output")
    parser.add_argument("--list", "-l", action="store_true", help="List available assets")
    args = parser.parse_args()
    
    # Initialize the analysis
    analysis = BTCCorrelationAnalysis(debug=args.debug)
    
    # List available assets if requested
    if args.list:
        assets = analysis.price_collector.get_available_assets()
        print("Available assets:")
        for i, asset in enumerate(sorted(assets), 1):
            print(f"{i}. {asset}")
        return
    
    # If no asset provided, run for multiple assets
    if not args.asset:
        assets = ["ETH", "SOL", "AVAX", "AAVE", "DOGE"]
        
        if args.debug:
            print(f"No asset specified. Running analysis for {len(assets)} assets.")
            
        results = []
        for asset in assets:
            result = analysis.run_analysis(asset)
            if result:
                print(f"Analysis completed for {asset}. Status: {result.get('status', 'unknown')}")
                results.append(result)
            else:
                print(f"Analysis failed for {asset}.")
                
        print(f"\nCompleted analysis for {len(results)} assets.")
    else:
        # Run analysis for the specified asset
        result = analysis.run_analysis(args.asset)
        
        if result:
            print(f"Analysis completed for {args.asset}. Status: {result.get('status', 'unknown')}")
            print(f"Correlation: {result.get('correlation', 0):.3f}")
            print(f"Beta: {result.get('beta', 0):.3f}")
        else:
            print(f"Analysis failed for {args.asset}.")


if __name__ == "__main__":
    main()
