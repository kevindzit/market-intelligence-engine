"""
Simple diagnostic to see what's actually in the database
"""
import psycopg2
import os
from dotenv import load_dotenv
from datetime import datetime

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
print("DATABASE DIAGNOSTIC - What's Actually There")
print("="*100)

# Check total tweets
cur.execute("SELECT COUNT(*) FROM twitter_sentiment")
total = cur.fetchone()[0]
print(f"\nTotal tweets in database: {total}")

# Check most recent tweets (just show the 10 most recent, no time filter)
print("\n" + "="*100)
print("10 MOST RECENT TWEETS (No Time Filter)")
print("="*100)

cur.execute("""
    SELECT
        token,
        author_username,
        author_followers,
        LEFT(tweet_text, 60) as tweet,
        sentiment_score,
        scraped_at,
        NOW() as current_db_time,
        NOW() - scraped_at as age
    FROM twitter_sentiment
    ORDER BY scraped_at DESC
    LIMIT 10
""")

print(f"\n{'Token':<8} | {'Username':<15} | {'Followers':>10} | {'Scraped At':<25} | {'Age':<20}")
print("-"*100)

for row in cur.fetchall():
    token, username, followers, tweet, sentiment, scraped_at, db_time, age = row
    print(f"{token:<8} | {username:<15} | {followers:>10,} | {str(scraped_at):<25} | {str(age):<20}")

# Check database timezone
cur.execute("SHOW timezone")
db_tz = cur.fetchone()[0]
print(f"\nDatabase timezone: {db_tz}")

# Check current database time
cur.execute("SELECT NOW(), NOW() AT TIME ZONE 'UTC'")
db_now, db_utc = cur.fetchone()
print(f"Database NOW():    {db_now}")
print(f"Database UTC:      {db_utc}")
print(f"Python NOW():      {datetime.now()}")

# Check tweets by time window
print("\n" + "="*100)
print("TWEETS BY TIME WINDOW")
print("="*100)

time_windows = [
    ("Last 5 minutes", "5 minutes"),
    ("Last 15 minutes", "15 minutes"),
    ("Last 30 minutes", "30 minutes"),
    ("Last 1 hour", "1 hour"),
    ("Last 6 hours", "6 hours"),
    ("Last 24 hours", "24 hours"),
]

for label, interval in time_windows:
    cur.execute(f"""
        SELECT COUNT(*), MIN(scraped_at), MAX(scraped_at)
        FROM twitter_sentiment
        WHERE scraped_at > NOW() - INTERVAL '{interval}'
    """)
    count, min_time, max_time = cur.fetchone()
    print(f"{label:<20}: {count:>5} tweets  (oldest: {min_time}, newest: {max_time})")

# Check what tokens we have
print("\n" + "="*100)
print("TOKENS IN DATABASE")
print("="*100)

cur.execute("""
    SELECT token, COUNT(*) as total, MAX(scraped_at) as last_scraped
    FROM twitter_sentiment
    GROUP BY token
    ORDER BY total DESC
""")

print(f"\n{'Token':<15} | {'Total Tweets':>12} | {'Last Scraped':<30}")
print("-"*100)

for token, count, last in cur.fetchall():
    print(f"{token:<15} | {count:>12} | {str(last):<30}")

print("\n" + "="*100)

cur.close()
conn.close()