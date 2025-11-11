"""
Browser LLM Interface - Advanced AI Chat Control
Test Claude, ChatGPT, DeepSeek, or Gemini with full model selection and options
"""

import sys
import os
import re
import time
from typing import Dict, Optional

# Add parent directory (repo root) to path so we can import our packages
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from crypto_ai_trader.browser_ai import BrowserAI, cleanup_all_browsers

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Colorama for cross-platform colored output
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


# Model configurations for each provider
PROVIDER_MODELS = {
    'claude': {
        'name': 'Claude',
        'models': {
            # Current Generation (November 2025)
            '1': {'name': 'Sonnet 4.5', 'desc': 'Best for everyday tasks & coding (Default)', 'selector': 'Sonnet 4.5'},
            '2': {'name': 'Opus 4.1', 'desc': 'Deep brainstorming & reasoning (2x usage)', 'selector': 'Opus 4.1'},
            '3': {'name': 'Haiku 4.5', 'desc': 'Fastest for quick answers', 'selector': 'Haiku 4.5'},
            # Previous Generation
            '4': {'name': 'Opus 4', 'desc': 'Previous opus model', 'selector': 'Opus 4'},
            '5': {'name': 'Sonnet 4', 'desc': 'Previous sonnet model', 'selector': 'Sonnet 4'},
            '6': {'name': 'Sonnet 3.7', 'desc': 'Older sonnet model', 'selector': 'Sonnet 3.7'},
            '7': {'name': 'Opus 3', 'desc': 'Legacy opus model', 'selector': 'Opus 3'},
            '8': {'name': 'Haiku 3.5', 'desc': 'Legacy haiku model', 'selector': 'Haiku 3.5'},
        },
        'features': {
            'thinking_mode': True,
            'max_context': '1M tokens (Sonnet 4.5 beta)',
        }
    },
    'chatgpt': {
        'name': 'ChatGPT',
        'models': {
            # Current Generation (GPT-5)
            '1': {'name': 'Auto', 'desc': 'Decides how long to think (Default)', 'selector': 'Auto'},
            '2': {'name': 'Instant', 'desc': 'Answers right away', 'selector': 'Instant'},
            '3': {'name': 'Thinking mini', 'desc': 'Thinks quickly', 'selector': 'Thinking mini'},
            '4': {'name': 'Thinking', 'desc': 'Thinks longer for better answers', 'selector': 'Thinking'},
            '5': {'name': 'Pro', 'desc': 'Research-grade intelligence (requires upgrade)', 'selector': 'Pro'},
            # Legacy Models
            '6': {'name': 'GPT-4o', 'desc': 'Previous flagship model', 'selector': 'GPT-4o'},
            '7': {'name': 'GPT-4.1', 'desc': 'Enhanced GPT-4', 'selector': 'GPT-4.1'},
            '8': {'name': 'o3', 'desc': 'Optimized model', 'selector': 'o3'},
            '9': {'name': 'o4-mini', 'desc': 'Compact model', 'selector': 'o4-mini'},
        },
        'features': {
            'thinking_mode': False,  # Thinking is part of model selection
            'max_context': '128K tokens',
        }
    },
    'deepseek': {
        'name': 'DeepSeek',
        'models': {
            '1': {'name': 'DeepSeek', 'desc': 'Default model (Default)', 'selector': 'default'},
        },
        'features': {
            'deepthink': True,
            'search': True,
            'max_context': '128K tokens',
        }
    },
    'gemini': {
        'name': 'Gemini',
        'models': {
            '1': {'name': '2.5 Pro', 'desc': 'Advanced reasoning & analysis (Default)', 'selector': '2.5 Pro'},
            '2': {'name': '2.5 Flash', 'desc': 'Fast all-around help', 'selector': '2.5 Flash'},
        },
        'features': {
            'max_context': '2M tokens',
            'reasoning': True,
            'code_execution': True,
        }
    }
}


def select_provider() -> str:
    """Let user select AI provider"""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}BROWSER LLM INTERFACE{Style.RESET_ALL}")
    print("=" * 80)
    print(f"\n{Fore.YELLOW}Available AI Providers:{Style.RESET_ALL}\n")

    providers = list(PROVIDER_MODELS.keys())
    for i, provider in enumerate(providers, 1):
        config = PROVIDER_MODELS[provider]
        print(f"  {Fore.WHITE}{i}. {config['name']:<30}{Style.RESET_ALL} ({len(config['models'])} models)")

    while True:
        choice = input(f"\n{Fore.CYAN}Select provider (1-{len(providers)}): {Style.RESET_ALL}").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(providers):
            return providers[int(choice) - 1]
        print(f"{Fore.RED}Invalid choice, please try again{Style.RESET_ALL}")


def select_model(provider: str) -> tuple[str, str]:
    """Let user select specific model for the provider"""
    config = PROVIDER_MODELS[provider]
    total_models = len(config['models'])

    print(f"\n{Fore.YELLOW}{config['name']} Models:{Style.RESET_ALL}")
    print("-" * 80)

    if total_models == 1:
        key, model = next(iter(config['models'].items()))
        print(f"\n{Fore.GREEN}Current Generation:{Style.RESET_ALL}\n")
        print(f"  {Fore.WHITE}{model['name']:<20}{Style.RESET_ALL} {model['desc']}")
        print(f"\n{Fore.CYAN}Only one model available. Using {model['name']}.{Style.RESET_ALL}")
        return model['name'], model['selector']

    # Determine split point for current vs legacy models
    # Claude: 3 current + 5 legacy, ChatGPT: 5 current + 4 legacy, DeepSeek: 1 (no legacy), Gemini: 2 (no legacy)
    if provider == 'chatgpt':
        current_gen_split = 5  # First 5 are GPT-5 models
    elif provider == 'claude':
        current_gen_split = 3  # First 3 are current generation
    elif provider == 'deepseek':
        current_gen_split = 1  # Only 1 model, no legacy
    elif provider == 'gemini':
        current_gen_split = 2  # Only 2 models available
    else:
        current_gen_split = 2  # Default for other providers

    # Show current generation models
    print(f"\n{Fore.GREEN}Current Generation:{Style.RESET_ALL}\n")
    for key, model in list(config['models'].items())[:current_gen_split]:
        print(f"  {Fore.WHITE}{key}. {model['name']:<20}{Style.RESET_ALL} {model['desc']}")

    # Show legacy models if available
    legacy = list(config['models'].items())[current_gen_split:]
    if legacy:
        print(f"\n{Fore.CYAN}Legacy Models:{Style.RESET_ALL}\n")
        for key, model in legacy:
            print(f"  {Fore.WHITE}{key}. {model['name']:<20}{Style.RESET_ALL} {model['desc']}")

    while True:
        choice = input(f"\n{Fore.CYAN}Select model (1-{len(config['models'])}): {Style.RESET_ALL}").strip()
        if choice in config['models']:
            model = config['models'][choice]
            return model['name'], model['selector']
        print(f"{Fore.RED}Invalid choice, please try again{Style.RESET_ALL}")


def get_claude_options() -> Dict:
    """Get Claude-specific options"""
    options = {}

    print(f"\n{Fore.YELLOW}Claude Options:{Style.RESET_ALL}")
    print("-" * 80)

    # Thinking mode
    print(f"\n{Fore.CYAN}Extended Thinking Mode:{Style.RESET_ALL}")
    print("  Allows Claude to think through complex problems step-by-step")
    print("  (Available on Sonnet 4.5, Opus 4.1, and Haiku 4.5)")

    thinking = input(f"\n  {Fore.WHITE}Enable thinking mode? (y/N, default=No): {Style.RESET_ALL}").strip().lower()
    options['thinking_mode'] = thinking == 'y'

    return options


def get_chatgpt_options(model_name: Optional[str] = None, model_selector: Optional[str] = None) -> Dict:
    """Get ChatGPT-specific options"""
    options = {}

    print(f"\n{Fore.YELLOW}ChatGPT Options:{Style.RESET_ALL}")
    print("-" * 80)

    # Only show thinking level option if "Thinking" mode is selected (not "Thinking mini")
    if model_name == 'Thinking' and model_selector == 'Thinking':
        print(f"\n{Fore.CYAN}Thinking Level:{Style.RESET_ALL}")
        print("  Standard: Default thinking level")
        print("  Extended: Longer, more thorough thinking")

        while True:
            thinking_level = input(f"\n  {Fore.WHITE}Select thinking level (s=Standard/e=Extended, default=Standard): {Style.RESET_ALL}").strip().lower()
            if thinking_level in ['', 's', 'standard']:
                options['thinking_level'] = 'standard'
                break
            elif thinking_level in ['e', 'extended']:
                options['thinking_level'] = 'extended'
                break
            else:
                print(f"  {Fore.RED}Invalid choice. Please enter 's' for Standard or 'e' for Extended.{Style.RESET_ALL}")

    return options


def get_deepseek_options() -> Dict:
    """Get DeepSeek-specific options"""
    options = {}

    print(f"\n{Fore.YELLOW}DeepSeek Options:{Style.RESET_ALL}")
    print("-" * 80)

    # DeepThink toggle
    print(f"\n{Fore.CYAN}DeepThink:{Style.RESET_ALL}")
    print("  Enables deep reasoning mode for complex problems")

    deepthink = input(f"\n  {Fore.WHITE}Enable DeepThink? (y/N, default=No): {Style.RESET_ALL}").strip().lower()
    options['deepthink'] = deepthink == 'y'  # Default to disabled

    # Search toggle
    print(f"\n{Fore.CYAN}Web Search:{Style.RESET_ALL}")
    print("  Enables web search for up-to-date information")

    search = input(f"\n  {Fore.WHITE}Enable Search? (y/N, default=No): {Style.RESET_ALL}").strip().lower()
    options['search'] = search == 'y'  # Default to disabled

    return options


def get_prompt_options(provider: str, model_name: Optional[str] = None, model_selector: Optional[str] = None) -> tuple[str, Dict]:
    """Get prompt and provider-specific options"""
    print(f"\n{Fore.YELLOW}Prompt Configuration:{Style.RESET_ALL}")
    print("-" * 80)

    # Get the prompt
    print(f"\n{Fore.CYAN}Enter your prompt:{Style.RESET_ALL}")
    print(f"  {Fore.WHITE}(Prompt is required; press Enter without text to re-enter){Style.RESET_ALL}")
    prompt = ""
    while not prompt:
        prompt = input(f"\n{Fore.WHITE}> {Style.RESET_ALL}").strip()
        if not prompt:
            print(f"  {Fore.YELLOW}Please enter a prompt (empty input sends nothing).{Style.RESET_ALL}")

    # Get provider-specific options
    options = {}
    if provider == 'claude':
        options = get_claude_options()
    elif provider == 'chatgpt':
        options = get_chatgpt_options(model_name, model_selector)
    elif provider == 'deepseek':
        options = get_deepseek_options()
    elif provider == 'gemini':
        print(f"\n{Fore.YELLOW}Gemini Options:{Style.RESET_ALL}")
        print("  Using default Gemini settings")

    return prompt, options


def inject_claude_model_selection(browser_ai, model_selector: str):
    """
    Select a specific Claude model by clicking the dropdown and selecting the option
    """
    try:
        import time
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

        driver = getattr(browser_ai, "driver", None)
        if not driver:
            print(f"   {Fore.YELLOW}[WARNING] Browser not initialized; cannot select model{Style.RESET_ALL}")
            return

        if not model_selector:
            print(f"   {Fore.YELLOW}[WARNING] Empty model selector supplied{Style.RESET_ALL}")
            return

        print(f"   {Fore.YELLOW}[INFO] Selecting model: {model_selector}{Style.RESET_ALL}")

        wait = WebDriverWait(driver, 10)

        def normalize(text: str) -> str:
            return " ".join((text or "").split()).lower()

        def tokenize(text: str) -> list[str]:
            if not text:
                return []
            return [tok for tok in re.split(r"[^a-z0-9\.]+", text.lower()) if tok]

        target_tokens = tokenize(model_selector)
        model_keywords = ("sonnet", "opus", "haiku")

        def matches_target(text: str) -> bool:
            lowered = normalize(text)
            if not lowered or not target_tokens:
                return False
            words = tokenize(lowered)
            if not words:
                return False
            window = len(target_tokens)
            for idx in range(len(words) - window + 1):
                if words[idx:idx + window] == target_tokens:
                    return True
            return False

        def safe_click(element) -> bool:
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                    element,
                )
                time.sleep(0.1)
            except Exception:
                pass

            for clicker in (
                lambda: element.click(),
                lambda: ActionChains(driver).move_to_element(element).click().perform(),
                lambda: driver.execute_script("arguments[0].click();", element),
            ):
                try:
                    clicker()
                    return True
                except Exception:
                    continue

            try:
                rect = driver.execute_script(
                    """
                    const rect = arguments[0].getBoundingClientRect();
                    if (!rect || (!rect.width && !rect.height)) {
                        return null;
                    }
                    return {
                        x: rect.left + rect.width - Math.min(12, Math.max(4, rect.width * 0.2)),
                        y: rect.top + rect.height / 2
                    };
                    """,
                    element,
                )
            except Exception:
                rect = None

            if rect and rect.get("x") is not None and rect.get("y") is not None:
                try:
                    clicked = driver.execute_script(
                        """
                        const target = document.elementFromPoint(arguments[0], arguments[1]);
                        if (!target) {
                            return false;
                        }
                        target.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                        target.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                        target.click();
                        return true;
                        """,
                        rect["x"],
                        rect["y"],
                    )
                    if clicked:
                        return True
                except Exception:
                    pass
            return False

        def collect_menu_items() -> list:
            keyword_expr = (
                "translate(normalize-space(.), "
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
            )
            keyword_condition = (
                f"contains({keyword_expr}, 'opus') or "
                f"contains({keyword_expr}, 'sonnet') or "
                f"contains({keyword_expr}, 'haiku')"
            )

            selectors = [
                (By.CSS_SELECTOR, "[data-radix-portal] [data-radix-collection-item]"),
                (By.CSS_SELECTOR, "[data-radix-portal] [role='menuitem']"),
                (By.CSS_SELECTOR, "[data-radix-portal] [role='option']"),
                (By.CSS_SELECTOR, "[role='menu'] *[role='menuitem']"),
                (By.CSS_SELECTOR, "[role='listbox'] *[role='option']"),
                (
                    By.XPATH,
                    f"//*[({keyword_condition}) and "
                    "(self::button or self::div or self::li or self::span or @role='menuitem' or @role='option')]",
                ),
            ]

            items = []
            for by, value in selectors:
                try:
                    found = driver.find_elements(by, value)
                except Exception:
                    continue
                for elem in found:
                    try:
                        if elem.is_displayed():
                            items.append(elem)
                    except StaleElementReferenceException:
                        continue
            return items

        def find_dropdown_button():
            dropdown_selectors = [
                (By.CSS_SELECTOR, "button[data-testid*='model']"),
                (By.CSS_SELECTOR, "button[aria-haspopup='menu']"),
                (By.CSS_SELECTOR, "button[aria-haspopup='listbox']"),
                (By.CSS_SELECTOR, "button[role='combobox']"),
                (By.CSS_SELECTOR, "div[role='combobox']"),
                (By.CSS_SELECTOR, "div[role='button'][aria-haspopup='true']"),
            ]

            for by, value in dropdown_selectors:
                try:
                    elements = driver.find_elements(by, value)
                except Exception:
                    continue
                for elem in elements:
                    try:
                        if not elem.is_displayed():
                            continue
                        text_bits = [
                            elem.text,
                            elem.get_attribute("aria-label"),
                            elem.get_attribute("title"),
                        ]
                        combined = normalize(" ".join(filter(None, text_bits)))
                        if combined and any(word in combined for word in model_keywords):
                            return elem
                    except StaleElementReferenceException:
                        continue

            try:
                fallback = driver.find_elements(By.XPATH, "//button | //div[@role='button']")
            except Exception:
                fallback = []

            for elem in fallback:
                try:
                    if not elem.is_displayed():
                        continue
                    combined = normalize(elem.text)
                    if combined and any(word in combined for word in model_keywords):
                        return elem
                except StaleElementReferenceException:
                    continue
            return None

        def is_dropdown_open(element) -> bool:
            if not element:
                return False
            try:
                expanded = (element.get_attribute("aria-expanded") or "").lower()
                if expanded == "true":
                    return True

                controls_id = element.get_attribute("aria-controls")
                if controls_id:
                    try:
                        panel = driver.find_element(By.ID, controls_id)
                        if panel.is_displayed():
                            return True
                    except Exception:
                        pass
            except StaleElementReferenceException:
                return False
            except Exception:
                pass
            return False

        def open_dropdown(button):
            current = button
            for _ in range(3):
                if current is None:
                    current = find_dropdown_button()
                    if not current:
                        break
                if is_dropdown_open(current):
                    return current
                if safe_click(current):
                    try:
                        wait.until(
                            lambda _: is_dropdown_open(current)
                            or len(collect_menu_items()) > 0
                        )
                        print(f"   {Fore.GREEN}[OK] Dropdown opened{Style.RESET_ALL}")
                        return current
                    except TimeoutException:
                        if is_dropdown_open(current):
                            print(f"   {Fore.GREEN}[OK] Dropdown opened{Style.RESET_ALL}")
                            return current
                time.sleep(0.4)
                current = find_dropdown_button()
            return None

        def expand_more_models():
            for elem in collect_menu_items():
                try:
                    if "more models" in normalize(elem.text):
                        if safe_click(elem):
                            time.sleep(0.4)
                            print(f"   {Fore.CYAN}[INFO] Expanded 'More models'{Style.RESET_ALL}")
                            return True
                except StaleElementReferenceException:
                    continue
            return False

        def click_matching_option(anchor=None):
            items = collect_menu_items()
            texts_seen = []
            for elem in items:
                try:
                    text_bits = [
                        elem.text,
                        elem.get_attribute("aria-label"),
                        elem.get_attribute("title"),
                    ]
                    combined = " ".join(filter(None, text_bits)).strip()
                    if combined:
                        texts_seen.append(combined)
                    if combined and matches_target(combined):
                        if safe_click(elem):
                            time.sleep(0.5)
                            return True, combined, texts_seen
                except StaleElementReferenceException:
                    continue

            # Fallback: search entire DOM for clickable keyword matches
            try:
                candidates = driver.find_elements(
                    By.XPATH,
                    "//*[self::button or self::div or self::span or self::li or @role='menuitem' or @role='option']",
                )
            except Exception:
                candidates = []

            for elem in candidates:
                try:
                    if not elem.is_displayed():
                        continue
                    combined = (elem.text or "").strip()
                    if combined:
                        texts_seen.append(combined)
                    if combined and matches_target(combined):
                        if safe_click(elem):
                            time.sleep(0.5)
                            return True, combined, texts_seen
                except StaleElementReferenceException:
                    continue
            return False, "", texts_seen

        def close_menu():
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            except Exception:
                try:
                    driver.execute_script(
                        "if (document.activeElement) { document.activeElement.blur(); }"
                    )
                except Exception:
                    pass
            time.sleep(0.2)

        def read_current_model_label():
            script = """
            const candidates = Array.from(
                document.querySelectorAll('button[aria-haspopup], div[role="combobox"]')
            );
            for (const el of candidates) {
                if (!el || el.offsetParent === null) continue;
                const text = (el.innerText || '').trim();
                if (text && /(opus|sonnet|haiku)/i.test(text)) {
                    return text;
                }
            }
            return '';
            """
            try:
                return driver.execute_script(script) or ""
            except Exception:
                return ""

        dropdown_button = find_dropdown_button()
        if not dropdown_button:
            print(f"   {Fore.YELLOW}[WARNING] Could not find model dropdown{Style.RESET_ALL}")
            return

        dropdown_button = open_dropdown(dropdown_button)
        if not dropdown_button:
            print(f"   {Fore.YELLOW}[WARNING] Dropdown did not open; continuing with default model{Style.RESET_ALL}")
            close_menu()
            return

        print(f"   {Fore.CYAN}[INFO] Looking for '{model_selector}'...{Style.RESET_ALL}")
        success, clicked_text, seen_items = click_matching_option()

        if not success:
            if expand_more_models():
                success, clicked_text, seen_items = click_matching_option()

        if not success:
            print(f"   {Fore.YELLOW}[WARNING] Could not find '{model_selector}' in dropdown{Style.RESET_ALL}")
            if seen_items:
                print(f"   {Fore.CYAN}[DEBUG] Visible options:{Style.RESET_ALL}")
                for option in seen_items[:6]:
                    print(f"      - {option}")
            close_menu()
            return

        close_menu()

        try:
            wait.until(lambda _: matches_target(read_current_model_label()))
            print(f"   {Fore.GREEN}[OK] Selected model: {clicked_text or model_selector}{Style.RESET_ALL}")
        except TimeoutException:
            current_label = read_current_model_label()
            print(
                f"   {Fore.YELLOW}[WARNING] Clicked '{clicked_text}', but current label is '{current_label or 'unknown'}'{Style.RESET_ALL}"
            )

    except Exception as e:
        print(f"   {Fore.YELLOW}[WARNING] Model selection error: {e}{Style.RESET_ALL}")


def inject_chatgpt_model_selection(browser_ai, model_selector: str):
    """
    Select a specific ChatGPT model by clicking the dropdown and selecting the option
    """
    try:
        import time
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

        driver = getattr(browser_ai, "driver", None)
        if not driver:
            print(f"   {Fore.YELLOW}[WARNING] Browser not initialized; cannot select model{Style.RESET_ALL}")
            return

        if not model_selector:
            print(f"   {Fore.YELLOW}[WARNING] Empty model selector supplied{Style.RESET_ALL}")
            return

        print(f"   {Fore.YELLOW}[INFO] Selecting model: {model_selector}{Style.RESET_ALL}")

        wait = WebDriverWait(driver, 10)

        def normalize(text: str) -> str:
            return " ".join((text or "").split()).lower()

        def tokenize(text: str) -> list[str]:
            if not text:
                return []
            return [tok for tok in re.split(r"[^a-z0-9\.\-]+", text.lower()) if tok]

        target_tokens = tokenize(model_selector)
        model_keywords = ("gpt", "auto", "instant", "thinking", "pro", "o3", "o4")

        def matches_target(text: str) -> bool:
            lowered = normalize(text)
            if not lowered or not target_tokens:
                return False

            # First try exact match (normalized)
            if normalize(model_selector) == lowered:
                return True

            # Then try token matching - but tokens must match EXACTLY (same count)
            words = tokenize(lowered)
            if not words:
                return False

            # Only match if token sequences are identical (prevents "thinking" matching "thinking mini")
            if words == target_tokens:
                return True

            # Fallback: allow subsequence matching only if target has multiple tokens
            if len(target_tokens) > 1:
                window = len(target_tokens)
                for idx in range(len(words) - window + 1):
                    if words[idx:idx + window] == target_tokens:
                        return True

            return False

        def safe_click(element) -> bool:
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                    element,
                )
                time.sleep(0.1)
            except Exception:
                pass

            for clicker in (
                lambda: element.click(),
                lambda: ActionChains(driver).move_to_element(element).click().perform(),
                lambda: driver.execute_script("arguments[0].click();", element),
            ):
                try:
                    clicker()
                    return True
                except Exception:
                    continue
            try:
                rect = driver.execute_script(
                    """
                    const rect = arguments[0].getBoundingClientRect();
                    if (!rect || (!rect.width && !rect.height)) {
                        return null;
                    }
                    return {
                        x: rect.left + rect.width - Math.min(12, Math.max(4, rect.width * 0.2)),
                        y: rect.top + rect.height / 2
                    };
                    """,
                    element,
                )
            except Exception:
                rect = None

            if rect and rect.get("x") is not None and rect.get("y") is not None:
                try:
                    clicked = driver.execute_script(
                        """
                        const target = document.elementFromPoint(arguments[0], arguments[1]);
                        if (!target) {
                            return false;
                        }
                        target.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                        target.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                        target.click();
                        return true;
                        """,
                        rect["x"],
                        rect["y"],
                    )
                    if clicked:
                        return True
                except Exception:
                    pass
            return False

        def collect_menu_items() -> list:
            keyword_expr = (
                "translate(normalize-space(.), "
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
            )
            keyword_condition = (
                f"contains({keyword_expr}, 'gpt') or "
                f"contains({keyword_expr}, 'auto') or "
                f"contains({keyword_expr}, 'instant') or "
                f"contains({keyword_expr}, 'thinking') or "
                f"contains({keyword_expr}, 'pro') or "
                f"contains({keyword_expr}, 'o3') or "
                f"contains({keyword_expr}, 'o4')"
            )

            selectors = [
                (By.CSS_SELECTOR, "[data-radix-portal] [data-radix-collection-item]"),
                (By.CSS_SELECTOR, "[data-radix-portal] [role='menuitem']"),
                (By.CSS_SELECTOR, "[data-radix-portal] [role='option']"),
                (By.CSS_SELECTOR, "[role='menu'] *[role='menuitem']"),
                (By.CSS_SELECTOR, "[role='listbox'] *[role='option']"),
                (
                    By.XPATH,
                    f"//*[({keyword_condition}) and "
                    "(self::button or self::div or self::li or self::span or @role='menuitem' or @role='option')]",
                ),
            ]

            items = []
            for by, value in selectors:
                try:
                    found = driver.find_elements(by, value)
                except Exception:
                    continue
                for elem in found:
                    try:
                        if elem.is_displayed():
                            items.append(elem)
                    except StaleElementReferenceException:
                        continue
            return items

        def find_dropdown_button():
            dropdown_selectors = [
                (By.CSS_SELECTOR, "button[data-testid*='model']"),
                (By.CSS_SELECTOR, "button[aria-haspopup='menu']"),
                (By.CSS_SELECTOR, "button[aria-haspopup='listbox']"),
                (By.CSS_SELECTOR, "button[role='combobox']"),
                (By.CSS_SELECTOR, "div[role='combobox']"),
                (By.CSS_SELECTOR, "div[role='button'][aria-haspopup='true']"),
            ]

            for by, value in dropdown_selectors:
                try:
                    elements = driver.find_elements(by, value)
                except Exception:
                    continue
                for elem in elements:
                    try:
                        if not elem.is_displayed():
                            continue
                        text_bits = [
                            elem.text,
                            elem.get_attribute("aria-label"),
                            elem.get_attribute("title"),
                        ]
                        combined = normalize(" ".join(filter(None, text_bits)))
                        if combined and any(word in combined for word in model_keywords):
                            return elem
                    except StaleElementReferenceException:
                        continue

            try:
                fallback = driver.find_elements(By.XPATH, "//button | //div[@role='button']")
            except Exception:
                fallback = []

            for elem in fallback:
                try:
                    if not elem.is_displayed():
                        continue
                    combined = normalize(elem.text)
                    if combined and any(word in combined for word in model_keywords):
                        return elem
                except StaleElementReferenceException:
                    continue
            return None

        def is_dropdown_open(element) -> bool:
            if not element:
                return False
            try:
                expanded = (element.get_attribute("aria-expanded") or "").lower()
                if expanded == "true":
                    return True

                controls_id = element.get_attribute("aria-controls")
                if controls_id:
                    try:
                        panel = driver.find_element(By.ID, controls_id)
                        if panel.is_displayed():
                            return True
                    except Exception:
                        pass
            except StaleElementReferenceException:
                return False
            except Exception:
                pass
            return False

        def open_dropdown(button):
            current = button
            for _ in range(3):
                if current is None:
                    current = find_dropdown_button()
                    if not current:
                        break
                if is_dropdown_open(current):
                    return current
                if safe_click(current):
                    try:
                        wait.until(
                            lambda _: is_dropdown_open(current)
                            or len(collect_menu_items()) > 0
                        )
                        print(f"   {Fore.GREEN}[OK] Dropdown opened{Style.RESET_ALL}")
                        return current
                    except TimeoutException:
                        if is_dropdown_open(current):
                            print(f"   {Fore.GREEN}[OK] Dropdown opened{Style.RESET_ALL}")
                            return current
                time.sleep(0.4)
                current = find_dropdown_button()
            return None

        def expand_legacy_models():
            for elem in collect_menu_items():
                try:
                    elem_text = normalize(elem.text)
                    if "legacy" in elem_text or "legacy models" in elem_text:
                        if safe_click(elem):
                            time.sleep(0.4)
                            print(f"   {Fore.CYAN}[INFO] Expanded 'Legacy models'{Style.RESET_ALL}")
                            return True
                except StaleElementReferenceException:
                    continue
            return False

        def click_matching_option(anchor=None):
            items = collect_menu_items()
            texts_seen = []
            for elem in items:
                try:
                    text_bits = [
                        elem.text,
                        elem.get_attribute("aria-label"),
                        elem.get_attribute("title"),
                    ]
                    combined = " ".join(filter(None, text_bits)).strip()
                    if combined:
                        texts_seen.append(combined)
                    if combined and matches_target(combined):
                        if safe_click(elem):
                            time.sleep(0.5)
                            return True, combined, texts_seen
                except StaleElementReferenceException:
                    continue

            # Fallback: search entire DOM for clickable keyword matches
            try:
                candidates = driver.find_elements(
                    By.XPATH,
                    "//*[self::button or self::div or self::span or self::li or @role='menuitem' or @role='option']",
                )
            except Exception:
                candidates = []

            for elem in candidates:
                try:
                    if not elem.is_displayed():
                        continue
                    combined = (elem.text or "").strip()
                    if combined:
                        texts_seen.append(combined)
                    if combined and matches_target(combined):
                        if safe_click(elem):
                            time.sleep(0.5)
                            return True, combined, texts_seen
                except StaleElementReferenceException:
                    continue
            return False, "", texts_seen

        def close_menu():
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            except Exception:
                try:
                    driver.execute_script(
                        "if (document.activeElement) { document.activeElement.blur(); }"
                    )
                except Exception:
                    pass
            time.sleep(0.2)

        def read_current_model_label():
            script = """
            const candidates = Array.from(
                document.querySelectorAll('button[aria-haspopup], div[role="combobox"]')
            );
            for (const el of candidates) {
                if (!el || el.offsetParent === null) continue;
                const text = (el.innerText || '').trim();
                if (text && /(gpt|auto|instant|thinking|pro|o3|o4)/i.test(text)) {
                    return text;
                }
            }
            return '';
            """
            try:
                return driver.execute_script(script) or ""
            except Exception:
                return ""

        dropdown_button = find_dropdown_button()
        if not dropdown_button:
            print(f"   {Fore.YELLOW}[WARNING] Could not find model dropdown{Style.RESET_ALL}")
            return

        dropdown_button = open_dropdown(dropdown_button)
        if not dropdown_button:
            print(f"   {Fore.YELLOW}[WARNING] Dropdown did not open; continuing with default model{Style.RESET_ALL}")
            close_menu()
            return

        dropdown_anchor = None
        try:
            dropdown_anchor = driver.execute_script(
                """
                const rect = arguments[0].getBoundingClientRect();
                return {
                    x: rect.x + rect.width / 2,
                    y: rect.y + rect.height / 2
                };
                """,
                dropdown_button,
            )
        except Exception:
            dropdown_anchor = None

        print(f"   {Fore.CYAN}[INFO] Looking for '{model_selector}'...{Style.RESET_ALL}")
        success, clicked_text, seen_items = click_matching_option(dropdown_anchor)

        if not success:
            if expand_legacy_models():
                success, clicked_text, seen_items = click_matching_option(dropdown_anchor)

        if not success:
            print(f"   {Fore.YELLOW}[WARNING] Could not find '{model_selector}' in dropdown{Style.RESET_ALL}")
            if seen_items:
                print(f"   {Fore.CYAN}[DEBUG] Visible options:{Style.RESET_ALL}")
                for option in seen_items[:6]:
                    print(f"      - {option}")
            close_menu()
            return

        close_menu()

        try:
            wait.until(lambda _: matches_target(read_current_model_label()))
            print(f"   {Fore.GREEN}[OK] Selected model: {clicked_text or model_selector}{Style.RESET_ALL}")
        except TimeoutException:
            current_label = read_current_model_label()
            print(
                f"   {Fore.YELLOW}[WARNING] Clicked '{clicked_text}', but current label is '{current_label or 'unknown'}'{Style.RESET_ALL}"
            )

    except Exception as e:
        print(f"   {Fore.YELLOW}[WARNING] Model selection error: {e}{Style.RESET_ALL}")


def inject_chatgpt_thinking_level(browser_ai, thinking_level: str):
    """
    Inject ChatGPT thinking level (Standard/Extended) - only for "Thinking" model.

    The UI remembers whichever thinking length you last picked, so we must explicitly
    open the timing chip every run and re-select the requested option.
    """
    try:
        import time
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.common.exceptions import TimeoutException, StaleElementReferenceException

        driver = getattr(browser_ai, "driver", None)
        if not driver:
            print(f"   {Fore.YELLOW}[WARNING] Browser not initialized; cannot set thinking level{Style.RESET_ALL}")
            return

        desired_level = (thinking_level or "standard").strip().lower()
        if desired_level not in ("standard", "extended"):
            desired_level = "standard"

        wait = WebDriverWait(driver, 12)

        print(f"   {Fore.YELLOW}[INFO] Setting thinking level to: {desired_level.title()}{Style.RESET_ALL}")
        print(f"   {Fore.CYAN}[INFO] Locating Thinking/Extended chip...{Style.RESET_ALL}")

        def safe_click(element) -> bool:
            """Click helper that tries native click, Actions, and JS."""
            try:
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                    element,
                )
                time.sleep(0.1)
            except Exception:
                pass

            for clicker in (
                lambda: element.click(),
                lambda: ActionChains(driver).move_to_element(element).click().perform(),
                lambda: driver.execute_script("arguments[0].click();", element),
            ):
                try:
                    clicker()
                    return True
                except Exception:
                    continue
            return False

        def find_thinking_chip():
            """Return the visible chip element near the composer."""
            script = """
                const visible = (el) => {
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    return rect && rect.width > 40 && rect.width < 360 &&
                           rect.height > 20 && rect.height < 96;
                };
                const labelFor = (el) => {
                    const parts = [
                        (el.innerText || el.textContent || ''),
                        el.getAttribute('aria-label') || ''
                    ];
                    return parts.join(' ').replace(/\\s+/g, ' ').trim().toLowerCase();
                };
                const candidates = [];
                const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
                const elements = Array.from(document.querySelectorAll('button, div[role="button"], span[role="button"]'));
                for (const el of elements) {
                    if (!visible(el)) continue;
                    const text = labelFor(el);
                    if (!text || !text.includes('thinking')) continue;
                    if (text.includes('mini') || text.includes('instant') || text.includes('auto')) continue;
                    const rect = el.getBoundingClientRect();
                    // Prefer chips that live near the composer (bottom of the page).
                    candidates.push({ el, top: rect.top, hasExtended: text.includes('extended') });
                }
                if (!candidates.length) {
                    return null;
                }
                candidates.sort((a, b) => {
                    if (a.hasExtended !== b.hasExtended) {
                        return a.hasExtended ? -1 : 1;
                    }
                    return b.top - a.top;
                });
                return candidates[0].el;
            """
            try:
                return driver.execute_script(script)
            except Exception:
                return None

        def option_labels(level: str) -> list[str]:
            if level == "extended":
                return ["extended", "extended thinking"]
            return ["standard", "standard thinking"]

        def find_dropdown_option(level: str):
            """Return the dropdown item element for the requested level."""
            script = """
                const targets = arguments[0];
                const visible = (el) => {
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    return rect && rect.width > 0 && rect.height > 0;
                };
                const menus = Array.from(document.querySelectorAll('[data-radix-portal], [role="menu"], [role="listbox"]'));
                const matches = [];
                for (const root of menus) {
                    if (!visible(root)) continue;
                    const rootText = (root.innerText || root.textContent || '').toLowerCase();
                    const items = Array.from(root.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="option"], button, div, span'));
                    for (const rawItem of items) {
                        const item = rawItem.closest('[role="menuitem"], [role="menuitemradio"], [role="option"], button') || rawItem;
                        if (!visible(item)) continue;
                        const label = (item.innerText || item.textContent || item.getAttribute('aria-label') || '')
                            .replace(/\\s+/g, ' ').trim().toLowerCase();
                        if (!label) continue;
                        if (targets.includes(label)) {
                            const priority = rootText.includes('thinking time') ? 0 : 1;
                            matches.push({ el: item, priority });
                        }
                    }
                }
                if (!matches.length) {
                    return null;
                }
                matches.sort((a, b) => a.priority - b.priority);
                return matches[0].el;
            """
            try:
                return driver.execute_script(script, option_labels(level))
            except Exception:
                return None

        def click_dropdown_option(level: str):
            """Click option directly via JS to avoid element state issues."""
            script = """
                const targets = arguments[0];
                const visible = (el) => {
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    return rect && rect.width > 0 && rect.height > 0;
                };
                const menus = Array.from(document.querySelectorAll('[data-radix-portal], [role="menu"], [role="listbox"]'));
                const result = { clicked: false, reason: 'not_found' };
                for (const root of menus) {
                    if (!visible(root)) continue;
                    const items = Array.from(root.querySelectorAll('[role="menuitem"], [role="menuitemradio"], [role="option"], button, div, span'));
                    for (const rawItem of items) {
                        const item = rawItem.closest('[role="menuitem"], [role="menuitemradio"], [role="option"], button') || rawItem;
                        if (!visible(item)) continue;
                        const label = (item.innerText || item.textContent || item.getAttribute('aria-label') || '')
                            .replace(/\\s+/g, ' ').trim().toLowerCase();
                        if (!label || !targets.includes(label)) continue;
                        try {
                            item.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
                            item.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
                        } catch (err) {}
                        try {
                            item.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                            item.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                        } catch (err) {}
                        try {
                            item.click();
                        } catch (err) {}
                        return { clicked: true, label };
                    }
                }
                return result;
            """
            try:
                return driver.execute_script(script, option_labels(level))
            except Exception as js_error:
                return {"clicked": False, "reason": str(js_error)}

        def chip_state():
            """Return normalized chip label text."""
            chip = find_thinking_chip()
            if not chip:
                return ""
            try:
                text = driver.execute_script(
                    "return (arguments[0].innerText || arguments[0].textContent || arguments[0].getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim().toLowerCase();",
                    chip,
                )
                return text or ""
            except StaleElementReferenceException:
                return ""

        # Wait for the chip to be present once after model selection.
        try:
            wait.until(lambda _: find_thinking_chip() is not None)
        except TimeoutException:
            print(f"   {Fore.YELLOW}[WARNING] Could not find Thinking chip after selecting model{Style.RESET_ALL}")
            return

        option_element = None
        for attempt in range(3):
            chip = find_thinking_chip()
            if not chip:
                time.sleep(0.5)
                continue
            if not safe_click(chip):
                time.sleep(0.4)
                continue
            # Allow dropdown animation to render.
            time.sleep(0.3)
            try:
                option_element = WebDriverWait(driver, 5).until(lambda _: find_dropdown_option(desired_level))
                break
            except TimeoutException:
                option_element = None
                time.sleep(0.4)

        if not option_element:
            print(f"   {Fore.YELLOW}[WARNING] Thinking dropdown did not appear; leaving previous selection{Style.RESET_ALL}")
            return

        js_click_result = click_dropdown_option(desired_level)
        if not js_click_result.get("clicked"):
            if not safe_click(option_element):
                print(f"   {Fore.YELLOW}[WARNING] Could not click desired thinking level option{Style.RESET_ALL}")
                return
        else:
            clicked_label = js_click_result.get("label", desired_level)
            print(f"   {Fore.GREEN}[OK] Clicked {clicked_label.title()} option{Style.RESET_ALL}")

        # Wait for chip text to reflect the requested level.
        def desired_state_met():
            text = chip_state()
            if not text:
                return False
            if desired_level == "extended":
                return "extended" in text
            return "extended" not in text  # Standard chip just says "Thinking"

        try:
            wait.until(lambda _: desired_state_met())
            current = chip_state() or desired_level
            print(f"   {Fore.GREEN}[OK] Thinking level set to: {current.title()}{Style.RESET_ALL}")
        except TimeoutException:
            current = chip_state() or "unknown"
            print(
                f"   {Fore.YELLOW}[WARNING] Could not confirm thinking level change (chip shows '{current}')"
                f"{Style.RESET_ALL}"
            )

    except Exception as e:
        print(f"   {Fore.CYAN}[INFO] Could not set thinking level: {e}{Style.RESET_ALL}")


def inject_claude_options(browser_ai, options: Dict):
    """
    Inject Claude-specific options like thinking mode
    """
    try:
        thinking_mode = options.get('thinking_mode', False)

        # Check if element exists and its current state
        result = browser_ai.driver.execute_script(f"""
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {{
                var btn = buttons[i];
                var text = btn.textContent || btn.getAttribute('aria-label') || '';
                if (text.toLowerCase().includes('thinking')) {{
                    // Check if it's currently active (usually has aria-pressed or active class)
                    var isActive = btn.getAttribute('aria-pressed') === 'true' ||
                                 btn.classList.contains('active') ||
                                 btn.getAttribute('data-state') === 'on';

                    // Click if we need to toggle the state
                    var shouldBeActive = {str(thinking_mode).lower()};
                    if (isActive !== shouldBeActive) {{
                        btn.click();
                        return shouldBeActive ? 'enabled' : 'disabled';
                    }}
                    return shouldBeActive ? 'already_enabled' : 'already_disabled';
                }}
            }}
            return 'not_found';
        """)

        if result == 'enabled':
            print(f"   {Fore.GREEN}[OK] Thinking mode enabled{Style.RESET_ALL}")
        elif result == 'disabled':
            print(f"   {Fore.GREEN}[OK] Thinking mode disabled{Style.RESET_ALL}")
        elif result == 'already_enabled':
            print(f"   {Fore.CYAN}[INFO] Thinking mode already enabled{Style.RESET_ALL}")
        elif result == 'already_disabled':
            print(f"   {Fore.CYAN}[INFO] Thinking mode already disabled{Style.RESET_ALL}")

    except Exception as e:
        print(f"   {Fore.CYAN}[INFO] Could not set advanced options: {e}{Style.RESET_ALL}")
def inject_deepseek_options(browser_ai, options: Dict):
    """
    Inject DeepSeek-specific options (DeepThink and Search toggles)
    """
    try:
        deepthink_enabled = options.get('deepthink', True)
        search_enabled = options.get('search', False)

        # Toggle DeepThink
        deepthink_result = browser_ai.driver.execute_script(f"""
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {{
                var btn = buttons[i];
                var text = btn.textContent || btn.getAttribute('aria-label') || '';
                if (text.toLowerCase().includes('deepthink')) {{
                    // Check if it's currently active
                    var isActive = btn.getAttribute('aria-pressed') === 'true' ||
                                 btn.classList.contains('active') ||
                                 btn.getAttribute('data-state') === 'on' ||
                                 btn.classList.contains('selected');

                    // Click if we need to toggle the state
                    var shouldBeActive = {str(deepthink_enabled).lower()};
                    if (isActive !== shouldBeActive) {{
                        btn.click();
                        return shouldBeActive ? 'enabled' : 'disabled';
                    }}
                    return shouldBeActive ? 'already_enabled' : 'already_disabled';
                }}
            }}
            return 'not_found';
        """)

        if deepthink_result == 'enabled':
            print(f"   {Fore.GREEN}[OK] DeepThink enabled{Style.RESET_ALL}")
        elif deepthink_result == 'disabled':
            print(f"   {Fore.GREEN}[OK] DeepThink disabled{Style.RESET_ALL}")
        elif deepthink_result == 'already_enabled':
            print(f"   {Fore.CYAN}[INFO] DeepThink already enabled{Style.RESET_ALL}")
        elif deepthink_result == 'already_disabled':
            print(f"   {Fore.CYAN}[INFO] DeepThink already disabled{Style.RESET_ALL}")

        # Toggle Search
        search_result = browser_ai.driver.execute_script(f"""
            var buttons = document.querySelectorAll('button');
            for (var i = 0; i < buttons.length; i++) {{
                var btn = buttons[i];
                var text = btn.textContent || btn.getAttribute('aria-label') || '';
                if (text.toLowerCase().includes('search')) {{
                    // Check if it's currently active
                    var isActive = btn.getAttribute('aria-pressed') === 'true' ||
                                 btn.classList.contains('active') ||
                                 btn.getAttribute('data-state') === 'on' ||
                                 btn.classList.contains('selected');

                    // Click if we need to toggle the state
                    var shouldBeActive = {str(search_enabled).lower()};
                    if (isActive !== shouldBeActive) {{
                        btn.click();
                        return shouldBeActive ? 'enabled' : 'disabled';
                    }}
                    return shouldBeActive ? 'already_enabled' : 'already_disabled';
                }}
            }}
            return 'not_found';
        """)

        if search_result == 'enabled':
            print(f"   {Fore.GREEN}[OK] Search enabled{Style.RESET_ALL}")
        elif search_result == 'disabled':
            print(f"   {Fore.GREEN}[OK] Search disabled{Style.RESET_ALL}")
        elif search_result == 'already_enabled':
            print(f"   {Fore.CYAN}[INFO] Search already enabled{Style.RESET_ALL}")
        elif search_result == 'already_disabled':
            print(f"   {Fore.CYAN}[INFO] Search already disabled{Style.RESET_ALL}")

    except Exception as e:
        print(f"   {Fore.CYAN}[INFO] Could not set DeepSeek options: {e}{Style.RESET_ALL}")


def inject_gemini_model_selection(browser_ai, model_selector: str):
    """
    Select a specific Gemini model by ALWAYS clicking the dropdown and selecting the option
    """
    try:
        import time
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support.ui import WebDriverWait

        driver = getattr(browser_ai, "driver", None)
        if not driver:
            print(f"   {Fore.YELLOW}[WARNING] Browser not initialized; cannot select model{Style.RESET_ALL}")
            return

        if not model_selector:
            print(f"   {Fore.YELLOW}[WARNING] Empty model selector supplied{Style.RESET_ALL}")
            return

        print(f"   {Fore.YELLOW}[INFO] Force-selecting model: {model_selector}{Style.RESET_ALL}")

        wait = WebDriverWait(driver, 10)

        def find_dropdown_button():
            for attempt in range(4):
                try:
                    js_button = driver.execute_script(
                        """
                        const threshold = window.innerHeight * 0.45;
                        const candidates = Array.from(
                            document.querySelectorAll('button,div[role="button"],div[role="combobox"]')
                        );
                        for (const btn of candidates) {
                            if (!btn || !btn.offsetParent) continue;
                            const rect = btn.getBoundingClientRect();
                            if (!rect || rect.width < 60 || rect.height < 26) continue;
                            if (rect.top < threshold) continue;
                            const text = (btn.innerText || btn.textContent || '')
                                .replace(/\\s+/g, ' ')
                                .trim()
                                .toLowerCase();
                            if (!text) continue;
                            if (
                                text.includes('choose your model') ||
                                (text.includes('2.5') && (text.includes('pro') || text.includes('flash')))
                            ) {
                                return btn;
                            }
                        }
                        return null;
                        """
                    )
                    if js_button:
                        print(f"   {Fore.GREEN}[OK] Found model dropdown button{Style.RESET_ALL}")
                        return js_button
                except Exception:
                    pass
                time.sleep(0.4)
            return None

        # Simplified dropdown interaction - ALWAYS click and select
        dropdown_button = find_dropdown_button()
        if not dropdown_button:
            print(f"   {Fore.YELLOW}[WARNING] Could not find model dropdown{Style.RESET_ALL}")
            return

        print(f"   {Fore.CYAN}[INFO] Opening dropdown to select '{model_selector}'...{Style.RESET_ALL}")

        # Click the dropdown button (or its caret) to open it
        try:
            # Try to click the caret/arrow icon first if it exists
            clicked = driver.execute_script("""
                const btn = arguments[0];
                if (!btn) return false;

                // Look for a caret/arrow element within the button
                const caret = btn.querySelector('svg, [aria-hidden="true"], .caret, .arrow, span:last-child');
                if (caret) {
                    caret.click();
                    return 'caret';
                }

                // Otherwise click the button itself
                btn.click();
                return 'button';
            """, dropdown_button)

            time.sleep(1.0)  # Give menu time to open fully
            print(f"   {Fore.GREEN}[OK] Dropdown opened (clicked {clicked}){Style.RESET_ALL}")
        except Exception as e:
            print(f"   {Fore.YELLOW}[WARNING] Failed to open dropdown: {e}{Style.RESET_ALL}")
            return

        # Find and click the target model option using JavaScript for reliability
        try:
            time.sleep(0.5)  # Let dropdown fully render

            # Use JavaScript to find and click the option directly
            success = driver.execute_script(r"""
                const modelSelector = arguments[0];
                const targetTokens = modelSelector.toLowerCase().split(/[^a-z0-9\.]+/).filter(Boolean);

                // Function to check if text matches our target - but not if it contains OTHER model names too
                function matchesTarget(text) {
                    const normalized = text.toLowerCase().replace(/\s+/g, ' ').trim();

                    // Must contain all our target tokens
                    const hasAllTokens = targetTokens.every(token => normalized.includes(token));
                    if (!hasAllTokens) return false;

                    // But should NOT contain both "flash" and "pro" (that would be the container)
                    if (normalized.includes('flash') && normalized.includes('pro') &&
                        normalized.includes('reasoning') && normalized.includes('fast')) {
                        return false; // This is likely the container with both options
                    }

                    // Check if this looks like a single option (not too long)
                    if (normalized.length > 100) {
                        return false; // Too long, probably a container
                    }

                    return true;
                }

                // Find all potential option elements - be more specific
                const selectors = [
                    '[role="option"]',
                    '[role="menuitem"]',
                    'div[data-value]',
                    'li[data-value]',
                    'button[data-value]'
                ];

                let allOptions = [];
                for (const selector of selectors) {
                    const elements = Array.from(document.querySelectorAll(selector));
                    allOptions.push(...elements);
                }

                // Also look for divs/spans that are children of role="listbox" or role="menu"
                const menuContainers = document.querySelectorAll('[role="listbox"], [role="menu"]');
                menuContainers.forEach(container => {
                    const children = container.querySelectorAll('div, span, li, button');
                    children.forEach(child => {
                        if (!allOptions.includes(child) && child.offsetParent) {
                            const text = (child.textContent || '').trim();
                            // Only add if it looks like an individual option
                            if (text && text.length < 100 && !text.includes('Choose your model')) {
                                allOptions.push(child);
                            }
                        }
                    });
                });

                // Sort options by text length (prefer shorter, more specific matches)
                allOptions.sort((a, b) => {
                    const aText = (a.textContent || '').trim();
                    const bText = (b.textContent || '').trim();
                    return aText.length - bText.length;
                });

                // Try to find and click the matching option
                for (const option of allOptions) {
                    if (!option.offsetParent) continue;  // Skip hidden
                    const text = (option.textContent || option.innerText || '').trim();
                    if (!text) continue;

                    if (matchesTarget(text)) {
                        console.log('Found match:', text);

                        // Scroll into view
                        option.scrollIntoView({block: 'center', inline: 'center'});

                        // Try multiple click methods
                        try {
                            option.click();
                            return {success: true, text: text};
                        } catch(e1) {
                            try {
                                option.dispatchEvent(new MouseEvent('click', {
                                    bubbles: true,
                                    cancelable: true,
                                    view: window
                                }));
                                return {success: true, text: text};
                            } catch(e2) {
                                try {
                                    // Simulate pointer events
                                    option.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}));
                                    option.dispatchEvent(new PointerEvent('pointerup', {bubbles: true}));
                                    option.click();
                                    return {success: true, text: text};
                                } catch(e3) {
                                    continue;
                                }
                            }
                        }
                    }
                }

                // If no match found, try a more direct approach - look for the Flash option specifically
                const allElements = Array.from(document.querySelectorAll('*'));
                for (const elem of allElements) {
                    if (!elem.offsetParent) continue;
                    const text = (elem.textContent || '').trim();

                    // Look for an element that contains "2.5 Flash" but NOT "2.5 Pro"
                    if (text.includes('2.5 Flash') && !text.includes('2.5 Pro') &&
                        text.length < 50) {  // Should be a short label

                        console.log('Found Flash option directly:', text);
                        elem.scrollIntoView({block: 'center', inline: 'center'});

                        try {
                            elem.click();
                            return {success: true, text: text};
                        } catch(e) {
                            elem.dispatchEvent(new MouseEvent('click', {
                                bubbles: true,
                                cancelable: true,
                                view: window
                            }));
                            return {success: true, text: text};
                        }
                    }
                }

                // Return list of visible options if we couldn't find a match
                const visibleTexts = [];
                for (const option of allOptions) {
                    if (option.offsetParent) {
                        const text = (option.textContent || option.innerText || '').trim();
                        if (text && !visibleTexts.includes(text)) {
                            visibleTexts.push(text);
                        }
                    }
                }
                return {success: false, visibleOptions: visibleTexts};
            """, model_selector)

            if success and success.get('success'):
                time.sleep(0.5)
                print(f"   {Fore.GREEN}[OK] Selected model: {success.get('text', model_selector)}{Style.RESET_ALL}")
            else:
                print(f"   {Fore.YELLOW}[WARNING] Could not find '{model_selector}' in dropdown{Style.RESET_ALL}")
                if success and success.get('visibleOptions'):
                    visible_opts = success['visibleOptions']
                    print(f"   {Fore.CYAN}[DEBUG] Visible options: {', '.join(visible_opts[:6])}{Style.RESET_ALL}")

                # Try to close dropdown
                try:
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                except Exception:
                    pass

        except Exception as e:
            print(f"   {Fore.YELLOW}[WARNING] Error selecting model: {e}{Style.RESET_ALL}")
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            except Exception:
                pass

    except Exception as e:
        print(f"   {Fore.YELLOW}[WARNING] Model selection error: {e}{Style.RESET_ALL}")


def ensure_gemini_new_chat(browser_ai):
    """Ensure Gemini starts a fresh conversation before sending prompts."""
    driver = getattr(browser_ai, "driver", None)
    if not driver:
        return

    import time

    # Try built-in helper first (uses configured selectors)
    try:
        browser_ai.try_new_chat()
    except Exception:
        pass

    # Fallback: search for any button-like element whose text hints at "New chat" or "Ask Gemini"
    try:
        clicked = driver.execute_script(
            """
            const keywords = (arguments[0] || []).map(k => (k || '').toLowerCase()).filter(Boolean);
            if (!keywords.length) {
                return '';
            }
            const normalize = text => (text || '').replace(/\\s+/g, ' ').trim().toLowerCase();
            const nodes = Array.from(
                document.querySelectorAll('button,a,div[role="button"],span[role="button"],md-filled-button,md-outlined-button,md-icon-button')
            );
            for (const node of nodes) {
                if (!node || node.offsetParent === null) continue;
                const combined = [
                    normalize(node.innerText),
                    normalize(node.textContent),
                    normalize(node.getAttribute('aria-label')),
                    normalize(node.getAttribute('title'))
                ].filter(Boolean).join(' ');
                if (!combined) continue;
                if (keywords.some(keyword => combined.includes(keyword))) {
                    node.click();
                    return combined;
                }
            }
            return '';
            """,
            [
                "new chat",
                "new conversation",
                "start chat",
                "start a chat",
                "ask gemini",
                "start over",
                "new prompt",
            ],
        )
        if clicked:
            time.sleep(0.6)
            print(f"   {Fore.CYAN}[INFO] Started new Gemini chat{Style.RESET_ALL}")
    except Exception:
        pass


def provider_requires_login(browser_ai, provider: str) -> bool:
    """Check whether the provider page is still prompting for login."""
    try:
        if browser_ai.needs_login():
            return True
    except Exception:
        return True

    driver = getattr(browser_ai, "driver", None)
    if not driver:
        return True

    try:
        current_url = (driver.current_url or "").lower()
    except Exception:
        current_url = ""

    if "accounts.google" in current_url:
        return True

    try:
        script = """
        const keywords = (arguments[0] || []).map(k => (k || '').toLowerCase());
        if (!keywords.length) {
            return false;
        }
        const elements = Array.from(
            document.querySelectorAll('a,button,div[role="button"],span[role="button"],md-outlined-button,md-filled-button')
        );
        for (const el of elements) {
            if (!el || el.offsetParent === null) continue;
            const label = [
                el.innerText || '',
                el.textContent || '',
                el.getAttribute('aria-label') || '',
                el.getAttribute('title') || ''
            ].join(' ').replace(/\\s+/g, ' ').trim().toLowerCase();
            if (!label) continue;
            if (keywords.some(keyword => label.includes(keyword))) {
                return true;
            }
        }
        return false;
        """
        keywords = [
            "sign in",
            "sign-in",
            "log in",
            "login",
            "sign into",
            "use another account",
            "try gemini",
        ]
        if driver.execute_script(script, keywords):
            return True
    except Exception:
        pass

    return False


def main():
    """Main function to run the browser LLM interface"""

    # Select provider
    provider = select_provider()

    # Select specific model
    model_name, model_selector = select_model(provider)

    # Get prompt and options
    prompt, options = get_prompt_options(provider, model_name, model_selector)

    # Show summary
    print(f"\n{Fore.YELLOW}Configuration Summary:{Style.RESET_ALL}")
    print("=" * 80)
    print(f"\n  {Fore.CYAN}Provider:{Style.RESET_ALL}  {PROVIDER_MODELS[provider]['name']}")
    print(f"  {Fore.CYAN}Model:{Style.RESET_ALL}     {model_name}")
    if options:
        for key, value in options.items():
            print(f"  {Fore.CYAN}{key.replace('_', ' ').title()}:{Style.RESET_ALL} {value}")
    print(f"  {Fore.CYAN}Prompt:{Style.RESET_ALL}    {prompt[:60]}{'...' if len(prompt) > 60 else ''}")
    print("=" * 80)

    try:
        print(f"\n{Fore.YELLOW}[INFO] Starting browser...{Style.RESET_ALL}")

        browser_ai = BrowserAI(provider=provider, session_dir=SCRIPT_DIR)

        import undetected_chromedriver as uc

        chrome_options = uc.ChromeOptions()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')

        print(f"{Fore.YELLOW}[INFO] Opening browser window...{Style.RESET_ALL}")
        browser_ai.driver = uc.Chrome(options=chrome_options)

        if provider == 'claude':
            try:
                if browser_ai.clear_site_cache():
                    print(f"   {Fore.CYAN}[INFO] Cleared Claude cache (cookies preserved){Style.RESET_ALL}")
            except Exception as cache_error:
                print(f"   {Fore.CYAN}[INFO] Cache clear skipped: {cache_error}{Style.RESET_ALL}")

        driver = browser_ai.driver
        url = browser_ai.urls.get(provider)
        if not url:
            print(f"{Fore.RED}[ERROR] No URL defined for provider: {provider}{Style.RESET_ALL}")
            return

        print(f"{Fore.YELLOW}[INFO] Navigating to {url}...{Style.RESET_ALL}")
        driver.get(url)
        time.sleep(3)

        loaded_cookies = browser_ai.load_cookies()
        loaded_storage = browser_ai.load_storage() if hasattr(browser_ai, 'load_storage') else False

        if loaded_cookies or loaded_storage:
            if loaded_cookies:
                print(f"{Fore.GREEN}[OK] Loaded saved cookies{Style.RESET_ALL}")
            if loaded_storage:
                print(f"{Fore.GREEN}[OK] Restored local storage{Style.RESET_ALL}")
            driver.get(url)
            time.sleep(3)

        login_attempts = 0
        max_login_attempts = 3

        def perform_login_flow(clear_cookies: bool = False):
            nonlocal loaded_cookies
            if clear_cookies:
                try:
                    driver.delete_all_cookies()
                    print(f"{Fore.CYAN}[INFO] Cleared expired cookies; please login again{Style.RESET_ALL}")
                except Exception:
                    pass
                loaded_cookies = False

            print("Please complete the login flow in the browser window.")
            if url:
                try:
                    driver.get(url)
                    time.sleep(2)
                except Exception:
                    pass

            input(f"\n{Fore.WHITE}Press Enter after login: {Style.RESET_ALL}")

            try:
                browser_ai.save_cookies()
                if hasattr(browser_ai, 'save_storage'):
                    browser_ai.save_storage()
                print(f"{Fore.GREEN}[OK] Session saved{Style.RESET_ALL}")
            except Exception as save_error:
                print(f"{Fore.YELLOW}[WARNING] Could not save session data: {save_error}{Style.RESET_ALL}")

            if url:
                driver.get(url)
                time.sleep(3)
                print(f"{Fore.GREEN}[OK] Reloaded chat interface{Style.RESET_ALL}")

        while login_attempts < max_login_attempts:
            if provider_requires_login(browser_ai, provider):
                login_attempts += 1
                print("\n" + "-" * 60)
                print(f"{Fore.YELLOW}[WARNING] LOGIN REQUIRED{Style.RESET_ALL}")
                print("-" * 60)
                perform_login_flow(clear_cookies=loaded_cookies and login_attempts == 1)
            else:
                break

        if provider_requires_login(browser_ai, provider):
            print(f"{Fore.YELLOW}[WARNING] Could not verify login automatically; continuing.{Style.RESET_ALL}")

        browser_ai.is_initialized = True

        # Select requested model for each provider
        if provider == 'claude':
            inject_claude_model_selection(browser_ai, model_selector)
        elif provider == 'chatgpt':
            inject_chatgpt_model_selection(browser_ai, model_selector)
            # Force the thinking-level chip to open whenever the Thinking model is chosen
            if model_selector == 'Thinking':
                desired_level = (options or {}).get('thinking_level', 'standard')
                time.sleep(0.5)
                inject_chatgpt_thinking_level(browser_ai, desired_level)
        elif provider == 'gemini':
            ensure_gemini_new_chat(browser_ai)
            inject_gemini_model_selection(browser_ai, model_selector)
        elif provider == 'deepseek':
            pass  # DeepSeek has only one model today

        # Provider-specific option toggles
        if provider == 'claude':
            if options:
                inject_claude_options(browser_ai, options)
        elif provider == 'deepseek' and options:
            inject_deepseek_options(browser_ai, options)

        print(f"\n{Fore.YELLOW}[INFO] Sending prompt...{Style.RESET_ALL}")
        print(f"{Fore.WHITE}   (Watch the browser window!){Style.RESET_ALL}\n")

        response = browser_ai.send_prompt(prompt, timeout=45)

        print(f"\n{Fore.CYAN}{Style.BRIGHT}RESPONSE:{Style.RESET_ALL}")

        if response:
            print(f"{Fore.WHITE}{response}{Style.RESET_ALL}\n")
            print(f"{Fore.GREEN}[OK] Received {len(response)} characters{Style.RESET_ALL}")
            print(f"{Fore.CYAN}[INFO] Model: {model_name}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}[INFO] Provider: {provider.upper()}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}[ERROR] No response received{Style.RESET_ALL}")

    except KeyboardInterrupt:
        print(f"\n\n{Fore.YELLOW}[WARNING] Cancelled by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n\n{Fore.RED}[ERROR] {e}{Style.RESET_ALL}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"\n{Fore.YELLOW}[INFO] Closing browser...{Style.RESET_ALL}")

        # Suppress stderr to hide Chrome cleanup errors
        import sys
        import os
        old_stderr = sys.stderr

        try:
            sys.stderr = open(os.devnull, 'w')

            # Properly close the driver to avoid __del__ exceptions
            if browser_ai and hasattr(browser_ai, 'driver') and browser_ai.driver:
                try:
                    browser_ai.driver.quit()
                except:
                    pass
                browser_ai.driver = None
                browser_ai.is_initialized = False

            # Clean up all instances
            cleanup_all_browsers()
        except:
            pass
        finally:
            # Restore stderr
            try:
                sys.stderr.close()
            except:
                pass
            sys.stderr = old_stderr

        print(f"{Fore.GREEN}[OK] Done!{Style.RESET_ALL}\n")


if __name__ == "__main__":
    import warnings
    import atexit

    warnings.filterwarnings("ignore")

    # Suppress stderr on exit to hide Chrome driver cleanup errors
    def suppress_stderr_on_exit():
        import sys
        import os
        try:
            sys.stderr = open(os.devnull, 'w')
        except:
            pass

    atexit.register(suppress_stderr_on_exit)

    main()
