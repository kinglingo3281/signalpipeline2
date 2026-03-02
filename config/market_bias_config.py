#!/usr/bin/env python
"""
Market Bias Configuration Manager
---------------------------------
Manages the market bias settings for trade parameter adjustments.
Allows manual override of market bias (bullish/bearish/neutral).
"""

import os
import sys
import json
from typing import Dict, Any

# Add parent directory to path to allow imports from root after moving to config/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Define project root for consistent file paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configuration file paths - check both locations
CONFIG_FILE_ROOT = os.path.join(PROJECT_ROOT, "tracker", "config.json")
CONFIG_FILE_ORIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracker", "config.json")

# Use the path that exists, or fall back to the PROJECT_ROOT path
CONFIG_FILE = CONFIG_FILE_ORIG if os.path.exists(CONFIG_FILE_ORIG) else CONFIG_FILE_ROOT

class MarketBiasConfig:
    def __init__(self, config_file=CONFIG_FILE):
        self.config_file = config_file
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                
                # Ensure market_bias section exists
                if "market_bias" not in config:
                    config["market_bias"] = {
                        "bias": "neutral",  # Options: "bullish", "bearish", "neutral"
                        "favorable_adjustment": 1.5,  # % to adjust entries in the favored direction
                        "unfavorable_adjustment": 5.0,  # % to adjust entries in the unfavored direction
                        "enabled": True,
                        "use_auto_bias": False  # Whether to use bias from analysis files or manual setting
                    }
                    
                return config
        except Exception as e:
            print(f"Error loading market bias config: {e}")
            # Return default config if file not found or invalid
            return {
                "market_bias": {
                    "bias": "neutral",
                    "favorable_adjustment": 1.5,
                    "unfavorable_adjustment": 5.0,
                    "enabled": True
                }
            }
            
    def _save_config(self) -> bool:
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving market bias config: {e}")
            return False
            
    def reload_config(self) -> None:
        """Reload configuration from file"""
        try:
            self.config = self._load_config()
        except Exception as e:
            print(f"Error reloading market bias config: {e}")
            
    def get_market_bias_settings(self) -> Dict[str, Any]:
        """Get the current market bias settings"""
        self.reload_config()
        
        # Get market_bias section from config or use empty dict if not found
        if "market_bias" in self.config:
            # Return actual values from config.json without any defaults
            return self.config["market_bias"]
        else:
            # No market_bias section found, use defaults
            return {
                "bias": "neutral",
                "favorable_adjustment": 1.5,
                "unfavorable_adjustment": 5.0,
                "enabled": True
            }
        
    def set_market_bias(self, bias: str) -> bool:
        """Set the market bias (bullish, bearish, or neutral)"""
        if bias not in ["bullish", "bearish", "neutral"]:
            return False
            
        if "market_bias" not in self.config:
            self.config["market_bias"] = {}
            
        self.config["market_bias"]["bias"] = bias
        success = self._save_config()
        self.reload_config()
        return success
        
    def set_favorable_adjustment(self, value: float) -> bool:
        """Set the favorable direction adjustment percentage"""
        if not isinstance(value, (int, float)) or value < 0:
            return False
            
        if "market_bias" not in self.config:
            self.config["market_bias"] = {}
            
        self.config["market_bias"]["favorable_adjustment"] = value
        success = self._save_config()
        self.reload_config()
        return success
        
    def set_unfavorable_adjustment(self, value: float) -> bool:
        """Set the unfavorable direction adjustment percentage"""
        if not isinstance(value, (int, float)) or value < 0:
            return False
            
        if "market_bias" not in self.config:
            self.config["market_bias"] = {}
            
        self.config["market_bias"]["unfavorable_adjustment"] = value
        success = self._save_config()
        self.reload_config()
        return success
        
    def set_market_bias_enabled(self, enabled: bool) -> bool:
        """Enable or disable market bias adjustments"""
        if "market_bias" not in self.config:
            self.config["market_bias"] = {}
            
        self.config["market_bias"]["enabled"] = bool(enabled)
        success = self._save_config()
        self.reload_config()
        return success
        
    def get_market_bias(self) -> str:
        """Get the current market bias setting"""
        self.reload_config()
        return self.config.get("market_bias", {}).get("bias", "neutral")
        
    def get_favorable_adjustment(self) -> float:
        """Get the favorable direction adjustment percentage"""
        self.reload_config()
        return self.config.get("market_bias", {}).get("favorable_adjustment", 1.5)
        
    def get_unfavorable_adjustment(self) -> float:
        """Get the unfavorable direction adjustment percentage"""
        self.reload_config()
        return self.config.get("market_bias", {}).get("unfavorable_adjustment", 5.0)
        
    def is_market_bias_enabled(self) -> bool:
        """Check if market bias adjustments are enabled"""
        self.reload_config()
        return self.config.get("market_bias", {}).get("enabled", True)
        
    def set_use_auto_bias(self, use_auto: bool) -> bool:
        """Set whether to use automatic bias from analysis files"""
        if "market_bias" not in self.config:
            self.config["market_bias"] = {}
            
        self.config["market_bias"]["use_auto_bias"] = bool(use_auto)
        success = self._save_config()
        self.reload_config()
        return success
        
    def is_auto_bias_enabled(self) -> bool:
        """Check if automatic bias detection is enabled"""
        self.reload_config()
        return self.config.get("market_bias", {}).get("use_auto_bias", False)

# Create singleton instance
market_bias_config = MarketBiasConfig()
