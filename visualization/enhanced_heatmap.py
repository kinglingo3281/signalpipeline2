#!/usr/bin/env python
"""
Enhanced Heatmap Module
---------------------
Creates enhanced visualizations of liquidation cascades.
"""

import os
import sys

# Add parent directory to path to allow imports from root after moving to visualization/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def create_liquidation_cascade_heatmap(asset, positions_df, current_price, output_dir=None):
    """
    Creates an enhanced heatmap visualization specifically highlighting
    liquidation cascades and potential trigger zones.
    This is the main entry point used by fetch_top_traders.py
    
    Args:
        asset: Asset symbol
        positions_df: DataFrame with trader positions for this asset
        current_price: Current asset price
        output_dir: Directory to save the visualization (default: data/visualizations)
        
    Returns:
        Dictionary with analysis results
    """
    print(f"Creating enhanced liquidation cascade heatmap for {asset}...")
    
    # Simply call our fully-featured implementation
    return create_enhanced_cascade_visualization(
        asset=asset,
        positions_df=positions_df,
        current_price=current_price,
        orderbook=None,  # This will be passed from the main flow if available
        output_dir=output_dir
    )

def create_enhanced_cascade_visualization(asset, positions_df, current_price, orderbook=None, output_dir=None):
    """
    Creates an enhanced visualization of liquidation cascades with improved metrics:
    - Dynamic thresholds based on orderbook volatility
    - Exponential decay weighting for proximity to current price
    - Multi-level cluster identification
    - Market impact potential calculation
    - Thin liquidity spot highlighting
    
    Args:
        asset: Asset symbol
        positions_df: DataFrame with trader positions for this asset
        current_price: Current asset price
        orderbook: Order book data for additional liquidity analysis
        output_dir: Directory to save the visualization (default: data/visualizations)
    
    Returns:
        Dictionary with analysis results including key clusters and metrics
    """
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        import pandas as pd
        from matplotlib.colors import LinearSegmentedColormap
        import os
        from datetime import datetime
        import seaborn as sns
        from scipy.ndimage import gaussian_filter1d
        from scipy.signal import find_peaks
    except ImportError as e:
        print(f"Error: Required visualization libraries not available: {e}")
        return None
    
    # Create output directory if needed
    if not output_dir:
        # When in visualization/ subdir, data dir is in the parent
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(base_dir, "data", "visualizations")
    os.makedirs(output_dir, exist_ok=True)
    
    # Filter positions for the asset
    if 'coin' in positions_df.columns:
        asset_positions = positions_df[positions_df['coin'] == asset].copy()
    else:
        asset_positions = positions_df.copy()
    
    if len(asset_positions) == 0:
        print(f"No positions found for {asset}")
        return None
    
    # Calculate dynamic threshold based on orderbook volatility
    dynamic_threshold = 0.005  # Default 0.5% threshold
    
    if orderbook:
        try:
            # Calculate spread as a volatility indicator
            best_bid = max([price for price, _ in orderbook['bids']], default=0)
            best_ask = min([price for price, _ in orderbook['asks']], default=0)
            
            if best_bid > 0 and best_ask > 0:
                spread_pct = (best_ask - best_bid) / best_bid
                
                # Adjust threshold based on spread - wider spread means more volatility
                dynamic_threshold = max(0.003, min(0.02, spread_pct * 2))
                print(f"Dynamic threshold set to {dynamic_threshold:.4f} based on orderbook spread of {spread_pct:.4f}")
        except (KeyError, IndexError) as e:
            print(f"Error calculating dynamic threshold from orderbook: {e}")
    
    # Set a reasonable price range for visualization
    min_liq = asset_positions['liquidation_price'].min()
    max_liq = asset_positions['liquidation_price'].max()
    
    # Set range with padding
    price_range = max(abs(max_liq - current_price), abs(current_price - min_liq))
    # Don't exceed 30% range to keep visualization focused
    price_range = min(price_range, current_price * 0.3)
    
    min_price = max(current_price - price_range, min_liq * 0.95)
    max_price = min(current_price + price_range, max_liq * 1.05)
    
    # Create price bins for visualization
    price_bins = np.linspace(min_price, max_price, 200)  # Higher resolution
    bin_width = price_bins[1] - price_bins[0]
    
    # Calculate liquidation density and apply exponential decay weighting
    long_density = np.zeros(len(price_bins))
    short_density = np.zeros(len(price_bins))
    
    # Calculate distance weight - closer to current price is more impactful
    def calc_proximity_weight(liq_price, decay_factor=0.1):
        distance_pct = abs(liq_price - current_price) / current_price
        return np.exp(-decay_factor * distance_pct * 100)
    
    # Process long positions liquidations
    long_positions = asset_positions[asset_positions['side'] == 'LONG']
    for _, pos in long_positions.iterrows():
        liq_price = pos['liquidation_price']
        size = pos['size']
        
        # Apply proximity weighting
        proximity_weight = calc_proximity_weight(liq_price)
        weighted_size = size * proximity_weight
        
        # Find the bin where this liquidation falls
        bin_idx = np.searchsorted(price_bins, liq_price)
        if 0 <= bin_idx < len(price_bins):
            long_density[bin_idx] += weighted_size
    
    # Process short positions liquidations
    short_positions = asset_positions[asset_positions['side'] == 'SHORT']
    for _, pos in short_positions.iterrows():
        liq_price = pos['liquidation_price']
        size = pos['size']
        
        # Apply proximity weighting
        proximity_weight = calc_proximity_weight(liq_price)
        weighted_size = size * proximity_weight
        
        # Find the bin where this liquidation falls
        bin_idx = np.searchsorted(price_bins, liq_price)
        if 0 <= bin_idx < len(price_bins):
            short_density[bin_idx] += weighted_size
    
    # Apply smoothing for better visualization
    long_density_smooth = gaussian_filter1d(long_density, sigma=2)
    short_density_smooth = gaussian_filter1d(short_density, sigma=2)
    
    # Calculate density per price range (per $1) instead of just total
    long_density_per_dollar = long_density_smooth / bin_width
    short_density_per_dollar = short_density_smooth / bin_width
    
    # Find significant liquidation clusters
    def identify_clusters(density, is_long=True, threshold_factor=1.0):
        # Find peaks using dynamic threshold based on volatility
        threshold = np.max(density) * dynamic_threshold * threshold_factor
        if threshold <= 0:
            return []
            
        peaks, properties = find_peaks(density, height=threshold, distance=5)
        
        clusters = []
        direction = "long" if is_long else "short"
        side = "downward" if is_long else "upward"  # Long positions cause downward cascades
        
        for i, peak_idx in enumerate(peaks):
            if peak_idx < 0 or peak_idx >= len(price_bins):
                continue
                
            peak_price = price_bins[peak_idx]
            peak_size = density[peak_idx]
            
            # Calculate cluster width and total value
            left_idx = peak_idx
            right_idx = peak_idx
            
            # Expand left until below threshold
            while left_idx > 0 and density[left_idx] > threshold * 0.5:
                left_idx -= 1
                
            # Expand right until below threshold
            while right_idx < len(density)-1 and density[right_idx] > threshold * 0.5:
                right_idx += 1
                
            cluster_width = price_bins[right_idx] - price_bins[left_idx]
            cluster_total = np.sum(density[left_idx:right_idx+1])
            
            # Calculate market impact
            market_impact = 0
            if orderbook:
                try:
                    # For long positions (downward cascade), calculate how much bid liquidity is available
                    if is_long:
                        # Extract bid data
                        bid_prices = [price for price, _ in orderbook['bids']]
                        bid_sizes = [size for _, size in orderbook['bids']]
                        
                        # Find closest bid price
                        bid_idx = np.searchsorted(bid_prices, peak_price)
                        if bid_idx < len(bid_prices) and bid_idx > 0:
                            nearby_liquidity = bid_sizes[bid_idx-1] * current_price
                            liq_value = cluster_total * current_price
                            
                            if nearby_liquidity > 0:
                                market_impact = min(1.0, liq_value / (nearby_liquidity * current_price))
                    else:
                        # For short positions (upward cascade)
                        ask_prices = [price for price, _ in orderbook['asks']]
                        ask_sizes = [size for _, size in orderbook['asks']]
                        
                        ask_idx = np.searchsorted(ask_prices, peak_price)
                        if ask_idx < len(ask_prices):
                            nearby_liquidity = ask_sizes[ask_idx] * current_price
                            liq_value = cluster_total * current_price
                            
                            if nearby_liquidity > 0:
                                market_impact = min(1.0, liq_value / (nearby_liquidity * current_price))
                except Exception as e:
                    print(f"Error calculating market impact: {e}")
            
            # Calculate isolation score (how isolated this cluster is from others)
            isolation_score = 0
            min_distance_to_other_peak = float('inf')
            for other_idx in peaks:
                if other_idx == peak_idx:
                    continue
                distance = abs(price_bins[other_idx] - peak_price)
                min_distance_to_other_peak = min(min_distance_to_other_peak, distance)
            
            # Normalize isolation score to 0-1 range
            if min_distance_to_other_peak < float('inf'):
                isolation_score = min(1.0, min_distance_to_other_peak / (current_price * 0.05))
            else:
                isolation_score = 1.0  # Completely isolated
                
            # Calculate risk/reward ratio
            # Risk is how close to current price, reward is size of cluster
            distance_to_current = abs(peak_price - current_price) / current_price
            price_impact_ratio = 0.01  # Assuming 1% price impact per $N of liquidations
            potential_impact = cluster_total * price_impact_ratio
            
            if distance_to_current > 0:
                risk_reward = potential_impact / distance_to_current
            else:
                risk_reward = potential_impact * 100  # Very close to current price
            
            # Determine triggering prices
            triggering_price = None
            if is_long and peak_price < current_price:
                # For long liquidations, need price to drop to this level
                triggering_price = peak_price
            elif not is_long and peak_price > current_price:
                # For short liquidations, need price to rise to this level
                triggering_price = peak_price
            
            # Calculate ideal entry based on risk/reward
            ideal_entry = None
            if triggering_price:
                # For long liquidations (shorting opportunity)
                if is_long:
                    # Enter above the triggering price
                    ideal_entry = current_price - (current_price - triggering_price) * 0.3
                else:
                    # For short liquidations (longing opportunity)
                    # Enter below the triggering price
                    ideal_entry = current_price + (triggering_price - current_price) * 0.3
            
            # Create cluster info
            cluster = {
                "price": peak_price,
                "size": peak_size,
                "width": cluster_width,
                "total_value": cluster_total,
                "direction": direction,
                "cascade_direction": side,
                "market_impact": market_impact,
                "isolation_score": isolation_score,
                "risk_reward": risk_reward,
                "triggering_price": triggering_price,
                "ideal_entry": ideal_entry,
                "target_side": "short" if is_long else "long"  # Trade opposing the liquidation side
            }
            
            clusters.append(cluster)
        
        # Sort by potential impact (risk_reward * market_impact)
        for cluster in clusters:
            cluster["potential_score"] = cluster["risk_reward"] * (0.5 + 0.5 * cluster["market_impact"]) * (0.2 + 0.8 * cluster["isolation_score"])
        
        clusters.sort(key=lambda x: x["potential_score"], reverse=True)
        return clusters
    
    # Identify clusters
    long_clusters = identify_clusters(long_density_smooth, is_long=True)
    short_clusters = identify_clusters(short_density_smooth, is_long=False)
    
    # Determine top opportunity
    top_opportunity = None
    all_clusters = long_clusters + short_clusters
    if all_clusters:
        all_clusters.sort(key=lambda x: x["potential_score"], reverse=True)
        top_opportunity = all_clusters[0]
    
    # Prepare the visualization
    fig, axes = plt.subplots(3, 1, figsize=(14, 20), gridspec_kw={'height_ratios': [2, 1, 1]})
    plt.subplots_adjust(hspace=0.3)
    
    # Set title
    fig.suptitle(f"{asset} Enhanced Liquidation Analysis - {datetime.now().strftime('%Y-%m-%d')}", 
                fontsize=20, fontweight='bold')
    
    # Plot 1: Liquidation Heatmap with enhanced visualization
    ax1 = axes[0]
    
    # Plot long liquidation density as a heatmap-like visualization
    # Use different color scheme for enhanced visualization
    ax1.fill_between(price_bins, 0, long_density_smooth, color='#D32F2F', alpha=0.6, label='Long Liquidations')
    ax1.fill_between(price_bins, 0, -1 * short_density_smooth, color='#388E3C', alpha=0.6, label='Short Liquidations')
    
    # Add current price line
    ax1.axvline(x=current_price, color='black', linestyle='--', linewidth=2, 
               label=f'Current Price: ${current_price:.2f}')
    
    # Add horizontal line at zero
    ax1.axhline(y=0, color='black', linewidth=1, alpha=0.5)
    
    # Add cluster annotations
    for cluster in long_clusters[:3]:  # Top 3 long clusters
        ax1.annotate(f"${cluster['price']:.2f}\nImpact: {cluster['market_impact']:.2f}",
                    xy=(cluster['price'], long_density_smooth[np.searchsorted(price_bins, cluster['price'])]),
                    xytext=(0, 20), textcoords='offset points',
                    arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=.2", color='#D32F2F'),
                    bbox=dict(boxstyle="round,pad=0.3", fc='#FFCDD2', ec='#D32F2F', alpha=0.7))
    
    for cluster in short_clusters[:3]:  # Top 3 short clusters
        ax1.annotate(f"${cluster['price']:.2f}\nImpact: {cluster['market_impact']:.2f}",
                    xy=(cluster['price'], -short_density_smooth[np.searchsorted(price_bins, cluster['price'])]),
                    xytext=(0, -20), textcoords='offset points',
                    arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=.2", color='#388E3C'),
                    bbox=dict(boxstyle="round,pad=0.3", fc='#C8E6C9', ec='#388E3C', alpha=0.7))
    
    # If we have top opportunity, highlight it
    if top_opportunity:
        direction = top_opportunity['direction']
        price = top_opportunity['price']
        
        y_pos = long_density_smooth[np.searchsorted(price_bins, price)] if direction == 'long' else -short_density_smooth[np.searchsorted(price_bins, price)]
        color = '#D32F2F' if direction == 'long' else '#388E3C'
        bg_color = '#FFCDD2' if direction == 'long' else '#C8E6C9'
        
        ax1.scatter(price, y_pos, s=120, color=color, edgecolor='black', zorder=10)
        
        # Annotate top opportunity details
        ax1.annotate(f"TOP OPPORTUNITY\n"
                    f"${price:.2f} - {top_opportunity['target_side'].upper()}\n"
                    f"Score: {top_opportunity['potential_score']:.2f}",
                    xy=(price, y_pos),
                    xytext=(30, 30 if direction == 'long' else -30), textcoords='offset points',
                    arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=.2", color=color, lw=2),
                    bbox=dict(boxstyle="round,pad=0.3", fc=bg_color, ec=color, alpha=0.9),
                    fontweight='bold')
        
        # Show ideal entry if available
        if top_opportunity['ideal_entry']:
            ax1.axvline(x=top_opportunity['ideal_entry'], color=color, linestyle=':', linewidth=2)
            ax1.annotate(f"Ideal Entry: ${top_opportunity['ideal_entry']:.2f}",
                        xy=(top_opportunity['ideal_entry'], 0),
                        xytext=(5, 10), textcoords='offset points',
                        bbox=dict(boxstyle="round,pad=0.2", fc='white', ec=color, alpha=0.7))
    
    # Add labels and legend
    ax1.set_title("Enhanced Liquidation Density Analysis", fontsize=16, fontweight='bold')
    ax1.set_ylabel("Liquidation Size (Weighted)", fontsize=12)
    ax1.legend(loc='upper right')
    ax1.grid(True, alpha=0.3)
    
    # Add dynamic threshold info
    ax1.text(0.02, 0.98, f"Dynamic Threshold: {dynamic_threshold:.4f}", 
             transform=ax1.transAxes, fontsize=10, va='top', 
             bbox=dict(boxstyle="round,pad=0.3", fc='white', ec='gray', alpha=0.7))
    
    # Plot 2: Cascade potential visualization
    ax2 = axes[1]
    
    # Calculate enhanced cascade potential with exponential propagation
    def calculate_enhanced_cascade(density, is_long=True):
        cascade = np.zeros(len(price_bins))
        propagation_factor = 0.85  # How much each level propagates to the next
        
        if is_long:
            # For long liquidations (price moves down), we accumulate from higher to lower prices
            for i in range(len(price_bins)-1, -1, -1):
                if i < len(price_bins) - 1:
                    # Add propagation from the price level above
                    cascade[i] = density[i] + cascade[i+1] * propagation_factor
                else:
                    cascade[i] = density[i]
        else:
            # For short liquidations (price moves up), we accumulate from lower to higher prices
            for i in range(len(price_bins)):
                if i > 0:
                    # Add propagation from the price level below
                    cascade[i] = density[i] + cascade[i-1] * propagation_factor
                else:
                    cascade[i] = density[i]
        
        # Normalize for visualization
        if cascade.max() > 0:
            cascade = cascade / cascade.max()
        
        return cascade
    
    # Calculate enhanced cascade potential
    downward_cascade = calculate_enhanced_cascade(long_density_smooth, is_long=True)
    upward_cascade = calculate_enhanced_cascade(short_density_smooth, is_long=False)
    
    # Plot cascade potential
    ax2.plot(price_bins, downward_cascade, color='#D32F2F', linewidth=2, label='Downward Cascade Potential')
    ax2.plot(price_bins, upward_cascade, color='#388E3C', linewidth=2, label='Upward Cascade Potential')
    
    # Add current price line
    ax2.axvline(x=current_price, color='black', linestyle='--', linewidth=2)
    
    # Add labels and legend
    ax2.set_title("Liquidation Cascade Potential", fontsize=16, fontweight='bold')
    ax2.set_ylabel("Cascade Potential", fontsize=12)
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Orderbook vs Liquidations plot if orderbook is available
    ax3 = axes[2]
    
    if orderbook:
        try:
            # Extract bid and ask data
            bid_prices = [price for price, _ in orderbook['bids']]
            bid_sizes = [size for _, size in orderbook['bids']]
            ask_prices = [price for price, _ in orderbook['asks']]
            ask_sizes = [size for _, size in orderbook['asks']]
            
            # Convert to cumulative values
            cum_bid_sizes = np.cumsum(bid_sizes)
            cum_ask_sizes = np.cumsum(ask_sizes)
            
            # Plot cumulative bids and asks
            ax3.step(bid_prices, cum_bid_sizes, color='#1E88E5', linewidth=2, label='Bid Liquidity', where='post')
            ax3.step(ask_prices, cum_ask_sizes, color='#FFA000', linewidth=2, label='Ask Liquidity', where='post')
            
            # Add liquidation overlay
            # Scale liquidation density to match orderbook size scale
            scale_factor = max(max(cum_bid_sizes), max(cum_ask_sizes)) / max(max(long_density_smooth), max(short_density_smooth)) * 0.5
            
            # Plot scaled liquidation density
            ax3.plot(price_bins, long_density_smooth * scale_factor, color='#D32F2F', alpha=0.7, 
                    linestyle=':', linewidth=2, label='Long Liquidations (scaled)')
            ax3.plot(price_bins, short_density_smooth * scale_factor, color='#388E3C', alpha=0.7, 
                    linestyle=':', linewidth=2, label='Short Liquidations (scaled)')
            
            # Add current price line
            ax3.axvline(x=current_price, color='black', linestyle='--', linewidth=2)
            
            # Identify and mark thin liquidity spots
            thin_spots = []
            
            # Detect where liquidation density exceeds available liquidity
            for i, price in enumerate(price_bins):
                if long_density_smooth[i] > 0:
                    # Find closest bid price
                    bid_idx = np.searchsorted(bid_prices, price)
                    if bid_idx < len(bid_prices) and bid_idx > 0:
                        nearby_liquidity = bid_sizes[bid_idx-1] * current_price
                        liq_value = long_density_smooth[i] * scale_factor * current_price
                        
                        if liq_value > nearby_liquidity * 0.5:  # Liquidation exceeds 50% of available liquidity
                            absorption_ratio = liq_value / max(nearby_liquidity, 1)
                            thin_spots.append({
                                "price": price,
                                "direction": "downward",
                                "liquidation_value": liq_value,
                                "available_liquidity": nearby_liquidity,
                                "absorption_ratio": absorption_ratio
                            })
                            
                if short_density_smooth[i] > 0:
                    # Find closest ask price
                    ask_idx = np.searchsorted(ask_prices, price)
                    if ask_idx < len(ask_prices):
                        nearby_liquidity = ask_sizes[ask_idx] * current_price
                        liq_value = short_density_smooth[i] * scale_factor * current_price
                        
                        if liq_value > nearby_liquidity * 0.5:  # Liquidation exceeds 50% of available liquidity
                            absorption_ratio = liq_value / max(nearby_liquidity, 1)
                            thin_spots.append({
                                "price": price,
                                "direction": "upward",
                                "liquidation_value": liq_value,
                                "available_liquidity": nearby_liquidity,
                                "absorption_ratio": absorption_ratio
                            })
            
            # Sort and mark top thin spots
            if thin_spots:
                thin_spots.sort(key=lambda x: x["absorption_ratio"], reverse=True)
                for spot in thin_spots[:3]:  # Top 3 thin spots
                    price = spot["price"]
                    direction = spot["direction"]
                    ratio = spot["absorption_ratio"]
                    
                    color = '#D32F2F' if direction == 'downward' else '#388E3C'
                    marker = 'v' if direction == 'downward' else '^'
                    
                    ax3.scatter(price, spot["liquidation_value"], 
                              marker=marker, s=100, color=color, edgecolor='black', zorder=10)
                    
                    ax3.annotate(f"Thin Spot\nRatio: {ratio:.1f}x",
                                xy=(price, spot["liquidation_value"]),
                                xytext=(10, 10 if direction == 'upward' else -30), textcoords='offset points',
                                arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=.2", color=color),
                                bbox=dict(boxstyle="round,pad=0.3", fc='white', ec=color, alpha=0.7))
            
            # Add labels and legend
            ax3.set_title("Orderbook Depth vs Liquidation Density", fontsize=16, fontweight='bold')
            ax3.set_xlabel("Price ($)", fontsize=12)
            ax3.set_ylabel("Size", fontsize=12)
            ax3.legend(loc='upper right', fontsize=10)
            ax3.grid(True, alpha=0.3)
            
        except Exception as e:
            print(f"Error plotting orderbook data: {e}")
            ax3.text(0.5, 0.5, "Orderbook plotting error", ha='center', va='center', fontsize=14)
    else:
        ax3.text(0.5, 0.5, "Orderbook data not available", ha='center', va='center', fontsize=14)
    
    # Format x-axis labels as currency
    for ax in axes:
        ax.xaxis.set_major_formatter('${x:.2f}')
    
    # Set a common xlim for all plots
    for ax in axes:
        ax.set_xlim(min_price * 0.995, max_price * 1.005)
    
    # Add timestamp and analysis info
    fig.text(0.5, 0.01, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Price: ${current_price:.2f}", 
             ha='center', fontsize=10)
    
    if top_opportunity:
        trade_direction = top_opportunity['target_side'].upper()
        fig.text(0.5, 0.03, f"Top Trading Opportunity: {trade_direction} at ${top_opportunity['ideal_entry']:.2f} • "
                 f"Score: {top_opportunity['potential_score']:.2f} • "
                 f"Market Impact: {top_opportunity['market_impact']:.2f}", 
                 ha='center', fontsize=12, fontweight='bold',
                 bbox=dict(boxstyle="round,pad=0.3", fc='#E3F2FD', ec='#1565C0', alpha=0.8))
    
    # Save the visualization
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"{asset}_enhanced_liquidation_cascade_{timestamp}.png")
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"Enhanced visualization saved to: {output_path}")
    plt.close(fig)
    
    # Return analysis results
    return {
        "asset": asset,
        "current_price": current_price,
        "dynamic_threshold": dynamic_threshold,
        "long_clusters": long_clusters,
        "short_clusters": short_clusters,
        "top_opportunity": top_opportunity,
        "thin_spots": thin_spots if 'thin_spots' in locals() else [],
        "visualization_path": output_path
    }