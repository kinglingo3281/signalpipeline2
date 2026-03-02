"""
Integration module for advanced trading chart visualizations with technical indicators
that persist across toggles, zooms, and pans.

This module enhances the TradingChart component by providing:
1. Persistent technical indicators that maintain state
2. Proper price axis alignment
3. Preserved indicator state during zoom/pan operations
4. Integration with liquidation data for advanced visualization
"""

import os
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import matplotlib.dates as mdates
from matplotlib.ticker import MultipleLocator
import matplotlib.gridspec as gridspec
import matplotlib.colors as mcolors
from matplotlib.patches import Rectangle

# Try to import optional visualization enhancements
try:
    import mplfinance as mpf
    MPF_AVAILABLE = True
except ImportError:
    MPF_AVAILABLE = False
    print("Warning: mplfinance not available. Using basic plotting instead.")

class TradingChartIntegration:
    """
    Handles integration between liquidation analysis and chart visualizations
    with persistent technical indicators.
    """
    
    def __init__(self, price_data=None, liquidation_data=None, output_dir=None):
        """
        Initialize the trading chart integration.
        
        Args:
            price_data: DataFrame with OHLCV data
            liquidation_data: DataFrame or dict with liquidation levels
            output_dir: Directory to save visualizations
        """
        self.price_data = price_data
        self.liquidation_data = liquidation_data
        
        # Set up output directory
        if not output_dir:
            output_dir = os.path.join("data", "visualizations")
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Indicator cache to maintain persistence
        self.indicator_cache = {}
        
        # State tracking for zoom/pan operations
        self.view_state = {
            "x_range": None,
            "y_range": None,
            "indicators": []
        }
    
    def load_price_data(self, symbol, timeframe="1h", limit=100):
        """
        Load price data for the specified symbol and timeframe.
        Placeholder for actual API integration.
        
        Args:
            symbol: Trading pair symbol
            timeframe: Chart timeframe (e.g., "1m", "5m", "1h", "1d")
            limit: Number of candles to retrieve
        """
        try:
            # This would be replaced with actual API call in production
            # For demonstration, we'll create mock data
            now = datetime.now()
            dates = [now - timedelta(hours=i) for i in range(limit)]
            dates.reverse()
            
            # Create mock OHLCV data
            seed_price = 1000  # Starting price
            volatility = 0.02  # Price volatility (2%)
            
            ohlc_data = []
            current_price = seed_price
            
            for _ in range(limit):
                # Simulate price movement
                price_change = current_price * volatility * (np.random.random() * 2 - 1)
                open_price = current_price
                close_price = current_price + price_change
                high_price = max(open_price, close_price) * (1 + np.random.random() * 0.005)
                low_price = min(open_price, close_price) * (1 - np.random.random() * 0.005)
                volume = np.random.random() * 1000 + 100
                
                ohlc_data.append([open_price, high_price, low_price, close_price, volume])
                current_price = close_price
            
            # Create DataFrame
            self.price_data = pd.DataFrame(
                ohlc_data, 
                index=dates, 
                columns=["open", "high", "low", "close", "volume"]
            )
            
            print(f"Loaded {len(self.price_data)} candles for {symbol} ({timeframe})")
            return self.price_data
            
        except Exception as e:
            print(f"Error loading price data: {e}")
            return None
    
    def add_technical_indicator(self, indicator_type, params=None):
        """
        Add a technical indicator to the chart.
        
        Args:
            indicator_type: Type of indicator (e.g., "ma", "ema", "bbands", "rsi")
            params: Dictionary of parameters for the indicator
            
        Returns:
            Indicator data
        """
        if self.price_data is None:
            print("Error: No price data available for indicators")
            return None
        
        # Set default params if none provided
        if params is None:
            params = {}
            
        # Check if indicator is already in cache
        indicator_key = f"{indicator_type}_{json.dumps(params, sort_keys=True)}"
        if indicator_key in self.indicator_cache:
            print(f"Using cached {indicator_type} indicator")
            return self.indicator_cache[indicator_key]
        
        # Calculate indicators
        if indicator_type.lower() == "ma":
            # Simple Moving Average
            period = params.get("period", 20)
            indicator_data = self.price_data["close"].rolling(window=period).mean()
            indicator_result = {"type": "ma", "period": period, "data": indicator_data}
            
        elif indicator_type.lower() == "ema":
            # Exponential Moving Average
            period = params.get("period", 20)
            indicator_data = self.price_data["close"].ewm(span=period, adjust=False).mean()
            indicator_result = {"type": "ema", "period": period, "data": indicator_data}
            
        elif indicator_type.lower() == "bbands":
            # Bollinger Bands
            period = params.get("period", 20)
            std_dev = params.get("std_dev", 2)
            
            middle_band = self.price_data["close"].rolling(window=period).mean()
            std = self.price_data["close"].rolling(window=period).std()
            upper_band = middle_band + (std * std_dev)
            lower_band = middle_band - (std * std_dev)
            
            indicator_result = {
                "type": "bbands", 
                "period": period,
                "std_dev": std_dev,
                "middle": middle_band,
                "upper": upper_band,
                "lower": lower_band
            }
            
        elif indicator_type.lower() == "rsi":
            # Relative Strength Index
            period = params.get("period", 14)
            delta = self.price_data["close"].diff()
            
            gain = delta.copy()
            loss = delta.copy()
            gain[gain < 0] = 0
            loss[loss > 0] = 0
            loss = abs(loss)
            
            avg_gain = gain.rolling(window=period).mean()
            avg_loss = loss.rolling(window=period).mean()
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            indicator_result = {"type": "rsi", "period": period, "data": rsi}
            
        else:
            print(f"Unsupported indicator type: {indicator_type}")
            return None
        
        # Cache the indicator
        self.indicator_cache[indicator_key] = indicator_result
        
        # Track in view state
        if indicator_type not in self.view_state["indicators"]:
            self.view_state["indicators"].append(indicator_type)
            
        return indicator_result
    
    def _create_chart_with_indicators(self, title, entry_point=None, stop_loss=None, take_profit=None):
        """
        Create a trading chart with candlesticks, volume, and technical indicators.
        
        Args:
            title: Chart title
            entry_point: Optional entry price for annotation
            stop_loss: Optional stop loss price for annotation
            take_profit: Optional take profit price for annotation
            
        Returns:
            Figure and axis objects
        """
        if self.price_data is None or len(self.price_data) == 0:
            print("Error: No price data available for chart")
            return None, None
        
        # Try to use mplfinance if available for better visualization
        if MPF_AVAILABLE:
            # Create a figure with 2 rows (price and volume)
            fig = plt.figure(figsize=(14, 10))
            gs = gridspec.GridSpec(2, 1, height_ratios=[3, 1])
            
            ax1 = plt.subplot(gs[0])
            ax2 = plt.subplot(gs[1], sharex=ax1)
            
            # Convert to mplfinance format
            ohlc_data = self.price_data.copy()
            
            # Plot candlesticks
            mpf.plot(
                ohlc_data,
                type='candle',
                style='charles',
                ax=ax1,
                volume=ax2,
                ylabel='Price',
                ylabel_lower='Volume',
                datetime_format='%Y-%m-%d %H:%M',
                show_nontrading=True
            )
            
        else:
            # Fallback to matplotlib
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={'height_ratios': [3, 1]}, sharex=True)
            
            # Format dates for x-axis
            dates = mdates.date2num(self.price_data.index.to_pydatetime())
            
            # Plot candlesticks
            width = 0.6 / len(self.price_data) * 30  # Adjust candle width
            
            up = self.price_data[self.price_data.close >= self.price_data.open]
            down = self.price_data[self.price_data.close < self.price_data.open]
            
            # Plot up candles
            for i, row in up.iterrows():
                date_idx = mdates.date2num(i.to_pydatetime())
                ax1.bar(
                    date_idx, 
                    row['high'] - row['low'], 
                    width, 
                    bottom=row['low'], 
                    color='green',
                    alpha=0.5
                )
                ax1.bar(
                    date_idx, 
                    row['close'] - row['open'], 
                    width * 0.8, 
                    bottom=row['open'], 
                    color='green'
                )
            
            # Plot down candles
            for i, row in down.iterrows():
                date_idx = mdates.date2num(i.to_pydatetime())
                ax1.bar(
                    date_idx, 
                    row['high'] - row['low'], 
                    width, 
                    bottom=row['low'], 
                    color='red',
                    alpha=0.5
                )
                ax1.bar(
                    date_idx, 
                    row['open'] - row['close'], 
                    width * 0.8, 
                    bottom=row['close'], 
                    color='red'
                )
            
            # Plot volume
            volume_colors = ['green' if close >= open else 'red' 
                            for open, close in zip(self.price_data['open'], self.price_data['close'])]
            
            ax2.bar(dates, self.price_data['volume'], width=width, color=volume_colors, alpha=0.7)
            
            # Format x-axis for dates
            date_format = mdates.DateFormatter('%Y-%m-%d %H:%M')
            ax1.xaxis.set_major_formatter(date_format)
            ax2.xaxis.set_major_formatter(date_format)
        
        # Add title
        fig.suptitle(title, fontsize=16)
        
        # Set labels
        ax1.set_ylabel('Price')
        ax2.set_ylabel('Volume')
        ax2.set_xlabel('Date')
        
        # Add entry/sl/tp annotations if provided
        if entry_point:
            price_range = self.price_data['high'].max() - self.price_data['low'].min()
            
            # Add entry point
            ax1.axhline(y=entry_point, color='blue', linestyle='--', alpha=0.7, label=f'Entry: {entry_point}')
            
            # Add stop loss if provided
            if stop_loss:
                ax1.axhline(y=stop_loss, color='red', linestyle='--', alpha=0.7, label=f'Stop: {stop_loss}')
                
                # Calculate and display potential loss
                loss_pct = (stop_loss - entry_point) / entry_point * 100
                ax1.annotate(
                    f'{loss_pct:.2f}%', 
                    xy=(dates[-1], (entry_point + stop_loss) / 2),
                    xytext=(5, 0),
                    textcoords='offset points',
                    color='red'
                )
                
            # Add take profit if provided
            if take_profit:
                ax1.axhline(y=take_profit, color='green', linestyle='--', alpha=0.7, label=f'Target: {take_profit}')
                
                # Calculate and display potential profit
                profit_pct = (take_profit - entry_point) / entry_point * 100
                ax1.annotate(
                    f'+{profit_pct:.2f}%', 
                    xy=(dates[-1], (entry_point + take_profit) / 2),
                    xytext=(5, 0),
                    textcoords='offset points',
                    color='green'
                )
        
        # Add any cached indicators
        for indicator_type in self.view_state["indicators"]:
            # Find indicator in cache
            for key, indicator in self.indicator_cache.items():
                if key.startswith(indicator_type):
                    self._add_indicator_to_chart(ax1, indicator)
        
        # Apply custom styling
        plt.style.use('dark_background')
        ax1.grid(alpha=0.3)
        ax2.grid(alpha=0.3)
        
        # Apply view state (zoom/pan) if available
        if self.view_state["x_range"] is not None:
            ax1.set_xlim(self.view_state["x_range"])
            
        if self.view_state["y_range"] is not None:
            ax1.set_ylim(self.view_state["y_range"])
            
        # Add legend
        ax1.legend(loc='upper left')
        
        plt.tight_layout()
        return fig, (ax1, ax2)
    
    def _add_indicator_to_chart(self, ax, indicator):
        """
        Add technical indicator to chart.
        
        Args:
            ax: Matplotlib axis
            indicator: Indicator data dictionary
        """
        if indicator["type"] == "ma" or indicator["type"] == "ema":
            period = indicator["period"]
            indicator_name = "MA" if indicator["type"] == "ma" else "EMA"
            ax.plot(
                self.price_data.index, 
                indicator["data"], 
                label=f'{indicator_name}({period})',
                alpha=0.7,
                linewidth=1.5
            )
            
        elif indicator["type"] == "bbands":
            period = indicator["period"]
            std_dev = indicator["std_dev"]
            
            # Plot middle band
            ax.plot(
                self.price_data.index, 
                indicator["middle"], 
                label=f'BB Middle({period})',
                color='white',
                alpha=0.7,
                linewidth=1
            )
            
            # Plot upper and lower bands
            ax.plot(
                self.price_data.index, 
                indicator["upper"], 
                label=f'BB Upper({period}, {std_dev})',
                color='cyan',
                alpha=0.7,
                linewidth=1
            )
            
            ax.plot(
                self.price_data.index, 
                indicator["lower"], 
                label=f'BB Lower({period}, {std_dev})',
                color='cyan',
                alpha=0.7,
                linewidth=1
            )
            
            # Fill the area between bands
            ax.fill_between(
                self.price_data.index,
                indicator["upper"],
                indicator["lower"],
                color='cyan',
                alpha=0.1
            )
            
        elif indicator["type"] == "rsi":
            # Create a secondary axis for RSI
            ax2 = ax.twinx()
            
            # Plot RSI
            ax2.plot(
                self.price_data.index, 
                indicator["data"], 
                label=f'RSI({indicator["period"]})',
                color='magenta',
                alpha=0.7,
                linewidth=1
            )
            
            # Add overbought/oversold levels
            ax2.axhline(y=70, color='red', linestyle='--', alpha=0.3)
            ax2.axhline(y=30, color='green', linestyle='--', alpha=0.3)
            
            # Set y-axis range for RSI
            ax2.set_ylim(0, 100)
            ax2.set_ylabel('RSI')
            
            # Add RSI legend
            lines, labels = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines + lines2, labels + labels2, loc='upper left')
    
    def create_liquidation_trading_chart(self, asset, liquidation_clusters, current_price):
        """
        Create a trading chart with liquidation levels highlighted.
        
        Args:
            asset: Asset symbol
            liquidation_clusters: Liquidation clusters data
            current_price: Current price of the asset
            
        Returns:
            Path to saved chart image
        """
        if self.price_data is None:
            # Try to load mock data if none provided
            self.load_price_data(asset)
            
        # Create base chart with candlesticks and volume
        title = f"{asset} Price Chart with Liquidation Levels"
        fig, (ax1, _) = self._create_chart_with_indicators(title)
        
        if fig is None:
            return None
            
        # Add liquidation levels as horizontal lines/zones
        if liquidation_clusters:
            # Extract cluster information
            for i, cluster in enumerate(liquidation_clusters.get('clusters', [])):
                price_level = cluster.get('price', 0)
                size = cluster.get('size', 0)
                impact = cluster.get('market_impact', 0)
                direction = cluster.get('direction', 'unknown')
                
                # Determine color and style based on direction and impact
                if direction == 'downward':
                    color = 'red'
                    label = f"Long Liq. ${price_level:.2f} (${size:,.0f})"
                elif direction == 'upward':
                    color = 'green'
                    label = f"Short Liq. ${price_level:.2f} (${size:,.0f})"
                else:
                    color = 'yellow'
                    label = f"Mixed Liq. ${price_level:.2f} (${size:,.0f})"
                    
                # Adjust alpha based on impact
                alpha = min(0.8, max(0.3, impact))
                
                # Draw horizontal line at liquidation level
                ax1.axhline(
                    y=price_level, 
                    color=color, 
                    linestyle='-', 
                    alpha=alpha, 
                    linewidth=2,
                    label=label
                )
                
                # Add annotation for significant liquidation levels (high impact)
                if impact > 0.5:
                    # Add rectangle to highlight high-impact zone
                    y_range = ax1.get_ylim()
                    height = (y_range[1] - y_range[0]) * 0.03  # 3% of the chart height
                    
                    rect = Rectangle(
                        (min(self.price_data.index), price_level - height/2),
                        max(self.price_data.index) - min(self.price_data.index),
                        height,
                        color=color,
                        alpha=0.3
                    )
                    ax1.add_patch(rect)
                    
                    # Add annotation with details
                    ax1.annotate(
                        f"Impact: {impact:.2f}\nSize: ${size:,.0f}",
                        xy=(self.price_data.index[-1], price_level),
                        xytext=(10, 0),
                        textcoords="offset points",
                        color=color,
                        fontsize=9,
                        bbox=dict(
                            boxstyle="round,pad=0.3", 
                            fc='black', 
                            ec=color, 
                            alpha=0.7
                        )
                    )
        
        # Add technical indicators
        # Default indicators - can be customized
        self.add_technical_indicator("ma", {"period": 20})
        self.add_technical_indicator("ma", {"period": 50})
        self.add_technical_indicator("bbands", {"period": 20, "std_dev": 2})
        
        # Add current price reference line
        if current_price:
            ax1.axhline(
                y=current_price,
                color='white',
                linestyle='-.',
                alpha=0.7,
                linewidth=1,
                label=f"Current: ${current_price:.2f}"
            )
        
        # Update legend
        ax1.legend(loc='upper left', fontsize=9)
        
        # Save figure
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = self.output_dir.replace('/', os.sep).replace('\\', os.sep)
        os.makedirs(output_dir, exist_ok=True)  # Create directory if it doesn't exist
        
        # Fix the filename construction to use proper path joining
        filename = os.path.join(output_dir, f"{asset.replace('/', '_')}_trading_chart_{timestamp}.png")
        plt.savefig(filename, dpi=150, bbox_inches="tight")
        plt.close(fig)
        
        print(f"Trading chart saved to {filename}")
        return filename
    
    def create_liquidation_cascade_heatmap(self, asset, liquidation_clusters, current_price):
        """
        Create a trading chart that shows liquidation levels as a heatmap overlay.
        
        Args:
            asset: Asset symbol
            liquidation_clusters: Liquidation clusters data
            current_price: Current price of the asset
            
        Returns:
            Path to saved chart image
        """
        if self.price_data is None:
            # Try to load mock data if none provided
            self.load_price_data(asset)
            
        # Create base chart with candlesticks and volume
        title = f"{asset} Liquidation Cascade Heatmap"
        fig, (ax1, ax2) = self._create_chart_with_indicators(title)
        
        if fig is None:
            return None
        
        # Add liquidation heatmap overlay
        if liquidation_clusters and "clusters" in liquidation_clusters:
            import matplotlib.patches as patches
            import matplotlib.colors as mcolors
            
            # Get y-axis range
            y_min, y_max = ax1.get_ylim()
            height_unit = (y_max - y_min) * 0.01  # 1% of the chart height
            
            # Create colormaps for long and short liquidations
            cmap_long = mcolors.LinearSegmentedColormap.from_list(
                "long_liquidations", ["#FF9999", "#FF0000"]
            )
            cmap_short = mcolors.LinearSegmentedColormap.from_list(
                "short_liquidations", ["#99FF99", "#00AA00"]
            )
            
            # Group clusters by direction
            long_clusters = [c for c in liquidation_clusters["clusters"] 
                           if c.get("direction") == "downward"]
            short_clusters = [c for c in liquidation_clusters["clusters"] 
                            if c.get("direction") == "upward"]
            
            # Add long liquidation zones (downward cascades)
            for cluster in long_clusters:
                price = cluster.get("price", 0)
                impact = cluster.get("market_impact", 0)
                size = cluster.get("size", 0)
                
                # Skip if outside the chart range
                if price < y_min or price > y_max:
                    continue
                
                # Scale height by impact and size
                height = height_unit * (1 + 10 * impact)
                
                # Color based on impact
                color = cmap_long(min(1.0, impact * 1.5))
                
                # Create rectangle
                x_min, x_max = ax1.get_xlim()
                rect = patches.Rectangle(
                    (x_min, price - height/2),
                    x_max - x_min,
                    height,
                    color=color,
                    alpha=0.6,
                    zorder=1
                )
                ax1.add_patch(rect)
                
                # Add annotation for significant liquidation levels
                if impact > 0.5:
                    ax1.annotate(
                        f"Long Liq: ${price:.2f}\nSize: ${size:,.0f}",
                        xy=(self.price_data.index[-1], price),
                        xytext=(10, 0),
                        textcoords="offset points",
                        color="white",
                        fontsize=8,
                        bbox=dict(
                            boxstyle="round,pad=0.2", 
                            fc=color, 
                            alpha=0.8
                        )
                    )
            
            # Add short liquidation zones (upward cascades)
            for cluster in short_clusters:
                price = cluster.get("price", 0)
                impact = cluster.get("market_impact", 0)
                size = cluster.get("size", 0)
                
                # Skip if outside the chart range
                if price < y_min or price > y_max:
                    continue
                
                # Scale height by impact and size
                height = height_unit * (1 + 10 * impact)
                
                # Color based on impact
                color = cmap_short(min(1.0, impact * 1.5))
                
                # Create rectangle
                x_min, x_max = ax1.get_xlim()
                rect = patches.Rectangle(
                    (x_min, price - height/2),
                    x_max - x_min,
                    height,
                    color=color,
                    alpha=0.6,
                    zorder=1
                )
                ax1.add_patch(rect)
                
                # Add annotation for significant liquidation levels
                if impact > 0.5:
                    ax1.annotate(
                        f"Short Liq: ${price:.2f}\nSize: ${size:,.0f}",
                        xy=(self.price_data.index[-1], price),
                        xytext=(10, 0),
                        textcoords="offset points",
                        color="white",
                        fontsize=8,
                        bbox=dict(
                            boxstyle="round,pad=0.2", 
                            fc=color, 
                            alpha=0.8
                        )
                    )
        
        # Add current price line
        if current_price:
            ax1.axhline(
                y=current_price,
                color="yellow",
                linestyle="-",
                alpha=0.8,
                linewidth=1,
                label=f"Current: ${current_price:.2f}"
            )
            
        # Update legend
        ax1.legend(loc="upper left", fontsize=9)
        
        # Save figure
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = self.output_dir.replace('/', os.sep).replace('\\', os.sep)
        os.makedirs(output_dir, exist_ok=True)  # Create directory if it doesn't exist
        
        # Fix the filename construction to use proper path joining
        filename = os.path.join(output_dir, f"{asset.replace('/', '_')}_cascade_heatmap_{timestamp}.png")
        plt.savefig(filename, dpi=150, bbox_inches="tight")
        plt.close(fig)
        
        print(f"Liquidation cascade heatmap saved to {filename}")
        return filename
    
    def generate_liquidation_cascade_heatmap(self, asset, liquidation_data, enhanced_clusters=None, 
                                          cascade_probabilities=None, optimized_ranges=None, savepath=None):
        """
        Generate a heatmap visualization showing liquidation clusters and cascade probabilities.
        
        Args:
            asset: Asset symbol
            liquidation_data: Output from analyze_asset_liquidations
            enhanced_clusters: Optional enhanced clustering data
            cascade_probabilities: Optional cascade probability analysis
            optimized_ranges: Optional optimized trading ranges
            savepath: Optional path to save the chart image
        
        Returns:
            Path to saved chart image if successful, None otherwise
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.colors as mcolors
            import matplotlib.cm as cm
            import numpy as np
            import os
            
            # Create figure and subplots
            fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 18), gridspec_kw={'height_ratios': [4, 2, 2]})
            
            current_price = liquidation_data.get("current_price", 0)
            price_bins = liquidation_data.get("price_bins", [])
            long_liquidations = liquidation_data.get("long_liquidations", {})
            short_liquidations = liquidation_data.get("short_liquidations", {})
            
            if not price_bins or not current_price:
                print(f"Warning: Missing data for {asset} heatmap")
                return None
            
            # Sort price bins
            price_bins.sort()
            
            # Extract values for each price bin
            long_values = [long_liquidations.get(price, {}).get("value", 0) for price in price_bins]
            short_values = [short_liquidations.get(price, {}).get("value", 0) for price in price_bins]
            
            # Create normalized arrays for heatmap colors
            max_long_value = max(long_values) if long_values else 1
            max_short_value = max(short_values) if short_values else 1
            
            normalized_long = np.array([val / max_long_value for val in long_values])
            normalized_short = np.array([val / max_short_value for val in short_values])
            
            # Set up colormaps for liquidations
            long_cmap = cm.get_cmap('Reds')
            short_cmap = cm.get_cmap('Blues')
            
            # Create X and Y coordinates for rectangles
            x = np.arange(len(price_bins))
            y_long = np.zeros_like(x)
            y_short = np.ones_like(x)
            width = 0.8
            height = 0.8
            
            # Plot long liquidation heatmap (bottom)
            for i, (price, long_val) in enumerate(zip(price_bins, normalized_long)):
                if long_val > 0:
                    rect = plt.Rectangle((i - width/2, -1), width, height, 
                                        facecolor=long_cmap(long_val), 
                                        alpha=min(1.0, long_val + 0.3),
                                        linewidth=1, edgecolor='darkred')
                    ax1.add_patch(rect)
            
            # Plot short liquidation heatmap (top)
            for i, (price, short_val) in enumerate(zip(price_bins, normalized_short)):
                if short_val > 0:
                    rect = plt.Rectangle((i - width/2, 0), width, height, 
                                        facecolor=short_cmap(short_val),
                                        alpha=min(1.0, short_val + 0.3),
                                        linewidth=1, edgecolor='darkblue')
                    ax1.add_patch(rect)
            
            # Add current price line
            current_price_idx = None
            for i, price in enumerate(price_bins):
                if price >= current_price:
                    current_price_idx = i
                    break
            
            if current_price_idx is not None:
                ax1.axvline(x=current_price_idx, color='green', linestyle='-', linewidth=2, alpha=0.7)
            
            # Mark clusters if available
            if enhanced_clusters and "clusters" in enhanced_clusters:
                for i, cluster in enumerate(enhanced_clusters["clusters"]):
                    direction = cluster.get("direction", "")
                    
                    if direction == "long":
                        y_pos = -0.6  # Position for long clusters (bottom)
                        color = 'darkred'
                    else:
                        y_pos = 0.4   # Position for short clusters (top)
                        color = 'darkblue'
                    
                    # Find center price index
                    center_price = cluster.get("center_price", 0)
                    center_idx = None
                    
                    for j, price in enumerate(price_bins):
                        if price >= center_price:
                            center_idx = j
                            break
                    
                    if center_idx is not None:
                        # Draw cluster marker
                        ax1.plot(center_idx, y_pos, 'o', markersize=10, 
                                color=color, alpha=0.7)
                        
                        # Add cluster label with opportunity score if available
                        opp_score = cluster.get("opportunity_score", 0)
                        if opp_score > 0:
                            ax1.text(center_idx, y_pos + 0.1, 
                                    f"C{i+1}\n{opp_score:.2f}", 
                                    color=color, fontsize=8, ha='center')
            
            # Mark cascade trigger zones if available
            if cascade_probabilities and "trigger_zones" in cascade_probabilities:
                for i, zone in enumerate(cascade_probabilities["trigger_zones"]):
                    # Only show zones with significant probability
                    if zone.get("trigger_probability", 0) < 0.4:
                        continue
                        
                    direction = zone.get("direction", "")
                    base_price = zone.get("base_price", 0)
                    min_price = zone.get("min_price", 0)
                    max_price = zone.get("max_price", 0)
                    
                    # Find indices for zone boundaries
                    min_idx = None
                    max_idx = None
                    
                    for j, price in enumerate(price_bins):
                        if min_idx is None and price >= min_price:
                            min_idx = j
                        if max_idx is None and price >= max_price:
                            max_idx = j
                            break
                    
                    if min_idx is not None and max_idx is not None:
                        # Draw trigger zone highlight
                        if direction == "long":
                            y_pos = -0.9  # Position for long zones (bottom)
                            color = 'maroon'
                        else:
                            y_pos = 0.7   # Position for short zones (top)
                            color = 'midnightblue'
                        
                        # Draw zone span
                        ax1.axvspan(min_idx, max_idx, y_pos - 0.1, y_pos + 0.1,
                                   color=color, alpha=0.3)
                        
                        # Add trigger probability label
                        trigger_prob = zone.get("trigger_probability", 0)
                        mid_idx = (min_idx + max_idx) / 2
                        ax1.text(mid_idx, y_pos, 
                                f"T{i+1}: {trigger_prob:.2f}", 
                                color=color, fontsize=8, ha='center')
            
            # Plot propagation paths if available
            if cascade_probabilities and "propagation_paths" in cascade_probabilities:
                for i, path in enumerate(cascade_probabilities["propagation_paths"]):
                    # Only show paths with significant probability
                    if path.get("cascade_probability", 0) < 0.5:
                        continue
                        
                    direction = path.get("direction", "")
                    start_price = path.get("start_price", 0)
                    end_target = path.get("end_target", 0)
                    
                    # Find indices for path boundaries
                    start_idx = None
                    end_idx = None
                    
                    for j, price in enumerate(price_bins):
                        if start_idx is None and price >= start_price:
                            start_idx = j
                        if end_idx is None and price >= end_target:
                            end_idx = j
                            break
                    
                    if start_idx is not None and end_idx is not None:
                        # Draw cascade path arrow
                        if direction == "long":
                            y_pos = -0.5  # Position for long paths (bottom)
                            color = 'red'
                            # For long, we go from higher to lower prices
                            if start_idx > end_idx:
                                start_idx, end_idx = end_idx, start_idx
                        else:
                            y_pos = 0.5   # Position for short paths (top)
                            color = 'blue'
                            # For short, we go from lower to higher prices
                            if start_idx > end_idx:
                                start_idx, end_idx = end_idx, start_idx
                        
                        # Draw path arrow
                        cascade_prob = path.get("cascade_probability", 0)
                        arrow_width = 0.02 + (cascade_prob * 0.05)  # Scale with probability
                        
                        ax1.arrow(start_idx, y_pos, end_idx - start_idx, 0,
                                 head_width=0.15, head_length=1, 
                                 fc=color, ec=color, alpha=0.7,
                                 length_includes_head=True, width=arrow_width)
                        
                        # Add cascade probability label
                        mid_idx = (start_idx + end_idx) / 2
                        ax1.text(mid_idx, y_pos + 0.15, 
                                f"C{i+1}: {cascade_prob:.2f}", 
                                color=color, fontsize=8, ha='center')
            
            # Mark optimized trading ranges if available
            if optimized_ranges and "top_opportunities" in optimized_ranges:
                for i, trade in enumerate(optimized_ranges["top_opportunities"]):
                    # Get trade details
                    trade_side = trade.get("trade_side", "")
                    entry_price = trade.get("entry_price", 0)
                    target_price = trade.get("target_price", 0)
                    stop_price = trade.get("stop_price", 0)
                    quality_score = trade.get("quality_score", 0)
                    
                    # Find indices for trade points
                    entry_idx = None
                    target_idx = None
                    stop_idx = None
                    
                    for j, price in enumerate(price_bins):
                        if entry_idx is None and price >= entry_price:
                            entry_idx = j
                        if target_idx is None and price >= target_price:
                            target_idx = j
                        if stop_idx is None and price >= stop_price:
                            stop_idx = j
                    
                    if entry_idx is not None and target_idx is not None and stop_idx is not None:
                        # Set colors based on trade side
                        if trade_side == "long":
                            color = 'green'
                            y_pos = 0.2  # Position for long trades
                        else:
                            color = 'red'
                            y_pos = -0.2  # Position for short trades
                        
                        # Draw trade range
                        ax1.plot(entry_idx, y_pos, 'o', markersize=8, 
                                color=color, alpha=0.8)
                        ax1.plot(target_idx, y_pos, 's', markersize=8, 
                                color=color, alpha=0.8)
                        ax1.plot(stop_idx, y_pos, 'x', markersize=8, 
                                color=color, alpha=0.8)
                        
                        # Connect points with lines
                        ax1.plot([entry_idx, target_idx], [y_pos, y_pos], 
                                '-', color=color, alpha=0.6)
                        ax1.plot([entry_idx, stop_idx], [y_pos, y_pos], 
                                '--', color=color, alpha=0.6)
                        
                        # Add label with quality score
                        ax1.text(entry_idx, y_pos + 0.1, 
                                f"T{i+1}: {quality_score:.2f}", 
                                color=color, fontsize=8, ha='center')
            
            # Set up x-axis with price labels
            tick_positions = np.arange(0, len(price_bins), max(1, len(price_bins) // 10))
            tick_labels = [f"{price_bins[i]:.2f}" for i in tick_positions]
            ax1.set_xticks(tick_positions)
            ax1.set_xticklabels(tick_labels, rotation=45)
            
            # Set up y-axis
            ax1.set_yticks([-0.5, 0.5])
            ax1.set_yticklabels(['Long Liquidations', 'Short Liquidations'])
            
            # Set plot limits
            ax1.set_xlim(-1, len(price_bins))
            ax1.set_ylim(-1.5, 1.5)
            
            # Add title and labels
            ax1.set_title(f"{asset} Liquidation Heatmap with Cascade Analysis")
            ax1.set_xlabel("Price Levels")
            
            # === Second subplot for Cascade Probabilities ===
            if cascade_probabilities:
                # Extract cascade probabilities
                cascade_probs = cascade_probabilities.get("cascade_probabilities", {})
                trigger_zones = cascade_probabilities.get("trigger_zones", [])
                domino_densities = cascade_probabilities.get("domino_densities", {})
                
                # Create bar data
                categories = ['Downward\nCascade', 'Upward\nCascade', 'Long\nDomino', 'Short\nDomino']
                values = [
                    cascade_probs.get("long", 0),  # Downward cascade (from long liquidations)
                    cascade_probs.get("short", 0), # Upward cascade (from short liquidations)
                    domino_densities.get("long", 0),
                    domino_densities.get("short", 0)
                ]
                
                # Plot bars
                colors = ['darkred', 'darkblue', 'red', 'blue']
                bars = ax2.bar(categories, values, color=colors, alpha=0.7)
                
                # Add value annotations
                for bars, values in zip([bars], [values]):
                    for bar, value in zip(bars, values):
                        height = bar.get_height()
                        ax2.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                                f'{value:.2f}', ha='center', va='bottom', fontsize=10)
                
                # Add trigger zone table if available
                if trigger_zones:
                    # Only show top 3 trigger zones
                    top_zones = trigger_zones[:3]
                    table_data = []
                    
                    for zone in top_zones:
                        direction = "↓" if zone.get("direction") == "long" else "↑"
                        prob = zone.get("trigger_probability", 0)
                        price_range = zone.get("price_range", 0)
                        value = zone.get("total_value", 0) / 1000  # Convert to K
                        
                        table_data.append([direction, f"{prob:.2f}", f"{price_range:.2f}", f"${value:.0f}K"])
                    
                    # Add table headers
                    headers = ["Dir", "Prob", "Range", "Value"]
                    table_data.insert(0, headers)
                    
                    # Create table
                    table = ax2.table(cellText=table_data, loc='right', cellLoc='center')
                    table.auto_set_font_size(False)
                    table.set_fontsize(9)
                    table.scale(1, 1.5)
                
                # Set axes labels
                ax2.set_title("Cascade Probabilities & Domino Effects")
                ax2.set_ylabel("Probability Score (0-1)")
                ax2.set_ylim(0, 1.1)
                ax2.grid(axis='y', linestyle='--', alpha=0.7)
            
            # === Third subplot for Range Optimizations ===
            if optimized_ranges:
                # Extract optimization data
                trading_ranges = optimized_ranges.get("trading_ranges", [])
                dynamic_factors = optimized_ranges.get("dynamic_factors", {})
                
                # Only use top 5 ranges
                top_ranges = trading_ranges[:5] if len(trading_ranges) > 5 else trading_ranges
                
                if top_ranges:
                    # Create bar data for quality scores
                    range_ids = [f"TR{i+1}" for i in range(len(top_ranges))]
                    quality_scores = [r.get("quality_score", 0) for r in top_ranges]
                    risk_rewards = [r.get("risk_reward", 0) for r in top_ranges]
                    trade_sides = [r.get("trade_side", "") for r in top_ranges]
                    
                    # Set bar colors based on trade side
                    bar_colors = ['green' if side == 'long' else 'red' for side in trade_sides]
                    
                    # Plot quality score bars
                    x = np.arange(len(range_ids))
                    width = 0.35
                    
                    bars1 = ax3.bar(x - width/2, quality_scores, width, label='Quality Score', 
                                   color=bar_colors, alpha=0.7)
                    bars2 = ax3.bar(x + width/2, risk_rewards, width, label='Risk/Reward', 
                                   color='orange', alpha=0.7)
                    
                    # Add value annotations
                    for bars, values in zip([bars1, bars2], [quality_scores, risk_rewards]):
                        for bar, value in zip(bars, values):
                            height = bar.get_height()
                            ax3.text(bar.get_x() + bar.get_width()/2., height + 0.05,
                                    f'{value:.2f}', ha='center', va='bottom', fontsize=9)
                    
                    # Add dynamic factors table
                    table_data = []
                    
                    # Add key metrics from dynamic factors
                    volatility = dynamic_factors.get("market_volatility", 0) * 100  # Convert to %
                    depth = dynamic_factors.get("orderbook_depth", 0)
                    density = dynamic_factors.get("cluster_density", 0)
                    
                    table_data.append(["Volatility", f"{volatility:.2f}%"])
                    table_data.append(["Book Depth", f"{depth:.2f}"])
                    table_data.append(["Cl. Density", f"{density:.2f}"])
                    
                    if "optimal_buffer_percentage" in optimized_ranges:
                        buffer = optimized_ranges.get("optimal_buffer_percentage", 0)
                        table_data.append(["Entry Buffer", f"{buffer:.2f}%"])
                    
                    # Create table
                    table = ax3.table(cellText=table_data, loc='right', cellLoc='center')
                    table.auto_set_font_size(False)
                    table.set_fontsize(9)
                    table.scale(1, 1.5)
                    
                    # Set up axes
                    ax3.set_ylabel("Score")
                    ax3.set_title("Optimized Trading Ranges")
                    ax3.set_xticks(x)
                    ax3.set_xticklabels(range_ids)
                    ax3.legend()
                    ax3.set_ylim(0, max(max(quality_scores), max(risk_rewards)) * 1.2)
                    ax3.grid(axis='y', linestyle='--', alpha=0.7)
            
            # Adjust layout
            plt.tight_layout()
            
            # Save chart if savepath provided
            if savepath:
                # Ensure directory exists
                os.makedirs(os.path.dirname(savepath), exist_ok=True)
                
                # Format path with proper separators
                savepath = os.path.normpath(savepath)
                
                plt.savefig(savepath, dpi=150, bbox_inches='tight')
                plt.close()
                
                return savepath
            else:
                plt.show()
                return None
                
        except Exception as e:
            print(f"Error generating liquidation cascade heatmap for {asset}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def update_view_state(self, x_range=None, y_range=None):
        """
        Update the view state to maintain zoom/pan state.
        
        Args:
            x_range: X-axis range (tuple of min, max)
            y_range: Y-axis range (tuple of min, max)
        """
        if x_range:
            self.view_state["x_range"] = x_range
        if y_range:
            self.view_state["y_range"] = y_range
            
    def toggle_indicator(self, indicator_type, params=None, enabled=True):
        """
        Toggle a technical indicator on or off.
        
        Args:
            indicator_type: Type of indicator
            params: Parameters for the indicator
            enabled: Whether to enable or disable the indicator
        """
        if enabled:
            # Add indicator if not already in view state
            if indicator_type not in self.view_state["indicators"]:
                self.view_state["indicators"].append(indicator_type)
                # Calculate indicator if not in cache
                self.add_technical_indicator(indicator_type, params)
        else:
            # Remove indicator from view state
            if indicator_type in self.view_state["indicators"]:
                self.view_state["indicators"].remove(indicator_type)

def integrate_liquidation_with_trading_chart(asset, positions_df, liquidation_clusters, current_price, output_dir=None):
    """
    Integrates liquidation analysis with trading chart visualization.
    This is the main entry point used by other modules.
    
    Args:
        asset: Asset symbol
        positions_df: DataFrame with position data
        liquidation_clusters: Liquidation cluster analysis results
        current_price: Current asset price
        output_dir: Directory to save visualizations
        
    Returns:
        Path to saved chart image
    """
    # Initialize chart integration
    chart = TradingChartIntegration(output_dir=output_dir)
    
    # Load mock price data (would be replaced with actual API call)
    chart.load_price_data(asset)
    
    # Add all default indicators
    chart.add_technical_indicator("ma", {"period": 20})
    chart.add_technical_indicator("ma", {"period": 50})
    chart.add_technical_indicator("ema", {"period": 21})
    chart.add_technical_indicator("bbands", {"period": 20})
    
    # Create trading chart with liquidation levels
    chart_path = chart.create_liquidation_trading_chart(asset, liquidation_clusters, current_price)
    
    return chart_path


if __name__ == "__main__":
    # Test the module with sample data
    chart = TradingChartIntegration()
    chart.load_price_data("BTC/USDT")
    
    # Test with mock liquidation clusters
    mock_clusters = {
        "clusters": [
            {"price": 950, "size": 2000000, "market_impact": 0.8, "direction": "downward"},
            {"price": 1050, "size": 1500000, "market_impact": 0.6, "direction": "upward"},
            {"price": 900, "size": 800000, "market_impact": 0.4, "direction": "downward"}
        ]
    }
    
    # Create test chart
    chart.create_liquidation_trading_chart("BTC/USDT", mock_clusters, 1000)
    print("Test chart created successfully")
