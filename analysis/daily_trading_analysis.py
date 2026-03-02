#!/usr/bin/env python
"""
Daily Trading Analysis Module
--------------------------
Identifies daily trading opportunities based on liquidation data.
"""

import os
import sys
import pandas as pd
from datetime import datetime

# Add parent directory to path to allow imports from root after moving to analysis/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Define project root for consistent file path handling
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Helper function to get data directory with fallback support
def get_data_directory():
    """Get data directory with fallback paths to support pre/post-move structures"""
    # First try data/ in the new structure (after moving files)
    data_dir = os.path.join(PROJECT_ROOT, 'data')
    if os.path.exists(data_dir) and os.path.isdir(data_dir):
        return data_dir
        
    # Fallback to data/ in the project root (current structure)
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    if os.path.exists(data_dir) and os.path.isdir(data_dir):
        return data_dir
        
    # Last resort, create data in the project root
    data_dir = os.path.join(PROJECT_ROOT, 'data')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


def daily_trading_analysis(asset_summaries_file=None, trader_positions_file=None, 
                        trader_orders_file=None, num_assets=10):
    """
    Integrated daily analysis to find the best trading opportunities based on liquidations
    
    Args:
        asset_summaries_file: Path to asset summaries CSV (optional)
        trader_positions_file: Path to trader positions CSV (optional)
        trader_orders_file: Path to trader orders CSV (optional)
        num_assets: Number of top assets to analyze
        
    Returns:
        DataFrame with daily trading opportunities
    """
    
    print("\n" + "="*80)
    print(f" DAILY TRADING ANALYSIS - {datetime.now().strftime('%Y-%m-%d')} ".center(80, "="))
    print("="*80 + "\n")
    
    # Find latest files if not specified
    if not asset_summaries_file:
        asset_summaries_file = find_latest_file("data", "asset_summaries_", ".csv")
        if not asset_summaries_file:
            print("Error: No asset summaries file found")
            return
        print(f"Using asset summaries file: {asset_summaries_file}")
    
    if not trader_positions_file:
        trader_positions_file = find_latest_file("data", "trader_positions_", ".csv")
        if not trader_positions_file:
            print("Error: No trader positions file found")
            return
        print(f"Using trader positions file: {trader_positions_file}")
        
    if not trader_orders_file:
        trader_orders_file = find_latest_file("data", "trader_orders_", ".csv")
        if trader_orders_file:
            print(f"Using trader orders file: {trader_orders_file}")
    
    # Step 1: Load asset summaries data
    try:
        summaries_df = pd.read_csv(asset_summaries_file)
        positions_df = pd.read_csv(trader_positions_file)
        
        # Load orders if available
        try:
            orders_df = pd.read_csv(trader_orders_file) if trader_orders_file else None
        except:
            orders_df = None
            print("Warning: Couldn't load orders file, proceeding without order data.")
        
        print(f"Loaded data for {len(summaries_df)} assets.")
    except Exception as e:
        print(f"Error loading data files: {e}")
        return
    
    # Step 2: Rank assets by liquidation opportunity
    # First calculate opportunity score - combining risk levels with liquidation values
    summaries_df['downward_risk_score'] = summaries_df['downward_risk_level'].map({
        'LOW': 1, 'MODERATE': 2, 'HIGH': 3, 'SEVERE': 4, 'UNKNOWN': 0
    })
    
    summaries_df['upward_risk_score'] = summaries_df['upward_risk_level'].map({
        'LOW': 1, 'MODERATE': 2, 'HIGH': 3, 'SEVERE': 4, 'UNKNOWN': 0
    })
    
    # Calculate opportunity scores
    summaries_df['downward_opportunity'] = (
        summaries_df['downward_risk_score'] * 
        summaries_df['long_liquidation_value'] / 
        (summaries_df['total_bid_liquidity'] + 1)  # Add 1 to avoid division by zero
    )
    
    summaries_df['upward_opportunity'] = (
        summaries_df['upward_risk_score'] * 
        summaries_df['short_liquidation_value'] / 
        (summaries_df['total_ask_liquidity'] + 1)  # Add 1 to avoid division by zero
    )
    
    # Determine best direction for each asset
    summaries_df['best_direction'] = summaries_df.apply(
        lambda x: 'SHORT' if x['downward_opportunity'] > x['upward_opportunity'] else 'LONG', axis=1
    )
    
    summaries_df['best_opportunity_score'] = summaries_df.apply(
        lambda x: max(x['downward_opportunity'], x['upward_opportunity']), axis=1
    )
    
    # Sort by opportunity score
    sorted_assets = summaries_df.sort_values('best_opportunity_score', ascending=False)
    
    # Limit to top assets
    top_assets = sorted_assets.head(num_assets)
    
    # Step 3: For each top asset, perform detailed liquidation analysis
    print(f"\nAnalyzing top {len(top_assets)} assets for trading opportunities...")
    
    opportunities = []
    
    for idx, row in top_assets.iterrows():
        asset = row['asset']
        direction = row['best_direction']
        current_price = row['current_price']
        
        print(f"\nAnalyzing {asset} for {direction} opportunities...")
        
        # Filter positions for this asset
        asset_positions = positions_df[positions_df['coin'] == asset]
        
        # Extract target side positions (LONG positions for SHORT direction and vice versa)
        target_side = 'LONG' if direction == 'SHORT' else 'SHORT'
        target_positions = asset_positions[asset_positions['side'] == target_side]
        
        # Skip if no positions for this direction
        if len(target_positions) == 0:
            print(f"No {target_side} positions found for {asset}, skipping...")
            continue
        
        # Find liquidation levels and distances from current price
        if direction == 'SHORT':
            # For SHORT direction, we're looking at LONG liquidations below current price
            relevant_positions = target_positions[target_positions['liquidation_price'] < current_price]
            
            # Skip if no relevant positions
            if len(relevant_positions) == 0:
                print(f"No LONG liquidations below current price for {asset}, skipping...")
                continue
                
            # Sort by liquidation price (descending) to find closest to current price
            sorted_positions = relevant_positions.sort_values('liquidation_price', ascending=False)
            
        else:  # LONG direction
            # For LONG direction, we're looking at SHORT liquidations above current price
            relevant_positions = target_positions[target_positions['liquidation_price'] > current_price]
            
            # Skip if no relevant positions
            if len(relevant_positions) == 0:
                print(f"No SHORT liquidations above current price for {asset}, skipping...")
                continue
                
            # Sort by liquidation price (ascending) to find closest to current price
            sorted_positions = relevant_positions.sort_values('liquidation_price', ascending=True)
        
        # Calculate liquidation clusters
        clusters = calculate_liquidation_clusters(sorted_positions, current_price)
        
        # Build opportunity entry
        if clusters:
            # Get the largest cluster
            largest_cluster = max(clusters, key=lambda c: c['total_value'])
            
            # Calculate entry and target prices
            entry_price = current_price
            
            # For SHORT, target is the average liquidation price
            # For LONG, target is the average liquidation price
            target_price = largest_cluster['avg_liquidation_price']
            
            # Calculate risk-reward
            # Use a 1% stop loss as default risk
            risk_pct = 1.0
            reward_pct = abs(target_price - current_price) / current_price * 100
            risk_reward = reward_pct / risk_pct
            
            # Create opportunity entry
            opportunity = {
                'asset': asset,
                'date': datetime.now().strftime('%Y-%m-%d'),
                'direction': direction,
                'current_price': current_price,
                'entry_price': entry_price,
                'target_price': target_price,
                'stop_loss': entry_price * (1 + 0.01) if direction == 'SHORT' else entry_price * (1 - 0.01),
                'risk_reward': risk_reward,
                'liquidation_cluster_size': largest_cluster['size'],
                'liquidation_value': largest_cluster['total_value'],
                'nearest_liquidation': sorted_positions.iloc[0]['liquidation_price'],
                'risk_level': row['downward_risk_level'] if direction == 'SHORT' else row['upward_risk_level'],
                'opportunity_score': row['best_opportunity_score'],
                'long_short_ratio': row['long_short_ratio'],
                'target_move_pct': reward_pct
            }
            
            opportunities.append(opportunity)
            
            print(f"Found {direction} opportunity for {asset}:")
            print(f"  Entry: ${entry_price:.2f}, Target: ${target_price:.2f}")
            print(f"  Risk/Reward: {risk_reward:.2f}, Cluster size: {largest_cluster['size']} positions")
            print(f"  Liquidation value: ${largest_cluster['total_value']:.2f}")
            
        else:
            print(f"No viable liquidation clusters found for {asset}")
    
    # Create opportunities DataFrame
    if opportunities:
        opps_df = pd.DataFrame(opportunities)
        
        # Sort by opportunity score
        opps_df = opps_df.sort_values('opportunity_score', ascending=False)
        
        # Add rank
        opps_df['rank'] = range(1, len(opps_df) + 1)
        
        # Reorder columns
        columns = [
            'rank', 'date', 'asset', 'direction', 'current_price', 
            'entry_price', 'target_price', 'stop_loss', 'risk_reward',
            'target_move_pct', 'opportunity_score', 'liquidation_cluster_size',
            'liquidation_value', 'nearest_liquidation', 'risk_level',
            'long_short_ratio'
        ]
        
        result_df = opps_df[columns]
        
        # Save to CSV
        output_file = f"data/trading_opportunities_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        result_df.to_csv(output_file, index=False)
        print(f"\nSaved {len(result_df)} trading opportunities to {output_file}")
        
        # Print top opportunities
        print("\nTOP TRADING OPPORTUNITIES:")
        print("="*100)
        print(result_df.head().to_string())
        print("="*100)
        
        return result_df
    else:
        print("\nNo viable trading opportunities found based on liquidation analysis.")
        return pd.DataFrame()

def find_latest_file(directory_name, prefix, suffix):
    """Find the latest file with given prefix and suffix in directory"""
    # Get data directory using helper function
    if directory_name == "data":
        directory = get_data_directory()
    else:
        directory = os.path.join(get_data_directory(), directory_name)
    
    latest_file = None
    latest_time = None
    
    if os.path.exists(directory) and os.path.isdir(directory):
        for filename in os.listdir(directory):
            if filename.startswith(prefix) and filename.endswith(suffix):
                file_path = os.path.join(directory, filename)
                file_time = os.path.getmtime(file_path)
                
                if latest_time is None or file_time > latest_time:
                    latest_time = file_time
                    latest_file = file_path
    
    return latest_file

def calculate_liquidation_clusters(positions_df, current_price, orderbook=None, proximity_threshold=0.05):
    """
    Calculate liquidation clusters with enhanced methodologies:
    - Multi-level range analysis (near, medium, far term)
    - Size and count imbalance tracking
    - Absorption ratio calculation (if orderbook provided)
    - Thin liquidity spot identification
    
    Args:
        positions_df: DataFrame with positions (already filtered for relevant direction)
        current_price: Current asset price
        orderbook: Optional orderbook data for liquidity analysis
        proximity_threshold: Base distance threshold for clustering
        
    Returns:
        Dictionary with clusters and enhanced imbalance metrics
    """
    import math
    import numpy as np
    
    # If no positions, return empty dictionary with metrics
    if len(positions_df) == 0:
        return {
            "clusters": [],
            "imbalance_metrics": {}
        }
    
    # Define tiered ranges (percentage from current price)
    ranges = {
        "near": (0, 0.03),     # 0-3% from current price
        "medium": (0.03, 0.07), # 3-7% from current price
        "far": (0.07, 0.15)     # 7-15% from current price
    }
    
    # Initialize range containers for imbalance analysis
    range_analysis = {}
    for range_name, (min_pct, max_pct) in ranges.items():
        lower_bound = current_price * (1 - max_pct)
        upper_bound = current_price * (1 + max_pct)
        
        # For positions below current price
        below_positions = positions_df[
            (positions_df['liquidation_price'] >= lower_bound) & 
            (positions_df['liquidation_price'] < current_price * (1 - min_pct))
        ]
        
        # For positions above current price
        above_positions = positions_df[
            (positions_df['liquidation_price'] <= upper_bound) & 
            (positions_df['liquidation_price'] > current_price * (1 + min_pct))
        ]
        
        # Calculate metrics for this range
        below_value = sum(below_positions['size'] * below_positions['entry_price']) if len(below_positions) > 0 else 0
        above_value = sum(above_positions['size'] * above_positions['entry_price']) if len(above_positions) > 0 else 0
        
        below_count = len(below_positions)
        above_count = len(above_positions)
        
        # Calculate imbalance ratios - normalized between -1 (all below) and 1 (all above)
        total_value = below_value + above_value
        value_imbalance = (above_value - below_value) / (total_value) if total_value > 0 else 0
        
        total_count = below_count + above_count
        count_imbalance = (above_count - below_count) / (total_count) if total_count > 0 else 0
        
        # Calculate avg position sizes
        avg_below_size = below_value / below_count if below_count > 0 else 0
        avg_above_size = above_value / above_count if above_count > 0 else 0
        
        # Store metrics for this range
        range_analysis[range_name] = {
            "below_value": below_value,
            "above_value": above_value,
            "below_count": below_count,
            "above_count": above_count,
            "total_value": total_value,
            "value_imbalance": value_imbalance,  # -1 to 1
            "count_imbalance": count_imbalance,  # -1 to 1
            "avg_below_size": avg_below_size,
            "avg_above_size": avg_above_size,
            # Add size ratio (how much larger is one side vs the other)
            "size_ratio": avg_above_size / avg_below_size if avg_below_size > 0 else (float('inf') if avg_above_size > 0 else 1.0)
        }
            
    # Calculate liquidity-adjusted metrics if orderbook is provided
    absorption_metrics = {}
    thin_spots = []
    
    if orderbook and 'bids' in orderbook and 'asks' in orderbook:
        # Calculate absorption ratio for both directions
        try:
            # Process bid side (for downward moves)
            bid_liquidity = []
            cumulative_bid_liquidity = 0
            for price, size in orderbook['bids']:
                cumulative_bid_liquidity += size * price  # Convert to USD value
                bid_liquidity.append((price, cumulative_bid_liquidity))
            
            # Process ask side (for upward moves)
            ask_liquidity = []
            cumulative_ask_liquidity = 0
            for price, size in orderbook['asks']:
                cumulative_ask_liquidity += size * price  # Convert to USD value
                ask_liquidity.append((price, cumulative_ask_liquidity))
            
            # Define price bins (every 0.5% from current price)
            bin_pct = 0.005  # 0.5% bins
            max_range_pct = 0.15  # 15% max range (matching our far range)
            
            # Create price bins
            downward_bins = [current_price * (1 - (i * bin_pct)) for i in range(1, int(max_range_pct / bin_pct) + 1)]
            upward_bins = [current_price * (1 + (i * bin_pct)) for i in range(1, int(max_range_pct / bin_pct) + 1)]
            
            # Group liquidations by bin
            downward_liq_by_bin = {}
            upward_liq_by_bin = {}
            
            # Process positions into bins
            for _, pos in positions_df.iterrows():
                liq_price = pos['liquidation_price']
                value = pos['size'] * pos['entry_price']
                
                # Find the appropriate bin
                if liq_price < current_price:
                    # Find the nearest bin (binary search would be more efficient for large datasets)
                    for bin_price in downward_bins:
                        if liq_price >= bin_price:
                            downward_liq_by_bin[bin_price] = downward_liq_by_bin.get(bin_price, 0) + value
                            break
                else:
                    for bin_price in upward_bins:
                        if liq_price <= bin_price:
                            upward_liq_by_bin[bin_price] = upward_liq_by_bin.get(bin_price, 0) + value
                            break
            
            # Calculate absorption ratio and identify thin spots for each bin
            downward_absorption = {}
            upward_absorption = {}
            
            # Calculate downward absorption
            for bin_price in downward_bins:
                liq_value = downward_liq_by_bin.get(bin_price, 0)
                if liq_value == 0:
                    continue
                    
                # Find available liquidity at this price
                available_liquidity = 0
                for b_price, b_liq in bid_liquidity:
                    if b_price >= bin_price:
                        available_liquidity = b_liq
                        break
                
                # Calculate absorption ratio (liquidation value / available liquidity)
                absorption_ratio = liq_value / available_liquidity if available_liquidity > 0 else float('inf')
                downward_absorption[bin_price] = absorption_ratio
                
                # Check for thin spot (absorption > 50%)
                if absorption_ratio > 0.5:
                    thin_spots.append({
                        'price': bin_price,
                        'direction': 'downward',
                        'liquidation_value': liq_value,
                        'available_liquidity': available_liquidity,
                        'absorption_ratio': min(absorption_ratio, 10.0),  # Cap for display purposes
                        'distance_from_current': (current_price - bin_price) / current_price
                    })
            
            # Calculate upward absorption
            for bin_price in upward_bins:
                liq_value = upward_liq_by_bin.get(bin_price, 0)
                if liq_value == 0:
                    continue
                    
                # Find available liquidity at this price
                available_liquidity = 0
                for a_price, a_liq in ask_liquidity:
                    if a_price <= bin_price:
                        available_liquidity = a_liq
                        break
                
                # Calculate absorption ratio
                absorption_ratio = liq_value / available_liquidity if available_liquidity > 0 else float('inf')
                upward_absorption[bin_price] = absorption_ratio
                
                # Check for thin spot
                if absorption_ratio > 0.5:
                    thin_spots.append({
                        'price': bin_price,
                        'direction': 'upward',
                        'liquidation_value': liq_value,
                        'available_liquidity': available_liquidity,
                        'absorption_ratio': min(absorption_ratio, 10.0),  # Cap for display
                        'distance_from_current': (bin_price - current_price) / current_price
                    })
            
            # Sort thin spots by absorption ratio (most significant first)
            thin_spots.sort(key=lambda x: x['absorption_ratio'], reverse=True)
            
            # Store absorption metrics
            absorption_metrics = {
                'downward': downward_absorption,
                'upward': upward_absorption,
                'max_downward_ratio': max(downward_absorption.values()) if downward_absorption else 0,
                'max_upward_ratio': max(upward_absorption.values()) if upward_absorption else 0
            }
        
        except Exception as e:
            print(f"Error calculating absorption metrics: {e}")
            absorption_metrics = {}
            thin_spots = []
    
    # Perform traditional clustering for backward compatibility
    # Simple distance-based clustering
    clusters = []
    remaining_positions = positions_df.copy().to_dict('records')
    
    # Apply exponential decay for proximity weighting
    decay_lambda = 8.0  # Controls how quickly importance decays with distance
    
    while remaining_positions:
        # Take the first position as a cluster seed
        seed = remaining_positions.pop(0)
        cluster = [seed]
        
        # Find positions with liquidation prices within threshold of seed
        i = 0
        while i < len(remaining_positions):
            pos = remaining_positions[i]
            
            # Use percentage-based threshold
            distance_threshold = current_price * proximity_threshold
            
            if abs(pos['liquidation_price'] - seed['liquidation_price']) <= distance_threshold:
                cluster.append(pos)
                remaining_positions.pop(i)
            else:
                i += 1
                
        # Add weight based on proximity to current price
        weighted_value = 0
        for pos in cluster:
            distance = abs(pos['liquidation_price'] - current_price) / current_price
            weight = math.exp(-decay_lambda * distance)
            weighted_value += pos['size'] * pos['entry_price'] * weight
                
        # Only save clusters with at least 3 positions
        if len(cluster) >= 3:
            # Calculate cluster metrics
            total_value = sum(pos['size'] * pos['entry_price'] for pos in cluster)
            avg_liquidation_price = sum(pos['liquidation_price'] for pos in cluster) / len(cluster)
            
            # Calculate market impact if orderbook is available
            market_impact = 0
            if orderbook:
                try:
                    # Determine direction (below = downward, above = upward)
                    direction = 'downward' if avg_liquidation_price < current_price else 'upward'
                    
                    # Find available liquidity between current price and target
                    if direction == 'downward':
                        # Find relevant bid levels
                        relevant_liquidity = sum(
                            bid[1] * bid[0] for bid in orderbook['bids'] 
                            if bid[0] >= avg_liquidation_price and bid[0] <= current_price
                        )
                    else:
                        # Find relevant ask levels
                        relevant_liquidity = sum(
                            ask[1] * ask[0] for ask in orderbook['asks'] 
                            if ask[0] <= avg_liquidation_price and ask[0] >= current_price
                        )
                    
                    # Calculate market impact
                    market_impact = total_value / relevant_liquidity if relevant_liquidity > 0 else 1.0
                    # Cap for display purposes
                    market_impact = min(1.0, market_impact)
                except Exception as e:
                    market_impact = 0
            
            clusters.append({
                'positions': cluster,
                'size': len(cluster),
                'total_value': total_value,
                'weighted_value': weighted_value,
                'avg_liquidation_price': avg_liquidation_price,
                'distance_from_current': abs(avg_liquidation_price - current_price) / current_price,
                'market_impact': market_impact
            })
    
    # Sort clusters by weighted value (largest first)
    clusters.sort(key=lambda c: c['weighted_value'], reverse=True)
    
    # Calculate consolidated imbalance metrics across all ranges
    consolidated_imbalance = {
        "near_term_value_imbalance": range_analysis["near"]["value_imbalance"],
        "medium_term_value_imbalance": range_analysis["medium"]["value_imbalance"],
        "far_term_value_imbalance": range_analysis["far"]["value_imbalance"],
        "near_term_count_imbalance": range_analysis["near"]["count_imbalance"],
        "total_liquidation_value": sum(c["total_value"] for c in clusters),
        "max_absorption_ratio": max(
            absorption_metrics.get("max_downward_ratio", 0),
            absorption_metrics.get("max_upward_ratio", 0)
        ) if absorption_metrics else 0,
        "thin_spot_count": len(thin_spots),
        "significant_thin_spots": [spot for spot in thin_spots if spot["absorption_ratio"] > 2.0]
    }
    
    # Calculate composite imbalance score
    # Prioritize near-term imbalances but factor in all ranges
    if consolidated_imbalance["thin_spot_count"] > 0:
        # Using thin spots significantly increases importance
        absorption_factor = min(5.0, consolidated_imbalance["max_absorption_ratio"])
        composite_score = (
            (abs(consolidated_imbalance["near_term_value_imbalance"]) * 0.5) +
            (abs(consolidated_imbalance["medium_term_value_imbalance"]) * 0.3) +
            (abs(consolidated_imbalance["far_term_value_imbalance"]) * 0.2)
        ) * absorption_factor
    else:
        # Without thin spots, score based purely on imbalance
        composite_score = (
            (abs(consolidated_imbalance["near_term_value_imbalance"]) * 0.5) +
            (abs(consolidated_imbalance["medium_term_value_imbalance"]) * 0.3) +
            (abs(consolidated_imbalance["far_term_value_imbalance"]) * 0.2)
        )
    
    consolidated_imbalance["composite_imbalance_score"] = composite_score
    
    return {
        "clusters": clusters,
        "range_analysis": range_analysis,
        "absorption_metrics": absorption_metrics,
        "thin_spots": thin_spots[:5],  # Limit to top 5 thin spots
        "consolidated_imbalance": consolidated_imbalance
    }