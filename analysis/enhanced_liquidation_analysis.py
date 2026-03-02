#!/usr/bin/env python
"""
Enhanced Liquidation Analysis
----------------------------
Analyzes liquidation data to identify clusters, cascade probabilities, and optimal price targets.
This is a complete rewrite designed to properly handle the data structure from fetch_top_traders.py.
"""

import os
import sys
import json
import math
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from collections import defaultdict
import argparse
import traceback

# Add parent directory to path to allow imports from root after moving to analysis/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Define project root for consistent file paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

# Import our analysis modules with directory structure handling
try:
    # Try imports after directory restructuring - use correct paths
    from analysis.liquidation_clusters import identify_liquidation_clusters, find_clusters, finalize_cluster
    from analysis.cascade_analysis import calculate_cascade_probability, simulate_cascade_paths
    from utils.price_targeting import generate_price_targets, generate_ta_price_targets  # Fixed: moved to utils/
    from analysis.risk_analyzer import RiskAnalyzer
except ImportError as e1:
    print(f"Error with new directory imports: {e1}")
    try:
        # Fallback to original imports during transition
        from liquidation_clusters import identify_liquidation_clusters, find_clusters, finalize_cluster
        from cascade_analysis import calculate_cascade_probability, simulate_cascade_paths
        from price_targeting import generate_price_targets, generate_ta_price_targets
        from risk_analyzer import RiskAnalyzer
        print("Successfully imported from original locations")
    except ImportError as e2:
        print(f"Error with original imports: {e2}")
        # Define stub functions if all imports fail
        def generate_price_targets(*args, **kwargs):
            return {"error": "price_targeting module not available"}
        def generate_ta_price_targets(*args, **kwargs):
            return {"error": "price_targeting module not available"}

# Import market context if available
try:
    # Try correct path - market_context is in utils/
    from utils.market_context import get_market_context, MarketContext
    MARKET_CONTEXT_AVAILABLE = True
except ImportError:
    try:
        # Fallback to original import during transition
        from market_context import get_market_context, MarketContext
        MARKET_CONTEXT_AVAILABLE = True
    except ImportError:
        print("Warning: market_context module not found. Enhanced analysis will use basic context.")
        MARKET_CONTEXT_AVAILABLE = False

# Import config modules that were moved to config/ directory
try:
    from config.support_resistance_config import SupportResistanceConfig
    SUPPORT_RESISTANCE_AVAILABLE = True
except ImportError:
    try:
        from support_resistance_config import SupportResistanceConfig
        SUPPORT_RESISTANCE_AVAILABLE = True
    except ImportError:
        print("Warning: support_resistance_config module not found.")
        SUPPORT_RESISTANCE_AVAILABLE = False

try:
    from config.market_bias_config import MarketBiasConfig
    MARKET_BIAS_CONFIG_AVAILABLE = True
except ImportError:
    try:
        from market_bias_config import MarketBiasConfig
        MARKET_BIAS_CONFIG_AVAILABLE = True
    except ImportError:
        print("Warning: market_bias_config module not found.")
        MARKET_BIAS_CONFIG_AVAILABLE = False

# Import utils modules that were moved to utils/ directory
try:
    from utils.fibonacci_levels import calculate_fibonacci_levels
    FIBONACCI_LEVELS_AVAILABLE = True
except ImportError:
    try:
        from fibonacci_levels import calculate_fibonacci_levels
        FIBONACCI_LEVELS_AVAILABLE = True
    except ImportError:
        print("Warning: fibonacci_levels module not found.")
        FIBONACCI_LEVELS_AVAILABLE = False

# Helper functions for consistent directory handling
def get_visualizations_directory():
    """Get visualizations directory with fallback locations for before/after move"""
    possible_dirs = [
        os.path.join(PROJECT_ROOT, "data", "visualizations"),  # After move, project-root relative
        os.path.join(os.path.dirname(PROJECT_ROOT), "data", "visualizations"),  # In case project root is shifted
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "visualizations"),  # Relative to script
        "data/visualizations"  # Simple relative path as last resort
    ]
    
    for dir_path in possible_dirs:
        if os.path.exists(dir_path):
            return dir_path
    
    # Default to project root visualizations directory if none exist
    default_dir = os.path.join(PROJECT_ROOT, "data", "visualizations")
    os.makedirs(default_dir, exist_ok=True)
    return default_dir

class EnhancedLiquidationAnalysis:
    """Main class for enhanced liquidation analysis"""
    
    def __init__(self, input_file=None, asset=None, debug=False, skip_btc_correlation=False):
        """Initialize the analysis with either a file or asset name"""
        self.debug = debug
        self.data = None
        self.asset = asset
        self.current_price = 0
        self.clusters = {}
        self.cascade_probabilities = {}
        self.price_targets = {}
        self.skip_btc_correlation = skip_btc_correlation
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if input_file:
            self.load_data_from_file(input_file)
        elif asset:
            self.load_data_for_asset(asset)
            
        if self.debug:
            print(f"Initialized analysis for {self.asset} with current price {self.current_price}")
        
    def load_data_from_file(self, filename):
        """Load liquidation data from a JSON file"""
        try:
            if not os.path.exists(filename):
                print(f"Error: File {filename} not found")
                return False
                
            with open(filename, 'r') as f:
                self.data = json.load(f)
                
            # Extract key information
            self.asset = self.data.get("asset", "UNKNOWN")
            self.current_price = self.data.get("current_price", 0)
            
            if self.debug:
                print(f"Loaded data for {self.asset} with current price {self.current_price}")
                print(f"Data keys: {list(self.data.keys())}")
                
            return True
        except Exception as e:
            print(f"Error loading data from file: {e}")
            return False
            
    def load_data_for_asset(self, asset):
        """Load liquidation data for a specific asset"""
        vis_dir = get_visualizations_directory()
        filename = os.path.join(vis_dir, f"{asset}_liquidation_analysis.json")
        return self.load_data_from_file(filename)
        
    def extract_liquidation_positions(self):
        """Extract actual position data from the liquidation data"""
        positions = {
            "long": [],
            "short": []
        }
        
        if not self.data:
            print("No data available")
            return positions
        
        print(f"DEBUG: Data keys: {list(self.data.keys())}")
        
        # Method 1: Extract from traditional liquidation_data structure (BTC/ETH format)
        if "liquidation_data" in self.data:
            liq_data = self.data["liquidation_data"]
            print(f"DEBUG: Liquidation data keys: {list(liq_data.keys())}")
            
            # Process long liquidations
            if "long_liquidations" in liq_data:
                long_liq = liq_data["long_liquidations"]
                print(f"DEBUG: Found long_liquidations with {len(long_liq)} entries")
                for price_key, data in long_liq.items():
                    try:
                        if "positions" in data and isinstance(data["positions"], list):
                            for pos in data["positions"]:
                                positions["long"].append({
                                    "price": float(pos.get("liquidation_price", price_key)),
                                    "size": float(pos.get("size", 0)),
                                    "trader": pos.get("trader", "unknown"),
                                    "entry_price": float(pos.get("entry_price", 0))
                                })
                    except Exception as e:
                        print(f"Error processing long position: {e}")
            else:
                print("DEBUG: No long_liquidations found in liquidation_data")
            
            # Process short liquidations
            if "short_liquidations" in liq_data:
                short_liq = liq_data["short_liquidations"]
                print(f"DEBUG: Found short_liquidations with {len(short_liq)} entries")
                for price_key, data in short_liq.items():
                    try:
                        if "positions" in data and isinstance(data["positions"], list):
                            for pos in data["positions"]:
                                positions["short"].append({
                                    "price": float(pos.get("liquidation_price", price_key)),
                                    "size": float(pos.get("size", 0)),
                                    "trader": pos.get("trader", "unknown"),
                                    "entry_price": float(pos.get("entry_price", 0))
                                })
                    except Exception as e:
                        print(f"Error processing short position: {e}")
            else:
                print("DEBUG: No short_liquidations found in liquidation_data")
        
        # Method 2: Extract from cascade_results structure (AAVE and other assets format)
        if "cascade_results" in self.data:
            print("DEBUG: Found cascade_results")
            cascade_data = self.data["cascade_results"]
            print(f"DEBUG: Cascade data keys: {list(cascade_data.keys())}")
            
            # Process downward cascade (typically contains long liquidations)
            if "downward_cascade" in cascade_data:
                downward = cascade_data["downward_cascade"]
                if downward is None:
                    print(f"DEBUG: downward_cascade is None")
                else:
                    print(f"DEBUG: Found downward_cascade keys: {list(downward.keys())}")
                    if "cascade_steps" in downward and isinstance(downward["cascade_steps"], list):
                        print(f"DEBUG: Found cascade_steps with {len(downward['cascade_steps'])} steps")
                        for step in downward["cascade_steps"]:
                            if "filled_levels" in step and isinstance(step["filled_levels"], list):
                                print(f"DEBUG: Found filled_levels with {len(step['filled_levels'])} entries")
                                for level in step["filled_levels"]:
                                    try:
                                        positions["long"].append({
                                            "price": float(level.get("price", 0)),
                                            "size": float(level.get("size", 0)),
                                            "usd_size": float(level.get("size", 0)) * float(level.get("price", 0)),
                                            "step": step.get("step", 0),
                                            "trigger_probability": step.get("trigger_probability", 0.1),
                                            "source": "cascade"
                                        })
                                    except Exception as e:
                                        print(f"Error processing long position: {e}")
                            else:
                                print("DEBUG: No filled_levels found in cascade step or not a list")
                    else:
                        print("DEBUG: No cascade_steps found in downward_cascade or not a list")
            else:
                print("DEBUG: No downward_cascade found in cascade_results")
            
            # Process upward cascade (typically contains short liquidations)
            if "upward_cascade" in cascade_data:
                upward = cascade_data["upward_cascade"]
                if upward is None:
                    print(f"DEBUG: upward_cascade is None")
                else:
                    print(f"DEBUG: Found upward_cascade keys: {list(upward.keys())}")
                    if "cascade_steps" in upward and isinstance(upward["cascade_steps"], list):
                        print(f"DEBUG: Found cascade_steps with {len(upward['cascade_steps'])} steps")
                        for step in upward["cascade_steps"]:
                            if "filled_levels" in step and isinstance(step["filled_levels"], list):
                                print(f"DEBUG: Found filled_levels with {len(step['filled_levels'])} entries")
                                for level in step["filled_levels"]:
                                    try:
                                        positions["short"].append({
                                            "price": float(level.get("price", 0)),
                                            "size": float(level.get("size", 0)),
                                            "usd_size": float(level.get("size", 0)) * float(level.get("price", 0)),
                                            "step": step.get("step", 0),
                                            "trigger_probability": step.get("trigger_probability", 0.1),
                                            "source": "cascade"
                                        })
                                    except Exception as e:
                                        print(f"Error processing short position: {e}")
                            else:
                                print("DEBUG: No filled_levels found in cascade step or not a list")
                    else:
                        print("DEBUG: No cascade_steps found in upward_cascade or not a list")  
            else:
                print("DEBUG: No upward_cascade found in cascade_results")
        else:
            print("DEBUG: No cascade_results found in data")
        
        print(f"DEBUG: Extracted {len(positions['long'])} long positions and {len(positions['short'])} short positions")
            
        return positions
        
    def run_analysis(self):
        """Run the complete enhanced analysis pipeline"""
        if not self.data:
            print("No data loaded, cannot run analysis")
            return False
            
        print(f"\n{'-'*80}")
        positions = self.extract_liquidation_positions()
        if not positions["long"] and not positions["short"]:
            print(f"No liquidation positions found for {self.asset}")
            return False
            
        # Identify liquidation clusters
        if self.debug:
            print(f"Identifying liquidation clusters for {self.asset}...")
        
        # Get orderbook data if available for liquidity-based filtering
        orderbook_data = None
        if "orderbook_analysis" in self.data:
            orderbook_data = self.data["orderbook_analysis"]
            if self.debug:
                print(f"Using orderbook data for liquidity-based cluster filtering")
        
        # Pass orderbook data to leverage liquidity-based filtering for single position clusters
        self.clusters = identify_liquidation_clusters(positions, self.current_price, self.asset, self.debug, orderbook_data)
        
        # Calculate cascade probabilities
        if self.debug:
            print(f"Calculating cascade probabilities for {self.asset}...")
        self.cascade_probabilities = calculate_cascade_probability(self.clusters, self.current_price, self.asset, self.debug)
        
        # Enhance clusters with orderbook risk analysis if orderbook data is available
        if "orderbook_analysis" in self.data:
            if self.debug:
                print(f"Enhancing clusters with orderbook risk analysis...")
            risk_analyzer = RiskAnalyzer(self.debug)
            self.enhanced_clusters = risk_analyzer.calculate_composite_risk_scores(
                self.clusters,
                self.data["orderbook_analysis"],
                self.current_price,
                self.asset
            )
            
            # Use enhanced clusters for further analysis if available
            if self.enhanced_clusters:
                self.clusters = self.enhanced_clusters
        
        # Generate price targets
        if self.debug:
            print(f"Generating price targets for {self.asset}...")
        self.price_targets = generate_price_targets(self.clusters, self.cascade_probabilities, self.current_price, self.asset, self.debug)
        
        # Generate TA-based price targets (alternative take-profit approach)
        if self.debug:
            print(f"Generating TA-based price targets for {self.asset}...")
        self.ta_price_targets = generate_ta_price_targets(self.clusters, self.cascade_probabilities, self.current_price, self.asset, self.debug)
        
        # Enhance price targets with risk analysis if orderbook data is available
        if "orderbook_analysis" in self.data and hasattr(self, 'enhanced_clusters'):
            if self.debug:
                print(f"Enhancing price targets with risk analysis...")
            risk_analyzer = RiskAnalyzer(self.debug)
            self.price_targets = risk_analyzer.generate_risk_enhanced_trade_recommendations(
                self.price_targets,
                self.enhanced_clusters,
                self.data["orderbook_analysis"]
            )
            
        # Determine overall cascade risk by comparing long and short cascade probabilities
        long_risk = self.cascade_probabilities["long_cascade"]["probability"]
        long_risk_level = self.cascade_probabilities["long_cascade"]["risk_level"]
        short_risk = self.cascade_probabilities["short_cascade"]["probability"]
        short_risk_level = self.cascade_probabilities["short_cascade"]["risk_level"]
        
        # Add overall risk assessment to the cascade probabilities data
        self.cascade_probabilities["dominant_direction"] = "long" if long_risk > short_risk else "short"
        dominant_direction = self.cascade_probabilities["dominant_direction"]
        self.cascade_probabilities["risk_level"] = long_risk_level if dominant_direction == "long" else short_risk_level
        overall_risk = self.cascade_probabilities["risk_level"]
        
        if dominant_direction == "long":  # Long liquidations (price decreasing)
            direction_text = "downside"
        else:  # Short liquidations (price increasing)
            direction_text = "upside"
        
        # Print cascade risk assessment
        print(f"Cascade Risk Assessment: {overall_risk}")
        print(f"Long Cascade Risk: {long_risk} ({self.cascade_probabilities['long_cascade']['probability']:.2f})")
        print(f"Short Cascade Risk: {short_risk} ({self.cascade_probabilities['short_cascade']['probability']:.2f})")
        
        # Generate price targets based on clusters and cascade probabilities
        print("\nStep 4: Generating price targets...")
        
        # Get market context if available
        if MARKET_CONTEXT_AVAILABLE:
            try:
                print("  Getting market context for enhanced targeting...")
                # This will automatically integrate with the price_targeting module
                self.price_targets = generate_price_targets(
                    self.clusters, 
                    self.cascade_probabilities, 
                    self.current_price, 
                    self.asset,
                    self.debug
                )
            except Exception as e:
                if self.debug:
                    print(f"Error getting market context: {e}")
                # Fallback to basic targeting
                self.price_targets = generate_price_targets(
                    self.clusters, 
                    self.cascade_probabilities, 
                    self.current_price, 
                    self.asset,
                    self.debug
                )
        else:
            # Use basic targeting without market context
            self.price_targets = generate_price_targets(
                self.clusters, 
                self.cascade_probabilities, 
                self.current_price, 
                self.asset,
                self.debug
            )
        
        # Print top recommendation if available
        # Print trading recommendations with enhanced details
        ranges = self.price_targets.get("ranges", [])
        long_targets = self.price_targets.get("long_targets", [])
        short_targets = self.price_targets.get("short_targets", [])
        enhanced_summary = self.price_targets.get("enhanced_summary", {})
        
        # Always provide at least a basic recommendation for both directions
        if not ranges and not long_targets and not short_targets:
            print("\nNo specific price targets generated.")
            print("Market conditions are balanced with no significant liquidation pressure detected.")
            print("Consider ranging strategies.")
        else:
            # Print the overall best recommendation first
            print("\n============ TOP TRADING RECOMMENDATION ============")
            if ranges:
                # Find the best range using a combined quality score
                def range_quality(r):
                    return r.get("risk_reward", 0) * r.get("cascade_probability", 0.1) * \
                           r.get("confidence", 0.1)
                
                top_range = max(ranges, key=range_quality)
                rec = self.price_targets.get("recommendation", {}).get("summary", "No specific recommendation")
                
                print(rec)
                print(f"Direction: {top_range.get('direction', 'NEUTRAL').upper()}")
                print(f"Entry: {top_range.get('entry', top_range.get('entry_price', 0)):.2f}")
                print(f"Stop Loss: {top_range.get('stop_loss', 0):.2f}")
                print(f"Take Profit: {top_range.get('take_profit', 0):.2f}")
                print(f"Risk-Reward Ratio: {top_range.get('risk_reward', 0):.2f}")
                print(f"Confidence: {top_range.get('confidence', 0):.2f}")
                
                # Show rationale for the top recommendation
                if 'rationale' in top_range:
                    print(f"\nRationale: {top_range['rationale']}")
            else:
                print("Market conditions are balanced with no significant liquidation pressure detected.")
                print("Consider ranging strategies.")
            
            # Always show both long and short recommendations
            print("\n============ LONG TRADING OPPORTUNITIES ============")
            if long_targets:
                # Find the best long target using a combined quality score
                def quality_score(target):
                    return (target.get("risk_reward", 0) * 0.4 + 
                            target.get("trigger_probability", 0.1) * 0.4 + 
                            target.get("confidence", 0.1) * 0.2)
                            
                best_long = max(long_targets, key=quality_score)
                
                # Display basic trade details
                print(f"Entry:            ${best_long.get('entry_price', 0):.2f}")
                print(f"Stop Loss:        ${best_long.get('stop_loss', 0):.2f}")
                print(f"Take Profit:      ${best_long.get('take_profit', 0):.2f}")
                print(f"Risk-Reward:       {best_long.get('risk_reward', 0):.2f}")
                print(f"Probability:       {best_long.get('trigger_probability', 0):.2f}")
                print(f"Confidence Score:  {best_long.get('confidence', 0):.2f}")
                
                # Display detailed analysis and reasoning
                if 'rationale' in best_long:
                    print("\n🔍 DETAILED ANALYSIS 🔍")
                    # Format the rationale with better separation
                    rationale = best_long['rationale']
                    
                    # Try to break the rationale into logical segments
                    if ". " in rationale:
                        segments = rationale.split(". ")
                        # Group related segments together
                        formatted_rationale = ""
                        current_paragraph = ""
                        for i, segment in enumerate(segments):
                            if not segment.strip():
                                continue
                                
                            current_paragraph += segment + ". "
                            
                            # Break into new paragraph at logical points
                            if (segment.endswith(".") or 
                                any(kw in segment for kw in ["ratio", "probability", "confidence"]) or
                                i == len(segments) - 1):
                                formatted_rationale += current_paragraph.strip() + "\n\n"
                                current_paragraph = ""
                                
                        print(formatted_rationale.strip())
                    else:
                        print(rationale)
            else:
                print("No significant long opportunities detected at current price levels.")
                print("Consider waiting for clearer setups or use very tight risk management.")
            
            print("\n============ SHORT TRADING OPPORTUNITIES ============")
            if short_targets:
                # Find the best short target using same quality score
                best_short = max(short_targets, key=quality_score)
                
                # Display basic trade details
                print(f"Entry:            ${best_short.get('entry_price', 0):.2f}")
                print(f"Stop Loss:        ${best_short.get('stop_loss', 0):.2f}")
                print(f"Take Profit:      ${best_short.get('take_profit', 0):.2f}")
                print(f"Risk-Reward:       {best_short.get('risk_reward', 0):.2f}")
                print(f"Probability:       {best_short.get('trigger_probability', 0):.2f}")
                print(f"Confidence Score:  {best_short.get('confidence', 0):.2f}")
                
                # Display detailed analysis and reasoning
                if 'rationale' in best_short:
                    print("\n🔍 DETAILED ANALYSIS 🔍")
                    # Format the rationale with better separation
                    rationale = best_short['rationale']
                    
                    # Try to break the rationale into logical segments
                    if ". " in rationale:
                        segments = rationale.split(". ")
                        # Group related segments together
                        formatted_rationale = ""
                        current_paragraph = ""
                        for i, segment in enumerate(segments):
                            if not segment.strip():
                                continue
                                
                            current_paragraph += segment + ". "
                            
                            # Break into new paragraph at logical points
                            if (segment.endswith(".") or 
                                any(kw in segment for kw in ["ratio", "probability", "confidence"]) or
                                i == len(segments) - 1):
                                formatted_rationale += current_paragraph.strip() + "\n\n"
                                current_paragraph = ""
                                
                        print(formatted_rationale.strip())
                    else:
                        print(rationale)
            else:
                print("No significant short opportunities detected at current price levels.")
                print("Consider waiting for clearer setups or use very tight risk management.")
            
            # Print enhanced metrics if available
            if enhanced_summary:
                print("\n============ MARKET ANALYSIS METRICS ============")
                print(f"Dominant Bias: {enhanced_summary.get('dominant_bias', 'neutral').upper()}")
                print(f"Directional Strength: {enhanced_summary.get('directional_strength', 0):.2f}")
                print(f"Risk Assessment: {enhanced_summary.get('risk_assessment', 'unknown').upper()}")
                print(f"Long Cascade Probability: {enhanced_summary.get('long_cascade_probability', 0):.3f}")
                print(f"Short Cascade Probability: {enhanced_summary.get('short_cascade_probability', 0):.3f}")
                print("\nTrade Quality Scores:")
                print(f"Long: {enhanced_summary.get('long_quality_score', 0):.3f}")
                print(f"Short: {enhanced_summary.get('short_quality_score', 0):.3f}")
                
                # Print explanation if available
                explanation = enhanced_summary.get('trade_explanation', {})
                if explanation:
                    print("\n============ DETAILED TRADE ANALYSIS ============")
                    if explanation.get('methodology'):
                        print(f"Methodology: {explanation['methodology']}")
                    if explanation.get('best_trades'):
                        print(f"\nBest Trades: {explanation['best_trades']}")
                    if explanation.get('risk_assessment'):
                        print(f"\nRisk Assessment: {explanation['risk_assessment']}")
                    if explanation.get('market_context'):
                        print(f"\nMarket Context: {explanation['market_context']}")
                
        # Step 5: Run BTC correlation analysis to enhance results
        if self.debug:
            print("Step 5: Running BTC correlation analysis...")
        
        # Skip if explicitly disabled
        if self.skip_btc_correlation:
            if self.debug:
                print("BTC correlation analysis is disabled. Skipping.")
            
            # Save results and return True to indicate success even without BTC correlation
            self.save_results()
            
            print(f"\n{'-'*80}")
            print(f"Enhanced analysis complete for {self.asset}")
            print(f"Results saved to: {DATA_DIR}/{self.asset}_enhanced_analysis_{self.timestamp}.json")
            print(f"{'-'*80}")
            
            return True
            
        # Check if BTC correlation module is available
        try:
            # Ensure project root is in Python's path
            import sys
            import os
            project_root = os.path.dirname(os.path.abspath(__file__))
            if project_root not in sys.path:
                sys.path.insert(0, project_root)
                
            # Now try to import the module
            from btc_correlation import BTCCorrelationAnalysis
            has_btc_correlation = True
        except ImportError as e:
            has_btc_correlation = False
            if self.debug:
                print(f"BTC correlation module not found. Skipping correlation analysis. Error: {e}")
        
        # Run BTC correlation analysis if available
        if has_btc_correlation:
            try:
                # Initialize the BTC correlation analysis
                btc_correlation = BTCCorrelationAnalysis(debug=self.debug)
                
                # Run the analysis
                correlation_result = btc_correlation.run_analysis(self.asset)
                
                if correlation_result and correlation_result.get('status') == 'success':
                    # Store the enhanced JSON
                    self.data['btc_correlation'] = correlation_result.get('enhanced_json', {}).get('btc_correlation', {})
                    self.data['btc_enhanced_trades'] = correlation_result.get('enhanced_json', {}).get('btc_enhanced_trades', [])
                    
                    if self.debug:
                        print(f"BTC correlation analysis completed successfully")
                        print(f"Correlation: {correlation_result.get('correlation', 0):.3f}")
                        print(f"Beta: {correlation_result.get('beta', 0):.3f}")
                        print(f"Enhanced trades: {len(correlation_result.get('enhanced_json', {}).get('btc_enhanced_trades', []))}")
                else:
                    if self.debug:
                        if correlation_result:
                            print(f"BTC correlation analysis status: {correlation_result.get('status', 'unknown')}")
                        else:
                            print("BTC correlation analysis failed.")
            except Exception as e:
                if self.debug:
                    print(f"Error running BTC correlation analysis: {e}")
        
        # Finally, save all results
        self.save_results()
        
        # Optional: Create visualizations - disabled to reduce file system usage
        # if not self.data.get('skip_visualizations', False):
        #     self.create_visualizations()
        
        print(f"\n{'-'*80}")
        print(f"Enhanced analysis complete for {self.asset}")
        print(f"Results saved to: {DATA_DIR}/{self.asset}_enhanced_analysis_{self.timestamp}.json")
        # print(f"Visualizations saved to: {DATA_DIR}/{self.asset}_enhanced_analysis_{self.timestamp}.png")
        print(f"{'-'*80}")
        
        return True
        
    def save_results(self):
        """Save the analysis results to a JSON file"""
        # Extract enhanced summary if available
        enhanced_summary = None
        if MARKET_CONTEXT_AVAILABLE and "enhanced_summary" in self.price_targets:
            enhanced_summary = self.price_targets.get("enhanced_summary")
        
        result = {
            "asset": self.asset,
            "current_price": self.current_price,
            "timestamp": self.timestamp,
            "clusters": self.clusters,
            "cascade_probabilities": self.cascade_probabilities,
            "price_targets": self.price_targets,
            "ta_price_targets": self.ta_price_targets,
            "summary": enhanced_summary
        }
        
        # Add BTC correlation data if available
        if hasattr(self, 'data') and self.data and 'btc_correlation' in self.data:
            result["btc_correlation"] = self.data["btc_correlation"]
            
        # Add BTC enhanced trades if available
        if hasattr(self, 'data') and self.data and 'btc_enhanced_trades' in self.data:
            result["btc_enhanced_trades"] = self.data["btc_enhanced_trades"]
            
        # Add orderbook analysis if available
        if hasattr(self, 'data') and self.data and 'orderbook_analysis' in self.data:
            result["orderbook_analysis"] = self.data["orderbook_analysis"]
        
        # Get visualizations directory with fallbacks
        vis_dir = get_visualizations_directory()
        os.makedirs(vis_dir, exist_ok=True)
        output_file = os.path.join(vis_dir, f"{self.asset}_enhanced_analysis_{self.timestamp}.json")
        
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
            
        return output_file
        
    def create_visualizations(self):
        """Create visual representations of the analysis results"""
        # Create figure with 2x2 grid
        fig, axs = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle(f"{self.asset} Enhanced Liquidation Analysis", fontsize=16)
        
        # Plot 1: Liquidation Clusters
        self._plot_liquidation_clusters(axs[0, 0])
        
        # Plot 2: Cascade Probability
        self._plot_cascade_probability(axs[0, 1])
        
        # Plot 3: Price Targets
        self._plot_price_targets(axs[1, 0])
        
        # Plot 4: Risk Summary
        self._plot_risk_summary(axs[1, 1])
        
        # Add timestamp and save
        plt.figtext(0.5, 0.01, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ha="center", fontsize=10)
        
        # Save the figure - commented out to reduce file system usage
        # vis_dir = get_visualizations_directory()
        # output_file = os.path.join(vis_dir, f"{self.asset}_enhanced_analysis_{self.timestamp}.png")
        # plt.savefig(output_file, dpi=150, bbox_inches="tight")
        
        # Never show plots interactively in batch mode
        # if self.debug:
        #     plt.show()
        
        plt.close()
        
        # Since output_file is commented out, return None instead
        return None
    
    def _plot_liquidation_clusters(self, ax):
        """Plot liquidation clusters"""
        # Set up the plot
        ax.set_title("Liquidation Clusters")
        ax.set_xlabel("Price")
        ax.set_ylabel("Size")
        
        # Get price range for x-axis
        price_range = [
            self.current_price * 0.8,  # 20% below current price
            self.current_price * 1.2   # 20% above current price
        ]
        
        # Plot current price as vertical line
        ax.axvline(self.current_price, color='black', linestyle='--', alpha=0.5, label="Current Price")
        
        # Plot long clusters (red)
        for cluster in self.clusters.get("long_clusters", []):
            center_price = cluster.get("center_price", 0)
            size = cluster.get("total_size", 0)
            prob = cluster.get("trigger_probability", 0.5)
            
            # Skip clusters outside our view range
            if center_price < price_range[0] or center_price > price_range[1]:
                continue
                
            # Plot cluster as circle with size proportional to position size and color by probability
            ax.scatter(center_price, size, s=size/5 + 50, color='red', alpha=min(0.9, prob), 
                      edgecolors='darkred', linewidths=1)
            
            # Add text label
            ax.text(center_price, size, f"{center_price:.1f}", ha='center', va='bottom', fontsize=8)
        
        # Plot short clusters (green)
        for cluster in self.clusters.get("short_clusters", []):
            center_price = cluster.get("center_price", 0)
            size = cluster.get("total_size", 0)
            prob = cluster.get("trigger_probability", 0.5)
            
            # Skip clusters outside our view range
            if center_price < price_range[0] or center_price > price_range[1]:
                continue
                
            # Plot cluster as circle
            ax.scatter(center_price, size, s=size/5 + 50, color='green', alpha=min(0.9, prob), 
                      edgecolors='darkgreen', linewidths=1)
            
            # Add text label
            ax.text(center_price, size, f"{center_price:.1f}", ha='center', va='bottom', fontsize=8)
        
        # Add legend
        ax.scatter([], [], s=100, color='red', alpha=0.7, label="Long Liquidations")
        ax.scatter([], [], s=100, color='green', alpha=0.7, label="Short Liquidations")
        ax.legend(loc='upper right')
        
        # Set axis limits
        ax.set_xlim(price_range)
        
    def _plot_cascade_probability(self, ax):
        """Plot cascade probability visualization"""
        # Set up the plot
        ax.set_title("Liquidation Cascade Risk")
        
        # Create risk level bars - must match levels in cascade_analysis.py
        risk_levels = ["LOW", "MEDIUM", "HIGH", "SEVERE"]
        long_prob = self.cascade_probabilities.get("long_cascade", {}).get("probability", 0)
        short_prob = self.cascade_probabilities.get("short_cascade", {}).get("probability", 0)
        
        # Convert probabilities to percentage
        long_pct = long_prob * 100
        short_pct = short_prob * 100
        
        # Create bar positions
        y_pos = np.arange(len(risk_levels))
        
        # Create long and short bars
        ax.barh(y_pos - 0.2, [25, 25, 25, 25], height=0.4, color='lightgray', alpha=0.3)
        ax.barh(y_pos + 0.2, [25, 25, 25, 25], height=0.4, color='lightgray', alpha=0.3)
        
        # Determine which risk level each probability falls into
        long_level = risk_levels.index(self.cascade_probabilities.get("long_cascade", {}).get("risk_level", "LOW"))
        short_level = risk_levels.index(self.cascade_probabilities.get("short_cascade", {}).get("risk_level", "LOW"))
        
        # Plot the active risk levels
        for i in range(long_level + 1):
            width = 25 if i < long_level else long_pct % 25
            ax.barh(y_pos[i] - 0.2, width, height=0.4, color='red', alpha=0.6 + i * 0.1)
            
        for i in range(short_level + 1):
            width = 25 if i < short_level else short_pct % 25
            ax.barh(y_pos[i] + 0.2, width, height=0.4, color='green', alpha=0.6 + i * 0.1)
        
        # Add labels
        for i, level in enumerate(risk_levels):
            ax.text(26, y_pos[i] - 0.2, f"Long: {long_pct:.1f}%" if i == long_level else "", 
                   va='center', fontsize=9, color='darkred')
            ax.text(26, y_pos[i] + 0.2, f"Short: {short_pct:.1f}%" if i == short_level else "", 
                   va='center', fontsize=9, color='darkgreen')
        
        # Set labels and styling
        ax.set_yticks(y_pos)
        ax.set_yticklabels(risk_levels)
        ax.set_xlabel("Risk Score (%)")
        ax.set_xlim(0, 50)
        
        # Add legend
        ax.barh([], [], color='red', alpha=0.7, label="Long Cascade")
        ax.barh([], [], color='green', alpha=0.7, label="Short Cascade")
        ax.legend(loc='upper right')
        
    def _plot_price_targets(self, ax):
        """Plot price targets and optimal trading ranges"""
        # Set up the plot
        ax.set_title("Price Targets and Trading Ranges")
        ax.set_xlabel("Price")
        
        # Plot current price as vertical line
        ax.axvline(self.current_price, color='black', linestyle='--', alpha=0.5, label="Current Price")
        
        # Get ranges to plot
        ranges = self.price_targets.get("ranges", [])
        
        if not ranges:
            ax.text(0.5, 0.5, "No price targets identified", ha='center', va='center', 
                   transform=ax.transAxes, fontsize=14)
            return
        
        # Plot each range
        y_positions = np.linspace(0.8, 0.2, len(ranges))  # Spread ranges vertically
        
        for i, range_data in enumerate(ranges):
            direction = range_data.get("direction", "neutral")
            entry = range_data.get("entry", self.current_price)
            stop_loss = range_data.get("stop_loss", self.current_price * 0.95)
            take_profit = range_data.get("take_profit", self.current_price * 1.05)
            risk_reward = range_data.get("risk_reward", 0)
            
            # Choose color based on direction
            color = 'green' if direction == "long" else 'red' if direction == "short" else 'gray'
            
            # Plot the range line
            ax.plot([stop_loss, take_profit], [y_positions[i], y_positions[i]], color=color, linewidth=2, alpha=0.7)
            
            # Plot entry point
            ax.scatter(entry, y_positions[i], color=color, s=100, marker='o', zorder=10)
            
            # Plot stop loss and take profit
            ax.scatter(stop_loss, y_positions[i], color=color, s=80, marker='s', alpha=0.7)
            ax.scatter(take_profit, y_positions[i], color=color, s=80, marker='d', alpha=0.7)
            
            # Add labels
            ax.text(entry, y_positions[i] + 0.03, f"Entry\n{entry:.1f}", ha='center', va='bottom', fontsize=9)
            ax.text(stop_loss, y_positions[i] - 0.03, f"SL\n{stop_loss:.1f}", ha='center', va='top', fontsize=8)
            ax.text(take_profit, y_positions[i] - 0.03, f"TP\n{take_profit:.1f}", ha='center', va='top', fontsize=8)
            
            # Add R:R label
            midpoint = (entry + take_profit) / 2
            ax.text(midpoint, y_positions[i] + 0.03, f"R:R = {risk_reward:.1f}", ha='center', 
                   va='bottom', fontsize=9, weight='bold')
        
        # Add legend
        ax.scatter([], [], color='green', s=100, marker='o', label="Long Positions")
        ax.scatter([], [], color='red', s=100, marker='o', label="Short Positions")
        ax.scatter([], [], color='gray', s=80, marker='s', label="Stop Loss")
        ax.scatter([], [], color='gray', s=80, marker='d', label="Take Profit")
        ax.legend(loc='upper right')
        
        # Remove y-axis ticks as they're not meaningful
        ax.set_yticks([])
        
        # Set reasonable x limits based on the ranges
        min_price = min([self.current_price * 0.9] + [r.get("stop_loss", self.current_price) for r in ranges])
        max_price = max([self.current_price * 1.1] + [r.get("take_profit", self.current_price) for r in ranges])
        ax.set_xlim(min_price, max_price)
        
    def _plot_risk_summary(self, ax):
        """Plot risk summary and recommendation"""
        # Set up the plot
        ax.set_title("Risk Assessment and Recommendation")
        
        # Hide axes
        ax.axis('off')
        
        # Get key metrics
        dominant_direction = self.cascade_probabilities.get("dominant_direction", "neutral")
        overall_risk = self.cascade_probabilities.get("risk_level", "UNKNOWN")
        
        # Calculate overall probability as the max of long and short probabilities
        long_prob = self.cascade_probabilities.get("long_cascade", {}).get("probability", 0)
        short_prob = self.cascade_probabilities.get("short_cascade", {}).get("probability", 0)
        overall_prob = max(long_prob, short_prob) * 100
        
        # Format direction for display
        direction_display = dominant_direction.upper() if dominant_direction != "neutral" else "NEUTRAL"
        
        # Choose text color based on risk level
        risk_colors = {
            "LOW": "green",
            "MODERATE": "blue",
            "HIGH": "orange",
            "SEVERE": "red",
            "UNKNOWN": "gray"
        }
        
        risk_color = risk_colors.get(overall_risk, "gray")
        
        # Add the main risk assessment text
        ax.text(0.5, 0.9, f"Risk Assessment: {overall_risk}", ha='center', fontsize=16, 
               weight='bold', color=risk_color)
        
        # Add direction bias
        bias_color = 'green' if dominant_direction == "long" else 'red' if dominant_direction == "short" else 'gray'
        ax.text(0.5, 0.8, f"Direction Bias: {direction_display}", ha='center', fontsize=14, 
               weight='bold', color=bias_color)
        
        # Add probability percentage
        ax.text(0.5, 0.7, f"Cascade Probability: {overall_prob:.1f}%", ha='center', fontsize=14)
        
        # Add the recommendation summary if available
        if "recommendation" in self.price_targets and "summary" in self.price_targets["recommendation"]:
            recommendation = self.price_targets["recommendation"]["summary"]
            
            # Word wrap for long recommendations
            wrapped_rec = ""
            words = recommendation.split()
            line = ""
            
            for word in words:
                if len(line + word) > 60:
                    wrapped_rec += line + "\n"
                    line = word + " "
                else:
                    line += word + " "
            
            wrapped_rec += line
            
            ax.text(0.5, 0.5, wrapped_rec, ha='center', va='center', fontsize=12, 
                   wrap=True, bbox=dict(facecolor='white', alpha=0.8, boxstyle='round,pad=1'))
            
        # Add stats for liquidation clusters
        long_count = len(self.clusters.get("long_clusters", []))
        short_count = len(self.clusters.get("short_clusters", []))
        ax.text(0.5, 0.2, f"Detected Clusters: {long_count + short_count} total\n({long_count} long, {short_count} short)", 
               ha='center', fontsize=10)
        
        # Add current price info
        ax.text(0.5, 0.1, f"Current Price: {self.current_price}", ha='center', fontsize=10)


# Force exit at the end to prevent hanging
def force_exit():
    print("\n==== Forcing exit to prevent hanging ====\n")
    os._exit(0)

def main():
    """Main function to run the enhanced liquidation analysis"""
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Enhanced Liquidation Analysis")
    parser.add_argument("--asset", "-a", type=str, help="Asset to analyze (e.g. ETH, BTC, SOL)")
    parser.add_argument("--file", "-f", type=str, help="Input file path for liquidation data")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug output")
    parser.add_argument("--list", "-l", action="store_true", help="List available assets")
    parser.add_argument("--no-auto", "-n", action="store_true", help="Disable automatic analysis of all assets")
    parser.add_argument("--no-btc-correlation", action="store_true", help="Disable BTC correlation analysis")
    parser.add_argument("--btc-correlation-only", action="store_true", help="Run only BTC correlation analysis on existing results")
    parser.add_argument("--skip-asset", type=str, help="Skip processing for specified asset")
    
    args = parser.parse_args()
    
    # Debug is always enabled by default
    args.debug = True
    
    # Handle --list argument
    if args.list:
        print("Listing available assets for analysis:")
        assets = []
        vis_dir = get_visualizations_directory()
        if os.path.exists(vis_dir):
            for file in os.listdir(vis_dir):
                if file.endswith("_liquidation_analysis.json"):
                    asset = file.split("_liquidation_analysis.json")[0]
                    assets.append(asset)
        
        if not assets:
            print("No assets available. Run fetch_top_traders.py first to generate data.")
        else:
            for i, asset in enumerate(sorted(assets), 1):
                print(f"{i}. {asset}")
        return
    
    # If no asset or file provided, offer interactive selection
    if not args.asset and not args.file:
        # Look for available asset files
        assets = []
        vis_dir = get_visualizations_directory()
        if os.path.exists(vis_dir):
            for file in os.listdir(vis_dir):
                if file.endswith("_liquidation_analysis.json"):
                    asset = file.split("_liquidation_analysis.json")[0]
                    assets.append(asset)
        
        if not assets:
            print("No assets available. Run fetch_top_traders.py first to generate data.")
            return
        
        print("Available assets for analysis:")
        for i, asset in enumerate(sorted(assets), 1):
            print(f"{i}. {asset}")
        
        # Check if BTC correlation is enabled
        btc_correlation_enabled = not args.no_btc_correlation if hasattr(args, 'no_btc_correlation') else True
        
        # Always run in automatic mode unless explicitly disabled
        if not args.no_auto:
            print("Running in automatic mode - analyzing all assets")
            if btc_correlation_enabled:
                print("BTC correlation analysis is ENABLED")
            else:
                print("BTC correlation analysis is DISABLED")
                
            successful = 0
            failed = 0
            
            # Analyze all assets
            assets_to_process = sorted(assets)
            if args.skip_asset:
                assets_to_process = [a for a in assets_to_process if a.upper() != args.skip_asset.upper()]
                if args.debug:
                    print(f"Skipping {args.skip_asset} as requested")
            
            # Define the worker function for parallel processing
            def process_asset(asset):
                print(f"Processing {asset}...")
                try:
                    analyzer = EnhancedLiquidationAnalysis(asset=asset, debug=args.debug, skip_btc_correlation=args.no_btc_correlation)
                    if analyzer.run_analysis():
                        return (asset, True, None)  # Success
                    else:
                        return (asset, False, "Analysis failed")  # Failed
                except Exception as e:
                    error_msg = f"Error analyzing {asset}: {e}"
                    print(error_msg)
                    traceback.print_exc()
                    return (asset, False, error_msg)  # Exception
            
            # Helper function to generate a random delay based on asset name hash
            def get_asset_specific_delay(asset_name):
                import hashlib
                import random
                # Generate a hash from the asset name
                hash_obj = hashlib.md5(asset_name.encode())
                # Get first 4 chars of hex digest
                hex_hash = hash_obj.hexdigest()[:4]
                # Convert to integer and normalize to 0-1 range
                normalized = int(hex_hash, 16) / 65535  # 0xFFFF
                # Scale to desired range (0.2 to 2 seconds)
                return 0.2 + normalized * 1.8
            
            # Use parallel processing with ThreadPoolExecutor
            import concurrent.futures
            import time
            max_workers = min(5, len(assets_to_process))  # Keep to 5 workers to avoid rate limits
            
            print(f"\nStarting parallel analysis with {max_workers} workers and randomized delays...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Add randomized delay based on asset name to reduce API rate limiting
                future_to_asset = {}
                for i, asset in enumerate(assets_to_process):
                    # Get asset-specific delay based on hash
                    delay = get_asset_specific_delay(asset)
                    print(f"Scheduling {asset} with delay of {delay:.2f} seconds...")
                    
                    # Sleep for the asset-specific delay
                    time.sleep(delay)
                    
                    # Submit the task
                    future = executor.submit(process_asset, asset)
                    future_to_asset[future] = asset
                    
                    # If we've submitted 3 assets, add an extra pause
                    if (i + 1) % 3 == 0 and i < len(assets_to_process) - 1:
                        time.sleep(1)
                        print(f"Added buffer pause between batches...")
                
                # Process results as they complete
                for future in concurrent.futures.as_completed(future_to_asset):
                    asset = future_to_asset[future]
                    try:
                        asset_name, success, error = future.result()
                        if success:
                            successful += 1
                            print(f"✓ {asset_name} analysis completed successfully")
                        else:
                            failed += 1
                            if error:
                                print(f"✗ {asset_name} analysis failed: {error}")
                            else:
                                print(f"✗ {asset_name} analysis failed")
                    except Exception as e:
                        failed += 1
                        print(f"✗ {asset} processing exception: {e}")
                    
            print(f"\nAnalysis complete: {successful} successful, {failed} failed")
            force_exit()
            return
        else:
            # Only enter interactive mode if auto is explicitly disabled
            try:
                selection = input("\nEnter asset number to analyze (or press Enter to analyze all): ")
                
                if not selection.strip():
                    # Analyze all assets
                    for asset in sorted(assets):
                        print(f"\nAnalyzing {asset}...")
                        analyzer = EnhancedLiquidationAnalysis(asset=asset, debug=args.debug, skip_btc_correlation=args.no_btc_correlation)
                        analyzer.run_analysis()
                    force_exit()
                    return
                
                index = int(selection) - 1
                if 0 <= index < len(assets):
                    args.asset = sorted(assets)[index]
                else:
                    print("Invalid selection")
                    force_exit()
                    return
            except ValueError:
                print("Invalid input")
                force_exit()
                return
    
    # Create analyzer with either file or asset
    if args.file:
        analyzer = EnhancedLiquidationAnalysis(input_file=args.file, debug=args.debug)
    else:
        analyzer = EnhancedLiquidationAnalysis(asset=args.asset, debug=args.debug)
    
    # Run the analysis
    analyzer.run_analysis()


if __name__ == "__main__":
    try:
        main()
        # Force exit in case we reach here
        force_exit()
    except Exception as e:
        print(f"Unhandled error: {e}")
        traceback.print_exc()
        # Force exit even on error
        force_exit()
