#!/usr/bin/env python
"""
Risk Reward Configuration Manager
---------------------------------
Manages the risk/reward filter configuration settings for trade filtering.
"""

import os
import sys
import json
from typing import Dict, Any, Tuple

# Add parent directory to path to allow imports from root after moving to config/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Default config file locations - try both root and from config/ directory
CONFIG_FILE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                            "tracker", "config.json")
CONFIG_FILE_ORIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                          "tracker", "config.json")
                          
# Use the file that exists, prefer root path after moving to config/
CONFIG_FILE = CONFIG_FILE_ROOT if os.path.exists(CONFIG_FILE_ROOT) else CONFIG_FILE_ORIG

class RiskRewardConfig:
    def __init__(self, config_file=CONFIG_FILE):
        self.config_file = config_file
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                
                # Ensure risk_reward_filters section exists
                if "risk_reward_filters" not in config:
                    config["risk_reward_filters"] = {
                        "min_risk_reward": 1.37,
                        "max_risk_reward": 10.0,
                        "enabled": True
                    }
                    
                return config
        except Exception as e:
            print(f"Error loading risk/reward config: {e}")
            # Return default config if file not found or invalid
            return {
                "risk_reward_filters": {
                    "min_risk_reward": 1.37,
                    "max_risk_reward": 10.0,
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
            print(f"Error saving risk/reward config: {e}")
            return False
            
    def reload_config(self) -> None:
        """Reload configuration from file"""
        try:
            self.config = self._load_config()
        except Exception as e:
            print(f"Error reloading risk/reward config: {e}")
            
    def get_risk_reward_settings(self) -> Dict[str, Any]:
        """Get the current risk/reward filter settings"""
        # Reload config to ensure we have the latest settings
        self.reload_config()
        return self.config.get("risk_reward_filters", {
            "min_risk_reward": 1.37,
            "max_risk_reward": 10.0,
            "enabled": True
        })
        
    def set_min_risk_reward(self, value: float) -> bool:
        """Set the minimum risk/reward value for filtering trades"""
        if not isinstance(value, (int, float)) or value <= 0:
            return False
            
        # Ensure we don't set min > max
        max_value = self.config.get("risk_reward_filters", {}).get("max_risk_reward", 10.0)
        if value >= max_value:
            return False
            
        if "risk_reward_filters" not in self.config:
            self.config["risk_reward_filters"] = {}
            
        self.config["risk_reward_filters"]["min_risk_reward"] = value
        return self._save_config()
        
    def set_max_risk_reward(self, value: float) -> bool:
        """Set the maximum risk/reward value for filtering trades"""
        if not isinstance(value, (int, float)) or value <= 0:
            return False
            
        # Ensure we don't set max < min
        min_value = self.config.get("risk_reward_filters", {}).get("min_risk_reward", 1.37)
        if value <= min_value:
            return False
            
        if "risk_reward_filters" not in self.config:
            self.config["risk_reward_filters"] = {}
            
        self.config["risk_reward_filters"]["max_risk_reward"] = value
        return self._save_config()
        
    def set_risk_reward_enabled(self, enabled: bool) -> bool:
        """Enable or disable risk/reward filtering"""
        if "risk_reward_filters" not in self.config:
            self.config["risk_reward_filters"] = {}
            
        self.config["risk_reward_filters"]["enabled"] = bool(enabled)
        success = self._save_config()
        # Reload config to ensure in-memory state matches file state
        self.reload_config()
        return success
        
    def get_min_risk_reward(self) -> float:
        """Get the minimum risk/reward value"""
        return self.config.get("risk_reward_filters", {}).get("min_risk_reward", 1.37)
        
    def get_max_risk_reward(self) -> float:
        """Get the maximum risk/reward value"""
        return self.config.get("risk_reward_filters", {}).get("max_risk_reward", 10.0)
        
    def is_risk_reward_enabled(self) -> bool:
        """Check if risk/reward filtering is enabled"""
        # Reload config to ensure we have the latest settings
        self.reload_config()
        return self.config.get("risk_reward_filters", {}).get("enabled", True)
        
    def set_risk_reward_range(self, min_value: float, max_value: float) -> bool:
        """Set both min and max risk/reward values at once"""
        if not isinstance(min_value, (int, float)) or min_value <= 0:
            return False
            
        if not isinstance(max_value, (int, float)) or max_value <= 0:
            return False
            
        if min_value >= max_value:
            return False
            
        if "risk_reward_filters" not in self.config:
            self.config["risk_reward_filters"] = {}
            
        self.config["risk_reward_filters"]["min_risk_reward"] = min_value
        self.config["risk_reward_filters"]["max_risk_reward"] = max_value
        success = self._save_config()
        # Reload config to ensure in-memory state matches file state
        self.reload_config()
        return success

# Create singleton instance
risk_reward_config = RiskRewardConfig()
