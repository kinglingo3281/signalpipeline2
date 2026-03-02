#!/usr/bin/env python
"""
Actionable Entry Visualization Module
----------------------------------
Visualizes actionable entry points based on liquidation clusters
and generates trading signals.
"""

import os
import sys
from datetime import datetime

# Add parent directory to path to allow imports from root after moving to visualization/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Define project root for consistent file paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def visualize_actionable_entries(asset, liquidation_analysis, orderbook, clusters):
    """
    Creates a visualization specifically highlighting actionable entry points
    based on liquidation clusters
    
    Args:
        asset: Asset symbol
        liquidation_analysis: Output from analyze_asset_liquidations
        orderbook: Dictionary with order book data
        clusters: Output from identify_liquidation_clusters
    """
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.patches import Rectangle
        import os
        from datetime import datetime
    except ImportError:
        print("Error: matplotlib is required for visualization")
        return
    
    # Create output directory
    viz_dir = os.path.join("data", "actionable_entries")
    os.makedirs(viz_dir, exist_ok=True)
    
    # Extract key data
    current_price = liquidation_analysis["current_price"]
    
    # Create figure
    fig, ax = plt.subplots(figsize=(14, 10))
    
    # Set title and labels
    title = f"{asset} Actionable Entry Points - {datetime.now().strftime('%Y-%m-%d')}"
    ax.set_title(title, fontsize=16, fontweight='bold')
    ax.set_xlabel('Price ($)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Liquidation Size', fontsize=12, fontweight='bold')
    
    # Extract and sort price bins for better visualization
    price_bins = sorted(liquidation_analysis["price_bins"])
    
    # Define price range for plotting (focus on actionable range)
    proximity = 0.10  # Show 10% above and below current price
    min_price = current_price * (1 - proximity)
    max_price = current_price * (1 + proximity)
    
    # Filter price bins within our range
    visible_bins = [p for p in price_bins if min_price <= p <= max_price]
    
    # Get long and short liquidation values
    long_values = [liquidation_analysis["long_liquidations"][p]["value"] for p in visible_bins]
    short_values = [liquidation_analysis["short_liquidations"][p]["value"] for p in visible_bins]
    
    # Plot liquidations as bars
    bar_width = (visible_bins[-1] - visible_bins[0]) / len(visible_bins) * 0.35
    ax.bar(visible_bins, long_values, width=bar_width, color='#D32F2F', alpha=0.7, label='Long Liquidations')
    ax.bar(visible_bins, short_values, width=bar_width, color='#388E3C', alpha=0.7, label='Short Liquidations', bottom=long_values)
    
    # Add order book overlay if available
    if orderbook and "bids" in orderbook and "asks" in orderbook:
        # Create twin axis for liquidity
        ax2 = ax.twinx()
        
        # Extract bid and ask data
        bid_prices = [bid[0] for bid in orderbook["bids"] if min_price <= bid[0] <= max_price]
        bid_sizes = [bid[1] for bid in orderbook["bids"] if min_price <= bid[0] <= max_price]
        ask_prices = [ask[0] for ask in orderbook["asks"] if min_price <= ask[0] <= max_price]
        ask_sizes = [ask[1] for ask in orderbook["asks"] if min_price <= ask[0] <= max_price]
        
        # Plot liquidity as lines
        if bid_prices and bid_sizes:
            ax2.plot(bid_prices, bid_sizes, color='blue', alpha=0.5, label='Bid Liquidity')
        if ask_prices and ask_sizes:
            ax2.plot(ask_prices, ask_sizes, color='purple', alpha=0.5, label='Ask Liquidity')
            
        ax2.set_ylabel('Orderbook Depth', fontsize=12)
        
        # Add legends for both axes
        lines1, labels1 = ax.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax2.legend(lines1 + lines2, labels1 + labels2, loc='upper right')
    else:
        ax.legend(loc='upper right')
    
    # Add current price line
    ax.axvline(x=current_price, color='black', linestyle='--', linewidth=2, label='Current Price')
    
    # Highlight actionable cluster zones
    if clusters and "clusters" in clusters and clusters["clusters"]:
        for i, cluster in enumerate(clusters["clusters"][:3]):  # Show top 3 opportunities
            direction = cluster["direction"]
            target_side = cluster["target_side"]
            prices = cluster["prices"]
            total_value = cluster["total_value"]
            ideal_entry = cluster.get("ideal_entry")
            target_price = cluster.get("target_price")
            risk_reward = cluster.get("risk_reward", 0)
            
            if not prices or ideal_entry is None:
                continue
                
            # Choose colors based on direction
            if direction == "long":
                color = '#D32F2F'  # Red for long liquidations (we short these)
                text_pos = 'bottom'
            else:
                color = '#388E3C'  # Green for short liquidations (we long these)
                text_pos = 'top'
            
            # Calculate x-range for highlighting
            min_x = min(prices)
            max_x = max(prices)
            width = max_x - min_x
            
            # Highlight the cluster range
            ax.axvspan(min_x, max_x, alpha=0.2, color=color)
            
            # Mark ideal entry price
            ax.axvline(x=ideal_entry, color=color, linestyle=':', linewidth=2)
            
            # Mark target price if available
            if target_price:
                ax.axvline(x=target_price, color=color, linestyle='-.', linewidth=2)
                
                # Draw arrow showing expected move
                arrow_y = ax.get_ylim()[1] * 0.8
                ax.annotate('', 
                    xy=(target_price, arrow_y), 
                    xytext=(ideal_entry, arrow_y),
                    arrowprops=dict(arrowstyle="<|-|>", color=color, lw=2)
                )
            
            # Add annotation for the cluster
            arrow_y = ax.get_ylim()[1] * (0.7 - i*0.1)
            ax.annotate(
                f"Opportunity #{i+1}: {target_side.upper()} Entry\n"
                f"Size: ${total_value:.2f}, R/R: {risk_reward:.2f}\n"
                f"Entry: ${ideal_entry:.2f}, Target: ${target_price:.2f}",
                xy=(ideal_entry, arrow_y),
                xytext=(20, 20) if direction == "long" else (-20, -20),
                textcoords="offset points",
                ha='left' if direction == "long" else 'right',
                va=text_pos,
                bbox=dict(boxstyle="round,pad=0.5", fc="white", ec=color, alpha=0.8),
                arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=.2", color=color)
            )
    
    # Add explanation box
    explanation = (
        "TRADING GUIDE:\n"
        "- RED zones: Potential short entries (to catch long liquidations)\n"
        "- GREEN zones: Potential long entries (to catch short liquidations)\n"
        "- Dotted lines: Ideal entry prices\n"
        "- Dash-dot lines: Target prices\n"
        "- Arrows show expected price movement\n"
        "- Higher R/R and larger size = better opportunity"
    )
    
    # Add explanation box at bottom left
    plt.figtext(0.02, 0.02, explanation, fontsize=10,
               bbox=dict(facecolor='white', alpha=0.8, boxstyle='round,pad=0.5', edgecolor='gray'))
    
    # Save the figure
    filename = f"{viz_dir}/{asset}_actionable_entries_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"Saved actionable entry visualization to {filename}")
    
    # Close the figure
    plt.close(fig)


def integrate_with_trading_chart(asset, clusters, current_price, output_dir=None):
    """
    Integrates liquidation analysis with enhanced trading chart visualization
    that properly maintains technical indicators.
    
    Args:
        asset: Asset symbol
        clusters: Dictionary with liquidation cluster data
        current_price: Current price of the asset
        output_dir: Directory to save visualizations
        
    Returns:
        Path to saved visualization
    """
    try:
        from trading_view_integration import integrate_liquidation_with_trading_chart
        import pandas as pd
        
        # Create a basic positions dataframe if not available
        positions_df = pd.DataFrame()
        
        # Call the integration function
        chart_path = integrate_liquidation_with_trading_chart(
            asset=asset, 
            positions_df=positions_df, 
            liquidation_clusters=clusters, 
            current_price=current_price, 
            output_dir=output_dir
        )
        
        return chart_path
        
    except ImportError as e:
        print(f"Error importing trading_view_integration: {e}")
        print("Make sure to create and implement trading_view_integration.py")
        return None
    except Exception as e:
        print(f"Error integrating with trading chart: {e}")
        return None


def create_enhanced_actionable_visualization(asset, positions_df, current_price, orderbook=None, 
                                            liquidation_clusters=None, output_dir=None):
    """
    Creates an enhanced visualization that combines liquidation analysis with
    technical indicators to provide actionable trading signals.
    
    Args:
        asset: Asset symbol
        positions_df: DataFrame with position data
        current_price: Current asset price
        orderbook: Optional orderbook data
        liquidation_clusters: Optional pre-calculated liquidation clusters
        output_dir: Directory to save visualizations
        
    Returns:
        Dictionary with analysis results and visualization paths
    """
    import os
    from datetime import datetime
    import pandas as pd
    import numpy as np
    
    # Set up output directory
    if not output_dir:
        output_dir = os.path.join("data", "visualizations")
    os.makedirs(output_dir, exist_ok=True)
    
    # If no clusters provided, generate them
    if liquidation_clusters is None:
        try:
            from daily_trading_analysis import calculate_liquidation_clusters
            from cluster_analysis import identify_liquidation_clusters
            
            # Extract analysis data from positions
            liquidation_analysis = {
                "asset": asset,
                "current_price": current_price,
                "positions": positions_df.to_dict('records') if isinstance(positions_df, pd.DataFrame) else []
            }
            
            # Generate clusters
            liquidation_clusters = identify_liquidation_clusters(
                asset=asset,
                liquidation_analysis=liquidation_analysis,
                orderbook=orderbook
            )
            
            print(f"Generated {len(liquidation_clusters.get('clusters', []))} liquidation clusters")
        except Exception as e:
            print(f"Error generating liquidation clusters: {e}")
            liquidation_clusters = {"clusters": []}
    
    # Use the trading chart integration
    chart_path = integrate_with_trading_chart(
        asset=asset,
        clusters=liquidation_clusters,
        current_price=current_price,
        output_dir=output_dir
    )
    
    # Create actionable entry points visualization
    if orderbook is not None:
        try:
            # Extract analysis data from positions
            liquidation_analysis = {
                "asset": asset,
                "current_price": current_price,
                "positions": positions_df.to_dict('records') if isinstance(positions_df, pd.DataFrame) else []
            }
            
            # Create the basic visualization
            visualize_actionable_entries(
                asset=asset,
                liquidation_analysis=liquidation_analysis,
                orderbook=orderbook,
                clusters=liquidation_clusters
            )
        except Exception as e:
            print(f"Error creating actionable entry visualization: {e}")
    
    # Return results
    result = {
        "asset": asset,
        "current_price": current_price,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "clusters": liquidation_clusters.get("clusters", []),
        "visualization_path": chart_path
    }
    
    # Add trading signals if available
    signals = extract_trading_signals_from_clusters(liquidation_clusters, current_price)
    if signals:
        result.update(signals)
    
    return result


def extract_trading_signals_from_clusters(clusters, current_price):
    """
    Extract actionable trading signals from liquidation clusters.
    
    Args:
        clusters: Dictionary with liquidation cluster data
        current_price: Current price of the asset
        
    Returns:
        Dictionary with trading signals
    """
    if not clusters or "clusters" not in clusters:
        return {}
    
    # Find the most significant long and short liquidation clusters
    long_clusters = [c for c in clusters["clusters"] if c.get("direction") == "downward"]
    short_clusters = [c for c in clusters["clusters"] if c.get("direction") == "upward"]
    
    # Sort by market impact and size
    long_clusters.sort(key=lambda c: (c.get("market_impact", 0), c.get("size", 0)), reverse=True)
    short_clusters.sort(key=lambda c: (c.get("market_impact", 0), c.get("size", 0)), reverse=True)
    
    signals = {}
    
    # Generate short signal (for long liquidations)
    if long_clusters and long_clusters[0].get("market_impact", 0) > 0.5:
        top_long = long_clusters[0]
        trigger_price = top_long.get("price", 0) * 1.01  # Entry just above liquidation level
        
        # Only suggest if within reasonable range of current price (5%)
        if 0.95 <= trigger_price / current_price <= 1.05:
            target_price = top_long.get("price", 0) * 0.97  # Target 3% below liquidation
            stop_price = trigger_price * 1.02  # Stop 2% above entry
            
            # Calculate risk/reward
            risk = (stop_price - trigger_price) / trigger_price * 100
            reward = (trigger_price - target_price) / trigger_price * 100
            risk_reward = reward / risk if risk > 0 else 0
            
            signals["short_signal"] = {
                "entry": trigger_price,
                "target": target_price,
                "stop": stop_price,
                "risk_reward": risk_reward,
                "impact": top_long.get("market_impact", 0),
                "confidence": min(0.9, top_long.get("market_impact", 0) + 0.2)
            }
    
    # Generate long signal (for short liquidations)
    if short_clusters and short_clusters[0].get("market_impact", 0) > 0.5:
        top_short = short_clusters[0]
        trigger_price = top_short.get("price", 0) * 0.99  # Entry just below liquidation level
        
        # Only suggest if within reasonable range of current price (5%)
        if 0.95 <= trigger_price / current_price <= 1.05:
            target_price = top_short.get("price", 0) * 1.03  # Target 3% above liquidation
            stop_price = trigger_price * 0.98  # Stop 2% below entry
            
            # Calculate risk/reward
            risk = (trigger_price - stop_price) / trigger_price * 100
            reward = (target_price - trigger_price) / trigger_price * 100
            risk_reward = reward / risk if risk > 0 else 0
            
            signals["long_signal"] = {
                "entry": trigger_price,
                "target": target_price,
                "stop": stop_price,
                "risk_reward": risk_reward,
                "impact": top_short.get("market_impact", 0),
                "confidence": min(0.9, top_short.get("market_impact", 0) + 0.2)
            }
    
    return signals