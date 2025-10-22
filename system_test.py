"""
Comprehensive System Test for Trading Bot
Tests all components and verifies everything is working correctly.
"""

import sys
import os

def test_imports():
    """Test if all required packages are installed."""
    print("\n" + "="*60)
    print("TESTING PACKAGE IMPORTS")
    print("="*60)

    packages = {
        'psycopg2': 'PostgreSQL database',
        'chromadb': 'ChromaDB vector database',
        'selenium': 'Web scraping (Selenium)',
        'feedparser': 'RSS feed parsing',
        'schedule': 'Task scheduling',
        'requests': 'HTTP requests',
        'crewai': 'CrewAI framework',
        'fredapi': 'FRED economic data',
        'yfinance': 'Yahoo Finance data',
    }

    results = {}
    for package, description in packages.items():
        try:
            __import__(package)
            results[package] = 'OK'
            print(f"[OK] {package:15} - {description}")
        except ImportError:
            results[package] = 'MISSING'
            print(f"[!!] {package:15} - {description} (MISSING)")

    missing = [pkg for pkg, status in results.items() if status == 'MISSING']
    if missing:
        print(f"\n[!] Missing {len(missing)} packages. Install with:")
        print(f"    pip install {' '.join(missing)}")
        return False

    print("\n[OK] All packages installed!")
    return True


def test_postgresql():
    """Test PostgreSQL connection and check tables."""
    print("\n" + "="*60)
    print("TESTING POSTGRESQL CONNECTION")
    print("="*60)

    try:
        import psycopg2

        conn = psycopg2.connect(
            dbname='postgres',
            user='postgres',
            password='postgres',
            host='localhost',
            port='54594',
            connect_timeout=5
        )
        cur = conn.cursor()

        print("[OK] PostgreSQL connection: SUCCESS")

        # Get all tables
        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        tables = cur.fetchall()

        if not tables:
            print("[!] No tables found in database")
            return True

        print(f"\n[OK] Found {len(tables)} tables:")
        for table in tables:
            table_name = table[0]
            cur.execute(f'SELECT COUNT(*) FROM {table_name}')
            count = cur.fetchone()[0]
            print(f"  • {table_name:25} - {count:,} rows")

        # Check for duplicates in congressional_trades
        if any('congressional_trades' in str(t) for t in tables):
            cur.execute("""
                SELECT filer_name, transaction_date, ticker, COUNT(*) as dupes
                FROM congressional_trades
                GROUP BY filer_name, transaction_date, ticker, transaction_type, amount_range
                HAVING COUNT(*) > 1
                LIMIT 5
            """)
            dupes = cur.fetchall()
            if dupes:
                print(f"\n[!] Found {len(dupes)} duplicate entries in congressional_trades")
            else:
                print(f"\n[OK] No duplicates in congressional_trades")

        conn.close()
        return True

    except ImportError:
        print("[X] psycopg2 not installed - skipping PostgreSQL test")
        return False
    except Exception as e:
        print(f"[X] PostgreSQL connection FAILED: {e}")
        return False


def test_chromadb():
    """Test ChromaDB connection and check collections."""
    print("\n" + "="*60)
    print("TESTING CHROMADB CONNECTION")
    print("="*60)

    try:
        import chromadb

        client = chromadb.PersistentClient(path="chroma_db_news")

        print("[OK] ChromaDB connection: SUCCESS")

        # Get news_articles collection
        try:
            collection = client.get_collection(name="news_articles")
            count = collection.count()

            print(f"[OK] Collection 'news_articles': {count:,} articles")

            if count > 0:
                # Get sample articles
                results = collection.get(limit=5, include=['metadatas'])

                print(f"\n[OK] Sample articles (showing 5/{count}):")
                sources = {}
                for meta in results['metadatas']:
                    source = meta.get('source', 'Unknown')
                    sources[source] = sources.get(source, 0) + 1
                    headline = meta.get('headline', 'No headline')[:60]
                    print(f"  • [{source:20}] {headline}...")

                # Count by source
                print(f"\n[OK] Articles by source:")
                for source, count in sorted(sources.items()):
                    print(f"  • {source:25} - {count} articles (in sample)")

            return True

        except Exception as e:
            print(f"[!] Collection 'news_articles' not found or error: {e}")
            return False

    except ImportError:
        print("[X] chromadb not installed - skipping ChromaDB test")
        return False
    except Exception as e:
        print(f"[X] ChromaDB connection FAILED: {e}")
        return False


def test_logs():
    """Check if log files exist and are being written."""
    print("\n" + "="*60)
    print("TESTING LOG FILES")
    print("="*60)

    log_files = [
        'logs/senate_scraper.log',
        'logs/house_scraper.log',
        'logs/rss_aggregator.log',
    ]

    found = 0
    for log_file in log_files:
        if os.path.exists(log_file):
            size = os.path.getsize(log_file)
            print(f"[OK] {log_file:30} - {size:,} bytes")
            found += 1
        else:
            print(f"[!] {log_file:30} - Not found (not run yet)")

    if found > 0:
        print(f"\n[OK] Found {found}/{len(log_files)} log files")

    return True


def test_file_structure():
    """Verify project structure is correct."""
    print("\n" + "="*60)
    print("TESTING FILE STRUCTURE")
    print("="*60)

    required_dirs = [
        'senate_scraper',
        'house_scraper',
        'news_scrapers',
        'data_api',
        'sec_data',
        'fundamentals_data',
        'logs',
        'outputs',
        'data',
    ]

    required_files = [
        'app.py',
        'CLAUDE.md',
        'plan.md',
        'TODO.txt',
        'senate_scraper/senate_scraper.py',
        'house_scraper/house_scraper.py',
        'news_scrapers/newsapi_reader.py',
        'news_scrapers/rss_aggregator.py',
    ]

    all_good = True

    print("\nDirectories:")
    for dir_name in required_dirs:
        if os.path.isdir(dir_name):
            print(f"[OK] {dir_name}/")
        else:
            print(f"[X] {dir_name}/ - MISSING")
            all_good = False

    print("\nKey Files:")
    for file_name in required_files:
        if os.path.isfile(file_name):
            print(f"[OK] {file_name}")
        else:
            print(f"[X] {file_name} - MISSING")
            all_good = False

    return all_good


def main():
    """Run all system tests."""
    print("\n")
    print("=" * 60)
    print("  TRADING BOT SYSTEM TEST  ".center(60))
    print("=" * 60)

    results = {}

    results['imports'] = test_imports()
    results['structure'] = test_file_structure()
    results['postgresql'] = test_postgresql()
    results['chromadb'] = test_chromadb()
    results['logs'] = test_logs()

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    for test_name, passed in results.items():
        status = "[OK] PASS" if passed else "[X] FAIL"
        print(f"{test_name.upper():20} - {status}")

    passed_count = sum(results.values())
    total_count = len(results)

    print(f"\n{passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        print("\n[SUCCESS] All systems operational!")
        return 0
    else:
        print("\n[!] Some tests failed. Check details above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
