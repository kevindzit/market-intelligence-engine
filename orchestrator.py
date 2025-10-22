"""
Scraper Orchestrator - Manages all data collection scrapers
Easy to expand: Just edit config/scrapers.yaml to add new scrapers!
"""

import os
import sys
import time
import subprocess
import yaml
import signal
from datetime import datetime
from pathlib import Path

# Global list of running processes
running_processes = {}

def load_config():
    """Load scraper configuration from YAML file."""
    config_path = Path("config/scrapers.yaml")

    if not config_path.exists():
        print("[ERROR] config/scrapers.yaml not found!")
        sys.exit(1)

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    return config.get('scrapers', [])


def get_python_executable():
    """Get the correct Python executable path."""
    # Try venv first
    venv_paths = [
        Path('.venv/Scripts/python.exe'),  # Windows
        Path('.venv/bin/python'),           # Unix
    ]

    for venv_path in venv_paths:
        if venv_path.exists():
            return str(venv_path.absolute())

    # Fall back to current Python
    return sys.executable


def start_scraper(scraper):
    """Start a single scraper as a background process."""
    name = scraper['name']
    script = scraper['script']

    if not os.path.exists(script):
        print(f"[WARNING] {name}: Script not found at {script}")
        return None

    try:
        python_exe = get_python_executable()

        # Start process in background
        process = subprocess.Popen(
            [python_exe, script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        )

        print(f"[STARTED] {name} (PID: {process.pid}) using {python_exe}")
        return process

    except Exception as e:
        print(f"[ERROR] {name}: Failed to start - {e}")
        return None


def stop_scraper(name, process):
    """Stop a running scraper."""
    try:
        if sys.platform == 'win32':
            # Windows: send CTRL_BREAK_EVENT
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            # Unix: send SIGTERM
            process.terminate()

        # Wait up to 5 seconds for graceful shutdown
        try:
            process.wait(timeout=5)
            print(f"[STOPPED] {name}")
        except subprocess.TimeoutExpired:
            # Force kill if still running
            process.kill()
            print(f"[KILLED] {name} (forced)")

        return True

    except Exception as e:
        print(f"[ERROR] Failed to stop {name}: {e}")
        return False


def stop_all_scrapers():
    """Stop all running scrapers."""
    print("\n" + "="*60)
    print("Stopping all scrapers...")
    print("="*60)

    for name, process in running_processes.items():
        if process and process.poll() is None:  # Still running
            stop_scraper(name, process)

    running_processes.clear()


def monitor_scrapers():
    """Monitor running scrapers and restart if they crash."""
    while True:
        try:
            # Check each process
            for name, process in list(running_processes.items()):
                if process and process.poll() is not None:  # Process ended
                    print(f"[WARNING] {name} stopped unexpectedly!")
                    # Could add auto-restart logic here

            # Sleep for a bit
            time.sleep(10)

        except KeyboardInterrupt:
            print("\n[SIGNAL] Keyboard interrupt received...")
            break


def show_status():
    """Display status of all scrapers."""
    print("\n" + "="*60)
    print("SCRAPER STATUS")
    print("="*60)

    scrapers = load_config()

    for scraper in scrapers:
        name = scraper['name']
        enabled = scraper.get('enabled', False)
        category = scraper.get('category', 'unknown')

        if name in running_processes:
            process = running_processes[name]
            if process and process.poll() is None:
                status = "[RUNNING]"
            else:
                status = "[STOPPED]"
        else:
            status = "[NOT STARTED]"

        enabled_str = "[ENABLED]" if enabled else "[DISABLED]"
        print(f"{status:15} {enabled_str:12} [{category:15}] {name}")

    print("="*60)


def main():
    """Main orchestrator function."""
    print("\n" + "="*60)
    print("  TRADING BOT ORCHESTRATOR  ".center(60))
    print("="*60)

    # Load configuration
    scrapers = load_config()
    enabled_scrapers = [s for s in scrapers if s.get('enabled', False)]

    if not enabled_scrapers:
        print("\n[WARNING] No scrapers are enabled in config/scrapers.yaml")
        print("[INFO] Edit config/scrapers.yaml and set 'enabled: true' for scrapers you want to run")
        return

    print(f"\nFound {len(enabled_scrapers)} enabled scrapers:")
    for scraper in enabled_scrapers:
        name = scraper['name']
        category = scraper.get('category', 'unknown')
        interval = scraper.get('interval', 'N/A')
        print(f"  • [{category:15}] {name:30} (runs {interval})")

    print("\n" + "="*60)
    print("Starting scrapers...")
    print("="*60 + "\n")

    # Start all enabled scrapers
    for scraper in enabled_scrapers:
        name = scraper['name']
        process = start_scraper(scraper)

        if process:
            running_processes[name] = process

        # Small delay between starts
        time.sleep(1)

    if not running_processes:
        print("\n[ERROR] No scrapers started successfully!")
        return

    # Show status
    show_status()

    print("\n" + "="*60)
    print("[INFO] Orchestrator running. Press Ctrl+C to stop all scrapers.")
    print("="*60 + "\n")

    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        print("\n[SIGNAL] Shutdown signal received...")
        stop_all_scrapers()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)

    # Monitor scrapers
    try:
        monitor_scrapers()
    finally:
        stop_all_scrapers()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Shutting down...")
        stop_all_scrapers()
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
        stop_all_scrapers()
        sys.exit(1)
