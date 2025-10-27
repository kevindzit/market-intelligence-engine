#!/usr/bin/env python3
"""
Quick database check script for Twitter sentiment data
Verifies that data is being saved correctly with all new columns
"""

import psycopg2
from datetime import datetime, timedelta
from collections import defaultdict

# Database config
DB_HOST = 'localhost'
DB_PORT = '54594'
DB_NAME = 'postgres'
DB_USER = 'postgres'
DB_PASSWORD = 'postgres'

def check_database():
    """Check Twitter sentiment database for recent data and quality"""
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    cursor = conn.cursor()

    print("="*70)
    print("TWITTER SENTIMENT DATABASE CHECK")
    print("="*70)

    # 1. Total tweets
    cursor.execute("SELECT COUNT(*) FROM twitter_sentiment")
    total = cursor.fetchone()[0]
    print(f"\n📊 Total tweets in database: {total:,}")

    # 2. Recent activity (last 24 hours)
    cursor.execute("""
        SELECT
            COUNT(*) as tweets,
            COUNT(DISTINCT token) as tokens,
            COUNT(DISTINCT author_username) as authors,
            COUNT(DISTINCT source) as sources,
            MIN(scraped_at) as oldest,
            MAX(scraped_at) as newest
        FROM twitter_sentiment
        WHERE scraped_at > NOW() - INTERVAL '24 hours'
    """)

    result = cursor.fetchone()
    if result[0] > 0:
        print(f"\n🕐 Last 24 Hours:")
        print(f"  • Tweets: {result[0]:,}")
        print(f"  • Unique tokens: {result[1]}")
        print(f"  • Unique authors: {result[2]}")
        print(f"  • Active scrapers: {result[3]}")
        print(f"  • Time range: {result[4].strftime('%H:%M')} to {result[5].strftime('%H:%M')}")
    else:
        print("\n⚠️  No tweets in last 24 hours")

    # 3. Check influence_weight data quality
    cursor.execute("""
        SELECT
            COUNT(*) as with_influence,
            AVG(influence_weight)::numeric(5,3) as avg,
            MIN(influence_weight)::numeric(5,3) as min,
            MAX(influence_weight)::numeric(5,3) as max,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY influence_weight)::numeric(5,3) as median
        FROM twitter_sentiment
        WHERE scraped_at > NOW() - INTERVAL '24 hours'
        AND influence_weight IS NOT NULL
    """)

    result = cursor.fetchone()
    if result[0] > 0:
        print(f"\n📈 Influence Weight Analysis (Yale Coefficient):")
        print(f"  • Tweets with influence: {result[0]:,}")
        print(f"  • Average: {result[1]}")
        print(f"  • Min: {result[2]}")
        print(f"  • Max: {result[3]}")
        print(f"  • Median: {result[4]}")

        # Check if values are in expected range
        if result[1] and 0.0001 <= float(result[1]) <= 0.001:
            print("  ✅ Values in optimal range (0.0001-0.001)")
        else:
            print("  ⚠️  Values outside optimal range")

    # 4. Check by source
    cursor.execute("""
        SELECT
            source,
            COUNT(*) as tweets,
            COUNT(DISTINCT token) as tokens,
            AVG(sentiment_score)::numeric(5,3) as avg_sentiment
        FROM twitter_sentiment
        WHERE scraped_at > NOW() - INTERVAL '1 hour'
        GROUP BY source
        ORDER BY tweets DESC
    """)

    sources = cursor.fetchall()
    if sources:
        print(f"\n📡 Last Hour by Scraper:")
        for source, tweets, tokens, sentiment in sources:
            print(f"  • {source}: {tweets} tweets, {tokens} tokens, sentiment: {sentiment}")

    # 5. Top tokens last hour
    cursor.execute("""
        SELECT
            token,
            COUNT(*) as tweets,
            AVG(sentiment_score)::numeric(5,3) as sentiment,
            AVG(influence_weight)::numeric(5,3) as influence,
            MAX(volume_spike)::numeric(5,2) as max_spike
        FROM twitter_sentiment
        WHERE scraped_at > NOW() - INTERVAL '1 hour'
        GROUP BY token
        ORDER BY tweets DESC
        LIMIT 10
    """)

    tokens = cursor.fetchall()
    if tokens:
        print(f"\n🪙 Top Tokens (Last Hour):")
        print(f"  {'Token':<8} {'Tweets':<8} {'Sentiment':<10} {'Influence':<10} {'Vol Spike'}")
        print(f"  {'-'*50}")
        for token, tweets, sentiment, influence, spike in tokens:
            spike_str = f"{spike}x" if spike else "N/A"
            inf_str = str(influence) if influence else "N/A"
            print(f"  {token:<8} {tweets:<8} {sentiment:<10} {inf_str:<10} {spike_str}")

    # 6. Check for whale tweets
    cursor.execute("""
        SELECT
            COUNT(*) as whale_tweets,
            COUNT(DISTINCT author_username) as whales
        FROM twitter_sentiment
        WHERE is_whale = true
        AND scraped_at > NOW() - INTERVAL '1 hour'
    """)

    result = cursor.fetchone()
    if result[0] > 0:
        print(f"\n🐋 Whale Activity (Last Hour):")
        print(f"  • Whale tweets: {result[0]}")
        print(f"  • Active whales: {result[1]}")

    # 7. Latest tweets sample
    cursor.execute("""
        SELECT
            token,
            author_username,
            sentiment_score,
            influence_weight,
            source,
            scraped_at
        FROM twitter_sentiment
        ORDER BY scraped_at DESC
        LIMIT 5
    """)

    latest = cursor.fetchall()
    if latest:
        print(f"\n📰 Latest 5 Tweets:")
        for token, author, sent, inf, source, time in latest:
            time_ago = (datetime.now(time.tzinfo) - time).total_seconds() / 60
            inf_str = f"{inf:.3f}" if inf else "N/A"
            print(f"  • {token} by @{author}: sent={sent:.2f}, inf={inf_str}, source={source} ({int(time_ago)}m ago)")

    cursor.close()
    conn.close()

    print("\n" + "="*70)
    print("✅ Database check complete!")
    print("="*70)

if __name__ == "__main__":
    try:
        check_database()
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nMake sure PostgreSQL is running on port 54594")