"""
Main Orchestrator - Launch and manage all three specialized orchestrators
Provides options to run Twitter, News/Fundamentals, and Binance/VPN orchestrators
"""

import os
import sys
import subprocess
import time
import signal
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Try to import colorama for colors
try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
except ImportError:
    class Fore:
        GREEN = RED = YELLOW = CYAN = WHITE = MAGENTA = BLUE = ""
    class Style:
        BRIGHT = RESET_ALL = ""

# Track running orchestrators
running_orchestrators = {}

def get_python_executable():
    """Get the correct Python executable."""
    if sys.platform == "win32":
        venv_python = Path(r"C:\venvs\pjxvenv\Scripts\python.exe")
        if venv_python.exists():
            return str(venv_python)
    return sys.executable

def start_orchestrator(name, script_name):
    """Start a specific orchestrator."""
    script_path = Path(__file__).parent / script_name

    if not script_path.exists():
        print(f"{Fore.RED}[ERROR] Script not found: {script_path}{Style.RESET_ALL}")
        return None

    try:
        python_exe = get_python_executable()

        # Start the orchestrator process
        process = subprocess.Popen(
            [python_exe, str(script_path)],
            cwd=str(Path(__file__).parent.parent),
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        )

        running_orchestrators[name] = process
        print(f"{Fore.GREEN}[STARTED] {name} Orchestrator (PID: {process.pid}){Style.RESET_ALL}")

        # Open in new window on Windows
        if sys.platform == "win32":
            print(f"  -> Opened in new window")

        return process

    except Exception as e:
        print(f"{Fore.RED}[ERROR] Failed to start {name}: {e}{Style.RESET_ALL}")
        return None

def stop_orchestrator(name, process):
    """Stop a running orchestrator."""
    if not process:
        return

    try:
        if sys.platform == "win32":
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)],
                         capture_output=True, timeout=5)
        else:
            process.terminate()
            process.wait(timeout=5)

        print(f"{Fore.YELLOW}[STOPPED] {name} Orchestrator{Style.RESET_ALL}")
    except:
        pass
    finally:
        running_orchestrators.pop(name, None)

def stop_all_orchestrators():
    """Stop all running orchestrators."""
    for name, process in list(running_orchestrators.items()):
        stop_orchestrator(name, process)

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    print(f"\n{Fore.YELLOW}[SHUTDOWN] Stopping all orchestrators...{Style.RESET_ALL}")
    stop_all_orchestrators()
    sys.exit(0)

def display_menu():
    """Display the main menu."""
    print("\n" + "="*80)
    print(" " * 25 + f"{Fore.CYAN}PJX MAIN ORCHESTRATOR{Style.RESET_ALL}")
    print(" " * 20 + "Manage All Data Collection Systems")
    print("="*80)

    print(f"\n{Fore.WHITE}Select which orchestrators to run:{Style.RESET_ALL}")
    print("-"*80)
    print(f"  1. {Fore.CYAN}Twitter Orchestrator{Style.RESET_ALL}")
    print(f"     -> All Twitter sentiment scrapers")
    print(f"     -> Mobile emulation enabled")
    print(f"     -> 7 scrapers (memes, large caps, DeFi, L1s, L2s, AI, whales)")
    print()
    print(f"  2. {Fore.GREEN}News & Fundamentals Orchestrator{Style.RESET_ALL}")
    print(f"     -> News, congressional trades, SEC filings")
    print(f"     -> Economic data, company fundamentals")
    print(f"     -> Crypto metrics (Fear & Greed, TVL, etc)")
    print(f"     -> No VPN required")
    print()
    print(f"  3. {Fore.MAGENTA}Binance/VPN Orchestrator{Style.RESET_ALL}")
    print(f"     -> All Binance data (OHLCV, order book, funding)")
    print(f"     -> Requires non-US IP or Tor proxy")
    print(f"     -> High-frequency market data")
    print()
    print(f"  4. {Fore.YELLOW}Run ALL Orchestrators{Style.RESET_ALL}")
    print(f"     -> Launch all three systems")
    print()
    print(f"  5. {Fore.WHITE}Custom Selection{Style.RESET_ALL}")
    print(f"     -> Choose multiple orchestrators")
    print()
    print(f"  0. {Fore.RED}Exit{Style.RESET_ALL}")
    print("-"*80)

def main():
    """Main function."""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, signal_handler)

    while True:
        display_menu()

        try:
            choice = input(f"\n{Fore.CYAN}Enter your choice (0-5): {Style.RESET_ALL}").strip()
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}[EXIT] Goodbye!{Style.RESET_ALL}")
            break

        if choice == '0':
            print(f"{Fore.YELLOW}[EXIT] Shutting down...{Style.RESET_ALL}")
            stop_all_orchestrators()
            break

        elif choice == '1':
            print(f"\n{Fore.CYAN}Starting Twitter Orchestrator...{Style.RESET_ALL}")
            start_orchestrator("Twitter", "twitter_orchestrator.py")
            time.sleep(2)

        elif choice == '2':
            print(f"\n{Fore.GREEN}Starting News & Fundamentals Orchestrator...{Style.RESET_ALL}")
            start_orchestrator("News/Fundamentals", "news_fundamentals_orchestrator.py")
            time.sleep(2)

        elif choice == '3':
            print(f"\n{Fore.MAGENTA}Starting Binance/VPN Orchestrator...{Style.RESET_ALL}")
            start_orchestrator("Binance/VPN", "binance_vpn_orchestrator.py")
            time.sleep(2)

        elif choice == '4':
            print(f"\n{Fore.YELLOW}Starting ALL orchestrators...{Style.RESET_ALL}")
            start_orchestrator("Twitter", "twitter_orchestrator.py")
            time.sleep(3)
            start_orchestrator("News/Fundamentals", "news_fundamentals_orchestrator.py")
            time.sleep(3)
            start_orchestrator("Binance/VPN", "binance_vpn_orchestrator.py")
            print(f"\n{Fore.GREEN}[SUCCESS] All orchestrators started!{Style.RESET_ALL}")
            time.sleep(2)

        elif choice == '5':
            print(f"\n{Fore.WHITE}Custom Selection:{Style.RESET_ALL}")
            print("Enter the numbers of orchestrators to run (comma-separated)")
            print("Example: 1,2 for Twitter and News")

            try:
                selections = input("Your selection: ").strip().split(',')
                selections = [s.strip() for s in selections]

                if '1' in selections:
                    start_orchestrator("Twitter", "twitter_orchestrator.py")
                    time.sleep(2)
                if '2' in selections:
                    start_orchestrator("News/Fundamentals", "news_fundamentals_orchestrator.py")
                    time.sleep(2)
                if '3' in selections:
                    start_orchestrator("Binance/VPN", "binance_vpn_orchestrator.py")
                    time.sleep(2)

                print(f"\n{Fore.GREEN}[SUCCESS] Selected orchestrators started!{Style.RESET_ALL}")
            except:
                print(f"{Fore.RED}[ERROR] Invalid selection{Style.RESET_ALL}")

        else:
            print(f"{Fore.RED}[ERROR] Invalid choice. Please enter 0-5.{Style.RESET_ALL}")
            continue

        # Show running orchestrators
        if running_orchestrators:
            print(f"\n{Fore.WHITE}Currently Running:{Style.RESET_ALL}")
            for name, process in running_orchestrators.items():
                if process.poll() is None:
                    print(f"  • {name} (PID: {process.pid})")
                else:
                    print(f"  • {name} ({Fore.RED}stopped{Style.RESET_ALL})")
                    running_orchestrators.pop(name, None)

            print(f"\n{Fore.YELLOW}Press Enter to return to menu, or Ctrl+C to stop all{Style.RESET_ALL}")
            try:
                input()
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}[SHUTDOWN] Stopping all orchestrators...{Style.RESET_ALL}")
                stop_all_orchestrators()
                break

    # Final cleanup
    stop_all_orchestrators()
    print(f"\n{Fore.GREEN}[COMPLETE] All orchestrators stopped. Goodbye!{Style.RESET_ALL}")

if __name__ == "__main__":
    main()