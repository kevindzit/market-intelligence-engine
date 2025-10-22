"""
Quick Test Script - Verifies system is ready
Run this before starting orchestrator
"""

import os
import sys
from pathlib import Path

def check_files():
    """Verify all required files exist."""
    print("\n" + "="*60)
    print("CHECKING FILE STRUCTURE")
    print("="*60)

    required_files = [
        'orchestrator.py',
        'app.py',
        'config/scrapers.yaml',
        'news_scrapers/newsapi_reader.py',
        'news_scrapers/rss_aggregator.py',
        'senate_scraper/senate_scraper.py',
        'house_scraper/house_scraper.py',
        'data_api/fred_data_reader.py',
        'sec_data/edgar_rss_reader.py',
        'fundamentals_data/fmp_fundamentals_reader.py',
        'fundamentals_data/yfinance_fundamentals_reader.py',
    ]

    all_good = True
    for file_path in required_files:
        if os.path.exists(file_path):
            print(f"[OK] {file_path}")
        else:
            print(f"[MISSING] {file_path}")
            all_good = False

    return all_good


def check_config():
    """Check orchestrator configuration."""
    print("\n" + "="*60)
    print("CHECKING CONFIGURATION")
    print("="*60)

    try:
        import yaml
        with open('config/scrapers.yaml', 'r') as f:
            config = yaml.safe_load(f)

        scrapers = config.get('scrapers', [])
        enabled = [s for s in scrapers if s.get('enabled', False)]

        print(f"Total scrapers: {len(scrapers)}")
        print(f"Enabled scrapers: {len(enabled)}")

        if enabled:
            print("\nEnabled scrapers:")
            for s in enabled:
                name = s.get('name', 'Unknown')
                category = s.get('category', 'unknown')
                print(f"  • [{category:15}] {name}")

        return True

    except Exception as e:
        print(f"[ERROR] Failed to read config: {e}")
        return False


def check_venv():
    """Check if virtual environment is set up."""
    print("\n" + "="*60)
    print("CHECKING VIRTUAL ENVIRONMENT")
    print("="*60)

    venv_path = Path('.venv/Scripts/python.exe')
    if venv_path.exists():
        print(f"[OK] Virtual environment found at {venv_path.absolute()}")
        return True
    else:
        print("[WARNING] Virtual environment not found")
        print(f"[INFO] Using system Python: {sys.executable}")
        return True  # Not critical


def main():
    """Run all checks."""
    print("\n" + "="*60)
    print("  QUICK SYSTEM CHECK  ".center(60))
    print("="*60)

    results = []

    results.append(("Files", check_files()))
    results.append(("Configuration", check_config()))
    results.append(("Virtual Environment", check_venv()))

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    all_passed = all(r[1] for r in results)

    for name, passed in results:
        status = "[OK]" if passed else "[FAIL]"
        print(f"{name:25} {status}")

    if all_passed:
        print("\n✓ System ready to run!")
        print("\nNext steps:")
        print("  1. Start orchestrator: python orchestrator.py")
        print("  2. Wait 5 minutes for data collection")
        print("  3. Run AI analysis: python app.py")
        print("\nSee TESTING.md for full testing guide.")
        return 0
    else:
        print("\n✗ Some checks failed. Review errors above.")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
