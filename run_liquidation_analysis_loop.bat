@echo off
echo Enhanced Liquidation Analysis Automation with BTC Correlation
echo This script will run the automated liquidation analysis pipeline every 3 hours
echo Press Ctrl+C to stop the loop

:loop
echo.
echo Starting analysis at %time% on %date%
echo ========================================================

REM Set batch mode environment variable to skip interactive prompts
set BATCH_MODE=1

REM Activate virtual environment if needed
cd /d "%~dp0"
call env\Scripts\activate

REM Return to main directory
cd /d "%~dp0"

REM Step 1: Fetch latest trader data
echo Running data collection script with 15-minute force exit timer...
echo Make sure to include BTC data for correlation analysis
python data_collection\fetch_top_traders.py --timeout 15

REM Wait 5 seconds before running the next script
echo Waiting 5 seconds before running enhanced analysis...
timeout /t 5 /nobreak

REM Step 2: Run enhanced liquidation analysis without BTC correlation
echo Running enhanced liquidation analysis without BTC correlation...
REM Set BTC correlation to disabled by default
set NO_BTC_CORRELATION=1
REM Check if BTC correlation should be disabled
if "%NO_BTC_CORRELATION%"=="1" (
    echo BTC correlation analysis is DISABLED
    python analysis\enhanced_liquidation_analysis.py --no-btc-correlation
) else (
    echo BTC correlation analysis is ENABLED
    
    REM First analyze BTC only to ensure file exists
    echo Running BTC analysis first...
    python analysis\enhanced_liquidation_analysis.py --asset BTC
    
    REM Then analyze all other assets with BTC correlation (skip BTC to avoid duplicate)
    echo Running analysis for all other assets...
    python analysis\enhanced_liquidation_analysis.py --skip-asset BTC
)

REM Step 3: Run cleanup script for old files
echo Running cleanup script for old files...
python helpers\cleanup_old_files.py

REM Step 3.5: Run database cleanup
echo Running database cleanup...
python helpers\db_cleanup.py

REM Step 4: Collect best trade recommendations
echo Collecting best trade recommendations...
python trading\collect_best_trades.py

echo.
echo Analysis complete at %time%

REM Show summary of BTC correlation results if available
if exist "data\btc_correlation" (
    echo BTC correlation results available in data\btc_correlation
    echo Listing correlation-enhanced files:
    dir /b "data\btc_correlation"
)

echo Waiting 30 minutes until next run...
echo ========================================================
echo.

REM Sleep for 30 minutes (1800 seconds)
timeout /t 1800 /nobreak

echo.
goto loop
