"""
Twitter Layer 2 Scraper
Tracks Ethereum Layer 2 scaling solution sentiment
Focus: Ethereum L2s - sentiment drives TVL migration and ecosystem growth
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from crypto_scrapers.twitter_token_base import TwitterTokenScraperBase

# LAYER 2 TOKENS - Ethereum scaling solutions (sentiment drives L2 migration)
TOKENS = [
    "ARB",      # Arbitrum - $12.5B TVL, largest L2, DAO governance
    "OP",       # Optimism - $7.8B TVL, OP Stack, superchain vision
    "MATIC",    # Polygon - $4.5B TVL, zkEVM, enterprise adoption
    "METIS",    # Metis - Optimistic rollup, decentralized sequencer
    "IMX"       # Immutable X - Gaming/NFT L2, StarkEx-based
]


class TwitterLayer2s(TwitterTokenScraperBase):
    def __init__(self):
        super().__init__(
            tokens=TOKENS,
            source="layer2s",
            scraper_name="Twitter Layer 2 Scraper"
        )


async def main():
    scraper = TwitterLayer2s()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
