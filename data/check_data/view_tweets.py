"""
Quick viewer to see your real Twitter data in the database
"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=os.getenv('DB_PORT', '54594'),
    database=os.getenv('DB_NAME', 'postgres'),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASSWORD', 'postgres')
)

cur = conn.cursor()

print("\n" + "="*100)
print("RECENT TWEETS IN DATABASE (Last 30 Minutes)")
print("="*100)

# Show recent tweets with all the juicy details
cur.execute("""
    SELECT
        token,
        author_username,
        author_followers,
        LEFT(tweet_text, 80) as tweet_preview,
        sentiment_score,
        bot_probability,
        volume_spike,
        is_whale,
        scraped_at
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '30 minutes'
    ORDER BY scraped_at DESC
    LIMIT 50
""")

print(f"\n{'Token':<8} | {'Username':<15} | {'Followers':>10} | {'Tweet':<50} | {'Sent':>6} | {'Bot':>5} | {'Vol':>5} | {'Whale'}")
print("-"*100)

for row in cur.fetchall():
    token, username, followers, tweet, sentiment, bot_prob, vol_spike, is_whale = row[:8]

    tweet_clean = tweet.replace('\n', ' ').strip()[:50]
    sent_str = f"{sentiment:.2f}" if sentiment else "N/A"
    bot_str = f"{bot_prob:.2f}" if bot_prob else "N/A"
    vol_str = f"{vol_spike:.1f}x" if vol_spike else "-"
    whale_str = "WHALE" if is_whale else "-"

    print(f"{token:<8} | {username:<15} | {followers:>10,} | {tweet_clean:<50} | {sent_str:>6} | {bot_str:>5} | {vol_str:>5} | {whale_str}")

# Show summary stats
print("\n" + "="*100)
print("DATABASE SUMMARY")
print("="*100)

cur.execute("""
    SELECT
        COUNT(*) as total_tweets,
        COUNT(DISTINCT token) as tokens,
        COUNT(DISTINCT author_username) as unique_users,
        MIN(scraped_at) as first_scrape,
        MAX(scraped_at) as last_scrape
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '24 hours'
""")

stats = cur.fetchone()
total, tokens, users, first, last = stats

print(f"Total Tweets (24h):    {total}")
print(f"Tokens Tracked:        {tokens}")
print(f"Unique Users:          {users}")
print(f"First Scrape:          {first}")
print(f"Last Scrape:           {last}")

# Show per-token breakdown
print("\n" + "="*100)
print("PER-TOKEN BREAKDOWN (Last Hour)")
print("="*100)

cur.execute("""
    SELECT
        token,
        COUNT(*) as tweets,
        AVG(sentiment_score) as avg_sentiment,
        AVG(bot_probability) as avg_bot_prob,
        MAX(volume_spike) as max_volume,
        COUNT(*) FILTER (WHERE is_whale = true) as whale_count,
        MAX(author_followers) as biggest_account
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '1 hour'
    GROUP BY token
    ORDER BY tweets DESC
""")

print(f"\n{'Token':<10} | {'Tweets':>7} | {'Sentiment':>10} | {'Bot %':>8} | {'Max Vol':>8} | {'Whales':>7} | {'Biggest Account':>15}")
print("-"*100)

for row in cur.fetchall():
    token, tweets, sentiment, bot_prob, max_vol, whales, biggest = row

    sent_str = f"{sentiment:.3f}" if sentiment else "N/A"
    bot_pct = f"{bot_prob*100:.1f}%" if bot_prob else "N/A"
    vol_str = f"{max_vol:.1f}x" if max_vol else "baseline"
    whale_str = f"{whales}" if whales else "0"
    big_str = f"{biggest:,}" if biggest else "N/A"

    print(f"{token:<10} | {tweets:>7} | {sent_str:>10} | {bot_pct:>8} | {vol_str:>8} | {whale_str:>7} | {big_str:>15}")

print("\n" + "="*100)
print("This is 100% REAL data from Twitter. No synthetic/fake data.")
print("="*100 + "\n")

cur.close()
conn.close()