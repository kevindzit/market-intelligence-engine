"""
Twitter Large Cap Scraper
Tracks top crypto by market cap - market-moving assets
Focus: BTC, ETH, SOL, BNB, XRP, ADA, TRX
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from crypto_scrapers.twitter_token_base import TwitterTokenScraperBase

# LARGE CAP TOKENS - Top 7 by market cap (market movers)
TOKENS = [
    "BTC",      # Bitcoin - $108K, 1.65M tweets/week, market leader
    "ETH",      # Ethereum - Top 2, 426K tweets/week, DeFi base
    "SOL",      # Solana - Top 5, 242K tweets/week, fast growth
    "BNB",      # Binance - 638K tweets/week, exchange dominance
    "XRP",      # Ripple - 141K tweets/week, institutional adoption
    "ADA",      # Cardano - $0.735, 120K tweets/week
    "TRX"       # Tron - $80.7B USDT hosted
]


class TwitterLargecaps(TwitterTokenScraperBase):
    def __init__(self):
        super().__init__(
            tokens=TOKENS,
            source="largecaps",
            scraper_name="Twitter Large Cap Scraper"
        )


async def main():
    scraper = TwitterLargecaps()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
