"""
Base Orchestrator Module - Shared functionality for all orchestrators
Contains common functions, configuration, and database monitoring
"""

import os
import sys
import time
import subprocess
import psycopg2
import threading
from collections import deque, defaultdict
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import signal

# Force UTF-8 console output
for stream_name in ("stdout", "stderr"):
    stream = getattr(sys, stream_name, None)
    if stream and hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

# Try to import colorama for Windows-compatible colors
try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    COLORS_ENABLED = True
except ImportError:
    # Fallback: no colors
    class Fore:
        GREEN = RED = YELLOW = CYAN = WHITE = MAGENTA = BLUE = ""
    class Style:
        BRIGHT = RESET_ALL = ""
    COLORS_ENABLED = False

# Project root (handles launches from other directories)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# Load environment variables from .env so child scrapers inherit required keys
DOTENV_PATH = PROJECT_ROOT / '.env'
if DOTENV_PATH.exists():
    load_dotenv(dotenv_path=DOTENV_PATH, override=False)
else:
    load_dotenv(override=False)

# Global state for tracking processes and metrics
running_processes = {}
restart_attempts = {}
scraper_start_times = {}
scraper_logs = defaultdict(lambda: deque(maxlen=10))
scraper_activity = defaultdict(dict)

# Configuration constants
MAX_RESTART_ATTEMPTS = 3
MONITOR_INTERVAL_SECONDS = 30
DEFAULT_STAGGER_SECONDS = 2
TWITTER_STAGGER_SECONDS = 5
STREAMING_STAGGER_SECONDS = 1

def parse_interval_seconds(interval_str):
    """Convert interval string to seconds."""
    if not interval_str:
        return 300  # Default 5 minutes

    interval = interval_str.lower().strip()

    # Direct number = minutes
    try:
        return int(interval) * 60
    except ValueError:
        pass

    # Parse with unit
    import re
    match = re.match(r'(\d+)\s*(second|minute|hour|day|s|m|h|d)', interval)
    if match:
        value = int(match.group(1))
        unit = match.group(2)[0]

        multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
        return value * multipliers.get(unit, 60)

    return 300  # Default fallback

def get_python_executable():
    """Get the correct Python executable path."""
    if sys.platform == "win32":
        venv_python = Path(r"C:\venvs\pjxvenv\Scripts\python.exe")
        if venv_python.exists():
            return str(venv_python)
    return sys.executable

def format_time_since(timestamp):
    """Format time elapsed since timestamp."""
    if not timestamp:
        return "never"
    elapsed = datetime.now() - timestamp
    total_seconds = int(elapsed.total_seconds())

    if total_seconds < 60:
        return f"{total_seconds}s"
    elif total_seconds < 3600:
        return f"{total_seconds // 60}m"
    elif total_seconds < 86400:
        return f"{total_seconds // 3600}h {(total_seconds % 3600) // 60}m"
    else:
        return f"{total_seconds // 86400}d {(total_seconds % 86400) // 3600}h"

def get_start_stagger_seconds(scraper):
    """Get appropriate stagger delay for starting scrapers."""
    name_lower = scraper['name'].lower()

    # High-frequency scrapers need minimal delay
    if any(x in name_lower for x in ['order book', 'liquidation']):
        return STREAMING_STAGGER_SECONDS

    # Twitter scrapers need more spacing
    if 'twitter' in name_lower:
        return TWITTER_STAGGER_SECONDS

    return DEFAULT_STAGGER_SECONDS

def monitor_scraper_output(stream, scraper_name, stream_type):
    """Monitor and log scraper output."""
    try:
        for line in iter(stream.readline, b''):
            if not line:
                break

            try:
                decoded = line.decode('utf-8', errors='replace').rstrip()
                if decoded:
                    # Store in logs
                    scraper_logs[scraper_name].append(decoded)

                    # Print with color coding
                    if stream_type == "stderr":
                        if any(err in decoded.lower() for err in ['error', 'failed', 'exception']):
                            print(f"  [{scraper_name}] {Fore.RED}{decoded}{Style.RESET_ALL}")
                        else:
                            print(f"  [{scraper_name}] {Fore.YELLOW}{decoded}{Style.RESET_ALL}")
                    else:
                        # Parse for specific patterns
                        if '[SUCCESS]' in decoded or '[OK]' in decoded:
                            print(f"  [{scraper_name}] {Fore.GREEN}{decoded}{Style.RESET_ALL}")
                        elif '[WARNING]' in decoded or '[WARN]' in decoded:
                            print(f"  [{scraper_name}] {Fore.YELLOW}{decoded}{Style.RESET_ALL}")
                        elif '[ERROR]' in decoded or '[FAILED]' in decoded:
                            print(f"  [{scraper_name}] {Fore.RED}{decoded}{Style.RESET_ALL}")
                        elif '[INFO]' in decoded or any(x in decoded for x in ['rows inserted', 'tweets found', 'articles found']):
                            print(f"  [{scraper_name}] {Fore.CYAN}{decoded}{Style.RESET_ALL}")
                        else:
                            print(f"  [{scraper_name}] {decoded}")
            except:
                pass
    except:
        pass
    finally:
        stream.close()

def start_output_monitor_thread(process, scraper_name):
    """Start threads to monitor stdout and stderr."""
    # Monitor stdout
    stdout_thread = threading.Thread(
        target=monitor_scraper_output,
        args=(process.stdout, scraper_name, "stdout"),
        daemon=True
    )
    stdout_thread.start()

    # Monitor stderr
    stderr_thread = threading.Thread(
        target=monitor_scraper_output,
        args=(process.stderr, scraper_name, "stderr"),
        daemon=True
    )
    stderr_thread.start()

def start_scraper(scraper, env_overrides=None):
    """Start a single scraper as a background process."""
    name = scraper['name']
    script = scraper['script']
    script_path = (PROJECT_ROOT / script).resolve()

    if not script_path.exists():
        print(f"{Fore.YELLOW}[WARNING] {name}: Script not found at {script_path}{Style.RESET_ALL}")
        return None

    try:
        python_exe = get_python_executable()

        # Create environment
        env = os.environ.copy()
        env['ORCHESTRATOR_RUNNING'] = 'true'
        env.setdefault('PYTHONIOENCODING', 'utf-8')

        # Apply any environment overrides
        if env_overrides:
            env.update(env_overrides)

        # Create startup command
        cmd = [python_exe, str(script_path)]

        # Start the process
        process = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )

        # Start output monitoring
        start_output_monitor_thread(process, name)

        # Track the process
        running_processes[name] = process
        scraper_start_times[name] = datetime.now()
        restart_attempts[name] = 0

        print(f"{Fore.GREEN}[STARTED] {name} (PID: {process.pid}){Style.RESET_ALL}")
        return process

    except Exception as e:
        print(f"{Fore.RED}[ERROR] Failed to start {name}: {e}{Style.RESET_ALL}")
        return None

def stop_scraper(name, process):
    """Stop a running scraper process."""
    if not process:
        return

    try:
        if sys.platform == "win32":
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)],
                         capture_output=True, timeout=5)
        else:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

        print(f"{Fore.YELLOW}[STOPPED] {name}{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}[ERROR] Failed to stop {name}: {e}{Style.RESET_ALL}")
    finally:
        running_processes.pop(name, None)

def stop_all_scrapers():
    """Stop all running scrapers."""
    for name, process in list(running_processes.items()):
        stop_scraper(name, process)

def check_database_connection():
    """Check if PostgreSQL database is accessible."""
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 54594)),
            dbname=os.getenv('DB_NAME', 'pjx'),
            user=os.getenv('DB_USER', 'postgres'),
            password=os.getenv('DB_PASSWORD', 'postgres')
        )

        with conn.cursor() as cur:
            # Get table count
            cur.execute("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            """)
            table_count = cur.fetchone()[0]

            # Get total row count
            cur.execute("""
                SELECT SUM(n_live_tup) FROM pg_stat_user_tables
            """)
            total_rows = cur.fetchone()[0] or 0

        conn.close()
        return True, {'tables': table_count, 'total_rows': total_rows}
    except Exception as e:
        return False, str(e)

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    print(f"\n{Fore.YELLOW}[SHUTDOWN] Received signal {signum}, stopping all scrapers...{Style.RESET_ALL}")
    stop_all_scrapers()
    sys.exit(0)

def monitor_and_restart_scrapers(scrapers, check_interval=30):
    """Monitor scrapers and restart if they fail."""
    while True:
        try:
            time.sleep(check_interval)

            for scraper in scrapers:
                name = scraper['name']
                process = running_processes.get(name)

                if process and process.poll() is not None:
                    # Process has terminated
                    exit_code = process.returncode
                    print(f"{Fore.YELLOW}[EXIT] {name} stopped with code {exit_code}{Style.RESET_ALL}")

                    # Check restart attempts
                    restart_attempts[name] = restart_attempts.get(name, 0) + 1

                    if restart_attempts[name] <= MAX_RESTART_ATTEMPTS:
                        print(f"{Fore.CYAN}[RESTART] Attempting to restart {name} (attempt {restart_attempts[name]}/{MAX_RESTART_ATTEMPTS}){Style.RESET_ALL}")
                        time.sleep(2)
                        start_scraper(scraper)
                    else:
                        print(f"{Fore.RED}[FAILED] {name} exceeded max restart attempts{Style.RESET_ALL}")
                        running_processes.pop(name, None)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"{Fore.RED}[MONITOR ERROR] {e}{Style.RESET_ALL}")
            time.sleep(check_interval)

def run_preflight_checks():
    """Run pre-flight system checks."""
    print("\n" + "="*80)
    print(" " * 20 + "PRE-FLIGHT SYSTEM CHECKS")
    print("="*80)

    checks_passed = True

    # Check Python version
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"[CHECK] Python version: {python_version} ... ", end="")
    if sys.version_info >= (3, 9):
        print(f"{Fore.GREEN}✓{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}✗ (requires 3.9+){Style.RESET_ALL}")
        checks_passed = False

    # Check required directories
    for dir_name in ['logs', 'outputs', 'config']:
        dir_path = PROJECT_ROOT / dir_name
        print(f"[CHECK] Directory '{dir_name}' ... ", end="")
        if dir_path.exists():
            print(f"{Fore.GREEN}✓{Style.RESET_ALL}")
        else:
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                print(f"{Fore.YELLOW}✓ Created{Style.RESET_ALL}")
            except:
                print(f"{Fore.RED}✗ Failed to create{Style.RESET_ALL}")
                checks_passed = False

    # Check database
    print(f"[CHECK] Database connection ... ", end="")
    db_ok, db_info = check_database_connection()
    if db_ok:
        print(f"{Fore.GREEN}✓ Connected{Style.RESET_ALL}")
        print(f"[INFO] Database Status:")
        print(f"       - {db_info['tables']} tables found")
        print(f"       - {db_info['total_rows']:,} total rows")
    else:
        print(f"{Fore.RED}✗ {db_info}{Style.RESET_ALL}")
        checks_passed = False

    # Check environment variables
    print(f"[CHECK] Environment variables ... ", end="")
    required_vars = []  # Add any required env vars here
    missing = [var for var in required_vars if not os.getenv(var)]
    if not missing:
        print(f"{Fore.GREEN}✓{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}⚠ Missing: {', '.join(missing)}{Style.RESET_ALL}")

    print("\n" + "="*80)
    if checks_passed:
        print(f"{Fore.GREEN}✓ ALL CHECKS PASSED - READY TO START{Style.RESET_ALL}")
    else:
        print(f"{Fore.YELLOW}⚠ SOME CHECKS FAILED - REVIEW WARNINGS ABOVE{Style.RESET_ALL}")
    print("="*80)

    return checks_passed

# Register signal handlers for graceful shutdown
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
if sys.platform == "win32":
    signal.signal(signal.SIGBREAK, signal_handler)