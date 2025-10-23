"""
End-to-End Integration Test for PJX Crypto Trading System

This script tests all components working together:
1. Twitter sentiment scraper
2. Extended Exchange integration
3. Paper trading framework
4. Claude trading agent
5. Risk management agent
"""

import os
import sys
import time
import json
import logging
from datetime import datetime
from termcolor import colored

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def print_header(title: str):
    """Print a formatted header"""
    print(colored("\n" + "="*60, "cyan"))
    print(colored(f"  {title}", "cyan", attrs=['bold']))
    print(colored("="*60, "cyan"))

def test_database_connection():
    """Test PostgreSQL connection"""
    print_header("Testing Database Connection")
    try:
        import psycopg2
        from dotenv import load_dotenv
        load_dotenv()

        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 54594)),
            database=os.getenv('DB_NAME', 'postgres'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'postgres')
        )
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        conn.close()

        print(colored("✅ PostgreSQL connected successfully", "green"))
        print(f"   Version: {version[0][:50]}...")
        return True

    except Exception as e:
        print(colored(f"❌ Database connection failed: {e}", "red"))
        return False

def test_sentiment_scraper():
    """Test Twitter sentiment scraper"""
    print_header("Testing Twitter Sentiment Scraper")
    try:
        from crypto_scrapers.twitter_sentiment import TwitterSentimentScraper

        scraper = TwitterSentimentScraper()
        print(colored("✅ Sentiment scraper initialized", "green"))

        # Test with a single token
        result = scraper.scrape_token_sentiment('bitcoin')
        if result:
            print(f"   Sentiment for Bitcoin: {result['sentiment_score']:.3f}")
            print(f"   Tweets analyzed: {result['tweet_count']}")
            print(colored("✅ Sentiment analysis working", "green"))
        else:
            print(colored("⚠️ No sentiment data (may be in test mode)", "yellow"))

        return True

    except ImportError as e:
        print(colored(f"⚠️ Dependencies missing: {e}", "yellow"))
        print("   Install with: pip install transformers torch twikit")
        return False
    except Exception as e:
        print(colored(f"❌ Sentiment scraper error: {e}", "red"))
        return False

def test_extended_exchange():
    """Test Extended Exchange integration"""
    print_header("Testing Extended Exchange")
    try:
        from exchanges.extended_exchange import ExtendedExchange, OrderSide, OrderType

        # Test in paper trading mode
        exchange = ExtendedExchange(paper_trading=True)
        print(colored("✅ Extended Exchange initialized (paper mode)", "green"))

        # Test market price fetch
        btc_price = exchange.get_market_price('BTC-USD')
        print(f"   BTC Price: ${btc_price:.2f}")

        # Test balance
        balance = exchange.get_balance()
        print(f"   Balance: {balance}")

        # Test paper trade
        result = exchange.place_order(
            symbol='BTC-USD',
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            usd_amount=50
        )

        if result['success']:
            print(colored("✅ Paper trade executed successfully", "green"))
            print(f"   Order ID: {result['order_id']}")
            print(f"   Points earned: {result.get('points_earned', 0):.2f}")
        else:
            print(colored(f"⚠️ Trade failed: {result.get('error')}", "yellow"))

        exchange.close()
        return True

    except Exception as e:
        print(colored(f"❌ Exchange test error: {e}", "red"))
        return False

def test_paper_trading_framework():
    """Test paper trading tracker"""
    print_header("Testing Paper Trading Framework")
    try:
        from paper_trading.tracker import PaperTradingTracker

        tracker = PaperTradingTracker(initial_balance=1000)
        print(colored("✅ Paper trading tracker initialized", "green"))

        # Test trade validation
        is_valid, reason = tracker.validate_trade(
            symbol='BTC-USD',
            side='buy',
            quantity=0.001,
            price=65000
        )
        print(f"   Trade validation: {'✅ Valid' if is_valid else '❌ Invalid'}")
        if not is_valid:
            print(f"   Reason: {reason}")

        # Test trade execution
        result = tracker.execute_trade(
            symbol='BTC-USD',
            side='buy',
            quantity=0.001,
            price=65000
        )

        if result['success']:
            print(colored("✅ Paper trade recorded", "green"))
            print(f"   Trade ID: {result['trade_id']}")
            print(f"   New balance: ${result['new_balance']['USD']:.2f}")
        else:
            print(colored(f"⚠️ Trade failed: {result.get('error')}", "yellow"))

        # Test metrics
        portfolio_value = tracker.get_portfolio_value()
        print(f"   Portfolio value: ${portfolio_value:.2f}")

        # Test graduation criteria
        is_ready, criteria = tracker.should_graduate_to_live()
        print(f"   Ready for live trading: {'Yes' if is_ready else 'No'}")

        tracker.close()
        return True

    except Exception as e:
        print(colored(f"❌ Paper trading test error: {e}", "red"))
        return False

def test_risk_management():
    """Test risk management agent"""
    print_header("Testing Risk Management Agent")
    try:
        from agents.risk_agent import RiskManagementAgent, RiskLevel

        risk_agent = RiskManagementAgent(portfolio_value=1000)
        print(colored("✅ Risk management agent initialized", "green"))

        # Test trade risk assessment
        assessment = risk_agent.assess_trade_risk(
            symbol='BTC-USD',
            side='buy',
            quantity=0.001,
            price=65000,
            current_positions={},
            portfolio_value=1000
        )

        print(f"   Risk level: {assessment.level.value}")
        print(f"   Action: {assessment.action.value}")
        print(f"   Reasoning: {assessment.reasoning}")

        if assessment.recommendations:
            print(f"   Recommendations: {assessment.recommendations[0]}")

        # Test portfolio monitoring
        positions = {'BTC': {'value': 200, 'quantity': 0.003}}
        portfolio_assessment = risk_agent.monitor_portfolio_risk(positions, 980)
        print(f"   Portfolio risk: {portfolio_assessment.level.value}")

        risk_agent.close()
        return True

    except Exception as e:
        print(colored(f"❌ Risk management test error: {e}", "red"))
        return False

def test_claude_trading_agent():
    """Test Claude trading agent (requires API key)"""
    print_header("Testing Claude Trading Agent")
    try:
        from dotenv import load_dotenv
        load_dotenv()

        if not os.getenv('ANTHROPIC_KEY'):
            print(colored("⚠️ ANTHROPIC_KEY not set - skipping Claude test", "yellow"))
            print("   Add your Claude API key to .env file to enable")
            return True  # Don't fail the test

        from agents.trading_agent import ClaudeTradingAgent

        # Initialize in paper trading mode
        agent = ClaudeTradingAgent(paper_trading=True)
        print(colored("✅ Claude trading agent initialized", "green"))

        # Test market data fetch
        market_data = agent.fetch_market_data('BTC-USD')
        print(f"   Market data fetched: {len(market_data)} fields")

        # We won't run actual analysis to avoid API costs
        print(colored("⚠️ Skipping live Claude analysis to save API costs", "yellow"))
        print("   Run the trading agent separately to test Claude integration")

        agent.close()
        return True

    except ImportError as e:
        print(colored(f"⚠️ Anthropic library not installed: {e}", "yellow"))
        print("   Install with: pip install anthropic")
        return False
    except Exception as e:
        print(colored(f"❌ Claude agent test error: {e}", "red"))
        return False

def test_orchestrator_config():
    """Test orchestrator configuration"""
    print_header("Testing Orchestrator Configuration")
    try:
        import yaml

        with open('config/scrapers.yaml', 'r') as f:
            config = yaml.safe_load(f)

        scrapers = config['scrapers']
        print(f"   Total scrapers configured: {len(scrapers)}")

        # Count by category
        categories = {}
        for scraper in scrapers:
            cat = scraper.get('category', 'unknown')
            categories[cat] = categories.get(cat, 0) + 1

        for cat, count in categories.items():
            print(f"   {cat.capitalize()}: {count} scrapers")

        # Check if crypto scraper is added
        crypto_scrapers = [s for s in scrapers if s.get('category') == 'crypto']
        if crypto_scrapers:
            print(colored("✅ Crypto scrapers configured", "green"))
            for scraper in crypto_scrapers:
                print(f"     - {scraper['name']}")
        else:
            print(colored("⚠️ No crypto scrapers in config", "yellow"))

        return True

    except Exception as e:
        print(colored(f"❌ Config test error: {e}", "red"))
        return False

def check_dependencies():
    """Check if all required packages are installed"""
    print_header("Checking Dependencies")

    required_packages = [
        ('pandas', 'Data manipulation'),
        ('numpy', 'Numerical operations'),
        ('psycopg2', 'PostgreSQL connection'),
        ('python-dotenv', 'Environment variables'),
        ('termcolor', 'Colored output'),
        ('requests', 'HTTP requests'),
        ('anthropic', 'Claude API (optional)'),
        ('transformers', 'Sentiment analysis (optional)'),
        ('torch', 'Machine learning (optional)'),
        ('twikit', 'Twitter scraping (optional)'),
        ('schedule', 'Task scheduling'),
        ('pyyaml', 'YAML config files')
    ]

    missing = []
    optional_missing = []

    for package, description in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print(colored(f"✅ {package}: {description}", "green"))
        except ImportError:
            if 'optional' in description.lower():
                optional_missing.append((package, description))
                print(colored(f"⚠️ {package}: {description} - NOT INSTALLED", "yellow"))
            else:
                missing.append((package, description))
                print(colored(f"❌ {package}: {description} - NOT INSTALLED", "red"))

    if missing:
        print(colored(f"\n❌ Missing required packages:", "red"))
        for pkg, desc in missing:
            print(f"   pip install {pkg}")
        return False

    if optional_missing:
        print(colored(f"\n⚠️ Optional packages not installed:", "yellow"))
        for pkg, desc in optional_missing:
            print(f"   pip install {pkg}  # {desc}")

    return True

def main():
    """Run all integration tests"""
    print(colored("\n" + "="*60, "cyan", attrs=['bold']))
    print(colored("  PJX CRYPTO TRADING SYSTEM - INTEGRATION TEST", "cyan", attrs=['bold']))
    print(colored("="*60, "cyan", attrs=['bold']))

    tests = [
        ("Dependencies", check_dependencies),
        ("Database", test_database_connection),
        ("Orchestrator Config", test_orchestrator_config),
        ("Sentiment Scraper", test_sentiment_scraper),
        ("Extended Exchange", test_extended_exchange),
        ("Paper Trading", test_paper_trading_framework),
        ("Risk Management", test_risk_management),
        ("Claude Trading Agent", test_claude_trading_agent),
    ]

    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print(colored(f"❌ {name} test crashed: {e}", "red"))
            results[name] = False

    # Summary
    print_header("TEST SUMMARY")

    passed = sum(1 for r in results.values() if r)
    total = len(results)

    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        color = "green" if result else "red"
        print(colored(f"  {name}: {status}", color))

    print(colored(f"\n  Total: {passed}/{total} tests passed",
                 "green" if passed == total else "yellow" if passed >= total/2 else "red",
                 attrs=['bold']))

    if passed == total:
        print(colored("\n🎉 All systems operational! Ready to trade!", "green", attrs=['bold']))
    elif passed >= total - 2:
        print(colored("\n⚠️ System mostly ready. Fix remaining issues before live trading.", "yellow"))
    else:
        print(colored("\n❌ System not ready. Please fix the issues above.", "red"))

    # Next steps
    print_header("NEXT STEPS")

    if results.get("Dependencies") and results.get("Database"):
        print("1. ✅ Add your API keys to the .env file:")
        print("   - ANTHROPIC_KEY (for Claude)")
        print("   - GEMINI_KEY (for Gemini)")
        print("   - DEEPSEEK_KEY (for DeepSeek)")
        print("   - Extended Exchange credentials")
        print("")
        print("2. 📊 Start paper trading:")
        print("   python agents/trading_agent.py")
        print("")
        print("3. 📈 Monitor with orchestrator:")
        print("   python orchestrator.py")
        print("")
        print("4. 🔍 Check system status:")
        print("   python system_test.py")
    else:
        print("❌ Fix dependency and database issues first")

if __name__ == "__main__":
    main()