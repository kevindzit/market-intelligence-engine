"""
Binance Liquidations Scraper
Tracks real-time liquidations via WebSocket for flash crash/pump detection
Streams live liquidation data from Binance Futures
Critical for catching reversals during capitulation events
"""

import os
import sys
import time
import json
from datetime import datetime
from pathlib import Path
import psycopg2
from dotenv import load_dotenv
import websocket
import threading

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(override=True)

# Database configuration
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '54594')
DB_NAME = os.getenv('DB_NAME', 'pjx')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

# Scraper configuration
WEBSOCKET_URL = "wss://fstream.binance.com/ws/!forceOrder@arr"
SAVE_INTERVAL = 30  # Save to database every 30 seconds

# All tokens we track
TOKENS = [
    'PEPE', 'DOGE', 'SHIB', 'BONK', 'WIF',
    'BTC', 'ETH', 'SOL', 'BNB', 'XRP',
    'ADA', 'TRX', 'LTC',
    'UNI', 'AAVE', 'LDO', 'MKR', 'CRV',
    'GMX', 'SNX', 'LINK',
    'AVAX', 'DOT', 'NEAR', 'ATOM', 'ICP',
    'ALGO', 'FTM',
    'ARB', 'OP', 'MATIC', 'METIS', 'IMX',
    'RENDER', 'FET', 'GRT', 'OCEAN', 'AGIX', 'TAO',
    'SUI', 'TON', 'SEI'
]

# Map full Binance symbol to our token (e.g., "BTCUSDT" -> "BTC")
SYMBOL_MAP = {f"{token}USDT": token for token in TOKENS}


class LiquidationScraper:
    """Streams liquidation data from Binance WebSocket"""

    def __init__(self):
        self.db_conn = None
        self.pending_liquidations = []
        self.liquidation_cache = set()  # Track seen liquidations (order_id)
        self.last_save = datetime.now()
        self.ws = None
        self.running = False

    def init_db(self):
        """Initialize database connection"""
        try:
            self.db_conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Connected to PostgreSQL")
        except Exception as e:
            print(f"[ERROR] Database connection failed: {e}")
            raise

    def on_message(self, ws, message):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(message)

            # WebSocket sends liquidation order data
            # Format: {"e":"forceOrder","E":timestamp,"o":{order details}}
            if data.get('e') == 'forceOrder':
                order = data.get('o', {})

                symbol = order.get('s', '')  # e.g., "BTCUSDT"
                token = SYMBOL_MAP.get(symbol)

                # Only process tokens we track
                if not token:
                    return

                # Unique identifier for deduplication
                order_id = order.get('T')  # Trade time as unique ID
                if not order_id or order_id in self.liquidation_cache:
                    return

                # Parse liquidation data
                liquidation = {
                    'token': token,
                    'side': order.get('S', 'UNKNOWN'),  # BUY or SELL
                    'price': float(order.get('p', 0)),  # Average price
                    'quantity': float(order.get('q', 0)),  # Original quantity
                    'liquidation_value': float(order.get('p', 0)) * float(order.get('q', 0)),
                    'timestamp': datetime.fromtimestamp(order.get('T', 0) / 1000),
                    'source': 'binance'
                }

                # Add to pending saves and cache
                self.pending_liquidations.append(liquidation)
                self.liquidation_cache.add(order_id)

                # Limit cache size
                if len(self.liquidation_cache) > 10000:
                    # Clear oldest half
                    self.liquidation_cache = set(list(self.liquidation_cache)[5000:])

                # Print significant liquidations
                if liquidation['liquidation_value'] > 100000:  # Over $100k
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Large liquidation: "
                          f"{token} ${liquidation['liquidation_value']:,.0f} ({liquidation['side']})")

                # Save periodically
                now = datetime.now()
                if (now - self.last_save).total_seconds() >= SAVE_INTERVAL:
                    self.save_to_db()
                    self.last_save = now

        except Exception as e:
            print(f"[ERROR] Failed to process message: {e}")

    def on_error(self, ws, error):
        """Handle WebSocket errors"""
        print(f"[ERROR] WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket close"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] WebSocket closed: {close_msg}")

        # Save any pending liquidations before closing
        if self.pending_liquidations:
            self.save_to_db()

    def on_open(self, ws):
        """Handle WebSocket open"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] WebSocket connected - streaming liquidations...")

    def save_to_db(self):
        """Save pending liquidations to database"""
        if not self.pending_liquidations:
            return

        saved = 0
        try:
            cursor = self.db_conn.cursor()

            for liq in self.pending_liquidations:
                try:
                    cursor.execute("""
                        INSERT INTO liquidations
                        (token, side, liquidation_value, price, quantity, timestamp, source)
                        VALUES (%(token)s, %(side)s, %(liquidation_value)s,
                                %(price)s, %(quantity)s, %(timestamp)s, %(source)s)
                    """, liq)
                    saved += 1
                except Exception as e:
                    # Skip duplicates or errors
                    pass

            self.db_conn.commit()
            cursor.close()

            if saved > 0:
                # Aggregate for display
                aggregated = self.aggregate_liquidations(self.pending_liquidations)

                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Saved {saved} liquidations")

                # Show top liquidated tokens
                sorted_tokens = sorted(aggregated.items(),
                                     key=lambda x: x[1]['total_value'], reverse=True)

                for token, data in sorted_tokens[:5]:
                    total_value = data['total_value']
                    long_pct = (data['long_liquidations'] / total_value * 100) if total_value > 0 else 0
                    short_pct = (data['short_liquidations'] / total_value * 100) if total_value > 0 else 0

                    signal = ""
                    if total_value > 1000000:
                        if long_pct > 70:
                            signal = "[LONG SQUEEZE]"
                        elif short_pct > 70:
                            signal = "[SHORT SQUEEZE]"

                    print(f"  {token:<8} ${total_value:>12,.0f} "
                          f"(Longs: {long_pct:>5.1f}% Shorts: {short_pct:>5.1f}%) {signal}")

            # Clear pending liquidations
            self.pending_liquidations = []

        except Exception as e:
            print(f"[ERROR] Database save failed: {e}")

    def aggregate_liquidations(self, liquidations):
        """Aggregate liquidations by token"""
        aggregated = {}

        for liq in liquidations:
            token = liq['token']
            if token not in aggregated:
                aggregated[token] = {
                    'total_value': 0,
                    'long_liquidations': 0,
                    'short_liquidations': 0,
                    'count': 0
                }

            aggregated[token]['total_value'] += liq['liquidation_value']
            aggregated[token]['count'] += 1

            if liq['side'] == 'SELL':  # Long liquidation (forced sell)
                aggregated[token]['long_liquidations'] += liq['liquidation_value']
            else:  # Short liquidation (forced buy)
                aggregated[token]['short_liquidations'] += liq['liquidation_value']

        return aggregated

    def run(self):
        """Main loop - connect to WebSocket and stream"""
        print("\n" + "="*70)
        print("BINANCE LIQUIDATIONS SCRAPER (WebSocket)")
        print(f"Tracking {len(TOKENS)} tokens")
        print(f"Saving to database every {SAVE_INTERVAL} seconds")
        print("="*70)

        self.init_db()
        self.running = True

        # WebSocket connection with auto-reconnect
        while self.running:
            try:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Connecting to Binance WebSocket...")

                self.ws = websocket.WebSocketApp(
                    WEBSOCKET_URL,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                    on_open=self.on_open
                )

                # Run forever (will reconnect on disconnect)
                self.ws.run_forever()

            except KeyboardInterrupt:
                print("\n[INFO] Shutting down...")
                self.running = False
                break
            except Exception as e:
                print(f"[ERROR] WebSocket connection failed: {e}")
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Reconnecting in 10 seconds...")
                time.sleep(10)

        # Cleanup
        if self.db_conn:
            if self.pending_liquidations:
                self.save_to_db()
            self.db_conn.close()


def main():
    scraper = LiquidationScraper()
    scraper.run()


if __name__ == "__main__":
    main()
