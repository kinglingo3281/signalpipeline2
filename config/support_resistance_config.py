#!/usr/bin/env python
"""Support/Resistance Configuration Manager
----------------------------------------
Manages the support/resistance adjustment settings for trade parameter adjustments.
Allows entry/TP/SL modifications based on proximity to support/resistance levels.
Includes Fibonacci retracement level configuration for more accurate adjustments.
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

class SupportResistanceConfig:
    def __init__(self, config_file=CONFIG_FILE):
        self.config_file = config_file
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                
                # Ensure support_resistance_adjustment section exists
                if "support_resistance_adjustment" not in config:
                    config["support_resistance_adjustment"] = {
                        "enabled": True,
                        "support_adjustment_percent": 0.5,
                        "resistance_adjustment_percent": 0.5,
                        "tp_widening_percent": 15.0,
                        "proximity_threshold_percent": 1.0,
                        "use_fibonacci": True,
                        "fibonacci_period": 125
                    }
                    
                return config
        except Exception as e:
            print(f"Error loading support/resistance config: {e}")
            # Return default config if file not found or invalid
            return {
                "support_resistance_adjustment": {
                    "enabled": True,
                    "support_adjustment_percent": 0.5,
                    "resistance_adjustment_percent": 0.5,
                    "tp_widening_percent": 15.0,
                    "proximity_threshold_percent": 1.0,
                    "use_fibonacci": True,
                    "fibonacci_period": 125
                }
            }
            
    def _save_config(self) -> bool:
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving support/resistance config: {e}")
            return False
            
    def reload_config(self) -> None:
        """Reload configuration from file"""
        try:
            self.config = self._load_config()
        except Exception as e:
            print(f"Error reloading support/resistance config: {e}")
            
    def get_support_resistance_settings(self) -> Dict[str, Any]:
        """Get the current support/resistance adjustment settings"""
        self.reload_config()
        return self.config.get("support_resistance_adjustment", {
            "enabled": True,
            "support_adjustment_percent": 0.5,
            "resistance_adjustment_percent": 0.5,
            "tp_widening_percent": 15.0,
            "proximity_threshold_percent": 1.0
        })
        
    def set_support_adjustment_percent(self, value: float) -> bool:
        """Set the support adjustment percentage"""
        if not isinstance(value, (int, float)) or value < 0:
            return False
            
        if "support_resistance_adjustment" not in self.config:
            self.config["support_resistance_adjustment"] = {}
            
        self.config["support_resistance_adjustment"]["support_adjustment_percent"] = value
        success = self._save_config()
        self.reload_config()
        return success
        
    def set_resistance_adjustment_percent(self, value: float) -> bool:
        """Set the resistance adjustment percentage"""
        if not isinstance(value, (int, float)) or value < 0:
            return False
            
        if "support_resistance_adjustment" not in self.config:
            self.config["support_resistance_adjustment"] = {}
            
        self.config["support_resistance_adjustment"]["resistance_adjustment_percent"] = value
        success = self._save_config()
        self.reload_config()
        return success
        
    def set_tp_widening_percent(self, value: float) -> bool:
        """Set the take profit widening percentage"""
        if not isinstance(value, (int, float)) or value < 0:
            return False
            
        if "support_resistance_adjustment" not in self.config:
            self.config["support_resistance_adjustment"] = {}
            
        self.config["support_resistance_adjustment"]["tp_widening_percent"] = value
        success = self._save_config()
        self.reload_config()
        return success
        
    def set_support_resistance_enabled(self, enabled: bool) -> bool:
        """Enable or disable support/resistance adjustments"""
        if "support_resistance_adjustment" not in self.config:
            self.config["support_resistance_adjustment"] = {}
            
        self.config["support_resistance_adjustment"]["enabled"] = bool(enabled)
        success = self._save_config()
        self.reload_config()
        return success
        
    def get_support_adjustment_percent(self) -> float:
        """Get the support adjustment percentage"""
        self.reload_config()
        return self.config.get("support_resistance_adjustment", {}).get("support_adjustment_percent", 0.5)
        
    def get_resistance_adjustment_percent(self) -> float:
        """Get the resistance adjustment percentage"""
        self.reload_config()
        return self.config.get("support_resistance_adjustment", {}).get("resistance_adjustment_percent", 0.5)
        
    def get_tp_widening_percent(self) -> float:
        """Get the take profit widening percentage"""
        self.reload_config()
        return self.config.get("support_resistance_adjustment", {}).get("tp_widening_percent", 15.0)
        
    def is_support_resistance_enabled(self) -> bool:
        """Check if support/resistance adjustments are enabled"""
        self.reload_config()
        return self.config.get("support_resistance_adjustment", {}).get("enabled", True)
        
    def set_proximity_threshold_percent(self, value: float) -> bool:
        """Set the proximity threshold percentage"""
        if not isinstance(value, (int, float)) or value < 0:
            return False
            
        if "support_resistance_adjustment" not in self.config:
            self.config["support_resistance_adjustment"] = {}
            
        self.config["support_resistance_adjustment"]["proximity_threshold_percent"] = value
        success = self._save_config()
        self.reload_config()
        return success
        
    def get_proximity_threshold_percent(self) -> float:
        """Get the proximity threshold percentage"""
        self.reload_config()
        return self.config.get("support_resistance_adjustment", {}).get("proximity_threshold_percent", 1.0)
        
    def get_fibonacci_settings(self) -> Dict[str, Any]:
        """Get the current Fibonacci adjustment settings"""
        self.reload_config()
        sr_config = self.config.get("support_resistance_adjustment", {})
        return {
            "enabled": sr_config.get("enabled", True),  # Reuse main enabled flag
            "use_fibonacci": sr_config.get("use_fibonacci", True),
            "fibonacci_period": sr_config.get("fibonacci_period", 125),
            "fibonacci_interval": sr_config.get("fibonacci_interval", "1d"),
            "proximity_threshold_percent": sr_config.get("proximity_threshold_percent", 1.0)
        }
        
    def set_use_fibonacci(self, enabled: bool) -> bool:
        """Enable or disable Fibonacci-based adjustments"""
        if "support_resistance_adjustment" not in self.config:
            self.config["support_resistance_adjustment"] = {}
            
        self.config["support_resistance_adjustment"]["use_fibonacci"] = bool(enabled)
        success = self._save_config()
        self.reload_config()
        return success
        
    def is_fibonacci_enabled(self) -> bool:
        """Check if Fibonacci-based adjustments are enabled"""
        self.reload_config()
        return self.config.get("support_resistance_adjustment", {}).get("use_fibonacci", True)

# Create singleton instance
support_resistance_config = SupportResistanceConfig()
