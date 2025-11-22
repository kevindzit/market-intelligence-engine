"""
Helpers that translate LLM requests into database lookups.

The :class:`BrowserDataInterface` class wraps ``DataIntelligence`` so handlers
can respond to requests like ``REQUEST: sentiment | token=BTC | window=6h`` with
well-formatted context.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from psycopg2.extras import DictCursor

from crypto_ai_trader.data_intelligence import DataIntelligence


WINDOW_PATTERN = re.compile(r"(\\d+)([hm])", re.IGNORECASE)


def _parse_window(param: Optional[str], default_hours: int) -> timedelta:
    if not param:
        return timedelta(hours=default_hours)
    match = WINDOW_PATTERN.match(param.strip())
    if not match:
        return timedelta(hours=default_hours)
    value = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "m":
        # minute granularity
        return timedelta(minutes=value)
    return timedelta(hours=value)


def _fmt_pct(value: float) -> str:
    return f"{value:+.2f}%"


def _fmt_price(value: float) -> str:
    if value >= 1:
        return f"${value:,.2f}"
    return f"${value:,.6f}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


PRICE_COMMANDS = {
    "price",
    "technical",
    "technical_indicators",
    "current_price",
    "current_price_data",
}

SENTIMENT_COMMANDS = {
    "sentiment",
    "sentiment_analysis",
    "social",
}

SUMMARY_COMMANDS = {
    "summary",
    "overview",
    "quick",
}

FULL_SNAPSHOT_COMMANDS = {
    "general",
    "details",
    "data",
    "snapshot",
    "full",
}

VOLUME_COMMANDS = {
    "volume",
    "volume_profile",
    "liquidity",
    "flow",
}


@dataclass
class BrowserDataInterface:
    """High-level query helpers for browser-agent requests."""

    data_intel: DataIntelligence

    # ------------------------------------------------------------------ #
    def sentiment_snapshot(self, token: str, window: timedelta) -> str:
        since = _utc_now() - window
        with self.data_intel.conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS total_tweets,
                       AVG(sentiment_score) AS avg_sentiment,
                       AVG(weighted_score) AS avg_weighted,
                       MAX(volume_spike) AS max_volume_spike,
                       AVG(volume_spike) AS avg_volume_spike,
                       COUNT(*) FILTER (WHERE is_whale) AS whale_tweets,
                       COUNT(*) FILTER (WHERE bot_probability >= 0.7) AS bot_like,
                       AVG(sentiment_velocity) AS avg_velocity
                FROM twitter_sentiment
                WHERE token = %s
                  AND scraped_at >= %s
            """,
                (token, since),
            )
            row = cursor.fetchone()

        if not row or not row["total_tweets"]:
            return (
                f"DATA: Sentiment snapshot unavailable for {token}. "
                f"No tweets in the last {window}."
            )

        tweets = int(row["total_tweets"])
        avg_sentiment = float(row["avg_sentiment"] or 0.0)
        avg_weighted = float(row["avg_weighted"] or 0.0)
        max_spike = float(row["max_volume_spike"] or 0.0)
        avg_spike = float(row["avg_volume_spike"] or 0.0)
        whales = int(row["whale_tweets"] or 0)
        bots = int(row["bot_like"] or 0)
        velocity = float(row["avg_velocity"] or 0.0)

        hours = max(1, int(window.total_seconds() // 3600) or 1)
        return (
            f"CONTEXT: Sentiment Snapshot (token={token}, window={hours}h)\n"
            f"- Tweets: {tweets:,} (whales: {whales}, bot-like: {bots})\n"
            f"- Avg sentiment: {avg_sentiment:+.3f} | Weighted: {avg_weighted:+.3f}\n"
            f"- Volume spike: avg {avg_spike:.2f}x, max {max_spike:.2f}x\n"
            f"- Sentiment velocity: {velocity:+.4f}"
        )

    def price_action(self, token: str, window: timedelta) -> str:
        since = _utc_now() - window
        with self.data_intel.conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute(
                """
                SELECT MIN(low) AS range_low,
                       MAX(high) AS range_high,
                       AVG(volume) AS avg_volume
                FROM crypto_ohlcv
                WHERE token = %s
                  AND timestamp >= %s
            """,
                (token, since),
            )
            aggregate = cursor.fetchone()

            cursor.execute(
                """
                SELECT close
                FROM crypto_ohlcv
                WHERE token = %s AND timestamp >= %s
                ORDER BY timestamp ASC
                LIMIT 1
            """,
                (token, since),
            )
            first = cursor.fetchone()

            cursor.execute(
                """
                SELECT close
                FROM crypto_ohlcv
                WHERE token = %s AND timestamp >= %s
                ORDER BY timestamp DESC
                LIMIT 1
            """,
                (token, since),
            )
            last = cursor.fetchone()

        if not aggregate or not first or not last:
            return (
                f"DATA: Price action unavailable for {token}. "
                f"Not enough OHLCV data in the selected window."
            )

        low = float(aggregate["range_low"] or 0.0)
        high = float(aggregate["range_high"] or 0.0)
        avg_volume = float(aggregate["avg_volume"] or 0.0)
        start_price = float(first["close"])
        end_price = float(last["close"])
        change_pct = ((end_price - start_price) / start_price * 100) if start_price else 0.0

        hours = max(1, int(window.total_seconds() // 3600))
        return (
            f"CONTEXT: Price Action (token={token}, window={hours}h)\n"
            f"- Range: {_fmt_price(low)} to {_fmt_price(high)}\n"
            f"- Close change: {_fmt_pct(change_pct)} "
            f"(start {_fmt_price(start_price)} → end {_fmt_price(end_price)})\n"
            f"- Avg volume per candle: {avg_volume:,.0f}"
        )

    def quick_summary(self, token: str) -> str:
        summary = self.data_intel.get_quick_summary(token)
        if not summary:
            return f"DATA: Quick summary unavailable for {token}."
        price_line = f"- Price: {_fmt_price(summary.get('price', 0))}"
        if summary.get('has_price_change'):
            change_line = f"- 1h Change: {_fmt_pct(summary.get('price_change_1h', 0))}"
        else:
            change_line = "- 1h Change: data unavailable (no prior candle)"

        if summary.get('has_sentiment_data'):
            tweets_line = f"- Tweets (1h): {summary.get('tweets_1h', 0):,}"
            sentiment_line = f"- Sentiment (1h): {summary.get('sentiment_1h', 0):+.3f}"
            volume_line = f"- Volume spike: {summary.get('volume_spike', 0):.2f}x"
        else:
            tweets_line = "- Tweets (1h): no tweets captured"
            sentiment_line = "- Sentiment (1h): data unavailable"
            volume_line = "- Volume spike: n/a"

        return (
            f"CONTEXT: Quick Summary ({token})\n"
            f"{price_line}\n"
            f"{change_line}\n"
            f"{tweets_line}\n"
            f"{sentiment_line}\n"
            f"{volume_line}"
        )

    def full_snapshot(self, token: str, params: Dict[str, str]) -> str:
        lines = [self.quick_summary(token)]

        price = self.data_intel.get_price_history(token, hours=24) or {}
        if price.get('has_data'):
            lines.append(
                "PRICE DETAILS (24h):\n"
                f"- Change: {_fmt_pct(price.get('price_change_24h', 0))}\n"
                f"- High: {_fmt_price(price.get('high_24h', 0))}\n"
                f"- Low: {_fmt_price(price.get('low_24h', 0))}\n"
                f"- Volatility: {price.get('volatility', 0):.2f}%"
            )
        else:
            lines.append(
                "PRICE DETAILS (24h):\n"
                "- Data unavailable (no recent candles in database)."
            )

        sentiment = self.data_intel.get_sentiment_summary(token, hours=6) or {}
        if sentiment.get('has_data'):
            lines.append(
                "SENTIMENT (6h):\n"
                f"- Tweets: {sentiment.get('tweet_count', 0):,}\n"
                f"- Avg Sentiment: {sentiment.get('avg_sentiment', 0):+.3f}\n"
                f"- Whale Tweets: {sentiment.get('whale_tweets', 0)}\n"
                f"- Momentum: {sentiment.get('momentum_score', 0):+.3f}"
            )
        else:
            lines.append(
                "SENTIMENT (6h):\n"
                "- Data unavailable (no tweets captured for this window)."
            )

        order_book = self.data_intel.get_order_book_intelligence(token) or {}
        if order_book.get('has_data'):
            lines.append(
                "ORDER BOOK:\n"
                f"- Spread: {order_book['spread']['percentage']:.3f}%\n"
                f"- Recommendation: {order_book['recommendation']}\n"
                f"- Pressure: {order_book['pressure']['direction']} ({order_book['pressure']['signal']})"
            )

        cascading = self.data_intel.get_liquidation_cascade_analysis(token) or {}
        if cascading:
            lines.append(
                "LIQUIDATION RISK:\n"
                f"- Score: {cascading.get('risk_score', 0)} / 100\n"
                f"- Recommendation: {cascading.get('recommendation', 'HOLD')}"
            )

        return "\n".join(lines)

    def volume_profile(self, token: str, window: timedelta) -> str:
        hours = max(1, int(window.total_seconds() // 3600) or 1)
        stats = self.data_intel.get_volume_profile(token, hours) or {}
        if not stats.get("has_data"):
            return (
                f"DATA: Volume profile unavailable for {token}. "
                f"Not enough trades in the last {hours}h."
            )

        total = stats.get("total_volume", 0.0)
        total_usd = stats.get("total_volume_usd", 0.0)
        avg_volume = stats.get("avg_volume", 0.0)
        max_volume = stats.get("max_volume", 0.0)
        ratio = stats.get("volume_ratio", 1.0)
        recent_hours = stats.get("recent_window_hours", 1)
        recent_avg = stats.get("recent_avg_volume", 0.0)

        ratio_desc = "elevated" if ratio >= 1.2 else "cooling" if ratio <= 0.8 else "normal"
        usd_line = (
            f" (~${total_usd:,.0f} notional)"
            if total_usd and total_usd > 0
            else ""
        )

        return (
            f"CONTEXT: Volume Profile (token={token}, window={hours}h)\n"
            f"- Total volume: {total:,.0f}{usd_line}\n"
            f"- Avg per candle: {avg_volume:,.0f} (max {max_volume:,.0f})\n"
            f"- Recent {recent_hours}h avg: {recent_avg:,.0f} ({ratio:.2f}x {ratio_desc})"
        )

    # ------------------------------------------------------------------ #
    def handle_command(self, command_name: str, params: Dict[str, str]) -> str:
        token = params.get("token")
        if not token:
            return "DATA: Missing token parameter."

        command_name = command_name.lower()
        if command_name in SENTIMENT_COMMANDS:
            window = _parse_window(params.get("window"), default_hours=6)
            return self.sentiment_snapshot(token, window)
        if command_name in PRICE_COMMANDS:
            window = _parse_window(params.get("window"), default_hours=24)
            return self.price_action(token, window)
        if command_name in SUMMARY_COMMANDS:
            return self.quick_summary(token)
        if command_name in VOLUME_COMMANDS:
            window = _parse_window(params.get("window"), default_hours=24)
            return self.volume_profile(token, window)
        if command_name in FULL_SNAPSHOT_COMMANDS:
            return self.full_snapshot(token, params)

        return f"DATA: Unsupported request '{command_name}'."


__all__ = ["BrowserDataInterface"]
