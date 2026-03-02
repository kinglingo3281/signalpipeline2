#!/usr/bin/env python
"""
Orderbook Adapter Module
----------------------
Adapter module for converting orderbook data formats between different representations.
Provides utility functions for standardizing orderbook data across the system.
"""

import os
import sys

# Add parent directory to path to allow imports from root after moving to utils/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def convert_orderbook_format(orderbook_data):
    """
    Converts orderbook data from dictionary format to list/tuple format
    
    Args:
        orderbook_data (dict): Orderbook data with 'bids' and 'asks' keys
        
    Returns:
        tuple: (bids, asks) where each is a list of (price, size) tuples
    """
    if not orderbook_data or not isinstance(orderbook_data, dict):
        print("Invalid orderbook data format")
        return None, None
    
    bids = orderbook_data.get("bids", [])
    asks = orderbook_data.get("asks", [])
    
    # Convert bids to list of (price, size) tuples
    formatted_bids = []
    for bid in bids:
        # Handle tuple format (already in the format we want)
        if isinstance(bid, tuple) and len(bid) == 2:
            formatted_bids.append((float(bid[0]), float(bid[1])))
        # Handle dictionary format
        elif isinstance(bid, dict) and "price" in bid and "size" in bid:
            formatted_bids.append((float(bid["price"]), float(bid["size"])))
    
    # Convert asks to list of (price, size) tuples
    formatted_asks = []
    for ask in asks:
        # Handle tuple format (already in the format we want)
        if isinstance(ask, tuple) and len(ask) == 2:
            formatted_asks.append((float(ask[0]), float(ask[1])))
        # Handle dictionary format
        elif isinstance(ask, dict) and "price" in ask and "size" in ask:
            formatted_asks.append((float(ask["price"]), float(ask["size"])))
    
    # Sort bids in descending order by price (highest first)
    formatted_bids.sort(key=lambda x: x[0], reverse=True)
    
    # Sort asks in ascending order by price (lowest first)
    formatted_asks.sort(key=lambda x: x[0])
    
    return formatted_bids, formatted_asks
