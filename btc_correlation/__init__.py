"""
BTC Correlation Analysis Package
-------------------------------
Provides tools to enhance altcoin liquidation analysis by leveraging BTC price data.

This package contains:
- correlation_engine.py: Multi-timeframe correlation calculator
- beta_calculator.py: Volatility regime-specific beta calculator
- cluster_translator.py: BTC cluster to altcoin price level translator
- json_enhancer.py: JSON output enhancer for BTC-derived signals
"""

from btc_correlation.correlation_engine import DynamicCorrelationEngine
from btc_correlation.beta_calculator import CryptoBetaCalculator
from btc_correlation.cluster_translator import BTCClusterTranslator
from btc_correlation.json_enhancer import CorrelationJSONEnhancer

# Import the main analysis class from __main__.py
from btc_correlation.__main__ import BTCCorrelationAnalysis

__all__ = [
    'BTCCorrelationAnalysis',
    'DynamicCorrelationEngine',
    'CryptoBetaCalculator',
    'BTCClusterTranslator',
    'CorrelationJSONEnhancer'
]
