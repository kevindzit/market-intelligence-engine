"""
Macro Intelligence Filter V2 - Fixed Version
Extracts only crypto-relevant signals from traditional finance data
Each method creates its own database connection to avoid transaction issues
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import Dict, Optional

class MacroIntelligence:
    """
    Filters traditional finance data to extract only crypto-relevant signals.
    This prevents information overload while capturing important macro events.
    """

    # Crypto-related keywords for filtering
    CRYPTO_KEYWORDS = [
        'bitcoin', 'btc', 'ethereum', 'eth', 'crypto', 'cryptocurrency',
        'blockchain', 'defi', 'stablecoin', 'usdt', 'usdc', 'binance', 'coinbase',
        'microstrategy', 'mstr', 'grayscale', 'gbtc', 'digital asset', 'web3'
    ]

    # Crypto-related stock tickers
    CRYPTO_STOCKS = ['COIN', 'MSTR', 'RIOT', 'MARA', 'HUT', 'CLSK', 'PYPL', 'SQ', 'TSLA']

    def __init__(self, db_config: Dict):
        """Initialize with database connection config"""
        self.db_config = db_config

    def get_crypto_macro_context(self) -> Dict:
        """
        Main method: Returns concise crypto-relevant macro signals.
        This is what the AI trader will use instead of raw data dumps.
        """
        context = {
            'timestamp': datetime.now().isoformat(),
            'signals': {},
            'alerts': [],
            'macro_score': 0
        }

        # 1. Check for crypto-relevant news
        news_signal = self._filter_crypto_news()
        if news_signal:
            context['signals']['news'] = news_signal
            # Add to macro score
            if news_signal['direction'] == 'BULLISH':
                context['macro_score'] += 30
            elif news_signal['direction'] == 'BEARISH':
                context['macro_score'] -= 30

        # 2. Check congressional crypto activity
        congress_signal = self._check_congressional_crypto()
        if congress_signal:
            context['signals']['congress'] = congress_signal
            # Add to macro score
            if congress_signal['signal'] == 'BULLISH':
                context['macro_score'] += 20
            elif congress_signal['signal'] == 'BEARISH':
                context['macro_score'] -= 20

        # Generate summary
        context['summary'] = self._generate_summary(context)
        return context

    def _filter_crypto_news(self, hours: int = 24) -> Optional[Dict]:
        """Filter news for crypto-relevant content only"""
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Get recent news
                cursor.execute("""
                    SELECT title, content, source, published_at
                    FROM news_articles
                    WHERE published_at > NOW() - INTERVAL %s
                    ORDER BY published_at DESC
                    LIMIT 100
                """, (f"{hours} hours",))

                articles = cursor.fetchall()
                if not articles:
                    return None

                crypto_articles = []
                for article in articles:
                    # Check if article is crypto-relevant
                    text = f"{article['title']} {article['content'] or ''}".lower()

                    if any(keyword in text for keyword in self.CRYPTO_KEYWORDS):
                        crypto_articles.append({
                            'title': article['title'],
                            'source': article['source']
                        })

                if not crypto_articles:
                    return None

                # Simple sentiment based on article count (simplified)
                return {
                    'article_count': len(crypto_articles),
                    'direction': 'BULLISH' if len(crypto_articles) > 10 else 'NEUTRAL',
                    'top_headlines': [a['title'] for a in crypto_articles[:3]]
                }

        except Exception as e:
            # Silently fail - this is optional data
            return None
        finally:
            if conn:
                conn.close()

    def _check_congressional_crypto(self, days: int = 7) -> Optional[Dict]:
        """Check for congressional trading in crypto-related stocks"""
        conn = None
        try:
            conn = psycopg2.connect(**self.db_config)
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Look for crypto stock trades
                placeholders = ','.join(['%s'] * len(self.CRYPTO_STOCKS))
                cursor.execute(f"""
                    SELECT ticker, transaction_type, representative_name
                    FROM congressional_trades
                    WHERE ticker IN ({placeholders})
                    AND transaction_date > NOW() - INTERVAL %s
                    ORDER BY transaction_date DESC
                """, self.CRYPTO_STOCKS + [f"{days} days"])

                trades = cursor.fetchall()
                if not trades:
                    return None

                # Analyze trade patterns
                buys = len([t for t in trades if t['transaction_type'] in ['Purchase', 'Buy']])
                sells = len([t for t in trades if t['transaction_type'] in ['Sale', 'Sell']])

                if buys > sells * 2:
                    signal = 'BULLISH'
                elif sells > buys * 2:
                    signal = 'BEARISH'
                else:
                    signal = 'NEUTRAL'

                return {
                    'signal': signal,
                    'buy_count': buys,
                    'sell_count': sells,
                    'confidence': 0.5
                }

        except Exception as e:
            # Silently fail - this is optional data
            return None
        finally:
            if conn:
                conn.close()

    def _generate_summary(self, context: Dict) -> str:
        """Generate a concise summary for the AI trader"""
        score = context['macro_score']

        # Determine overall bias
        if score > 30:
            bias = "BULLISH"
        elif score < -30:
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        summary_parts = [f"Macro bias: {bias} ({score:+d}/100)"]

        # Add signals if present
        signals = context.get('signals', {})
        if 'news' in signals:
            summary_parts.append(f"News: {signals['news']['article_count']} crypto articles")
        if 'congress' in signals:
            summary_parts.append(f"Congress: {signals['congress']['signal']}")

        return " | ".join(summary_parts)