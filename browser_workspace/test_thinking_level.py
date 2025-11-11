"""
Test script for ChatGPT Thinking level selection
Helps debug the Extended thinking mode selection
"""

import sys
import os
import time
import argparse

# Add parent directory to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from crypto_ai_trader.browser_ai import BrowserAI
from browser_workspace.browser_llm import inject_chatgpt_model_selection, inject_chatgpt_thinking_level

# Colorama for colored output
try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
except ImportError:
    class Fore:
        GREEN = RED = YELLOW = CYAN = WHITE = MAGENTA = BLUE = ""
    class Style:
        BRIGHT = RESET_ALL = ""

def test_thinking_level_selection(thinking_level: str):
    """Test selecting the requested thinking level in ChatGPT"""

    print(f"\n{Fore.CYAN}{Style.BRIGHT}TESTING CHATGPT THINKING LEVEL SELECTION{Style.RESET_ALL}")
    print("=" * 80)

    browser_ai = None
    try:
        # Initialize browser
        print(f"\n{Fore.YELLOW}[INFO] Starting browser...{Style.RESET_ALL}")
        browser_ai = BrowserAI(provider='chatgpt', session_dir=os.path.dirname(__file__))

        import undetected_chromedriver as uc
        chrome_options = uc.ChromeOptions()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')

        browser_ai.driver = uc.Chrome(options=chrome_options)
        driver = browser_ai.driver

        # Navigate to ChatGPT
        url = browser_ai.urls.get('chatgpt')
        print(f"{Fore.YELLOW}[INFO] Navigating to {url}...{Style.RESET_ALL}")
        driver.get(url)
        time.sleep(3)

        # Load cookies if available
        loaded_cookies = browser_ai.load_cookies()
        if loaded_cookies:
            print(f"{Fore.GREEN}[OK] Loaded saved cookies{Style.RESET_ALL}")
            driver.get(url)
            time.sleep(3)

        # Check if login needed
        if browser_ai.needs_login():
            print(f"\n{Fore.YELLOW}[WARNING] LOGIN REQUIRED{Style.RESET_ALL}")
            print("Please complete the login flow in the browser window.")
            input(f"\n{Fore.WHITE}Press Enter after login: {Style.RESET_ALL}")
            browser_ai.save_cookies()
            driver.get(url)
            time.sleep(3)

        browser_ai.is_initialized = True

        # Test 1: Select "Thinking" model
        print(f"\n{Fore.CYAN}Test 1: Selecting 'Thinking' model...{Style.RESET_ALL}")
        inject_chatgpt_model_selection(browser_ai, "Thinking")
        time.sleep(2)

        # Test 2: Select requested thinking level
        level_label = thinking_level.capitalize()
        print(f"\n{Fore.CYAN}Test 2: Setting {level_label} thinking level...{Style.RESET_ALL}")
        inject_chatgpt_thinking_level(browser_ai, thinking_level)
        time.sleep(2)

        # Debug: Check current state
        print(f"\n{Fore.CYAN}Debug: Checking current state...{Style.RESET_ALL}")
        current_state = driver.execute_script("""
            const normalize = (val) => (val || '').replace(/\\s+/g, ' ').trim().toLowerCase();
            // Find any indicators of current thinking level
            const elements = Array.from(document.querySelectorAll('*'));
            const indicators = [];

            for (const elem of elements) {
                const text = normalize(elem.innerText || elem.textContent);
                if (text === 'standard' || text === 'extended' ||
                    text.includes('thinking') || text.includes('thinking time')) {
                    const rect = elem.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && rect.height < 100) {
                        indicators.push({
                            text,
                            tagName: elem.tagName,
                            className: elem.className,
                            visible: elem.offsetParent !== null
                        });
                    }
                }
            }

            const chipCandidates = Array.from(document.querySelectorAll('button, div[role="button"], span[role="button"]'));
            const hasThinkingChip = chipCandidates.some(el => {
                const text = normalize(el.innerText || el.textContent || el.getAttribute('aria-label'));
                if (!text.includes('thinking')) return false;
                if (text.includes('mini') || text.includes('instant') || text.includes('auto')) return false;
                const rect = el.getBoundingClientRect();
                return rect.width > 40 && rect.height > 20 && rect.height < 120;
            });

            return {
                indicators: indicators.slice(0, 10),
                hasThinkingChip
            };
        """)

        print(f"{Fore.YELLOW}Current state:{Style.RESET_ALL}")
        print(f"  Has Thinking chip: {current_state.get('hasThinkingChip', False)}")
        if current_state.get('indicators'):
            print(f"  Found indicators:")
            for ind in current_state['indicators'][:5]:
                print(f"    - {ind['text']} (tag: {ind['tagName']}, visible: {ind['visible']})")

        # Test 3: Send a test prompt
        print(f"\n{Fore.CYAN}Test 3: Sending test prompt...{Style.RESET_ALL}")
        test_prompt = "What is 2 + 2? Think carefully."
        print(f"  Prompt: {test_prompt}")

        response = browser_ai.send_prompt(test_prompt, timeout=30)

        if response:
            print(f"\n{Fore.GREEN}[OK] Received response:{Style.RESET_ALL}")
            print(f"  {response[:200]}{'...' if len(response) > 200 else ''}")

            # Check if Extended thinking was actually used
            if "thinking" in response.lower() or "careful" in response.lower():
                print(f"\n{Fore.GREEN}✓ Extended thinking likely used (response shows careful consideration){Style.RESET_ALL}")
            else:
                print(f"\n{Fore.YELLOW}⚠ Not clear if Extended thinking was used{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.RED}[ERROR] No response received{Style.RESET_ALL}")

        print(f"\n{Fore.GREEN}[OK] Test completed!{Style.RESET_ALL}")

    except Exception as e:
        print(f"\n{Fore.RED}[ERROR] Test failed: {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()

    finally:
        if browser_ai and hasattr(browser_ai, 'driver') and browser_ai.driver:
            print(f"\n{Fore.YELLOW}[INFO] Closing browser...{Style.RESET_ALL}")
            try:
                browser_ai.driver.quit()
            except:
                pass
            browser_ai.driver = None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test ChatGPT Thinking level toggles via browser automation.")
    parser.add_argument(
        "--thinking-level",
        "-l",
        choices=("standard", "extended"),
        default="standard",
        help="Thinking level to enforce before sending the test prompt (default: standard).",
    )
    args = parser.parse_args()

    test_thinking_level_selection(args.thinking_level)
