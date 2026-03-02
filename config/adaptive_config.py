#!/usr/bin/env python
"""
Adaptive Trading Configuration Manager
--------------------------------------
Manages configuration for the adaptive trading system.
"""

import os
import sys
import json
from datetime import datetime

# Add parent directory to path to allow imports from root after moving to config/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Default config file locations - try both root and config/ directory paths
CONFIG_FILE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "adaptive_config.json")
CONFIG_FILE_ORIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adaptive_config.json")

# Use the file that exists, prefer root path after moving to config/
CONFIG_FILE = CONFIG_FILE_ROOT if os.path.exists(CONFIG_FILE_ROOT) else CONFIG_FILE_ORIG

class AdaptiveConfig:
    def __init__(self, config_file=CONFIG_FILE):
        self.config_file = config_file
        self.config = self._load_config()
        
    def _load_config(self):
        """Load configuration or create defaults"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading configuration: {e}")
                
        # Default configuration
        return {
            "enabled": True,
            "confidence_adjustment_enabled": True,
            "cooldown_system_enabled": True,
            "directions_enabled": {
                "long": True,
                "short": True
            },
            "min_multiplier": 0.6,
            "max_multiplier": 1.4,
            "cooldown_durations": {
                "level_1": 6,
                "level_2": 12,
                "level_3": 24
            },
            "last_updated": datetime.now().isoformat()
        }
        
    def save_config(self):
        """Save configuration to file"""
        self.config["last_updated"] = datetime.now().isoformat()
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving configuration: {e}")
            return False
            
    def reload_config(self):
        """Reload configuration from file"""
        try:
            self.config = self._load_config()
        except Exception as e:
            print(f"Error reloading configuration: {e}")
    
    def is_enabled(self):
        """Check if the entire system is enabled"""
        self.reload_config()
        return self.config.get("enabled", True)
        
    def is_confidence_enabled(self):
        """Check if confidence adjustment is enabled"""
        # If whole system is disabled, this is also disabled
        if not self.is_enabled():
            return False
        self.reload_config()
        return self.config.get("confidence_adjustment_enabled", True)
        
    def is_cooldown_enabled(self):
        """Check if cooldown system is enabled"""
        # If whole system is disabled, this is also disabled
        if not self.is_enabled():
            return False
        self.reload_config()
        return self.config.get("cooldown_system_enabled", True)
        
    def get_multiplier_range(self):
        """Get multiplier range (min, max)"""
        self.reload_config()
        return (
            self.config.get("min_multiplier", 0.6),
            self.config.get("max_multiplier", 1.4)
        )
        
    def get_cooldown_hours(self, level):
        """Get cooldown hours for a specific level"""
        self.reload_config()
        levels = self.config.get("cooldown_durations", {
            "level_1": 6,
            "level_2": 12,
            "level_3": 24
        })
        
        key = f"level_{level}"
        if key in levels:
            return levels[key]
            
        # Fallback values
        defaults = {"level_1": 6, "level_2": 12, "level_3": 24}
        return defaults.get(key, 6)  # Default to 6 hours if not found

    # Setters
    def set_enabled(self, value):
        """Enable or disable entire system"""
        self.config["enabled"] = bool(value)
        self.save_config()
        self.reload_config()
        
    def set_confidence_enabled(self, value):
        """Enable or disable confidence adjustment"""
        self.config["confidence_adjustment_enabled"] = bool(value)
        self.save_config()
        self.reload_config()
        
    def set_cooldown_enabled(self, value):
        """Enable or disable cooldown system"""
        self.config["cooldown_system_enabled"] = bool(value)
        self.save_config()
        self.reload_config()
        
    def set_multiplier_range(self, min_val, max_val):
        """Set multiplier range"""
        self.config["min_multiplier"] = float(min_val)
        self.config["max_multiplier"] = float(max_val)
        self.save_config()
        self.reload_config()
        
    def set_cooldown_hours(self, level_1, level_2, level_3):
        """Set cooldown hours for all levels"""
        self.config["cooldown_durations"] = {
            "level_1": int(level_1),
            "level_2": int(level_2),
            "level_3": int(level_3)
        }
        self.save_config()
        self.reload_config()
        
    def is_direction_enabled(self, direction):
        """Check if a specific trading direction is enabled
        
        Args:
            direction: 'long' or 'short'
            
        Returns:
            bool: Whether the direction is enabled
        """
        direction = direction.lower()
        # If system is disabled, all directions are disabled
        if not self.is_enabled():
            return False
            
        self.reload_config()
        directions = self.config.get("directions_enabled", {"long": True, "short": True})
        return directions.get(direction, True)  # Default to enabled if not set
    
    def set_direction_enabled(self, direction, enabled):
        """Enable or disable a specific trading direction
        
        Args:
            direction: 'long' or 'short'
            enabled: True to enable, False to disable
            
        Returns:
            bool: Success
        """
        direction = direction.lower()
        
        # Ensure directions_enabled exists
        if "directions_enabled" not in self.config:
            self.config["directions_enabled"] = {"long": True, "short": True}
            
        # Set the direction's enabled status
        self.config["directions_enabled"][direction] = bool(enabled)
        success = self.save_config()
        self.reload_config()
        return success
        
    def get_direction_multiplier(self, direction):
        """Get confidence multiplier for a direction based on enabled status
        
        Args:
            direction: 'long' or 'short'
            
        Returns:
            float: 1.0 if enabled, 0.0001 if disabled
        """
        return 1.0 if self.is_direction_enabled(direction) else 0.0001

# Create singleton instance
config = AdaptiveConfig()
