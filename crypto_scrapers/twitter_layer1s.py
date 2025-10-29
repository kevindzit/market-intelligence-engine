"""
Twitter Layer 1 Scraper
Tracks alternative Layer 1 blockchain sentiment
Focus: Alternative L1s competing with Ethereum - sentiment drives adoption and TVL
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from crypto_scrapers.twitter_token_base import TwitterTokenScraperBase

# LAYER 1 TOKENS - Alternative L1 blockchains (sentiment drives ecosystem growth)
TOKENS = [
    "AVAX",     # Avalanche - $10.8B cap, subnet innovation, AWS partnership
    "DOT",      # Polkadot - $7.4B cap, parachain auctions, interoperability
    "NEAR",     # NEAR Protocol - $5.5B cap, chain abstraction leader
    "ATOM",     # Cosmos - $7.8B cap, IBC ecosystem hub
    "ICP",      # Internet Computer - $3.7B cap, on-chain compute
    "ALGO",     # Algorand - $6.6B cap, enterprise adoption
    "FTM"       # Fantom - DeFi hub, Sonic rebranding upcoming
]


class TwitterLayer1s(TwitterTokenScraperBase):
    def __init__(self):
        super().__init__(
            tokens=TOKENS,
            source="layer1s",
            scraper_name="Twitter Layer 1 Scraper"
        )


async def main():
    scraper = TwitterLayer1s()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
