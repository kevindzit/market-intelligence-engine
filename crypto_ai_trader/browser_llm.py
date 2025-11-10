"""
Browser LLM Interface - Advanced AI Chat Control
Test Claude, ChatGPT, or DeepSeek with full model selection and options
"""

import sys
import os
import re
from typing import Dict, Optional

# Add parent directory to path so we can import config
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from browser_ai import BrowserAI, cleanup_all_browsers

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
            '1': {'name': 'DeepSeek V3.2-Exp', 'desc': 'Latest experimental model', 'selector': 'v3.2'},
            '2': {'name': 'DeepSeek R1', 'desc': 'Reasoning specialist', 'selector': 'r1'},
        },
        'features': {
            'thinking_mode': True,
            'max_context': '128K tokens',
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
    print(f"\n{Fore.YELLOW}{config['name']} Models:{Style.RESET_ALL}")
    print("-" * 80)

    # Determine split point for current vs legacy models
    # Claude: 3 current + 5 legacy, ChatGPT: 5 current + 4 legacy, DeepSeek: 2 current
    if provider == 'chatgpt':
        current_gen_split = 5  # First 5 are GPT-5 models
    elif provider == 'claude':
        current_gen_split = 3  # First 3 are current generation
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


def get_prompt_options(provider: str) -> tuple[str, Dict]:
    """Get prompt and provider-specific options"""
    print(f"\n{Fore.YELLOW}Prompt Configuration:{Style.RESET_ALL}")
    print("-" * 80)

    # Get the prompt
    print(f"\n{Fore.CYAN}Enter your prompt:{Style.RESET_ALL}")
    print(f"  {Fore.WHITE}(Press Enter to use test prompt: 'What is 2 + 2?'){Style.RESET_ALL}")
    prompt = input(f"\n{Fore.WHITE}> {Style.RESET_ALL}").strip()

    if not prompt:
        prompt = "What is 2 + 2? Answer with just the number."
        print(f"  {Fore.YELLOW}Using test prompt{Style.RESET_ALL}")

    # Get provider-specific options
    options = {}
    if provider == 'claude':
        options = get_claude_options()
    elif provider == 'chatgpt':
        print(f"\n{Fore.YELLOW}ChatGPT Options:{Style.RESET_ALL}")
        print("  Using default GPT settings")
    elif provider == 'deepseek':
        print(f"\n{Fore.YELLOW}DeepSeek Options:{Style.RESET_ALL}")
        print("  Using default DeepSeek settings")

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

        def click_matching_option():
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

        def click_matching_option():
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

        print(f"   {Fore.CYAN}[INFO] Looking for '{model_selector}'...{Style.RESET_ALL}")
        success, clicked_text, seen_items = click_matching_option()

        if not success:
            if expand_legacy_models():
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


def main():
    """Main function to run the browser LLM interface"""

    # Select provider
    provider = select_provider()

    # Select specific model
    model_name, model_selector = select_model(provider)

    # Get prompt and options
    prompt, options = get_prompt_options(provider)

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

        # Create browser AI instance
        browser_ai = BrowserAI(provider=provider)

        # Manually initialize with visible browser
        import undetected_chromedriver as uc
        import time

        # Setup Chrome options - NOT headless so you can watch!
        chrome_options = uc.ChromeOptions()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')

        print(f"{Fore.YELLOW}[INFO] Opening browser window...{Style.RESET_ALL}")
        browser_ai.driver = uc.Chrome(options=chrome_options)

        # Go to the AI service
        url = browser_ai.urls.get(provider)
        print(f"{Fore.YELLOW}[INFO] Navigating to {url}...{Style.RESET_ALL}")
        browser_ai.driver.get(url)
        time.sleep(3)

        # Try to load cookies
        if browser_ai.load_cookies():
            print(f"{Fore.GREEN}[OK] Loaded saved session{Style.RESET_ALL}")
            browser_ai.driver.refresh()
            time.sleep(3)

        # Check if login needed
        if browser_ai.needs_login():
            print("\n" + "-" * 60)
            print(f"{Fore.YELLOW}[WARNING] LOGIN REQUIRED{Style.RESET_ALL}")
            print("-" * 60)
            print("Please login in the browser window.")
            print("After logging in, come back here and press Enter.")
            input(f"\n{Fore.WHITE}Press Enter after login: {Style.RESET_ALL}")

            # Save cookies
            browser_ai.save_cookies()
            print(f"{Fore.GREEN}[OK] Session saved{Style.RESET_ALL}")

        browser_ai.is_initialized = True

        # For Claude, always select the specific model (browser remembers last choice)
        if provider == 'claude':
            inject_claude_model_selection(browser_ai, model_selector)

        # For ChatGPT, always select the specific model (browser remembers last choice)
        if provider == 'chatgpt':
            inject_chatgpt_model_selection(browser_ai, model_selector)

        # Apply provider-specific options
        if provider == 'claude' and options:
            inject_claude_options(browser_ai, options)

        print(f"\n{Fore.YELLOW}[INFO] Sending prompt...{Style.RESET_ALL}")
        print(f"{Fore.WHITE}   (Watch the browser window!){Style.RESET_ALL}\n")

        # Send the prompt
        response = browser_ai.send_prompt(prompt, timeout=45)

        # If no response, try refreshing (often the answer appears after refresh)
        if not response:
            print(f"{Fore.YELLOW}[WARNING] No response received, refreshing page...{Style.RESET_ALL}")
            browser_ai.driver.refresh()
            import time
            from selenium.webdriver.common.by import By
            time.sleep(5)  # Wait for page to fully load

            # Try to grab the response that's already on the page after refresh
            try:
                selectors = browser_ai.selectors.get(provider, {})
                response_selector = selectors.get('response', '')
                response_selector_list = [sel.strip() for sel in response_selector.split(',') if sel.strip()]

                for sel in response_selector_list:
                    try:
                        response_elements = browser_ai.driver.find_elements(By.CSS_SELECTOR, sel)
                        if response_elements and len(response_elements) > 0:
                            response = response_elements[-1].text
                            if response:
                                # Clean up UI elements
                                for element in ['Retry', 'Copy', 'Copy code', 'Regenerate', 'Continue']:
                                    response = response.replace(element, '').strip()
                                while '\n\n\n' in response:
                                    response = response.replace('\n\n\n', '\n\n')
                                response = response.strip()
                                print(f"{Fore.GREEN}[OK] Grabbed response after refresh{Style.RESET_ALL}")
                                break
                    except Exception:
                        continue
            except Exception as e:
                print(f"{Fore.YELLOW}[WARNING] Could not grab response after refresh: {e}{Style.RESET_ALL}")

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
