"""
Twitter Sentiment Scraper for Crypto
Scrapes Twitter for crypto mentions and analyzes sentiment using HuggingFace

Features:
- FREE (no $100/month API via twikit)
- Searches by keywords (BTC, ETH, SOL, PEPE, DOGE)
- Batch sentiment processing (efficient)
- Stores in PostgreSQL
- Smart rate limiting
- Tracks engagement (likes, retweets)
"""

import os
import sys
import asyncio
import time
import json
import psycopg2
from datetime import datetime
from pathlib import Path
from random import randint
from dotenv import load_dotenv
import httpx
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

original_client = httpx.Client

def patched_client(*args, **kwargs):
    if 'headers' not in kwargs:
        kwargs['headers'] = {}

    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ]

    kwargs['headers'].update({
        'User-Agent': user_agents[randint(0, len(user_agents)-1)],
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate'
    })

    kwargs.pop('proxy', None)
    return original_client(*args, **kwargs)

httpx.Client = patched_client

from twikit import Client, TooManyRequests

TOKENS_TO_TRACK = ["bitcoin", "ethereum", "solana", "pepe", "dogecoin"]
TWEETS_PER_TOKEN = 20
IGNORE_WORDS = ['discord', 'telegram', 'airdrop', 't.co/scam', 'giveaway']

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'postgres')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

class TwitterSentimentScraper:
    def __init__(self):
        self.client = None
        self.tokenizer = None
        self.model = None
        self.db_conn = None

    def init_db(self):
        try:
            self.db_conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
            print("[OK] Database connected")
        except Exception as e:
            print(f"[ERROR] Database connection failed: {e}")
            sys.exit(1)

    def init_sentiment_model(self):
        if self.model is None:
            print("Loading sentiment model...")
            self.tokenizer = AutoTokenizer.from_pretrained(
                "finiteautomata/bertweet-base-sentiment-analysis"
            )
            self.model = AutoModelForSequenceClassification.from_pretrained(
                "finiteautomata/bertweet-base-sentiment-analysis"
            )
            print("[OK] Sentiment model loaded")

    def analyze_sentiment_batch(self, texts):
        self.init_sentiment_model()

        sentiments = []
        labels = []
        batch_size = 8

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            inputs = self.tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=128,
                return_tensors="pt"
            )

            with torch.no_grad():
                outputs = self.model(**inputs)
                predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)

                for pred in predictions:
                    neg, neu, pos = pred.tolist()
                    score = pos - neg
                    sentiments.append(score)

                    if score > 0.3:
                        labels.append("positive")
                    elif score < -0.3:
                        labels.append("negative")
                    else:
                        labels.append("neutral")

        return sentiments, labels

    def init_twitter_client(self):
        if not os.path.exists("cookies.json"):
            print("[ERROR] cookies.json not found!")
            print("\nManually copy cookies from your browser:")
            print("1. Login to Twitter in Chrome/Edge")
            print("2. Press F12 -> Application -> Cookies -> x.com")
            print("3. Copy auth_token and ct0 values")
            print("4. Edit cookies.json with those values")
            sys.exit(1)

        try:
            self.client = Client('en-US')

            # Handle different cookie formats
            with open("cookies.json", 'r') as f:
                cookie_data = json.load(f)

            # Check if it's browser export format
            if isinstance(cookie_data, dict) and 'cookies' in cookie_data:
                # Browser export format - extract just the cookies
                cookies = cookie_data['cookies']
                # Save in twikit format
                with open("cookies.json", 'w') as f:
                    json.dump(cookies, f)

            self.client.load_cookies("cookies.json")
            print("[OK] Twitter client initialized")
        except Exception as e:
            print(f"[ERROR] Twitter client init failed: {e}")
            print("\nTry extracting cookies from browser:")
            print("1. Login to Twitter in Chrome/Edge")
            print("2. Press F12 -> Application -> Cookies")
            sys.exit(1)

    async def get_tweets_for_token(self, token):
        collected = []

        try:
            print(f"\nSearching Twitter for: {token}")
            time.sleep(randint(2, 4))

            tweets = await self.client.search_tweet(token, product='Latest')

            if tweets:
                for tweet in tweets:
                    if len(collected) >= TWEETS_PER_TOKEN:
                        break

                    text_lower = tweet.text.lower()
                    if any(word in text_lower for word in IGNORE_WORDS):
                        continue

                    collected.append({
                        'tweet_id': tweet.id,
                        'token': token,
                        'text': tweet.text,
                        'username': tweet.user.screen_name if tweet.user else 'unknown',
                        'followers': tweet.user.followers_count if tweet.user else 0,
                        'retweets': tweet.retweet_count or 0,
                        'likes': tweet.favorite_count or 0,
                        'created_at': tweet.created_at
                    })

                try:
                    while len(collected) < TWEETS_PER_TOKEN:
                        time.sleep(randint(3, 6))
                        more = await tweets.next()
                        if not more:
                            break

                        for tweet in more:
                            if len(collected) >= TWEETS_PER_TOKEN:
                                break

                            text_lower = tweet.text.lower()
                            if any(word in text_lower for word in IGNORE_WORDS):
                                continue

                            collected.append({
                                'tweet_id': tweet.id,
                                'token': token,
                                'text': tweet.text,
                                'username': tweet.user.screen_name if tweet.user else 'unknown',
                                'followers': tweet.user.followers_count if tweet.user else 0,
                                'retweets': tweet.retweet_count or 0,
                                'likes': tweet.favorite_count or 0,
                                'created_at': tweet.created_at
                            })
                except:
                    pass

            print(f"[OK] Collected {len(collected)} tweets for {token}")

        except TooManyRequests as e:
            reset_time = datetime.fromtimestamp(e.rate_limit_reset)
            wait_seconds = (reset_time - datetime.now()).total_seconds() + randint(10, 20)
            print(f"Rate limited. Waiting {int(wait_seconds)}s...")
            time.sleep(wait_seconds)

        except Exception as e:
            print(f"[ERROR] Error fetching {token}: {e}")

        return collected

    def save_to_db(self, tweets_data):
        if not tweets_data:
            return

        texts = [t['text'] for t in tweets_data]
        sentiments, labels = self.analyze_sentiment_batch(texts)

        cursor = self.db_conn.cursor()
        saved = 0
        duplicates = 0

        for i, tweet in enumerate(tweets_data):
            try:
                cursor.execute("""
                    INSERT INTO twitter_sentiment
                    (tweet_id, token, tweet_text, sentiment_score, sentiment_label,
                     author_username, author_followers, retweet_count, like_count,
                     tweet_created_at, scraped_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tweet_id, token) DO NOTHING
                """, (
                    tweet['tweet_id'],
                    tweet['token'],
                    tweet['text'],
                    round(sentiments[i], 4),
                    labels[i],
                    tweet['username'],
                    tweet['followers'],
                    tweet['retweets'],
                    tweet['likes'],
                    tweet['created_at'],
                    datetime.now()
                ))

                self.db_conn.commit()

                if cursor.rowcount == 0:
                    duplicates += 1
                else:
                    saved += 1

            except Exception as e:
                self.db_conn.rollback()
                duplicates += 1

        cursor.close()

        print(f"[OK] Saved {saved} new tweets, {duplicates} duplicates skipped")

    async def run(self):
        print("\n" + "="*60)
        print("Twitter Sentiment Scraper - Starting")
        print("="*60)

        self.init_db()
        self.init_twitter_client()

        all_tweets = []

        for token in TOKENS_TO_TRACK:
            tweets = await self.get_tweets_for_token(token)
            all_tweets.extend(tweets)

        if all_tweets:
            print(f"\nTotal tweets collected: {len(all_tweets)}")
            self.save_to_db(all_tweets)

            cursor = self.db_conn.cursor()
            cursor.execute("""
                SELECT token, AVG(sentiment_score), COUNT(*)
                FROM twitter_sentiment
                WHERE scraped_at > NOW() - INTERVAL '1 hour'
                GROUP BY token
                ORDER BY token
            """)

            print("\n" + "="*60)
            print("Sentiment Summary (Last Hour)")
            print("="*60)

            for row in cursor.fetchall():
                token, avg_sent, count = row
                score_pct = (float(avg_sent) + 1) * 50
                sentiment = "POSITIVE" if avg_sent > 0 else "NEGATIVE" if avg_sent < 0 else "NEUTRAL"
                print(f"{token:12} | Score: {score_pct:5.1f}/100 | {sentiment:8} | Tweets: {count}")

            cursor.close()
        else:
            print("No tweets collected this run")

        self.db_conn.close()

        print("\n" + "="*60)
        print("Twitter Sentiment Scraper - Complete")
        print("="*60 + "\n")

async def main():
    scraper = TwitterSentimentScraper()
    await scraper.run()

if __name__ == "__main__":
    asyncio.run(main())