from __future__ import annotations

import pytest

from app.posting.content_renderer import NoAlertEventError, build_post


def test_market_snapshot_contains_symbol_source_and_disclaimer(
    analysis_fixture: dict,
) -> None:
    post = build_post("market_snapshot", analysis=analysis_fixture)

    assert "BTCUSDT" in post
    assert "Bybit" in post
    assert "финсовет" in post
    assert len(post) < 4096


def test_daily_summary_requires_at_least_three_symbols(
    daily_summary_analyses: list[dict],
) -> None:
    with pytest.raises(ValueError, match="at least 3 symbols"):
        build_post("daily_summary", analyses=daily_summary_analyses[:2])


def test_daily_summary_renders_all_core_symbols(
    daily_summary_analyses: list[dict],
) -> None:
    post = build_post("daily_summary", analyses=daily_summary_analyses)

    assert "BTC" in post
    assert "ETH" in post
    assert "SOL" in post
    assert "Bybit" in post
    assert len(post) < 4096


def test_alert_raises_when_no_event_detected(analysis_fixture: dict) -> None:
    analysis_fixture["volume"]["ratio"] = 1.0
    analysis_fixture["funding"]["percent"] = 0.01
    analysis_fixture["open_interest"]["change_24h_percent"] = 0.5
    analysis_fixture["rsi"]["value"] = 50

    with pytest.raises(NoAlertEventError):
        build_post("alert", analysis=analysis_fixture)
