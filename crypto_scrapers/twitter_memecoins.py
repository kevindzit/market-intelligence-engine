"""
Twitter Meme Coin Scraper
Tracks meme coin sentiment with volume tracking and bot filtering
Focus: Pure meme coins with high Twitter sensitivity
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from crypto_scrapers.twitter_token_base import TwitterTokenScraperBase

# MEME COIN LIST - Pure meme tokens with high Twitter sensitivity
TOKENS = [
    "PEPE",   # Massive Twitter community, high liquidity
    "DOGE",   # Elon tweets move it instantly
    "SHIB",   # Large community, responds to sentiment
    "BONK",   # Active Solana community
    "WIF"     # Newer, high volatility, Twitter-sensitive
]


class TwitterMemecoins(TwitterTokenScraperBase):
    def __init__(self):
        super().__init__(
            tokens=TOKENS,
            source="memecoins",
            scraper_name="Twitter Meme Coin Scraper"
        )


async def main():
    scraper = TwitterMemecoins()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())