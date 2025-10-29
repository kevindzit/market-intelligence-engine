"""
Twitter AI/ML Scraper
Tracks AI and machine learning crypto token sentiment
Focus: AI/ML sector - sentiment drives narrative cycles and hype
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from crypto_scrapers.twitter_token_base import TwitterTokenScraperBase

# AI/ML TOKENS - Artificial intelligence and machine learning (narrative-driven sector)
TOKENS = [
    "RENDER",   # Render Network - $3.4B cap, decentralized GPU rendering
    "FET",      # Fetch.ai - $2.8B cap, autonomous AI agents
    "GRT",      # The Graph - $2.3B cap, blockchain data indexing
    "OCEAN",    # Ocean Protocol - Data marketplace for AI
    "AGIX",     # SingularityNET - AGI marketplace
    "TAO",      # Bittensor - Decentralized ML network
    "RNDR"      # Alternative ticker for Render (used interchangeably)
]


class TwitterAI(TwitterTokenScraperBase):
    def __init__(self):
        super().__init__(
            tokens=TOKENS,
            source="ai",
            scraper_name="Twitter AI/ML Scraper"
        )


async def main():
    scraper = TwitterAI()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
