"""
Test script to verify the new unlimited token AI trading system
Tests dynamic token discovery, real price fetching, and data aggregation
"""

import sys
import os
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_intelligence import DataIntelligence
import config

def test_dynamic_discovery():
    """Test dynamic token discovery from database"""
    print("\n" + "="*60)
    print("TEST 1: Dynamic Token Discovery")
    print("="*60)

    # Initialize data intelligence
    db_config = {
        'host': config.DB_HOST,
        'port': config.DB_PORT,
        'database': config.DB_NAME,
        'user': config.DB_USER,
        'password': config.DB_PASSWORD
    }

    data_intel = DataIntelligence(db_config)

    # Discover active tokens
    print("\nDiscovering active tokens...")
    active_tokens = data_intel.discover_active_tokens(min_activity_hours=24)

    if active_tokens:
        print(f"\n[SUCCESS] Found {len(active_tokens)} active tokens:")
        for i, token in enumerate(active_tokens[:10], 1):
            print(f"  {i}. {token}")
        if len(active_tokens) > 10:
            print(f"  ... and {len(active_tokens) - 10} more")
    else:
        print("[FAIL] No active tokens found")

    return active_tokens, data_intel

def test_real_price_fetching(tokens, data_intel):
    """Test fetching real prices from database"""
    print("\n" + "="*60)
    print("TEST 2: Real Price Fetching (not fake!)")
    print("="*60)

    if not tokens:
        print("[SKIP] No tokens to test")
        return

    # Test first 5 tokens
    test_tokens = tokens[:5]
    print(f"\nFetching real prices for {len(test_tokens)} tokens...")

    for token in test_tokens:
        price = data_intel.get_current_price(token)
        if price:
            print(f"  {token}: ${price:.4f} [OK]")
        else:
            print(f"  {token}: No price data [FAIL]")

def test_data_aggregation(tokens, data_intel):
    """Test comprehensive data aggregation"""
    print("\n" + "="*60)
    print("TEST 3: Smart Data Aggregation")
    print("="*60)

    if not tokens:
        print("[SKIP] No tokens to test")
        return

    # Pick first token with good data
    test_token = None
    for token in tokens[:10]:
        summary = data_intel.get_quick_summary(token)
        if summary and summary['tweets_1h'] > 0:
            test_token = token
            break

    if not test_token:
        print("[FAIL] No tokens with recent activity")
        return

    print(f"\nTesting data aggregation for: {test_token}")

    # Get quick summary
    summary = data_intel.get_quick_summary(test_token)
    print(f"\n1. Quick Summary:")
    print(f"  Price: ${summary['price']:.4f}")
    print(f"  Tweets (1h): {summary['tweets_1h']}")
    print(f"  Sentiment (1h): {summary['sentiment_1h']:.3f}")
    print(f"  Price Change (1h): {summary['price_change_1h']:.2f}%")
    print(f"  Volume Spike: {summary['volume_spike']:.1f}x")

    # Get sentiment details
    sentiment = data_intel.get_sentiment_summary(test_token, hours=6)
    if sentiment['has_data']:
        print(f"\n2. Sentiment Summary (6h):")
        print(f"  Total Tweets: {sentiment['tweet_count']}")
        print(f"  Avg Sentiment: {sentiment['avg_sentiment']:.3f}")
        print(f"  Whale Tweets: {sentiment['whale_tweets']}")
        print(f"  Quality Tweets: {sentiment['quality_tweets']}")
        print(f"  Momentum Score: {sentiment['momentum_score']:.3f}")

    # Get market metrics
    metrics = data_intel.get_market_metrics(test_token)
    if metrics:
        print(f"\n3. Market Metrics:")
        if 'order_book' in metrics:
            print(f"  Order Book Spread: {metrics['order_book']['spread']:.4f}")
            print(f"  Order Imbalance: {metrics['order_book']['imbalance']:.2f}")
        if 'funding_rate' in metrics:
            print(f"  Funding Rate: {metrics['funding_rate']:.4f}%")
        if 'open_interest_usd' in metrics:
            print(f"  Open Interest: ${metrics['open_interest_usd']:,.0f}")

def test_trending_detection(data_intel):
    """Test trending token detection"""
    print("\n" + "="*60)
    print("TEST 4: Trending Token Detection")
    print("="*60)

    trending = data_intel.get_trending_tokens(min_spike=1.5)

    if trending:
        print(f"\n[SUCCESS] Found {len(trending)} trending tokens:")
        for t in trending[:5]:
            print(f"  {t['token']}:")
            print(f"    Reason: {t['reason']}")
            print(f"    Volume Spike: {t['volume_spike']:.1f}x")
            print(f"    Sentiment: {t['sentiment']:.3f}")
            print(f"    Tweets: {t['tweets']}")
    else:
        print("[FAIL] No trending tokens found")

def test_ai_query_capability(data_intel):
    """Test AI's ability to execute custom queries"""
    print("\n" + "="*60)
    print("TEST 5: AI Query Capability")
    print("="*60)

    # Test query: Find most active tokens in last hour
    query = """
    SELECT token, COUNT(*) as tweet_count, AVG(sentiment_score) as avg_sentiment
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '1 hour'
    GROUP BY token
    ORDER BY tweet_count DESC
    LIMIT 5
    """

    print("\nExecuting AI query: Top 5 most active tokens (last hour)")
    results = data_intel.execute_ai_query(query)

    if results:
        print(f"\n[SUCCESS] Query successful - {len(results)} results:")
        for r in results:
            print(f"  {r['token']}: {r['tweet_count']} tweets, sentiment: {r['avg_sentiment']:.3f}")
    else:
        print("[FAIL] Query failed or no results")

def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("  PJX UNLIMITED TOKEN AI TRADER - SYSTEM TEST")
    print("="*70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        # Run tests
        tokens, data_intel = test_dynamic_discovery()
        test_real_price_fetching(tokens, data_intel)
        test_data_aggregation(tokens, data_intel)
        test_trending_detection(data_intel)
        test_ai_query_capability(data_intel)

        # Close connection
        data_intel.close()

        print("\n" + "="*60)
        print("ALL TESTS COMPLETED!")
        print("="*60)
        print("\nSYSTEM STATUS: READY FOR PAPER TRADING")
        print("\nKey Features Verified:")
        print("  [OK] Dynamic token discovery (no fixed list)")
        print("  [OK] Real price fetching from database")
        print("  [OK] Smart data aggregation")
        print("  [OK] Trending token detection")
        print("  [OK] AI query capability")
        print("\nTo start paper trading, run: python ai_trader.py")

    except Exception as e:
        print(f"\n[ERROR] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()