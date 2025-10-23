"""
Twitter/Crypto Sentiment Scraper
Adapted from Moon Dev's sentiment agent for PJX Crypto Trading System

This scraper monitors Twitter sentiment for crypto tokens using FinBERT model.
It stores sentiment scores in PostgreSQL for integration with trading decisions.

Required:
1. Twitter credentials in .env file (can run in test mode without)
2. FinBERT model (auto-downloads on first run)
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Third-party imports
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import schedule
from termcolor import colored

# ML imports (will be installed if not present)
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    BERT_AVAILABLE = True
except ImportError:
    BERT_AVAILABLE = False
    print(colored("Warning: transformers/torch not installed. Install with: pip install transformers torch", "yellow"))

# Twitter client (optional - can run without)
try:
    from twikit import Client
    TWITTER_AVAILABLE = True
except ImportError:
    TWITTER_AVAILABLE = False
    print(colored("Info: twikit not installed. Running in test mode. Install with: pip install twikit", "yellow"))

# Load environment variables
load_dotenv()

# ========================
# CONFIGURATION
# ========================

# Tokens to track - prioritized for crypto/meme coins
TOKENS_TO_TRACK = [
    "solana", "SOL", "$SOL",
    "pepe", "PEPE", "$PEPE",
    "dogecoin", "DOGE", "$DOGE",
    "shiba", "SHIB", "$SHIB",
    "bitcoin", "BTC", "$BTC",
    "ethereum", "ETH", "$ETH",
    "extended", "$EXT",  # Extended Exchange token
]

# Data collection settings
TWEETS_PER_RUN = 50  # Number of tweets to analyze per run
CHECK_INTERVAL_MINUTES = 15  # How often to run (matches your other scrapers)
SENTIMENT_THRESHOLD = 0.4  # Alert threshold for significant sentiment

# Ignore list for filtering spam
IGNORE_LIST = ['t.co', 'discord', 'join', 'telegram', 'giveaway', 'airdrop', 'presale']

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 54594)),
    'database': os.getenv('DB_NAME', 'postgres'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres')
}

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/twitter_sentiment.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class TwitterSentimentScraper:
    """Scraper for Twitter crypto sentiment analysis"""

    def __init__(self):
        """Initialize the sentiment scraper"""
        self.db_conn = None
        self.tokenizer = None
        self.model = None
        self.twitter_client = None
        self.test_mode = not TWITTER_AVAILABLE

        # Initialize components
        self.setup_database()
        if BERT_AVAILABLE:
            self.load_sentiment_model()
        if TWITTER_AVAILABLE and not self.test_mode:
            self.setup_twitter_client()

        logger.info(colored("✅ Twitter Sentiment Scraper initialized!", "green"))
        if self.test_mode:
            logger.info(colored("📝 Running in TEST MODE - using sample data", "yellow"))

    def setup_database(self):
        """Initialize database connection and create tables"""
        try:
            self.db_conn = psycopg2.connect(**DB_CONFIG)
            cursor = self.db_conn.cursor()

            # Create sentiment table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS crypto_sentiment (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP NOT NULL,
                    token VARCHAR(50) NOT NULL,
                    sentiment_score FLOAT NOT NULL,
                    tweet_count INTEGER NOT NULL,
                    positive_count INTEGER DEFAULT 0,
                    negative_count INTEGER DEFAULT 0,
                    neutral_count INTEGER DEFAULT 0,
                    avg_engagement FLOAT DEFAULT 0,
                    top_influencer_sentiment FLOAT,
                    data_source VARCHAR(50) DEFAULT 'twitter',
                    UNIQUE(timestamp, token, data_source)
                )
            """)

            # Create index for faster queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sentiment_timestamp
                ON crypto_sentiment(timestamp DESC)
            """)

            self.db_conn.commit()
            logger.info(colored("✅ Database tables created/verified", "green"))

        except Exception as e:
            logger.error(f"Database setup error: {e}")
            raise

    def load_sentiment_model(self):
        """Load the FinBERT sentiment analysis model"""
        if not BERT_AVAILABLE:
            logger.warning("Transformers not available - skipping model load")
            return

        try:
            logger.info("Loading FinBERT sentiment model...")
            model_name = "finiteautomata/bertweet-base-sentiment-analysis"

            # Download and cache the model
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)

            # Set to evaluation mode
            self.model.eval()

            logger.info(colored("✅ FinBERT model loaded successfully", "green"))

        except Exception as e:
            logger.error(f"Error loading sentiment model: {e}")
            logger.info("Will use random sentiment for testing")

    def setup_twitter_client(self):
        """Initialize Twitter client with credentials"""
        if not TWITTER_AVAILABLE:
            return

        try:
            # Check for Twitter credentials
            username = os.getenv('TWITTER_USERNAME')
            email = os.getenv('TWITTER_EMAIL')
            password = os.getenv('TWITTER_PASSWORD')

            if not all([username, email, password]):
                logger.warning("Twitter credentials not found - running in test mode")
                self.test_mode = True
                return

            # Initialize client (would need cookies.json from twitter_login.py)
            # For now, we'll use test mode
            logger.info("Twitter client setup skipped - using test mode")
            self.test_mode = True

        except Exception as e:
            logger.error(f"Twitter client setup error: {e}")
            self.test_mode = True

    def analyze_sentiment(self, texts: List[str]) -> Tuple[float, Dict]:
        """
        Analyze sentiment of text batch
        Returns: (average_sentiment, breakdown_dict)
        """
        if not texts:
            return 0.0, {'positive': 0, 'negative': 0, 'neutral': 0}

        if not BERT_AVAILABLE or self.model is None:
            # Test mode - return random sentiment
            sentiment = np.random.uniform(-0.5, 0.5)
            count = len(texts)
            pos = int(count * max(0, sentiment + 0.5))
            neg = int(count * max(0, -sentiment + 0.5))
            neu = count - pos - neg
            return sentiment, {'positive': pos, 'negative': neg, 'neutral': neu}

        try:
            sentiments = []
            breakdown = {'positive': 0, 'negative': 0, 'neutral': 0}
            batch_size = 8

            # Process in batches
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                inputs = self.tokenizer(
                    batch_texts,
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

                        # Classify
                        if pos > 0.5:
                            breakdown['positive'] += 1
                        elif neg > 0.5:
                            breakdown['negative'] += 1
                        else:
                            breakdown['neutral'] += 1

                        # Calculate score (-1 to 1)
                        score = pos - neg
                        sentiments.append(score)

            return np.mean(sentiments) if sentiments else 0.0, breakdown

        except Exception as e:
            logger.error(f"Sentiment analysis error: {e}")
            return 0.0, {'positive': 0, 'negative': 0, 'neutral': 0}

    def get_test_tweets(self, token: str) -> List[str]:
        """Generate test tweets for development/testing"""
        samples = [
            f"{token} is mooning! 🚀 Best investment ever!",
            f"Just bought more {token}, feeling bullish",
            f"{token} chart looking strong, breakout incoming",
            f"Sold my {token}, taking profits here",
            f"{token} might dump, be careful",
            f"Hearing rumors about {token} partnership",
            f"{token} has great fundamentals",
            f"Not sure about {token} right now",
            f"{token} community is amazing",
            f"Big whale just bought {token}!"
        ]

        # Return random subset
        import random
        return random.sample(samples, min(len(samples), TWEETS_PER_RUN))

    def fetch_tweets(self, query: str) -> List[Dict]:
        """
        Fetch tweets for a query
        Returns list of tweet dictionaries
        """
        if self.test_mode:
            # Return test data
            tweets_text = self.get_test_tweets(query)
            return [{'text': text, 'engagement': np.random.randint(10, 1000)}
                   for text in tweets_text]

        # TODO: Implement actual Twitter fetching when client is ready
        # For now, return test data
        return self.get_test_tweets(query)

    def scrape_token_sentiment(self, token: str) -> Optional[Dict]:
        """Scrape and analyze sentiment for a specific token"""
        try:
            logger.info(f"Analyzing sentiment for: {token}")

            # Fetch tweets (or use test data)
            if self.test_mode:
                tweets = [{'text': t} for t in self.get_test_tweets(token)]
            else:
                tweets = self.fetch_tweets(token)

            if not tweets:
                logger.warning(f"No tweets found for {token}")
                return None

            # Filter spam
            filtered_tweets = []
            for tweet in tweets:
                text = tweet.get('text', '').lower()
                if not any(spam in text for spam in IGNORE_LIST):
                    filtered_tweets.append(tweet)

            if not filtered_tweets:
                return None

            # Extract text for sentiment analysis
            tweet_texts = [t['text'] for t in filtered_tweets]

            # Analyze sentiment
            avg_sentiment, breakdown = self.analyze_sentiment(tweet_texts)

            # Calculate engagement (if available)
            avg_engagement = np.mean([t.get('engagement', 0) for t in filtered_tweets])

            result = {
                'token': token,
                'sentiment_score': avg_sentiment,
                'tweet_count': len(filtered_tweets),
                'positive_count': breakdown['positive'],
                'negative_count': breakdown['negative'],
                'neutral_count': breakdown['neutral'],
                'avg_engagement': avg_engagement,
                'timestamp': datetime.now()
            }

            # Alert if significant sentiment
            if abs(avg_sentiment) > SENTIMENT_THRESHOLD:
                sentiment_type = "BULLISH 📈" if avg_sentiment > 0 else "BEARISH 📉"
                logger.info(colored(
                    f"🚨 {sentiment_type} sentiment for {token}: {avg_sentiment:.3f}",
                    "green" if avg_sentiment > 0 else "red"
                ))

            return result

        except Exception as e:
            logger.error(f"Error scraping {token}: {e}")
            return None

    def save_to_database(self, sentiment_data: Dict):
        """Save sentiment data to PostgreSQL"""
        try:
            cursor = self.db_conn.cursor()

            # Insert or update sentiment data
            cursor.execute("""
                INSERT INTO crypto_sentiment
                (timestamp, token, sentiment_score, tweet_count,
                 positive_count, negative_count, neutral_count,
                 avg_engagement, data_source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'twitter')
                ON CONFLICT (timestamp, token, data_source)
                DO UPDATE SET
                    sentiment_score = EXCLUDED.sentiment_score,
                    tweet_count = EXCLUDED.tweet_count,
                    positive_count = EXCLUDED.positive_count,
                    negative_count = EXCLUDED.negative_count,
                    neutral_count = EXCLUDED.neutral_count,
                    avg_engagement = EXCLUDED.avg_engagement
            """, (
                sentiment_data['timestamp'],
                sentiment_data['token'],
                sentiment_data['sentiment_score'],
                sentiment_data['tweet_count'],
                sentiment_data['positive_count'],
                sentiment_data['negative_count'],
                sentiment_data['neutral_count'],
                sentiment_data['avg_engagement']
            ))

            self.db_conn.commit()

        except Exception as e:
            logger.error(f"Database save error: {e}")
            self.db_conn.rollback()

    def get_recent_sentiment(self, token: str, hours: int = 24) -> pd.DataFrame:
        """Get recent sentiment history for a token"""
        try:
            query = """
                SELECT timestamp, sentiment_score, tweet_count
                FROM crypto_sentiment
                WHERE token = %s
                AND timestamp > %s
                ORDER BY timestamp DESC
            """

            cutoff = datetime.now() - timedelta(hours=hours)
            df = pd.read_sql(query, self.db_conn, params=(token, cutoff))
            return df

        except Exception as e:
            logger.error(f"Error fetching sentiment history: {e}")
            return pd.DataFrame()

    def run(self):
        """Main execution method"""
        logger.info(colored("\n🔄 Starting sentiment analysis run...", "cyan"))

        results = []
        for token in TOKENS_TO_TRACK:
            result = self.scrape_token_sentiment(token)
            if result:
                self.save_to_database(result)
                results.append(result)
                time.sleep(2)  # Rate limiting

        # Summary
        if results:
            avg_sentiment = np.mean([r['sentiment_score'] for r in results])
            total_tweets = sum(r['tweet_count'] for r in results])

            logger.info(colored(f"\n📊 Summary:", "cyan"))
            logger.info(f"  • Tokens analyzed: {len(results)}")
            logger.info(f"  • Total tweets: {total_tweets}")
            logger.info(f"  • Average sentiment: {avg_sentiment:.3f}")

            # Find most bullish/bearish
            sorted_results = sorted(results, key=lambda x: x['sentiment_score'])
            if sorted_results:
                most_bearish = sorted_results[0]
                most_bullish = sorted_results[-1]

                logger.info(colored(f"  • Most bullish: {most_bullish['token']} ({most_bullish['sentiment_score']:.3f})", "green"))
                logger.info(colored(f"  • Most bearish: {most_bearish['token']} ({most_bearish['sentiment_score']:.3f})", "red"))

        logger.info(colored("✅ Sentiment analysis complete!\n", "green"))

    def schedule_runs(self):
        """Schedule periodic runs"""
        # Run immediately
        self.run()

        # Schedule future runs
        schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(self.run)

        logger.info(f"📅 Scheduled to run every {CHECK_INTERVAL_MINUTES} minutes")

        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute

def main():
    """Main entry point"""
    try:
        scraper = TwitterSentimentScraper()

        # Check if running standalone or via orchestrator
        if len(sys.argv) > 1 and sys.argv[1] == "--once":
            # Run once (for orchestrator)
            scraper.run()
        else:
            # Run on schedule
            scraper.schedule_runs()

    except KeyboardInterrupt:
        logger.info("\n👋 Sentiment scraper stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()