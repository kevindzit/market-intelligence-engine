"""
Twitter Sentiment V2 Monitoring - Focus on Volume & Quality Signals
Shows volume spikes (primary predictor), bot ratios, and trading signals
"""

import psycopg2
import os
from dotenv import load_dotenv
from datetime import datetime

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

print("\n" + "="*120)
print(f"TWITTER SENTIMENT V2 MONITORING - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*120)

# 1. TRADING SIGNALS (Most Important)
print("\n" + "="*120)
print("ACTIVE TRADING SIGNALS (Last 15 Minutes)")
print("="*120)
print(f"{'Token':<10} | {'Signal':<12} | {'Volume':<10} | {'Sentiment':<10} | {'Tweets':<8} | {'Pump Risk':<10} | {'Action'}")
print("-"*120)

cur.execute("""
    SELECT
        token,
        CASE
            WHEN MAX(volume_spike) >= 3.0 AND AVG(CASE WHEN bot_probability < 0.3 THEN sentiment_score END) > 0.2
                THEN 'STRONG BUY'
            WHEN MAX(volume_spike) >= 2.0 AND AVG(CASE WHEN bot_probability < 0.3 THEN sentiment_score END) > 0.1
                THEN 'BUY'
            WHEN MAX(volume_spike) >= 2.0 AND AVG(CASE WHEN bot_probability < 0.3 THEN sentiment_score END) < -0.2
                THEN 'SELL'
            WHEN MAX(pump_score) >= 0.7
                THEN 'PUMP WARN'
            ELSE 'HOLD'
        END as signal,
        MAX(volume_spike) as volume,
        AVG(CASE WHEN bot_probability < 0.3 THEN sentiment_score END) as quality_sentiment,
        COUNT(*) as total_tweets,
        MAX(pump_score) as pump_risk
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '15 minutes'
    GROUP BY token
    HAVING COUNT(*) >= 5
    ORDER BY MAX(volume_spike) DESC NULLS LAST
""")

signals = []
for row in cur.fetchall():
    token, signal, volume, sentiment, tweets, pump = row
    volume_str = f"{volume:.1f}x" if volume else "baseline"
    sent_str = f"{sentiment:.3f}" if sentiment else "N/A"
    pump_str = f"{pump:.2f}" if pump else "Safe"

    action = ""
    if signal == "STRONG BUY":
        action = ">>> ENTER NOW (exit <24h)"
        signals.append((token, signal, volume))
    elif signal == "BUY":
        action = "Enter position"
    elif signal == "SELL":
        action = "Exit/Short"
    elif signal == "PUMP WARN":
        action = "!!! AVOID"
    else:
        action = "Wait"

    print(f"{token:<10} | {signal:<12} | {volume_str:<10} | {sent_str:<10} | {tweets:<8} | {pump_str:<10} | {action}")

if signals:
    print("\n" + "!!!"*40)
    print("ALERTS:")
    for token, signal, volume in signals:
        print(f"  !!! {token}: {signal} signal with {volume:.1f}x volume spike!")
    print("!!!"*40)

# 2. VOLUME SPIKE TRACKING (Primary Signal)
print("\n" + "="*120)
print("VOLUME SPIKE ANALYSIS (5-Minute Intervals)")
print("="*120)
print(f"{'Time':<8} | {'Token':<10} | {'Tweets':<8} | {'Volume':<10} | {'Human %':<10} | {'Sentiment':<10} | {'Whales'}")
print("-"*120)

cur.execute("""
    SELECT
        TO_CHAR(DATE_TRUNC('minute', scraped_at) -
                (EXTRACT(minute FROM scraped_at)::integer % 5) * INTERVAL '1 minute', 'HH24:MI') as time_5min,
        token,
        COUNT(*) as tweet_count,
        MAX(volume_spike) as max_spike,
        (COUNT(*) FILTER (WHERE bot_probability < 0.5))::float / NULLIF(COUNT(*), 0) * 100 as human_pct,
        AVG(CASE WHEN bot_probability < 0.5 THEN sentiment_score END) as human_sentiment,
        COUNT(*) FILTER (WHERE is_whale = true) as whale_count
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '30 minutes'
    GROUP BY time_5min, token
    HAVING COUNT(*) > 5
    ORDER BY time_5min DESC, max_spike DESC NULLS LAST
    LIMIT 15
""")

for row in cur.fetchall():
    time_str, token, tweets, spike, human_pct, sentiment, whales = row
    spike_str = f"{spike:.1f}x" if spike else "baseline"
    human_str = f"{human_pct:.0f}%" if human_pct else "N/A"
    sent_str = f"{sentiment:.3f}" if sentiment else "N/A"
    whale_str = f"{whales} whales" if whales > 0 else "-"

    print(f"{time_str:<8} | {token:<10} | {tweets:<8} | {spike_str:<10} | {human_str:<10} | {sent_str:<10} | {whale_str}")

# 3. BOT DETECTION STATISTICS
print("\n" + "="*120)
print("BOT ACTIVITY ANALYSIS")
print("="*120)
print(f"{'Token':<10} | {'Total':<8} | {'Bots':<8} | {'Bot %':<10} | {'Humans':<8} | {'Quality'}")
print("-"*120)

cur.execute("""
    SELECT
        token,
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE bot_probability >= 0.7) as likely_bots,
        (COUNT(*) FILTER (WHERE bot_probability >= 0.7))::float / NULLIF(COUNT(*), 0) * 100 as bot_pct,
        COUNT(*) FILTER (WHERE bot_probability < 0.3) as likely_humans,
        CASE
            WHEN (COUNT(*) FILTER (WHERE bot_probability >= 0.7))::float / NULLIF(COUNT(*), 0) > 0.5
                THEN 'X Poor'
            WHEN (COUNT(*) FILTER (WHERE bot_probability >= 0.7))::float / NULLIF(COUNT(*), 0) > 0.3
                THEN '! Suspicious'
            ELSE 'Good'
        END as quality
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '1 hour'
    GROUP BY token
    ORDER BY bot_pct DESC
""")

for row in cur.fetchall():
    token, total, bots, bot_pct, humans, quality = row
    bot_pct_str = f"{bot_pct:.1f}%"
    print(f"{token:<10} | {total:<8} | {bots:<8} | {bot_pct_str:<10} | {humans:<8} | {quality}")

# 4. HIGH-IMPACT INFLUENCERS
print("\n" + "="*120)
print("HIGH-IMPACT TWEETS (Whales & Influencers)")
print("="*120)
print(f"{'Token':<10} | {'Username':<20} | {'Followers':>12} | {'Sentiment':<10} | {'Weight':<10} | {'Alert'}")
print("-"*120)

cur.execute("""
    SELECT
        token,
        author_username,
        author_followers,
        sentiment_score,
        weighted_score,
        alert_level
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '1 hour'
        AND author_followers >= 100000
        AND bot_probability < 0.5
    ORDER BY weighted_score DESC
    LIMIT 10
""")

for row in cur.fetchall():
    token, username, followers, sentiment, weight, alert = row
    username_str = username[:20] if username else "unknown"
    sent_str = "Bullish" if sentiment > 0.2 else "Bearish" if sentiment < -0.2 else "Neutral"
    weight_str = f"{weight:.1f}" if weight else "N/A"
    alert_str = f"!!! {alert}" if alert else "-"

    print(f"{token:<10} | {username_str:<20} | {followers:>12,} | {sent_str:<10} | {weight_str:<10} | {alert_str}")

# 5. PUMP & DUMP DETECTION
print("\n" + "="*120)
print("PUMP & DUMP RISK ASSESSMENT")
print("="*120)

cur.execute("""
    SELECT
        token,
        MAX(pump_score) as max_pump,
        COUNT(*) FILTER (WHERE pump_score > 0.5) as suspicious_tweets,
        COUNT(*) as total_tweets
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '30 minutes'
    GROUP BY token
    HAVING MAX(pump_score) > 0.3
    ORDER BY max_pump DESC
""")

pump_warnings = cur.fetchall()
if pump_warnings:
    print(f"{'Token':<10} | {'Risk Score':<12} | {'Suspicious':<12} | {'Status'}")
    print("-"*120)
    for token, pump, suspicious, total in pump_warnings:
        risk = "[HIGH RISK]" if pump > 0.7 else "[MEDIUM]" if pump > 0.5 else "[Low]"
        print(f"{token:<10} | {pump:.2f} | {suspicious}/{total} tweets | {risk}")
else:
    print("[OK] No pump & dump patterns detected")

# 6. SUMMARY STATISTICS
print("\n" + "="*120)
print("OVERALL STATISTICS (Last Hour)")
print("="*120)

cur.execute("""
    SELECT
        COUNT(DISTINCT token) as tokens_tracked,
        COUNT(*) as total_tweets,
        AVG(bot_probability) * 100 as avg_bot_prob,
        COUNT(*) FILTER (WHERE volume_spike >= 2.0) as volume_spikes,
        COUNT(*) FILTER (WHERE alert_level IN ('HIGH', 'EXTREME')) as high_alerts,
        MAX(weighted_score) as max_impact
    FROM twitter_sentiment
    WHERE scraped_at > NOW() - INTERVAL '1 hour'
""")

stats = cur.fetchone()
if stats:
    tokens, tweets, bot_avg, spikes, alerts, impact = stats
    print(f"Tokens Tracked:    {tokens}")
    print(f"Total Tweets:      {tweets}")
    print(f"Bot Percentage:    {bot_avg:.1f}%" if bot_avg else "Bot Percentage:    N/A")
    print(f"Volume Spikes:     {spikes} (2x+ baseline)")
    print(f"High Alerts:       {alerts}")
    print(f"Max Impact Score:  {impact:.1f}" if impact else "Max Impact Score:  N/A")

print("\n" + "="*120)
print("TRADING TIPS:")
print("- Volume spikes (2-3x) are the PRIMARY buy signal")
print("- Exit all Twitter-based positions within 24-48 hours")
print("- Ignore signals with >50% bot activity")
print("- Focus on meme coins, not BTC/ETH")
print("="*120 + "\n")

cur.close()
conn.close()