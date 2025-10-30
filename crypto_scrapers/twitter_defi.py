"""
Twitter DeFi Scraper
Tracks DeFi protocol sentiment with volume tracking and bot filtering
Focus: Major DeFi protocols - sentiment drives TVL flows and governance
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
from crypto_scrapers.twitter_token_base import TwitterTokenScraperBase

# DEFI TOKENS - Major DeFi protocols (sentiment drives TVL flows)
TOKENS = [
    "UNI",      # Uniswap - $7.5B TVL, largest DEX, 85K tweets/week
    "AAVE",     # Aave - $20B TVL, leading lending protocol
    "LDO",      # Lido - $34B TVL, liquid staking dominance
    "MKR",      # MakerDAO - $8B TVL, DAI stablecoin issuer
    "CRV",      # Curve - $4.2B TVL, stablecoin DEX, gauge wars
    "GMX",      # GMX - Perpetuals DEX, real yield pioneer
    "SNX",      # Synthetix - Derivatives platform, v3 launch
    "LINK"      # Chainlink - Oracle network, powers DeFi price feeds
]


class TwitterDeFi(TwitterTokenScraperBase):
    def __init__(self):
        super().__init__(
            tokens=TOKENS,
            source="defi",
            scraper_name="Twitter DeFi Scraper"
        )


async def main():
    scraper = TwitterDeFi()
    await scraper.run()


if __name__ == "__main__":
    asyncio.run(main())
