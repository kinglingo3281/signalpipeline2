#!/usr/bin/env python
"""
Database Cleanup Script
-----------------------
This script calls PostgreSQL cleanup functions to remove old database records.
Designed to be called from the liquidation analysis loop.
"""

import psycopg2
import os
from datetime import datetime

def cleanup_database():
    """
    Calls PostgreSQL cleanup functions to remove old records.
    """
    try:
        # Database connection string
        db_url = os.getenv('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/sse_dashboard')
        
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting database cleanup...")
        
        # Connect to database
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Clean up old comprehensive_trades (10+ days old)
        cursor.execute('SELECT cleanup_old_comprehensive_trades(10)')
        trades_deleted = cursor.fetchone()[0]
        
        # Clean up old analysis_sessions (30+ days old)
        cursor.execute('SELECT cleanup_old_analysis_data(30)')
        analysis_deleted = cursor.fetchone()[0]
        
        # Commit the changes
        conn.commit()
        
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Database cleanup complete:")
        print(f"  - {trades_deleted} old trade records deleted")
        print(f"  - {analysis_deleted} old analysis sessions deleted")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Database cleanup failed: {e}")
        return False

if __name__ == "__main__":
    cleanup_database()
