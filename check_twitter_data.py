"""Quick check of Twitter sentiment data with influence scoring"""
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

conn = psycopg2.connect(
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD
)

cur = conn.cursor()

print("\n" + "="*110)
print("TOP INFLUENCER ACCOUNTS (by follower count)")
print("="*110)
print(f"{'Token':<10} | {'Username':<20} | {'Followers':>12} | {'Sentiment':>10} | {'Weighted':>10} | {'Alert':<8} | {'Whale'}")
print("-"*110)

cur.execute("""
    SELECT token, author_username, author_followers,
           sentiment_score, weighted_score, alert_level, is_whale
    FROM twitter_sentiment
    WHERE weighted_score IS NOT NULL AND ABS(weighted_score) > 0.001
    ORDER BY author_followers DESC
    LIMIT 20
""")

for row in cur.fetchall():
    token, username, followers, sentiment, weighted, alert, whale = row
    alert_str = alert if alert else "None"
    weighted_val = weighted if weighted is not None else 0.0
    print(f"{token:<10} | {username:<20} | {followers:>12,} | {sentiment:>10.3f} | {weighted_val:>10.3f} | {alert_str:<8} | {whale}")

print("\n" + "="*110)
print("SUMMARY STATISTICS")
print("="*110)

cur.execute("""
    SELECT
        COUNT(*) as total_tweets,
        COUNT(*) FILTER (WHERE is_whale = true) as whale_tweets,
        COUNT(*) FILTER (WHERE alert_level IS NOT NULL) as alerts,
        COUNT(*) FILTER (WHERE alert_level = 'HIGH') as high_alerts,
        COUNT(*) FILTER (WHERE alert_level = 'EXTREME') as extreme_alerts,
        AVG(author_followers) as avg_followers,
        MAX(author_followers) as max_followers,
        AVG(weighted_score) as avg_weighted,
        MAX(weighted_score) as max_weighted
    FROM twitter_sentiment
""")

stats = cur.fetchone()
print(f"Total tweets:      {stats[0]:>6}")
print(f"Whale tweets:      {stats[1]:>6} ({stats[1]/stats[0]*100:.1f}%)")
print(f"Total alerts:      {stats[2]:>6}")
print(f"  HIGH alerts:     {stats[3]:>6}")
print(f"  EXTREME alerts:  {stats[4]:>6}")
print(f"Avg followers:     {stats[5]:>6,.0f}")
print(f"Max followers:     {stats[6]:>6,}")
print(f"Avg weighted:      {stats[7]:>6.2f}")
print(f"Max weighted:      {stats[8]:>6.2f}")
print("="*110 + "\n")

cur.close()
conn.close()
