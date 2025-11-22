"""
Trading Interface - Simple abstraction layer for Binance trading
Handles both paper trading (testnet) and real trading with a single switch
"""

import os
from decimal import Decimal
from typing import Dict, Optional, Tuple
from datetime import datetime
from dotenv import load_dotenv

# pip install python-binance
from binance.client import Client
from binance.exceptions import BinanceAPIException

load_dotenv()

class TradingInterface:
    """
    Simple trading interface that works with both Binance Testnet (paper) and Real trading
    Just change PAPER_TRADING flag to switch between modes
    """

    def __init__(self, paper_trading: bool = True):
        """
        Initialize trading interface

        Args:
            paper_trading: True for testnet (paper), False for real trading
        """
        self.paper_trading = paper_trading
        self._symbol_cache = {}

        if paper_trading:
            # TESTNET CREDENTIALS (Paper Trading)
            # Get these from: https://testnet.binance.vision/
            # Login with GitHub, generate API keys
            api_key = os.getenv('BINANCE_TESTNET_API_KEY', '')
            api_secret = os.getenv('BINANCE_TESTNET_API_SECRET', '')

            if not api_key:
                print("\n[SETUP] To use Binance Testnet paper trading:")
                print("1. Visit: https://testnet.binance.vision/")
                print("2. Login with GitHub")
                print("3. Generate HMAC_SHA256 API Key")
                print("4. Add to .env file:")
                print("   BINANCE_TESTNET_API_KEY=your_key")
                print("   BINANCE_TESTNET_API_SECRET=your_secret")
                raise ValueError("Testnet API keys not configured")

            # Create client with testnet=True
            self.client = Client(api_key, api_secret, testnet=True)
            print("[TRADING] Connected to Binance TESTNET (Paper Trading)")

        else:
            # REAL TRADING CREDENTIALS
            # Get these from: https://www.binance.com/en/my/settings/api-management
            api_key = os.getenv('BINANCE_API_KEY', '')
            api_secret = os.getenv('BINANCE_API_SECRET', '')

            if not api_key:
                print("\n[WARNING] Real trading requires Binance API keys!")
                print("Add to .env file:")
                print("   BINANCE_API_KEY=your_real_key")
                print("   BINANCE_API_SECRET=your_real_secret")
                raise ValueError("Real API keys not configured")

            # Create client for real trading
            self.client = Client(api_key, api_secret, testnet=False)
            print("[TRADING] Connected to Binance REAL (Live Trading)")

        # Cache for symbol info (decimal places, min quantities, etc.)
        self.symbol_info_cache = {}

    def get_balance(self, asset: str = 'USDT') -> float:
        """Get balance for an asset"""
        try:
            balance = self.client.get_asset_balance(asset=asset)
            if balance:
                free_balance = float(balance['free'])
                locked_balance = float(balance['locked'])
                total = free_balance + locked_balance

                if self.paper_trading:
                    print(f"[TESTNET BALANCE] {asset}: {total:.2f} (Free: {free_balance:.2f}, Locked: {locked_balance:.2f})")

                return free_balance  # Return only free balance for trading
            return 0.0
        except Exception as e:
            print(f"[ERROR] Failed to get balance for {asset}: {e}")
            return 0.0

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol (e.g., 'BTCUSDT')"""
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except Exception as e:
            print(f"[ERROR] Failed to get price for {symbol}: {e}")
            return None

    def _get_symbol_info(self, symbol: str) -> Dict:
        """Get trading rules for a symbol (min qty, decimals, etc.)"""
        if symbol in self.symbol_info_cache:
            return self.symbol_info_cache[symbol]

        try:
            info = self.client.get_symbol_info(symbol)

            # Extract important filters
            result = {
                'min_qty': 0.001,
                'max_qty': 9999999,
                'qty_step': 0.001,
                'min_notional': 10.0,  # Minimum order value in USDT
                'price_precision': 2,
                'qty_precision': 3
            }

            for filter in info['filters']:
                if filter['filterType'] == 'LOT_SIZE':
                    result['min_qty'] = float(filter['minQty'])
                    result['max_qty'] = float(filter['maxQty'])
                    result['qty_step'] = float(filter['stepSize'])
                elif filter['filterType'] == 'MIN_NOTIONAL':
                    result['min_notional'] = float(filter['minNotional'])

            # Calculate decimal places for quantity
            step_str = str(result['qty_step'])
            if '.' in step_str:
                result['qty_precision'] = len(step_str.split('.')[1].rstrip('0'))

            self.symbol_info_cache[symbol] = result
            return result

        except Exception as e:
            print(f"[WARNING] Failed to get symbol info for {symbol}: {e}")
            # Return defaults
            return {
                'min_qty': 0.001,
                'max_qty': 9999999,
                'qty_step': 0.001,
                'min_notional': 10.0,
                'price_precision': 2,
                'qty_precision': 3
            }

    def is_symbol_tradeable(self, token: str) -> bool:
        """
        Quick eligibility check for Binance spot USDT pairs.
        """
        symbol = f"{token}USDT"
        try:
            info = self.client.get_symbol_info(symbol)
            if not info:
                print(f"[SKIP] {symbol} not listed on Binance")
                return False
            status = info.get('status')
            if status not in {'TRADING', 'TRD_GUARD'}:
                print(f"[SKIP] {symbol} status={status}")
                return False
            filters = {f['filterType']: f for f in info.get('filters', [])}
            min_notional = float(filters.get('NOTIONAL', {}).get('minNotional', 0))
            if min_notional <= 0:
                print(f"[WARN] {symbol} missing minNotional; proceeding cautiously")
            return True
        except Exception as e:
            print(f"[ERROR] Symbol eligibility check failed for {symbol}: {e}")
            return False

    def _round_quantity(self, symbol: str, quantity: float) -> float:
        """Round quantity to correct decimal places for symbol"""
        info = self._get_symbol_info(symbol)
        precision = info['qty_precision']
        return round(quantity, precision)

    def buy(self, token: str, usd_amount: float) -> Optional[Dict]:
        """
        Buy a token with USD amount

        Args:
            token: Token to buy (e.g., 'BTC')
            usd_amount: Amount in USDT to spend

        Returns:
            Order result or None if failed
        """
        symbol = f"{token}USDT"

        try:
            # Get current price
            price = self.get_current_price(symbol)
            if not price:
                print(f"[ERROR] Cannot get price for {symbol}")
                return None

            # Calculate quantity
            quantity = usd_amount / price

            # Round to correct decimals
            quantity = self._round_quantity(symbol, quantity)

            # Check minimum order size
            info = self._get_symbol_info(symbol)
            if quantity < info['min_qty']:
                print(f"[ERROR] Quantity {quantity} below minimum {info['min_qty']} for {symbol}")
                return None

            if usd_amount < info['min_notional']:
                print(f"[ERROR] Order value ${usd_amount:.2f} below minimum ${info['min_notional']:.2f}")
                return None

            # Place market buy order
            print(f"[ORDER] Buying {quantity:.6f} {token} for ${usd_amount:.2f} at ${price:.2f}")

            order = self.client.order_market_buy(
                symbol=symbol,
                quantity=quantity
            )

            if self.paper_trading:
                print(f"[TESTNET] Buy order executed: {order['orderId']}")
            else:
                print(f"[REAL] Buy order executed: {order['orderId']}")

            return order

        except BinanceAPIException as e:
            print(f"[BINANCE ERROR] Buy failed: {e.message}")
            return None
        except Exception as e:
            print(f"[ERROR] Buy failed: {e}")
            return None

    def sell(self, token: str, quantity: Optional[float] = None, sell_all: bool = False) -> Optional[Dict]:
        """
        Sell a token

        Args:
            token: Token to sell (e.g., 'BTC')
            quantity: Amount to sell (if None, sells all)
            sell_all: If True, sells entire balance

        Returns:
            Order result or None if failed
        """
        symbol = f"{token}USDT"

        try:
            # Get balance if selling all
            if sell_all or quantity is None:
                balance = self.get_balance(token)
                if balance <= 0:
                    print(f"[ERROR] No {token} balance to sell")
                    return None
                quantity = balance

            # Round to correct decimals
            quantity = self._round_quantity(symbol, quantity)

            # Check minimum order size
            info = self._get_symbol_info(symbol)
            if quantity < info['min_qty']:
                print(f"[ERROR] Quantity {quantity} below minimum {info['min_qty']} for {symbol}")
                return None

            # Get current price to check notional value
            price = self.get_current_price(symbol)
            if price:
                notional = quantity * price
                if notional < info['min_notional']:
                    print(f"[ERROR] Order value ${notional:.2f} below minimum ${info['min_notional']:.2f}")
                    return None

            # Place market sell order
            print(f"[ORDER] Selling {quantity:.6f} {token}")

            order = self.client.order_market_sell(
                symbol=symbol,
                quantity=quantity
            )

            if self.paper_trading:
                print(f"[TESTNET] Sell order executed: {order['orderId']}")
            else:
                print(f"[REAL] Sell order executed: {order['orderId']}")

            return order

        except BinanceAPIException as e:
            print(f"[BINANCE ERROR] Sell failed: {e.message}")
            return None
        except Exception as e:
            print(f"[ERROR] Sell failed: {e}")
            return None

    def get_portfolio_value(self) -> float:
        """Calculate total portfolio value in USDT"""
        try:
            account = self.client.get_account()
            total_value = 0.0

            for balance in account['balances']:
                asset = balance['asset']
                amount = float(balance['free']) + float(balance['locked'])

                if amount > 0:
                    if asset == 'USDT':
                        total_value += amount
                    else:
                        # Get current price in USDT
                        symbol = f"{asset}USDT"
                        price = self.get_current_price(symbol)
                        if price:
                            value = amount * price
                            total_value += value
                            if amount > 0.0001:  # Only show significant holdings
                                print(f"  {asset}: {amount:.6f} (${value:.2f})")

            print(f"\n[PORTFOLIO] Total Value: ${total_value:.2f}")
            return total_value

        except Exception as e:
            print(f"[ERROR] Failed to get portfolio value: {e}")
            return 0.0

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Get list of open orders"""
        try:
            if symbol:
                orders = self.client.get_open_orders(symbol=symbol)
            else:
                orders = self.client.get_open_orders()

            return orders
        except Exception as e:
            print(f"[ERROR] Failed to get open orders: {e}")
            return []

    def cancel_order(self, symbol: str, order_id: int) -> bool:
        """Cancel an open order"""
        try:
            result = self.client.cancel_order(symbol=symbol, orderId=order_id)
            print(f"[ORDER] Cancelled order {order_id} for {symbol}")
            return True
        except Exception as e:
            print(f"[ERROR] Failed to cancel order {order_id}: {e}")
            return False

    def test_connection(self) -> bool:
        """Test if the connection works"""
        try:
            # Test with a simple ping
            self.client.ping()

            # Get server time
            server_time = self.client.get_server_time()
            server_dt = datetime.fromtimestamp(server_time['serverTime'] / 1000)

            print(f"[CONNECTION] ✓ Connected to Binance {'TESTNET' if self.paper_trading else 'REAL'}")
            print(f"[CONNECTION] Server time: {server_dt}")

            # Show some balance
            usdt_balance = self.get_balance('USDT')
            print(f"[CONNECTION] USDT Balance: ${usdt_balance:.2f}")

            if self.paper_trading:
                print("[INFO] Using TESTNET - Funds are virtual and reset monthly")
                print("[INFO] To switch to real trading: TradingInterface(paper_trading=False)")
            else:
                print("[WARNING] REAL TRADING MODE - Using actual funds!")

            return True

        except Exception as e:
            print(f"[ERROR] Connection test failed: {e}")
            return False


# Example usage
if __name__ == "__main__":
    # Initialize with paper trading (testnet)
    trader = TradingInterface(paper_trading=True)

    # Test connection
    if trader.test_connection():
        print("\n[TEST] Connection successful!")

        # Get BTC price
        btc_price = trader.get_current_price('BTCUSDT')
        if btc_price:
            print(f"\n[PRICE] BTC: ${btc_price:,.2f}")

        # Show portfolio value
        trader.get_portfolio_value()

        # Example: Buy $20 worth of BTC (paper trade)
        # result = trader.buy('BTC', 20)

        # Example: Sell all BTC
        # result = trader.sell('BTC', sell_all=True)
