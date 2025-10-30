"""
Twitter Emerging Layer 1 Scraper
Tracks new high-performance Layer 1 blockchains
Focus: Emerging L1s with strong 2024-2025 performance and Twitter momentum
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from crypto_scrapers.twitter_token_base import TwitterTokenScraperBase

# EMERGING L1 TOKENS - New high-performance chains (narrative-driven, strong Twitter presence)
TOKENS = [
    "SUI",      # Sui - $2.46, 90% bullish sentiment, $885M TVL, strong Oct 2025 performance
    "TON",      # Telegram - $2.12, 87M US users, 900M+ potential, corporate treasury adoption
    "SEI"       # Sei - $0.27, first parallelized EVM, Hamilton Lane fund launch Oct 2025
]


class TwitterEmerging(TwitterTokenScraperBase):
    def __init__(self):
        super().__init__(
            tokens=TOKENS,
            source="emerging",
            scraper_name="Twitter Emerging L1 Scraper"
        )


async def main():
    scraper = TwitterEmerging()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
