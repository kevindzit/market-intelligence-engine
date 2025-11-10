"""Quick test to verify Claude model selection works"""
import sys
sys.path.insert(0, 'crypto_ai_trader')

from browser_llm import inject_claude_model_selection
from browser_ai import BrowserAI
import undetected_chromedriver as uc
import time
from colorama import init, Fore, Style

init(autoreset=True)

def test_model_selection():
    """Test that we can select different Claude models"""
    print(f"\n{Fore.CYAN}=== CLAUDE MODEL SELECTION TEST ==={Style.RESET_ALL}\n")

    # Create browser instance
    browser_ai = BrowserAI(provider='claude')

    # Setup visible browser for testing
    chrome_options = uc.ChromeOptions()
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')

    print(f"{Fore.YELLOW}[INFO] Starting browser...{Style.RESET_ALL}")
    browser_ai.driver = uc.Chrome(options=chrome_options)

    # Navigate to Claude
    print(f"{Fore.YELLOW}[INFO] Going to Claude...{Style.RESET_ALL}")
    browser_ai.driver.get('https://claude.ai/new')
    time.sleep(3)

    # Load cookies if available
    if browser_ai.load_cookies():
        print(f"{Fore.GREEN}[OK] Loaded cookies{Style.RESET_ALL}")
        browser_ai.driver.refresh()
        time.sleep(3)

    # Check if login needed
    if browser_ai.needs_login():
        print(f"\n{Fore.YELLOW}Please login to Claude in the browser window{Style.RESET_ALL}")
        input("Press Enter after logging in: ")
        browser_ai.save_cookies()

    browser_ai.is_initialized = True

    # Test different models
    models_to_test = ["Haiku 4.5", "Opus 4.1", "Sonnet 4.5"]

    for model in models_to_test:
        print(f"\n{Fore.CYAN}Testing model: {model}{Style.RESET_ALL}")
        print("-" * 40)
        inject_claude_model_selection(browser_ai, model)

        print(f"Check if {model} is selected in the browser")
        response = input(f"Is {model} selected? (y/n): ").lower()

        if response == 'y':
            print(f"{Fore.GREEN}[OK] {model} selection worked!{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}[FAIL] {model} selection failed{Style.RESET_ALL}")

    print(f"\n{Fore.YELLOW}[INFO] Test complete. Closing browser...{Style.RESET_ALL}")
    browser_ai.cleanup()

if __name__ == "__main__":
    test_model_selection()