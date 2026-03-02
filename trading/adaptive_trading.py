#!/usr/bin/env python
"""
Adaptive Trading System
----------------------
Tracks trading performance and adjusts confidence scores based on historical PnL.
Provides weighted multipliers for trade confidence based on:
1. Global direction performance (longs vs shorts)
2. Asset-specific performance 
3. Asset-direction pair performance

Also implements progressive cooldown periods based on consecutive losses and volatility regime changes.
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Union, Any

# Add parent directory to path to allow imports from root after moving to trading/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Try importing volatility regime detection from utils directory
try:
    # Try first from utils directory after move
    from utils.volatility_regime import is_in_volatility_cooldown
    VOLATILITY_REGIME_AVAILABLE = True
except ImportError:
    try:
        # Then try from root directory during transition
        from volatility_regime import is_in_volatility_cooldown
        VOLATILITY_REGIME_AVAILABLE = True
    except ImportError:
        VOLATILITY_REGIME_AVAILABLE = False

# File to store performance metrics - handle both locations
PERFORMANCE_FILE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "performance_data.json")
PERFORMANCE_FILE_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "performance_data.json")

# Use the file that exists, or default to the root location
PERFORMANCE_FILE = PERFORMANCE_FILE_ROOT if os.path.exists(PERFORMANCE_FILE_ROOT) else PERFORMANCE_FILE_LOCAL

class AdaptiveTradingSystem:
    def __init__(self, performance_file=PERFORMANCE_FILE):
        self.performance_file = performance_file
        self.performance_data = self._load_performance_data()
        
    def _load_performance_data(self) -> Dict:
        """Load performance data from file or create default structure"""
        if os.path.exists(self.performance_file):
            try:
                with open(self.performance_file, 'r') as f:
                    data = json.load(f)
                    # Ensure trade_history exists in loaded data
                    if "trade_history" not in data:
                        data["trade_history"] = {}
                    return data
            except Exception as e:
                print(f"Error loading performance data: {e}")
                
        # Default structure if file doesn't exist or has issues
        return {
            "global": {
                "long": {"pnl": 0.0, "trades": 0},
                "short": {"pnl": 0.0, "trades": 0}
            },
            "assets": {},
            "pairs": {},
            "trade_history": {},  # Store recent trades with timestamps
            "last_updated": datetime.now().isoformat()
        }
    
    def _save_performance_data(self):
        """Save performance data to file"""
        self.performance_data["last_updated"] = datetime.now().isoformat()
        try:
            with open(self.performance_file, 'w') as f:
                json.dump(self.performance_data, f, indent=2)
        except Exception as e:
            print(f"Error saving performance data: {e}")
    
    def update_performance(self, asset: str, direction: str, pnl: float, trade_size: float = 10.0):
        """
        Update performance metrics with a completed trade
        
        Args:
            asset: Asset symbol (e.g., 'BTC')
            direction: Trade direction ('long' or 'short')
            pnl: Profit/Loss amount in USD
            trade_size: Size of the trade in USD
        """
        direction = direction.lower()
        
        # Normalize PnL by trade size for consistent comparison
        normalized_pnl = pnl / trade_size
        
        # Update global direction performance
        if direction in self.performance_data["global"]:
            self.performance_data["global"][direction]["pnl"] += normalized_pnl
            self.performance_data["global"][direction]["trades"] += 1
        
        # Update asset-specific performance
        if asset not in self.performance_data["assets"]:
            self.performance_data["assets"][asset] = {"pnl": 0.0, "trades": 0}
        self.performance_data["assets"][asset]["pnl"] += normalized_pnl
        self.performance_data["assets"][asset]["trades"] += 1
        
        # Update asset-direction pair performance
        pair_key = f"{asset}_{direction}"
        if pair_key not in self.performance_data["pairs"]:
            self.performance_data["pairs"][pair_key] = {"pnl": 0.0, "trades": 0}
        self.performance_data["pairs"][pair_key]["pnl"] += normalized_pnl
        self.performance_data["pairs"][pair_key]["trades"] += 1
        
        # Add trade to history with timestamp
        pair_history_key = f"{asset}_{direction}"
        if "trade_history" not in self.performance_data:
            self.performance_data["trade_history"] = {}
            
        if pair_history_key not in self.performance_data["trade_history"]:
            self.performance_data["trade_history"][pair_history_key] = []
            
        # Add new trade record with timestamp
        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "pnl": normalized_pnl,
            "size": trade_size,
            "is_profit": normalized_pnl > 0
        }
        
        # Add to history and limit to 20 most recent trades
        self.performance_data["trade_history"][pair_history_key].append(trade_record)
        if len(self.performance_data["trade_history"][pair_history_key]) > 20:
            # Keep only the 20 most recent trades
            self.performance_data["trade_history"][pair_history_key] = \
                self.performance_data["trade_history"][pair_history_key][-20:]
        
        # Save updated data
        self._save_performance_data()
    
    def get_confidence_multiplier(self, asset: str, direction: str) -> float:
        """
        Calculate a confidence multiplier based on historical performance
        
        Args:
            asset: Asset symbol (e.g., 'BTC')
            direction: Trade direction ('long' or 'short')
            
        Returns:
            float: Confidence multiplier (0.6-1.4)
        """
        direction = direction.lower()
        
        # Get performance metrics from each level
        global_metrics = self._get_direction_metrics(direction)
        asset_metrics = self._get_asset_metrics(asset)
        pair_metrics = self._get_pair_metrics(asset, direction)
        
        # Calculate PnL efficiency (normalized performance) for each level
        global_efficiency = self._calculate_efficiency(global_metrics)
        asset_efficiency = self._calculate_efficiency(asset_metrics)
        pair_efficiency = self._calculate_efficiency(pair_metrics)
        
        # Apply weights to each level (more specific levels have higher weights)
        # Only use levels with sufficient data (at least 3 trades)
        weights = [0, 0, 0]  # global, asset, pair
        values = [1.0, 1.0, 1.0]  # default neutral values
        
        if global_metrics and global_metrics["trades"] >= 3:
            weights[0] = 1.0
            values[0] = global_efficiency
            
        if asset_metrics and asset_metrics["trades"] >= 3:
            weights[1] = 2.0
            values[1] = asset_efficiency
            
        if pair_metrics and pair_metrics["trades"] >= 3:
            weights[2] = 4.0
            values[2] = pair_efficiency
        
        # If no data available, return neutral multiplier
        if sum(weights) == 0:
            return 1.0
            
        # Calculate weighted average
        weighted_efficiency = sum(w * v for w, v in zip(weights, values)) / sum(weights)
        
        # Convert efficiency to multiplier (0.6-1.4 range)
        # Efficiency is typically in range -1 to +1
        multiplier = 1.0 + (weighted_efficiency * 0.4)
        
        # Ensure multiplier stays within bounds
        return max(0.6, min(1.4, multiplier))
    
    def check_volatility_cooldown(self, asset: str) -> Tuple[bool, Optional[str]]:
        """
        Check if asset is in volatility cooldown period
        
        Args:
            asset: Asset symbol
            
        Returns:
            Tuple[bool, Optional[str]]: Whether in cooldown and reason
        """
        if not VOLATILITY_REGIME_AVAILABLE:
            return False, None
            
        try:
            return is_in_volatility_cooldown(asset)
        except Exception as e:
            logging.warning(f"Error checking volatility cooldown: {e}")
            return False, None
            
    def _get_consecutive_direction_losses(self, direction: str) -> Tuple[int, Optional[str]]:
        """
        Get number of consecutive losses for a trading direction
        Only tracks the first wallet found to avoid counting losses across wallets
        
        Args:
            direction: Trade direction ('long' or 'short')
            
        Returns:
            Tuple of (consecutive_count, latest_loss_timestamp)
        """
        direction = direction.lower()
        consecutive_count = 0
        last_loss_time = None
        processed_timestamps = set()  # Track processed timestamps to avoid duplicates
        
        # Collect all trades in this direction from one wallet only
        tracked_wallet = None
        all_direction_trades = []
        
        try:
            # Get trade history for all pairs
            for pair_key, trades in self.performance_data.get("trade_history", {}).items():
                # Only include pairs in the specified direction
                if not pair_key.endswith(f"_{direction}"):
                    continue
                    
                # Add all trades from this pair (from the tracked wallet only)
                for trade in trades:
                    if "timestamp" in trade and "is_profit" in trade:
                        # Get wallet ID from trade, use 'default' if not specified
                        wallet = trade.get("wallet", "default")
                        
                        # If we haven't chosen a wallet to track yet, use this one
                        if tracked_wallet is None:
                            tracked_wallet = wallet
                        
                        # Only track trades from our chosen wallet
                        if wallet == tracked_wallet:
                            all_direction_trades.append(trade)
            
            # Sort all trades by timestamp, newest first
            all_direction_trades.sort(
                key=lambda x: x.get("timestamp", ""),
                reverse=True
            )
            
            # Get current time for filtering old trades
            now = datetime.now()
            max_age_hours = 48  # Only consider trades from the last 48 hours
            
            # Count consecutive losses
            for trade in all_direction_trades:
                # Skip if we've seen this timestamp before (avoid duplicates)
                timestamp = trade.get("timestamp", "")
                if timestamp in processed_timestamps:
                    continue
                processed_timestamps.add(timestamp)
                
                # Skip trades older than max_age_hours
                try:
                    trade_time = datetime.fromisoformat(timestamp)
                    hours_old = (now - trade_time).total_seconds() / 3600
                    if hours_old > max_age_hours:
                        break  # Stop processing if we hit an old trade
                except (ValueError, TypeError):
                    continue  # Skip trades with invalid timestamps
                
                # Check if this trade was profitable
                is_profit = trade.get("is_profit", trade.get("pnl", 0) > 0)
                
                # If we hit a profitable trade, break the sequence
                if is_profit:
                    break
                    
                # Otherwise, increment consecutive loss counter
                consecutive_count += 1
                if not last_loss_time:
                    last_loss_time = timestamp
                    
                # Cap at 10 for practical purposes
                if consecutive_count >= 10:
                    break
                    
            return consecutive_count, last_loss_time
                    
        except Exception as e:
            print(f"Error getting direction losses: {e}")
            return 0, None
            
    def get_direction_cooldown_status(self, direction: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a trading direction is in cooldown period based on global performance
        
        Args:
            direction: Trade direction ('long' or 'short')
            
        Returns:
            Tuple of (in_cooldown, reason)
        """
        direction = direction.lower()
        
        # Check if cooldowns are disabled for this direction
        try:
            from direction_cooldown_config import direction_cooldown_config
            if direction == 'long' and direction_cooldown_config.is_long_cooldowns_disabled():
                return False, None
            elif direction == 'short' and direction_cooldown_config.is_short_cooldowns_disabled():
                return False, None
        except ImportError:
            # If the module doesn't exist, just continue with normal cooldown logic
            pass
        except Exception as e:
            print(f"Error checking disabled cooldowns status: {e}")
        
        # Check for consecutive direction losses
        consecutive_losses, last_loss_time = self._get_consecutive_direction_losses(direction)
        
        # If fewer than 3 consecutive losses, no cooldown
        if consecutive_losses < 3 or not last_loss_time:
            return False, None
        
        # Set 3-hour cooldown for 3+ consecutive losses in a direction
        cooldown_hours = 3
        
        # Convert last loss time to datetime
        try:
            last_loss_dt = datetime.fromisoformat(last_loss_time)
            # Calculate time since last loss
            now = datetime.now()
            hours_since_loss = (now - last_loss_dt).total_seconds() / 3600
            
            # Check if we're still in cooldown period
            if hours_since_loss < cooldown_hours:
                hours_left = cooldown_hours - hours_since_loss
                return True, f"Direction cooldown: {consecutive_losses} consecutive {direction} losses ({hours_left:.1f}h remaining)"
                
        except (ValueError, TypeError) as e:
            print(f"Error calculating direction cooldown: {e}")
            
        return False, None
    
    def get_enhanced_cooldown_status(self, asset: str, direction: str) -> Tuple[bool, Optional[str]]:
        """
        Get combined cooldown status from asset-specific, direction-based and volatility-based cooldowns
        
        Args:
            asset: Asset symbol
            direction: Trade direction ('long' or 'short')
            
        Returns:
            Tuple[bool, Optional[str]]: Whether in cooldown and reason
        """
        direction = direction.lower()
        
        # Check asset-direction specific cooldown first
        in_cooldown, reason = self.get_cooldown_status(asset, direction)
        
        # If already in cooldown, return that
        if in_cooldown:
            return True, reason
            
        # Check direction-based cooldown (global across all assets) 
        in_dir_cooldown, dir_reason = self.get_direction_cooldown_status(direction)
        if in_dir_cooldown:
            return True, dir_reason
            
        # Finally check volatility cooldown
        in_vol_cooldown, vol_reason = self.check_volatility_cooldown(asset)
        
        if in_vol_cooldown:
            return True, vol_reason
            
        # Not in any cooldown
        return False, None
    
    def get_cooldown_status(self, asset: str, direction: str) -> Tuple[bool, Optional[str]]:
        """
        Check if an asset-direction pair is in cooldown period
        
        Args:
            asset: Asset symbol
            direction: Trade direction ('long' or 'short')
            
        Returns:
            Tuple of (in_cooldown, reason)
        """
        direction = direction.lower()
        
        # Check for consecutive losses
        consecutive_losses, last_loss_time = self._get_consecutive_losses(asset, direction)
        
        # If no losses found, no cooldown
        if consecutive_losses < 1 or not last_loss_time:
            return False, None
        
        # Calculate cooldown based on consecutive losses
        cooldown_hours = {
            1: 3,    # 1 loss: 3 hour cooldown
            2: 12,   # 2 consecutive losses: 12 hour cooldown
            3: 24    # 3+ consecutive losses: 24 hour cooldown
        }.get(consecutive_losses, 24)  # Default to 24 hours for 3+ consecutive losses
        
        # Convert last loss time to datetime
        try:
            last_loss_dt = datetime.fromisoformat(last_loss_time)
            # Calculate time since last loss
            now = datetime.now()
            hours_since_loss = (now - last_loss_dt).total_seconds() / 3600
            
            # Check if we're still in cooldown period
            if hours_since_loss < cooldown_hours:
                hours_left = cooldown_hours - hours_since_loss
                return True, f"Cooling down after {consecutive_losses} consecutive losses ({hours_left:.1f}h remaining)"
                
        except (ValueError, TypeError) as e:
            print(f"Error calculating cooldown: {e}")
            
        return False, None
    
    def _get_direction_metrics(self, direction: str) -> Optional[Dict]:
        """Get performance metrics for a direction"""
        return self.performance_data["global"].get(direction)
    
    def _get_asset_metrics(self, asset: str) -> Optional[Dict]:
        """Get performance metrics for an asset"""
        return self.performance_data["assets"].get(asset)
    
    def _get_pair_metrics(self, asset: str, direction: str) -> Optional[Dict]:
        """Get performance metrics for an asset-direction pair"""
        pair_key = f"{asset}_{direction}"
        return self.performance_data["pairs"].get(pair_key)
    
    def _calculate_efficiency(self, metrics: Optional[Dict]) -> float:
        """Calculate PnL efficiency from metrics"""
        if not metrics or metrics["trades"] == 0:
            return 0.0
            
        # Simple PnL per trade metric
        return metrics["pnl"] / metrics["trades"]
    
    def refresh_data(self):
        """Reload performance data from disk to ensure latest state"""
        self.performance_data = self._load_performance_data()
        
    def _get_consecutive_losses(self, asset: str, direction: str) -> Tuple[int, Optional[str]]:
        """
        Get number of consecutive losses for an asset-direction pair and latest loss timestamp
        
        Args:
            asset: Asset symbol
            direction: Trade direction ('long' or 'short')
            
        Returns:
            Tuple of (consecutive_count, latest_loss_timestamp)
        """
        direction = direction.lower()
        pair_key = f"{asset}_{direction}"
        
        # Check if we have trade history for this pair
        if "trade_history" not in self.performance_data or \
           pair_key not in self.performance_data["trade_history"] or \
           not self.performance_data["trade_history"][pair_key]:
            return 0, None
            
        # Get trade history sorted by timestamp (newest first)
        try:
            trades = sorted(
                self.performance_data["trade_history"][pair_key],
                key=lambda x: x.get("timestamp", ""),
                reverse=True
            )
        except Exception as e:
            print(f"Error sorting trade history: {e}")
            return 0, None
            
        # Track consecutive losses
        consecutive_count = 0
        last_loss_time = None
        last_trade_time = None
        
        # Process trades from newest to oldest
        for trade in trades:
            # Skip trades without timestamp or PnL info
            if "timestamp" not in trade or "pnl" not in trade:
                continue
                
            current_time = trade["timestamp"]
            is_profit = trade.get("is_profit", trade["pnl"] > 0)
            
            # If this is our first trade in the sequence
            if last_trade_time is None:
                last_trade_time = current_time
                if not is_profit:
                    consecutive_count = 1
                    last_loss_time = current_time
                continue
                
            # Check if there's a significant time gap between trades (48+ hours)
            try:
                current_dt = datetime.fromisoformat(current_time)
                last_dt = datetime.fromisoformat(last_trade_time)
                time_gap = abs((last_dt - current_dt).total_seconds() / 3600)
                
                # Reset counter if trades are separated by more than 48 hours
                if time_gap > 48:
                    break
            except (ValueError, TypeError):
                # If timestamp parsing fails, assume continuity
                pass
                
            # Update last trade time
            last_trade_time = current_time
            
            # If we hit a profitable trade, break the sequence
            if is_profit:
                break
                
            # Otherwise, increment consecutive loss counter
            consecutive_count += 1
            if not last_loss_time:
                last_loss_time = current_time
                
            # Cap at 5 for practical purposes
            if consecutive_count >= 5:
                break
                
        return consecutive_count, last_loss_time

# Global instance for easy access
adaptive_system = AdaptiveTradingSystem()

def adjust_confidence(trade: Dict) -> Dict:
    """
    Adjust confidence score for a potential trade based on historical performance
    and direction enabled/disabled status
    
    Args:
        trade: Trade dictionary with asset, direction, confidence
        
    Returns:
        Updated trade dictionary with adjusted confidence
    """
    asset = trade["asset"]
    direction = trade["direction"].lower()
    
    # Get performance-based confidence multiplier
    performance_multiplier = adaptive_system.get_confidence_multiplier(asset, direction)
    
    # Get direction-enabled multiplier from config (1.0 or 0.1)
    try:
        # Try importing from config directory after refactoring
        from config.adaptive_config import config
        direction_multiplier = config.get_direction_multiplier(direction)
    except ImportError:
        # Fallback to root import during transition
        from adaptive_config import config
        direction_multiplier = config.get_direction_multiplier(direction)
    
    # Combine multipliers
    combined_multiplier = performance_multiplier * direction_multiplier
    
    # Apply multiplier to confidence
    original_confidence = trade["confidence"]
    trade["confidence"] = original_confidence * combined_multiplier
    
    # Add info about adjustment
    trade["original_confidence"] = original_confidence
    trade["confidence_multiplier"] = combined_multiplier
    trade["direction_enabled"] = direction_multiplier > 0.5  # True if direction enabled
    
    return trade

def update_from_pnl(asset: str, direction: str, pnl: float, trade_size: float = 10.0):
    """
    Update adaptive system with PnL results from a completed trade
    
    Args:
        asset: Asset symbol
        direction: Trade direction ('long' or 'short')
        pnl: Profit/Loss amount in USD
        trade_size: Size of the trade in USD
    """
    adaptive_system.update_performance(asset, direction, pnl, trade_size)

# Simple test function
if __name__ == "__main__":
    # Create test data
    update_from_pnl("BTC", "long", 5.0)
    update_from_pnl("BTC", "long", -2.0)
    update_from_pnl("ETH", "short", 3.0)
    
    # Test confidence adjustment
    test_trade = {"asset": "BTC", "direction": "long", "confidence": 0.8}
    adjusted = adjust_confidence(test_trade)
    print(f"Original confidence: {test_trade['original_confidence']}")
    print(f"Adjusted confidence: {adjusted['confidence']}")
    print(f"Multiplier: {adjusted['confidence_multiplier']}")
