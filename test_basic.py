"""
Basic Integration Test for PJX Crypto Trading System
This test works with minimal dependencies
"""

import os
import sys
import json

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def colored_print(text, color=None):
    """Simple colored print without termcolor"""
    colors = {
        'green': '\033[92m',
        'yellow': '\033[93m',
        'red': '\033[91m',
        'cyan': '\033[96m',
        'bold': '\033[1m',
        'end': '\033[0m'
    }
    if color and color in colors:
        print(f"{colors[color]}{text}{colors['end']}")
    else:
        print(text)

def print_header(title):
    """Print a header"""
    colored_print("\n" + "="*60, 'cyan')
    colored_print(f"  {title}", 'cyan')
    colored_print("="*60, 'cyan')

def test_database():
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

        # Check tables
        cursor.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
        """)
        tables = cursor.fetchall()

        colored_print("[OK] PostgreSQL connected successfully", 'green')
        colored_print(f"   Found {len(tables)} tables", 'green')

        # Check for our new tables
        our_tables = [
            'crypto_sentiment',
            'extended_orders',
            'extended_positions',
            'extended_points',
            'paper_trades',
            'paper_positions',
            'portfolio_snapshots',
            'trading_signals',
            'agent_decisions',
            'risk_assessments'
        ]

        existing_tables = [t[0] for t in tables]
        for table in our_tables:
            if table in existing_tables:
                colored_print(f"   [OK] {table} table exists", 'green')
            else:
                colored_print(f"   [!] {table} table missing", 'yellow')

        conn.close()
        return True

    except ImportError:
        colored_print("[X] psycopg2 not installed", 'red')
        colored_print("   Install with: pip install psycopg2-binary", 'red')
        return False
    except Exception as e:
        colored_print(f"[X] Database error: {e}", 'red')
        return False

def test_env_file():
    """Test environment variables"""
    print_header("Testing Environment Variables")
    try:
        from dotenv import load_dotenv
        load_dotenv()

        required_vars = {
            'ANTHROPIC_KEY': 'Claude API',
            'GEMINI_KEY': 'Gemini API',
            'DEEPSEEK_KEY': 'DeepSeek API',
            'DB_HOST': 'Database host',
            'DB_PORT': 'Database port',
            'DB_NAME': 'Database name',
            'DB_USER': 'Database user',
            'DB_PASSWORD': 'Database password'
        }

        optional_vars = {
            'EXTENDED_API_KEY': 'Extended Exchange',
            'EXTENDED_API_SECRET': 'Extended Exchange',
            'TWITTER_USERNAME': 'Twitter scraping',
            'COINGECKO_API_KEY': 'CoinGecko data',
            'OPENAI_KEY': 'OpenAI (optional)'
        }

        missing_required = []
        missing_optional = []

        for var, desc in required_vars.items():
            if os.getenv(var):
                colored_print(f"   [OK] {var} set ({desc})", 'green')
            else:
                missing_required.append((var, desc))
                colored_print(f"   [X] {var} not set ({desc})", 'red')

        for var, desc in optional_vars.items():
            if os.getenv(var):
                colored_print(f"   [OK] {var} set ({desc})", 'green')
            else:
                missing_optional.append((var, desc))
                colored_print(f"   [!] {var} not set ({desc})", 'yellow')

        if missing_required:
            colored_print("\n[X] Add these to your .env file:", 'red')
            for var, desc in missing_required:
                colored_print(f"   {var}=your_key_here", 'red')
            return False

        return True

    except ImportError:
        colored_print("[X] python-dotenv not installed", 'red')
        colored_print("   Install with: pip install python-dotenv", 'red')
        return False

def test_file_structure():
    """Test if all files were created"""
    print_header("Testing File Structure")

    required_files = {
        '.env': 'Environment configuration',
        'requirements_crypto.txt': 'Python dependencies',
        'crypto_scrapers/twitter_sentiment.py': 'Twitter sentiment scraper',
        'exchanges/extended_exchange.py': 'Extended Exchange integration',
        'paper_trading/tracker.py': 'Paper trading framework',
        'agents/trading_agent.py': 'Claude trading agent',
        'agents/risk_agent.py': 'Risk management agent',
        'test_integration.py': 'Full integration test',
        'moon-dev-reference/README.md': 'Moon Dev repository'
    }

    all_exist = True
    for file_path, description in required_files.items():
        full_path = os.path.join(os.path.dirname(__file__), file_path)
        if os.path.exists(full_path):
            colored_print(f"   [OK] {file_path} ({description})", 'green')
        else:
            colored_print(f"   [X] {file_path} missing ({description})", 'red')
            all_exist = False

    return all_exist

def test_config():
    """Test configuration files"""
    print_header("Testing Configuration")
    try:
        import yaml

        config_path = 'config/scrapers.yaml'
        if not os.path.exists(config_path):
            colored_print(f"[X] {config_path} not found", 'red')
            return False

        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        scrapers = config.get('scrapers', [])
        colored_print(f"   Total scrapers: {len(scrapers)}", 'green')

        # Check for crypto scraper
        crypto_scrapers = [s for s in scrapers if s.get('category') == 'crypto']
        if crypto_scrapers:
            colored_print(f"   [OK] Crypto scrapers found: {len(crypto_scrapers)}", 'green')
            for scraper in crypto_scrapers:
                colored_print(f"      - {scraper['name']}", 'green')
        else:
            colored_print("   [!] No crypto scrapers in config", 'yellow')

        return True

    except ImportError:
        colored_print("[X] pyyaml not installed", 'red')
        colored_print("   Install with: pip install pyyaml", 'red')
        return False
    except Exception as e:
        colored_print(f"[X] Config error: {e}", 'red')
        return False

def main():
    """Run basic tests"""
    colored_print("\n" + "="*60, 'cyan')
    colored_print("  PJX CRYPTO TRADING SYSTEM - BASIC TEST", 'cyan')
    colored_print("="*60, 'cyan')

    tests = [
        ("File Structure", test_file_structure),
        ("Environment Variables", test_env_file),
        ("Database Connection", test_database),
        ("Configuration", test_config),
    ]

    results = {}
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            colored_print(f"[X] {name} test crashed: {e}", 'red')
            results[name] = False

    # Summary
    print_header("SUMMARY")

    passed = sum(1 for r in results.values() if r)
    total = len(results)

    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        color = 'green' if result else 'red'
        colored_print(f"  {name}: {status}", color)

    colored_print(f"\n  Total: {passed}/{total} tests passed",
                 'green' if passed == total else 'yellow' if passed >= total/2 else 'red')

    # Next steps
    print_header("NEXT STEPS")

    if results.get("File Structure"):
        colored_print("1. Install missing dependencies:", 'cyan')
        colored_print("   pip install -r requirements_crypto.txt", 'cyan')
        colored_print("", 'cyan')

        if not results.get("Environment Variables"):
            colored_print("2. Add your API keys to .env file", 'cyan')
            colored_print("   Edit the .env file with your actual keys", 'cyan')
            colored_print("", 'cyan')

        colored_print("3. Test individual components:", 'cyan')
        colored_print("   python exchanges/extended_exchange.py  # Test exchange", 'cyan')
        colored_print("   python paper_trading/tracker.py  # Test paper trading", 'cyan')
        colored_print("   python agents/risk_agent.py  # Test risk management", 'cyan')
        colored_print("", 'cyan')

        colored_print("4. Start paper trading:", 'cyan')
        colored_print("   python agents/trading_agent.py --once  # Single run", 'cyan')
        colored_print("   python agents/trading_agent.py  # Continuous trading", 'cyan')
    else:
        colored_print("Fix file structure issues first", 'red')

if __name__ == "__main__":
    main()