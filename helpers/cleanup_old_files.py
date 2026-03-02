#!/usr/bin/env python
"""
Cleanup Script
--------------
This script deletes PNG and JSON files older than 30 days from the data directories.
"""

import os
import time
import datetime

def cleanup_old_files(days=3):
    """
    Deletes PNG, JSON, and CSV files older than the specified number of days
    from the data directories.
    
    Args:
        days: Number of days to keep files (default: 3)
    """
    # Calculate the cutoff timestamp
    cutoff_time = time.time() - (days * 24 * 60 * 60)
    
    # Use project-root-relative paths
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    directories = [
        os.path.join(project_root, "data"),
        os.path.join(project_root, "data", "visualizations"),
        os.path.join(project_root, "data", "enhanced_analysis"),
        os.path.join(project_root, "data", "sim_trades"),
        os.path.join(project_root, "data", "btc_correlation"),
    ]
    
    total_removed = 0
    
    print(f"Cleaning up files older than {days} days ({datetime.datetime.fromtimestamp(cutoff_time).strftime('%Y-%m-%d %H:%M:%S')})")
    
    # Check each directory
    for directory in directories:
        if not os.path.exists(directory):
            print(f"Directory does not exist: {directory}")
            continue
            
        print(f"Checking directory: {directory}")
        
        # Go through each file in the directory
        for filename in os.listdir(directory):
            if filename.lower().endswith(('.png', '.json', '.csv')):
                filepath = os.path.join(directory, filename)
                
                # Get the last modification time
                file_time = os.path.getmtime(filepath)
                
                # If the file is older than the cutoff
                if file_time < cutoff_time:
                    try:
                        os.remove(filepath)
                        print(f"Removed: {filepath}")
                        total_removed += 1
                    except Exception as e:
                        print(f"Error removing {filepath}: {e}")
    
    print(f"Cleanup complete. Removed {total_removed} old files.")

if __name__ == "__main__":
    cleanup_old_files(3)
