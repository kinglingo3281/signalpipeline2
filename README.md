> **Public portfolio snapshot:** This repository is a sanitized export of selected components from a larger private production system developed between 2023 and 2026. Original Git history, production credentials, user information, private endpoints, proprietary logic, restricted integrations, internal infrastructure, and some newer revisions are intentionally excluded. The public commit demonstrates selected architecture and implementation work; it does not represent the original development timeline or a complete production deployment.

# Liquidation Analysis Pipeline

Automated pipeline that fetches trader positions from Hyperliquid, performs liquidation analysis with cascade probability modeling, and outputs enhanced JSON analysis files consumed by the SSE server for real-time client distribution.

## Architecture

This is the analysis pipeline that feeds the SSE server, which streams data to the trading terminal:

```
┌───────────────────────┐    JSON files     ┌──────────────┐    SSE stream    ┌──────────────────┐
│  Analysis Pipeline    │ ────────────────> │  SSE Server   │ ──────────────> │ Trading Terminal  │
│  (this repo)          │  file watcher     │  (pipelineSSE)│                 │ (cryptoterminal)  │
│                       │                   │               │                 │                   │
│  1. Fetch traders     │                   └───────┬───────┘                 └──────────────────┘
│  2. Liquidation analysis                          ▲
│  3. Cleanup old files │                           │ webhook
│  4. Best trade recs   │               ┌───────────────────┐
│                       │               │  Signal Pipeline   │
└───────────────────────┘               │  (signalpipeline1) │
                                        └───────────────────┘
```

### Data Flow

1. **Fetch top traders** — Pulls position data from multiple Hyperliquid leaderboard sources in parallel
2. **Enhanced liquidation analysis** — For each asset, calculates liquidation levels, cascade probabilities, support/resistance, Fibonacci levels, risk analysis, and market context
3. **Output** — Writes `{ASSET}_enhanced_analysis_{timestamp}.json` files to a watched directory. The SSE server's `EnhancedDataWatcher` picks these up and broadcasts to connected clients
4. **Cleanup** — Removes old analysis files and stale database records
5. **Best trade recommendations** — Aggregates analysis results into actionable trade signals with confidence scoring

## Pipeline Steps (runs every 30 minutes)

| Step | Script | Description |
|------|--------|-------------|
| 1 | `data_collection/fetch_top_traders.py` | Fetches trader positions from Hyperliquid, analyzes liquidation levels and orderbook impact |
| 2 | `analysis/enhanced_liquidation_analysis.py` | Deep analysis: clusters, cascades, price targets, risk scoring, market context |
| 3 | `helpers/cleanup_old_files.py` | Removes analysis files older than 3 days |
| 3.5 | `helpers/db_cleanup.py` | Cleans up old database records (PostgreSQL) |
| 4 | `trading/collect_best_trades.py` | Produces ranked trade recommendations with adaptive confidence |

## Project Structure

```
├── run_liquidation_analysis_loop.bat/.sh   # Entry points (loop every 30 min)
├── data_collection/
│   └── fetch_top_traders.py                # Hyperliquid trader data fetcher
├── analysis/
│   ├── enhanced_liquidation_analysis.py    # Core analysis engine
│   ├── liquidation_clusters.py             # Cluster identification
│   ├── cascade_analysis.py                 # Cascade probability simulation
│   ├── risk_analyzer.py                    # Risk scoring
│   ├── cluster_analysis.py                 # Extended cluster analysis
│   └── daily_trading_analysis.py           # Daily aggregation
├── trading/
│   ├── collect_best_trades.py              # Trade recommendation engine
│   └── adaptive_trading.py                 # Adaptive confidence system
├── utils/
│   ├── price_targeting.py                  # Price target generation
│   ├── market_context.py                   # Market regime detection
│   ├── fibonacci_levels.py                 # Fibonacci level calculation
│   ├── trade_adjusters.py                  # Trade parameter adjustments
│   ├── market_alignment.py                 # Multi-timeframe alignment
│   ├── market_impact_enhancement.py        # Market impact modeling
│   └── orderbook_adapter.py               # Orderbook data adapter
├── config/
│   ├── support_resistance_config.py        # S/R detection parameters
│   ├── market_bias_config.py               # Market bias settings
│   ├── adaptive_config.py                  # Adaptive system config
│   └── risk_reward_config.py               # Risk/reward parameters
├── visualization/
│   ├── enhanced_heatmap.py                 # Liquidation heatmap generation
│   └── actionable_entry_visualization.py   # Entry point visualization
├── btc_correlation/                        # BTC correlation analysis (optional)
├── trading_view_integration.py             # TradingView chart integration
├── taapi_fallback.py                       # TAAPI technical indicator fallback
└── helpers/
    ├── cleanup_old_files.py                # File cleanup utility
    └── db_cleanup.py                       # Database cleanup utility
```

## Setup

### Prerequisites

- Python 3.8+
- PostgreSQL (for database cleanup, optional)
- Virtual environment recommended

### Installation

```bash
python -m venv env
source env/bin/activate  # Linux
# or: env\Scripts\activate  # Windows

pip install -r requirements.txt
```

### Configuration

The pipeline uses Hyperliquid's public API (no API keys needed for data fetching). Optional configuration:

- **BTC Correlation** — Enabled/disabled via `NO_BTC_CORRELATION` env var (default: disabled)
- **TAAPI Fallback** — If using taapi.io for technical indicators, pass your API key to `TaapiProvider`
- **Database** — Set `DATABASE_URL` env var for PostgreSQL cleanup features
- **Output Directory** — Analysis JSON files are written to `data/visualizations/` by default

### Running

**Linux:**
```bash
./run_liquidation_analysis_loop.sh
```

**Windows:**
```bat
run_liquidation_analysis_loop.bat
```

The loop runs continuously, executing the full pipeline every 30 minutes.

**Single run (no loop):**
```bash
python data_collection/fetch_top_traders.py --timeout 15
python analysis/enhanced_liquidation_analysis.py --no-btc-correlation
python helpers/cleanup_old_files.py
python trading/collect_best_trades.py
```

## Output

Each analysis cycle produces JSON files per asset:
- `{ASSET}_enhanced_analysis_{timestamp}.json` — Full analysis with liquidation clusters, cascade probabilities, price targets, risk scores, and market context

These files are consumed by the SSE server's file watcher for real-time distribution to the trading terminal.
