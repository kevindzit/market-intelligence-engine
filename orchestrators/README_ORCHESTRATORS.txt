# PJX Orchestrator System
# Reorganized into 3 specialized orchestrators for better management

## Quick Start

To run all scrapers (like before):
    python orchestrators/main_orchestrator.py
    Then press 4 to run all orchestrators

## Individual Orchestrators

1. TWITTER ORCHESTRATOR
   - File: orchestrators/twitter_orchestrator.py
   - Manages: All Twitter sentiment scrapers
   - Features: Mobile emulation enabled (Chad Scraper strategy)
   - Scrapers: Meme coins, Large caps, DeFi, Layer 1s, Layer 2s, AI/ML, Whales
   - Run: python orchestrators/twitter_orchestrator.py

2. NEWS & FUNDAMENTALS ORCHESTRATOR
   - File: orchestrators/news_fundamentals_orchestrator.py
   - Manages: All non-VPN data sources
   - Includes:
     * News: NewsAPI, RSS feeds
     * Congressional: Senate & House trade disclosures
     * Economic: FRED data
     * SEC: EDGAR filings
     * Fundamentals: FMP, yfinance
     * Crypto metrics: Fear & Greed, DEX liquidity, TVL, etc.
   - Run: python orchestrators/news_fundamentals_orchestrator.py

3. BINANCE/VPN ORCHESTRATOR
   - File: orchestrators/binance_vpn_orchestrator.py
   - Manages: All Binance and VPN-required scrapers
   - Includes: OHLCV, Order book, Liquidations, Funding rates, Open interest
   - Requirement: Non-US IP address or Tor proxy
   - Run: python orchestrators/binance_vpn_orchestrator.py

## Main Orchestrator Menu

Run: python orchestrators/main_orchestrator.py

Options:
1. Run Twitter Orchestrator only
2. Run News/Fundamentals only
3. Run Binance/VPN only
4. Run ALL orchestrators
5. Custom selection (choose which ones to run)
0. Exit

## Benefits of This Organization

- CLEANER: Each orchestrator focuses on one type of data
- EASIER TO DEBUG: Issues isolated to specific orchestrator
- BETTER RESOURCE MANAGEMENT: Run only what you need
- SIMPLER MAINTENANCE: Each file is smaller and focused
- FLEXIBILITY: Can run any combination of orchestrators

## Migration from Old System

Your old command:
    python orchestrator.py

New equivalent command:
    python orchestrators/main_orchestrator.py
    (then press 4 for all orchestrators)

## Notes

- All orchestrators share common functionality from base_orchestrator.py
- Mobile emulation is automatically enabled for Twitter scrapers
- Binance orchestrator will warn if you have US IP
- Each orchestrator opens in its own window on Windows
- All data still goes to the same PostgreSQL database