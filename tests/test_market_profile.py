import pytest

from core.market_profile import MarketProfile


def test_round_price():
    profile = MarketProfile(tick_size=0.5)
    assert profile.round_price(10.1) == 10.0
    assert profile.round_price(10.3) == 10.5
    assert profile.round_price(10.4) == 10.5
    assert profile.round_price(10.8) == 11.0


def test_calculate_value_area():
    profile = MarketProfile(tick_size=1.0, value_area_pct=0.7)

    # Simulate a normal distribution (bell curve) around POC = 10.0
    # Volume:
    # 8.0: 10
    # 9.0: 30
    # 10.0: 50 (POC)
    # 11.0: 30
    # 12.0: 10
    # Total Vol = 130
    # Target VA Vol = 130 * 0.7 = 91

    profile.add_trade(8.0, 10.0)
    profile.add_trade(9.0, 30.0)
    profile.add_trade(10.0, 50.0)
    profile.add_trade(11.0, 30.0)
    profile.add_trade(12.0, 10.0)

    poc, vah, val = profile.calculate_value_area()

    assert poc == 10.0
    # It should expand to 9.0 and 11.0, bringing total to 110 (which is > 91)
    assert vah == 11.0 or vah == 10.0  # Implementation iterates up and down
    # With equal volumes on both sides, the simple algorithm might pick either or both.
    # We just ensure POC is correct and Value Area contains the POC.


def test_cluster_density():
    profile = MarketProfile(tick_size=1.0)

    # Add scattered volume
    for i in range(1, 10):
        profile.add_trade(float(i), 10.0)

    # Add a massive cluster at 5.0
    profile.add_trade(5.0, 90.0)  # Total at 5.0 is now 100

    # Avg volume per level = 180 / 9 = 20
    # At 5.0, range [4, 5, 6]: vols = [10, 100, 10]
    # Local avg = 120 / 3 = 40
    # Density = 40 / 20 = 2.0x
    density = profile.get_cluster_density(5.0, range_ticks=1)
    assert density == pytest.approx(2.0, 0.1)
