"""Unit tests for the deterministic risk math in utils.price_targeting.

These cover the pure stop-loss and momentum-probability functions that gate
every generated signal, using fixed inputs so results are fully deterministic.
"""

import pytest

from utils.price_targeting import (
    adjust_probability_for_momentum,
    calculate_dynamic_stop_loss,
)


class TestCalculateDynamicStopLoss:
    def test_long_uses_default_percentage(self):
        # 2.5% below entry for a long with no volatility input
        assert calculate_dynamic_stop_loss(100.0, "long") == pytest.approx(97.5)

    def test_short_uses_default_percentage(self):
        # 2.5% above entry for a short
        assert calculate_dynamic_stop_loss(100.0, "short") == pytest.approx(102.5)

    def test_custom_default_percentage(self):
        assert calculate_dynamic_stop_loss(200.0, "long", default_pct=0.01) == pytest.approx(198.0)

    def test_volatility_widens_stop_within_upper_clamp(self):
        # volatility * 0.5 = 0.04 -> clamped to the 0.025 maximum
        assert calculate_dynamic_stop_loss(100.0, "long", asset_volatility=0.08) == pytest.approx(97.5)

    def test_low_volatility_clamped_to_floor(self):
        # volatility * 0.5 = 0.005 -> clamped up to the 0.015 minimum
        assert calculate_dynamic_stop_loss(100.0, "long", asset_volatility=0.01) == pytest.approx(98.5)

    def test_mid_volatility_scales_linearly(self):
        # volatility * 0.5 = 0.02, inside the [0.015, 0.025] band
        assert calculate_dynamic_stop_loss(100.0, "short", asset_volatility=0.04) == pytest.approx(102.0)

    def test_stop_is_always_on_protective_side(self):
        entry = 3_500.0
        assert calculate_dynamic_stop_loss(entry, "long", asset_volatility=0.05) < entry
        assert calculate_dynamic_stop_loss(entry, "short", asset_volatility=0.05) > entry


class TestAdjustProbabilityForMomentum:
    def test_returns_base_probability_without_history(self):
        assert adjust_probability_for_momentum(0.6, "long", 100.0) == 0.6
        assert adjust_probability_for_momentum(0.6, "long", 100.0, price_1h_ago=None) == 0.6

    def test_ignores_non_positive_historical_price(self):
        assert adjust_probability_for_momentum(0.6, "long", 100.0, price_1h_ago=0) == 0.6
        assert adjust_probability_for_momentum(0.6, "long", 100.0, price_1h_ago=-5) == 0.6

    def test_upward_momentum_boosts_long_probability(self):
        adjusted = adjust_probability_for_momentum(0.5, "long", 105.0, price_1h_ago=100.0)
        assert adjusted > 0.5

    def test_upward_momentum_reduces_short_probability(self):
        adjusted = adjust_probability_for_momentum(0.5, "short", 105.0, price_1h_ago=100.0)
        assert adjusted < 0.5

    def test_downward_momentum_boosts_short_probability(self):
        adjusted = adjust_probability_for_momentum(0.5, "short", 95.0, price_1h_ago=100.0)
        assert adjusted > 0.5

    def test_momentum_factor_saturates(self):
        # A 5% move and a 50% move both saturate the momentum factor at 1.0,
        # so both produce the same maximum +0.2 adjustment for a long.
        five_pct = adjust_probability_for_momentum(0.5, "long", 105.0, price_1h_ago=100.0)
        fifty_pct = adjust_probability_for_momentum(0.5, "long", 150.0, price_1h_ago=100.0)
        assert five_pct == pytest.approx(0.7)
        assert fifty_pct == pytest.approx(0.7)

    def test_probability_clamped_to_upper_bound(self):
        adjusted = adjust_probability_for_momentum(0.9, "long", 110.0, price_1h_ago=100.0)
        assert adjusted == pytest.approx(0.95)

    def test_probability_clamped_to_lower_bound(self):
        adjusted = adjust_probability_for_momentum(0.1, "long", 90.0, price_1h_ago=100.0)
        assert adjusted == pytest.approx(0.05)

    def test_flat_price_leaves_probability_unchanged(self):
        assert adjust_probability_for_momentum(0.5, "long", 100.0, price_1h_ago=100.0) == pytest.approx(0.5)
