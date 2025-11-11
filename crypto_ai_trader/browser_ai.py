"""
Browser AI System for Free AI Model Access
Uses Selenium to interact with AI chat interfaces (Claude, ChatGPT, DeepSeek, Gemini)
"""

import time
import os
import json
import re
from typing import Dict, Optional
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import undetected_chromedriver as uc
import pickle

try:
    from crypto_ai_trader import config
except ImportError:
    import config


GEMINI_INPUT_KEYWORDS = [
    'gemini',
    'ask',
    'prompt',
    'message',
    'search',
    'question',
    'write',
    'type',
]

GEMINI_WAKE_SELECTORS = [
    '[data-ask-gemini-input]',
    'textarea[aria-label*="Gemini"]',
    'div[aria-label*="Gemini"]',
    'button[aria-label*="Ask"]',
    'div[role="textbox"]',
    '[data-testid*="input"]',
]

GEMINI_INPUT_LOCATOR_SCRIPT = """
const selectors = Array.isArray(arguments[0]) ? arguments[0].filter(Boolean) : [];
const keywords = Array.isArray(arguments[1]) ? arguments[1].map(k => (k || '').toLowerCase()) : [];
const returnElement = Boolean(arguments[2]);

const fallbackSelectors = [
  'textarea[aria-label]',
  'textarea[placeholder]',
  'textarea:not([disabled])',
  'div[role="textbox"]',
  '[contenteditable="true"][role="textbox"]',
  '[contenteditable="true"]'
];

const seen = new Set();
function addMatches(selector) {
  if (!selector) return;
  try {
    document.querySelectorAll(selector).forEach(node => {
      if (!seen.has(node)) {
        seen.add(node);
      }
    });
  } catch (err) {}
}

if (selectors.length) {
  selectors.forEach(addMatches);
} else {
  fallbackSelectors.forEach(addMatches);
}

if (!seen.size) {
  fallbackSelectors.forEach(addMatches);
}

const candidates = Array.from(seen);

function isTextInput(el) {
  if (!el) return false;
  if (el.tagName === 'TEXTAREA') return true;
  if (el.isContentEditable) return true;
  const role = (el.getAttribute('role') || '').toLowerCase();
  return role === 'textbox' || role === 'combobox';
}

function isVisible(el) {
  if (!el || !el.isConnected) return false;
  const rect = el.getBoundingClientRect();
  if (!rect || rect.width < 4 || rect.height < 4) return false;
  const style = window.getComputedStyle(el);
  if (!style) return false;
  if (style.visibility === 'hidden' || style.display === 'none' || Number(style.opacity || 1) === 0) {
    return false;
  }
  return true;
}

function labelFor(el) {
  const parts = [
    el.getAttribute('aria-label'),
    el.getAttribute('placeholder'),
    el.getAttribute('aria-placeholder'),
    el.getAttribute('data-placeholder'),
    el.textContent
  ].filter(Boolean);
  return parts.join(' ').trim().toLowerCase();
}

let fallback = null;
for (const node of candidates) {
  if (!isTextInput(node) || !isVisible(node)) {
    continue;
  }

  if (!fallback) {
    fallback = node;
  }

  const label = labelFor(node);
  if (!keywords.length || (label && keywords.some(k => label.includes(k)))) {
    if (returnElement) {
      try { node.scrollIntoView({block: 'center', inline: 'center'}); } catch (err) {}
      try { node.focus(); } catch (err) {}
      return node;
    }
    return true;
  }
}

if (returnElement && fallback) {
  try { fallback.scrollIntoView({block: 'center', inline: 'center'}); } catch (err) {}
  try { fallback.focus(); } catch (err) {}
  return fallback;
}

return false;
"""

DEEPSEEK_THINKING_MARKERS = (
    'thought for',
    'thinking for',
    'internal monologue',
    'deepseek is thinking',
    'scratchpad',
    'analysis:',
    'analysis step',
    'deliberation',
    'reasoning trail',
    'reasoning:',
    'reasoning step',
    'hmm',
    'let me think',
    'notes:',
    'reflection',
    'plan:',
    'goal:',
    'subgoal',
    'search results',
    'tool call',
    'calling tool',
    'web search',
    'calc',
)

DEEPSEEK_REASONING_KEYWORDS = (
    'analysis',
    'thinking',
    'think',
    'thought',
    'reasoning',
    'scratchpad',
    'plan',
    'goal',
    'steps',
    'step',
    'observation',
    'action',
    'deliberation',
    'reflection',
    'tool',
    'function call',
    'web search',
    'result',
    'results',
    'intermediate',
    'draft',
    'brainstorm',
    'hmm',
    'note:',
    'notes:',
    'calc',
    'calculation',
    'progress',
    'continue thinking',
    'keep thinking',
    'gathering',
    'context',
    'analysis step',
)

DEEPSEEK_REASONING_PATTERNS = [
    re.compile(r'^\s*\d+(\.|:)\s'),
    re.compile(r'^\s*step\s*\d+', re.IGNORECASE),
    re.compile(r'^\s*[-•]+\s*(analysis|step|result|goal)', re.IGNORECASE),
    re.compile(r'^\s*(analysis|reasoning|plan|goal)\b', re.IGNORECASE),
    re.compile(r'^\s*tool call', re.IGNORECASE),
    re.compile(r'^\s*search results', re.IGNORECASE),
]

DEEPSEEK_SHORT_ANSWER_WHITELIST = {
    'yes',
    'no',
    'ok',
    'okay',
    'sure',
    'maybe',
    'fine',
    'good',
    'great',
    '4',
    '5',
    '6',
    '7',
    '8',
    '9',
    '10',
    '42',
    'true',
    'false',
    'none',
    'null',
    'n/a',
    'paris',
    'tokyo',
    'london',
}

CLAUDE_REASONING_MARKERS = (
    'thinking about',
    'gathering my thoughts',
    'searching the web',
    'searching for',
    'planning my response',
    'looking into this',
    'drafting a response',
    'reasoning through this',
    'exploring information',
    'collecting information',
    'checking sources',
    'checking data',
    'running searches',
    'step',
    'steps',
    'results',
    'intermediate reasoning',
    'tool output',
    'web search',
    'scanning',
    'analysis step',
    'thinking...',
    'thinking…',
)

CLAUDE_REASONING_LINE_PATTERNS = [
    re.compile(r'^\d+(\.\d+)?\s+(step|steps|result|results)\b'),
    re.compile(r'^\s*[-•]+\s*(step|result|search)'),
    re.compile(r'^\s*(search )?results?:', re.IGNORECASE),
    re.compile(r'searching\s+(the\s+)?web', re.IGNORECASE),
    re.compile(r'\bthinking\.\.\.$', re.IGNORECASE),
]


def strip_deepseek_thinking(text: str) -> str:
    """Remove DeepSeek's exposed thinking paragraphs, keep only the final answer."""
    if not text:
        return text

    cleaned = text.strip()
    if not cleaned:
        return cleaned

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return cleaned

    # Prefer an explicit numeric/textual answer if it exists on the final lines
    for line in reversed(lines[-4:]):
        if re.fullmatch(r"[+-]?(\d+(\.\d+)?|\w+)", line) and len(line) <= 32:
            if line.isdigit() or line.replace('.', '', 1).isdigit() or len(line) <= 6:
                return line

    filtered_lines = []
    for line in lines:
        if deepseek_line_is_reasoning(line):
            continue
        filtered_lines.append(line)

    if filtered_lines:
        return "\n".join(filtered_lines).strip()

    return lines[-1]


def claude_line_is_reasoning(line: str) -> bool:
    lowered = (line or "").strip().lower()
    if not lowered:
        return True
    for pattern in CLAUDE_REASONING_LINE_PATTERNS:
        if pattern.search(lowered):
            return True
    return any(marker in lowered for marker in CLAUDE_REASONING_MARKERS)


def claude_response_is_reasoning(text: str) -> bool:
    if not text:
        return True
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return True
    reasoning_lines = sum(1 for line in lines if claude_line_is_reasoning(line))
    if reasoning_lines == len(lines):
        return True
    if len(lines) <= 3 and reasoning_lines >= 1:
        return True
    return reasoning_lines >= max(1, len(lines) - 1)


def strip_claude_reasoning_lines(text: str) -> str:
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines()]
    # Drop leading reasoning lines
    cleaned = []
    skipping = True
    for line in lines:
        if skipping and claude_line_is_reasoning(line):
            continue
        skipping = False
        cleaned.append(line.strip())
    # Drop trailing reasoning lines (e.g., "Thinking...")
    while cleaned and claude_line_is_reasoning(cleaned[-1]):
        cleaned.pop()
    if not cleaned and lines:
        cleaned = [lines[-1].strip()]
    return "\n".join(cleaned).strip()


class BrowserAI:
    """Browser interface for AI chat services"""

    def __init__(self, provider: str = 'claude', session_dir: Optional[str] = None):
        """
        Initialize browser AI for a specific provider

        Args:
            provider: 'claude', 'chatgpt', 'deepseek', or 'gemini'
            session_dir: directory for storing cookies/storage files
        """
        self.provider = provider
        self.driver = None
        self.is_initialized = False
        self.session_dir = os.path.abspath(session_dir) if session_dir else os.getcwd()
        os.makedirs(self.session_dir, exist_ok=True)
        self.cookies_file = os.path.join(self.session_dir, f"cookies_{provider}.pkl")
        self.storage_file = os.path.join(self.session_dir, f"storage_{provider}.json")

        # URLs for each provider
        self.urls = {
            'claude': 'https://claude.ai/new',
            'chatgpt': 'https://chat.openai.com',
            'deepseek': 'https://chat.deepseek.com',
            'gemini': 'https://gemini.google.com/app'
        }

        # Only some providers require clicking "New Chat" before sending
        self.auto_new_chat = provider in {'chatgpt', 'deepseek'}

        # Simple selectors for each provider
        self.selectors = {
            'claude': {
                'input': 'div[contenteditable="true"]',
                'send': 'button[aria-label*="Send"], button[type="submit"]',
                'response': 'div.font-claude-message, div[data-test-render-count], div.whitespace-pre-wrap',
                'new_chat': 'button[aria-label*="New"], a[href="/new"]'
            },
            'chatgpt': {
                'input': 'textarea[placeholder*="Ask"], textarea[placeholder*="Message"], textarea[id="prompt-textarea"], div[contenteditable="true"]',
                'send': 'button[data-testid*="send"], button[aria-label*="Send"], button[type="button"]',
                'response': 'div.markdown, article, div[data-message-author-role="assistant"]',
                'new_chat': 'button[aria-label*="New chat"], a[href="/"]'
            },
            'deepseek': {
                'input': 'textarea[placeholder*="Ask"], div[contenteditable="true"], textarea',
                'send': 'button[type="submit"], button[aria-label*="Send"]',
                'response': 'div.markdown, div[class*="message"], div[class*="response"], article',
                'new_chat': 'button[aria-label*="New"], a[href*="chat"]'
            },
            'gemini': {
                'input': (
                    'textarea[aria-label*="Ask Gemini"],'
                    'textarea[placeholder*="Ask Gemini"],'
                    'textarea[placeholder*="Ask"],'
                    'div[aria-label*="Ask Gemini"][contenteditable="true"],'
                    'div[aria-label*="Ask"][contenteditable="true"],'
                    '[contenteditable="true"][data-ask-gemini-input],'
                    '.prompt-input'
                ),
                'send': 'button[aria-label*="Send"], button[aria-label*="Submit"], button[type="submit"]',
                'response': (
                    'div.response-content, div.model-response, '
                    'div[data-message-author="assistant"], .message-content, div.markdown-body'
                ),
                'new_chat': 'button[aria-label*="New chat"], button[aria-label*="New conversation"]'
            }
        }

    def clear_site_cache(self) -> bool:
        """
        Clear browser cache/storage (excluding cookies) for the provider origin.
        Returns True if any cache-clear action succeeded.
        """
        if not self.driver:
            return False

        cleared = False
        try:
            self.driver.execute_cdp_cmd("Network.clearBrowserCache", {})
            cleared = True
        except Exception:
            pass

        origin = None
        url = self.urls.get(self.provider)
        if url:
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                origin = f"{parsed.scheme}://{parsed.netloc}"

        if origin:
            try:
                self.driver.execute_cdp_cmd(
                    "Storage.clearDataForOrigin",
                    {
                        "origin": origin,
                        "storageTypes": "appcache,shader_cache,service_workers,cache_storage",
                    },
                )
                cleared = True
            except Exception:
                pass

        return cleared

    def dismiss_claude_errors(self) -> int:
        """Close Claude toast errors that stack in the top-right corner."""
        if self.provider != 'claude' or not self.driver:
            return 0

        script = """
        const selectors = [
            '[data-testid*="toast"]',
            '[role="alert"]',
            '[data-test-toast]',
            '.mantine-Notification-root',
            '.mantine-Notifications-root div[role="alert"]',
            '.toast',
            '.notification'
        ];
        let dismissed = 0;
        const errorPhrases = [
            "isn't working right now",
            'try again later',
            'something went wrong',
            'error',
            'failed',
            'issue'
        ];
        const seen = new Set();
        const isVisible = (el) => {
            if (!el || !el.isConnected) return false;
            const rect = el.getBoundingClientRect();
            return rect && rect.width && rect.height;
        };
        selectors.forEach(selector => {
            document.querySelectorAll(selector).forEach(node => {
                if (!node || seen.has(node) || !isVisible(node)) return;
                seen.add(node);
                const text = (node.innerText || '').toLowerCase();
                if (!text) return;
                if (!errorPhrases.some(p => text.includes(p))) return;
                const dismissButton = node.querySelector('[aria-label*="close"], [aria-label*="dismiss"], button, [role="button"]');
                if (dismissButton) {
                    dismissButton.click();
                } else if (node.remove) {
                    node.remove();
                } else if (node.parentElement) {
                    node.parentElement.removeChild(node);
                }
                dismissed += 1;
            });
        });
        return dismissed;
        """
        try:
            result = self.driver.execute_script(script)
            return int(result) if isinstance(result, (int, float)) else 0
        except Exception:
            return 0

    def _wait_for_claude_answer(self, selector: str, initial_text: str, extra_seconds: int = 8) -> str:
        """Wait a bit longer for Claude to replace status text with the real response."""
        if self.provider != 'claude' or not self.driver or not selector:
            return initial_text
        end_time = time.time() + max(3, extra_seconds)
        last_text = initial_text or ""
        while time.time() < end_time:
            time.sleep(0.5)
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if not elements:
                    continue
                current_text = (elements[-1].text or "").strip()
                if current_text and current_text != last_text:
                    if not claude_response_is_reasoning(current_text):
                        return current_text
                    last_text = current_text
            except Exception:
                break
        return last_text

    def _wait_for_deepseek_answer(self, selector: str, initial_text: str, extra_seconds: int = 8) -> str:
        """Give DeepSeek a little longer to replace reasoning output with the final answer."""
        if self.provider != 'deepseek' or not self.driver or not selector:
            return initial_text
        baseline = (initial_text or "").strip()
        baseline_len = len(baseline)
        last_text = baseline
        end_time = time.time() + max(4, extra_seconds)

        while time.time() < end_time:
            time.sleep(0.5)
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if not elements:
                    continue
                current_text = (elements[-1].text or "").strip()
                if not current_text:
                    continue
                if current_text != last_text:
                    last_text = current_text
                if len(current_text) > baseline_len + 5 or not deepseek_response_is_reasoning(current_text):
                    return current_text
            except Exception:
                break

        return last_text or baseline

        print(f"✓ {provider.upper()} browser initialized")

    def initialize(self) -> bool:
        """Start the browser and navigate to the AI service"""
        try:
            print(f"⏳ Starting {self.provider.upper()} browser...")

            # Setup Chrome options
            options = uc.ChromeOptions()

            # Headless mode from config (default True if not set)
            headless = getattr(config, 'BROWSER_HEADLESS', True)
            if headless:
                options.add_argument('--headless=new')
                options.add_argument('--disable-gpu')

            # Basic options for stability
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')

            # Start Chrome
            self.driver = uc.Chrome(options=options)

            # Go to the AI service
            url = self.urls.get(self.provider)
            if not url:
                print(f"❌ Unknown provider: {self.provider}")
                return False

            self.driver.get(url)
            time.sleep(3)

            # Try to load saved cookies
            loaded_anything = False

            if self.load_cookies():
                print(f"✓ Loaded saved cookies")
                loaded_anything = True

            if self.load_storage():
                print(f"✓ Restored local storage")
                loaded_anything = True

            if loaded_anything:
                self.driver.refresh()
                time.sleep(3)

            force_manual_login = self.provider == 'gemini' and not loaded_anything

            # Check if we need to login
            if force_manual_login or self.needs_login():
                print(f"⚠️  Please login to {self.provider.upper()} manually")
                print("Browser will open for login...")

                # If headless, restart in visible mode for login
                if headless:
                    self.driver.quit()
                    options = uc.ChromeOptions()
                    options.add_argument('--no-sandbox')
                    options.add_argument('--disable-dev-shm-usage')
                    self.driver = uc.Chrome(options=options)
                    self.driver.get(url)

                input("Press Enter after you've logged in...")

                # Save cookies and storage for next time
                self.save_cookies()
                self.save_storage()
                print(f"✓ Session saved")

            self.is_initialized = True
            print(f"✓ {self.provider.upper()} ready")
            return True

        except Exception as e:
            print(f"❌ Failed to initialize: {e}")
            if self.driver:
                self.driver.quit()
            return False

    def save_cookies(self):
        """Save cookies to file"""
        try:
            if self.driver:
                cookies = self.driver.get_cookies()
                with open(self.cookies_file, 'wb') as f:
                    pickle.dump(cookies, f)
        except Exception as e:
            print(f"⚠️  Failed to save cookies: {e}")

    def save_storage(self):
        """Persist localStorage and sessionStorage to file"""
        if not self.driver:
            return
        try:
            data = {}
            for storage_type in ('localStorage', 'sessionStorage'):
                items = self.driver.execute_script(f"""
                    var store = window.{storage_type};
                    var data = {{}};
                    if (!store) {{
                        return data;
                    }}
                    for (var i = 0; i < store.length; i++) {{
                        var key = store.key(i);
                        data[key] = store.getItem(key);
                    }}
                    return data;
                """)
                data[storage_type] = items or {}

            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"⚠️  Failed to save storage: {e}")

    def load_cookies(self) -> bool:
        """Load cookies from file"""
        try:
            if not self.driver:
                return False
            if os.path.exists(self.cookies_file):
                with open(self.cookies_file, 'rb') as f:
                    cookies = pickle.load(f)

                for cookie in cookies:
                    try:
                        self.driver.add_cookie(cookie)
                    except:
                        pass  # Some cookies might fail, that's ok

                return True
        except:
            pass
        return False

    def load_storage(self) -> bool:
        """Restore localStorage and sessionStorage"""
        if not self.driver or not os.path.exists(self.storage_file):
            return False
        try:
            with open(self.storage_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            restored = False
            for storage_type in ('localStorage', 'sessionStorage'):
                store_data = data.get(storage_type, {})
                if not isinstance(store_data, dict):
                    continue
                for key, value in store_data.items():
                    try:
                        self.driver.execute_script(
                            f"window.{storage_type}.setItem(arguments[0], arguments[1]);",
                            key,
                            value,
                        )
                        restored = True
                    except Exception:
                        continue
            return restored
        except Exception as e:
            print(f"⚠️  Failed to load storage: {e}")
            return False

    def needs_login(self) -> bool:
        """Check if login is needed"""
        if not self.driver:
            return True

        selectors = self.selectors.get(self.provider, {})
        input_selector = selectors.get('input')

        if input_selector:
            wait_timeout = 12 if self.provider == 'gemini' else 5
            if self.provider == 'gemini':
                if self._gemini_input_present(timeout=wait_timeout):
                    return False
            else:
                try:
                    WebDriverWait(self.driver, wait_timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, input_selector))
                    )
                    return False
                except TimeoutException:
                    pass
                except Exception:
                    pass

        # Check for login keywords
        try:
            page_text = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
            login_words = ['sign in', 'log in', 'sign up', 'welcome to', 'choose an account']

            for word in login_words:
                if word in page_text:
                    return True
        except:
            pass

        return self._provider_login_guard()

    def _provider_login_guard(self) -> bool:
        """Apply provider-specific login heuristics"""
        if not self.driver:
            return True

        if self.provider == 'gemini':
            try:
                current_url = (self.driver.current_url or '').lower()
                if 'accounts.google' in current_url:
                    return True
            except:
                pass

            try:
                sign_in_elements = self.driver.find_elements(
                    By.XPATH,
                    "//a[contains(@href,'accounts.google.com')] | "
                    "//button[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sign in')] | "
                    "//a[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sign in')]"
                )
                for elem in sign_in_elements:
                    try:
                        if elem.is_displayed():
                            return True
                    except:
                        continue
            except:
                pass

            try:
                aria_signin = self.driver.find_elements(By.CSS_SELECTOR, "[aria-label*='Sign in'], [aria-label*='Sign In']")
                for elem in aria_signin:
                    try:
                        if elem.is_displayed():
                            return True
                    except:
                        continue
            except:
                pass

            try:
                body_text = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
                keywords = ['sign in to gemini', 'choose an account', 'use another account', 'try gemini']
                if any(keyword in body_text for keyword in keywords):
                    return True
            except:
                pass

        return False

    def _gemini_selector_list(self):
        selectors = self.selectors.get('gemini', {}).get('input', '')
        return [sel.strip() for sel in selectors.split(',') if sel.strip()]

    def _probe_gemini_input(self, request_element: bool = False):
        if not self.driver:
            return None if request_element else False

        selector_list = self._gemini_selector_list()
        try:
            result = self.driver.execute_script(
                GEMINI_INPUT_LOCATOR_SCRIPT,
                selector_list,
                GEMINI_INPUT_KEYWORDS,
                request_element,
            )
        except Exception:
            result = None

        if request_element:
            return result
        return bool(result)

    def _nudge_gemini_input_surface(self) -> bool:
        if not self.driver:
            return False
        try:
            return bool(
                self.driver.execute_script(
                    """
                    const selectors = arguments[0] || [];
                    for (const sel of selectors) {
                        if (!sel) continue;
                        const el = document.querySelector(sel);
                        if (el && el.offsetParent !== null) {
                            try { el.scrollIntoView({block: 'center'}); } catch (err) {}
                            el.click();
                            return true;
                        }
                    }
                    return false;
                    """,
                    GEMINI_WAKE_SELECTORS,
                )
            )
        except Exception:
            return False

    def _gemini_input_present(self, timeout: float = 0) -> bool:
        if not self.driver:
            return False
        deadline = time.time() + max(0, timeout)
        while True:
            if self._probe_gemini_input(False):
                return True
            if time.time() >= deadline:
                break
            self._nudge_gemini_input_surface()
            time.sleep(0.35)
        return False

    def _find_gemini_input_element(self, timeout: float = 12.0):
        if not self.driver:
            return None
        end_time = time.time() + max(timeout, 1.0)
        while time.time() < end_time:
            element = self._probe_gemini_input(True)
            if element:
                return element
            self._nudge_gemini_input_surface()
            time.sleep(0.4)
        return None

    def send_prompt(self, prompt: str, timeout: int = 30) -> Optional[str]:
        """
        Send a prompt and get the response

        Args:
            prompt: The text to send
            timeout: Max seconds to wait for response

        Returns:
            The AI's response text or None
        """
        if not self.is_initialized:
            if not self.initialize():
                return None

        try:
            selectors = self.selectors.get(self.provider, {})

            response_selector = selectors.get('response')
            if not response_selector:
                print(f"❌ No response selector for {self.provider}")
                return None

            response_selector_list = [sel.strip() for sel in response_selector.split(',') if sel.strip()]
            if not response_selector_list:
                print(f"❌ Invalid response selector for {self.provider}")
                return None

            def snapshot_response_counts() -> Dict[str, int]:
                counts = {}
                for sel in response_selector_list:
                    try:
                        counts[sel] = len(self.driver.find_elements(By.CSS_SELECTOR, sel))
                    except Exception:
                        counts[sel] = 0
                return counts

            def wait_for_new_response(previous_counts: Dict[str, int], wait_timeout: int):
                end_time = time.time() + wait_timeout
                while time.time() < end_time:
                    for sel in response_selector_list:
                        try:
                            elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                        except Exception:
                            continue

                        prev = previous_counts.get(sel, 0)
                        if prev is None:
                            prev = 0

                        if len(elements) > prev:
                            return sel, elements
                    time.sleep(0.2)
                raise TimeoutException("Timed out waiting for response to appear")

            def generation_active() -> bool:
                indicator_selectors = [
                    "button[aria-label*='Stop']",
                    "button[data-testid*='stop']",
                    "button[aria-label*='Cancel']",
                    "[data-testid*='stop-generation']",
                    "[data-testid*='stop-button']",
                ]
                for sel in indicator_selectors:
                    try:
                        for elem in self.driver.find_elements(By.CSS_SELECTOR, sel):
                            if elem.is_displayed():
                                return True
                    except Exception:
                        continue

                try:
                    buttons = self.driver.find_elements(
                        By.XPATH,
                        "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'stop generating')]"
                    )
                    if any(btn.is_displayed() for btn in buttons):
                        return True
                except Exception:
                    pass

                spinner_selectors = [
                    "[data-testid*='loading']",
                    "[data-state='loading']",
                    "[role='status'] svg",
                    "svg.animate-spin",
                ]
                for sel in spinner_selectors:
                    try:
                        for elem in self.driver.find_elements(By.CSS_SELECTOR, sel):
                            if elem.is_displayed():
                                return True
                    except Exception:
                        continue

                return False

            # Try to start a new chat when the provider benefits from it
            if self.auto_new_chat:
                self.try_new_chat()

            if self.provider == 'claude':
                self.dismiss_claude_errors()

            # Find the input field
            input_selector = selectors.get('input')
            if not input_selector:
                print(f"❌ No input selector for {self.provider}")
                return None

            # Wait for and find the input - try multiple selectors
            input_element = None
            print(f"⏳ Sending prompt...")

            wait_timeout = 12 if self.provider == 'gemini' else 5
            if self.provider == 'gemini':
                input_element = self._find_gemini_input_element(wait_timeout)
            else:
                for selector in input_selector.split(','):
                    selector = selector.strip()
                    if not selector:
                        continue
                    try:
                        input_element = WebDriverWait(self.driver, wait_timeout).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                        if input_element:
                            break
                    except TimeoutException:
                        continue
                    except Exception:
                        continue

            if not input_element:
                print(f"❌ Could not find input field")
                return None

            # Click and clear the input
            try:
                input_element.click()
            except Exception:
                try:
                    self.driver.execute_script("arguments[0].click();", input_element)
                except Exception:
                    pass
            time.sleep(0.2)
            if self.provider == 'gemini':
                try:
                    self.driver.execute_script(
                        "arguments[0].focus(); arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
                        input_element,
                    )
                except Exception:
                    pass

            # Clear any existing text
            try:
                input_element.send_keys(Keys.CONTROL + "a")
                input_element.send_keys(Keys.DELETE)
            except Exception:
                try:
                    if (input_element.get_attribute("contenteditable") or "").lower() == "true":
                        self.driver.execute_script("arguments[0].innerText = '';", input_element)
                    else:
                        self.driver.execute_script("arguments[0].value = '';", input_element)
                except Exception:
                    pass
            time.sleep(0.15)

            # Type the prompt
            typed_prompt = False
            try:
                input_element.send_keys(prompt)
                typed_prompt = True
            except Exception:
                pass

            if not typed_prompt:
                try:
                    self.driver.execute_script(
                        """
                        const el = arguments[0];
                        const value = arguments[1];
                        if (!el) { return false; }
                        if (el.tagName === 'TEXTAREA') {
                            el.value = value;
                        } else if (el.isContentEditable) {
                            el.innerText = value;
                        } else {
                            el.textContent = value;
                        }
                        const Ctor = typeof InputEvent === 'function' ? InputEvent : Event;
                        el.dispatchEvent(new Ctor('input', {bubbles: true}));
                        return true;
                        """,
                        input_element,
                        prompt,
                    )
                    typed_prompt = True
                except Exception:
                    typed_prompt = False

            if not typed_prompt:
                print("❌ Failed to type prompt")
                return None

            previous_counts = snapshot_response_counts()

            # Send it (try button first, then Enter)
            send_selector = selectors.get('send')
            sent = False

            if send_selector:
                for selector in send_selector.split(','):
                    try:
                        send_button = self.driver.find_element(By.CSS_SELECTOR, selector.strip())
                        if send_button and send_button.is_displayed():
                            send_button.click()
                            sent = True
                            break
                    except Exception:
                        continue

            if not sent:
                input_element.send_keys(Keys.RETURN)

            # Wait for response
            print(f"⏳ Waiting for {self.provider.upper()} response...")

            wait_start = time.time()

            # Try to get response with refresh logic for ChatGPT
            refresh_attempted = False
            working_selector = None
            response_elements = None

            try:
                working_selector, response_elements = wait_for_new_response(previous_counts, timeout)
            except TimeoutException as e:
                # Special handling for ChatGPT - sometimes it gets stuck but a refresh fixes it
                if self.provider == 'chatgpt' and not refresh_attempted:
                    print(f"⚠️ ChatGPT seems stuck, refreshing page...")
                    refresh_attempted = True

                    try:
                        # Refresh the page
                        self.driver.refresh()
                        time.sleep(3)  # Give page time to reload

                        # Check if response is now available (it often is after refresh)
                        found_response = False
                        for sel in response_selector_list:
                            try:
                                elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                                if elements and len(elements) > 0:
                                    # Check if there's actual text content
                                    if elements[-1].text and len(elements[-1].text) > 0:
                                        working_selector = sel
                                        response_elements = elements
                                        found_response = True
                                        print(f"✓ Response found after refresh")
                                        break
                            except Exception:
                                continue

                        if not found_response:
                            raise e  # Re-raise the original timeout if still no response
                    except Exception as refresh_error:
                        if isinstance(refresh_error, TimeoutException):
                            raise refresh_error
                        print(f"⚠️ Refresh attempt failed: {refresh_error}")
                        raise e  # Re-raise original timeout
                else:
                    raise  # Re-raise for non-ChatGPT providers or if refresh already attempted

            elapsed = time.time() - wait_start
            remaining_timeout = max(5, timeout - int(elapsed))

            # If we still don't have a working selector, can't proceed
            if not working_selector or not response_elements:
                print(f"❌ No response found")
                return None

            # Wait for the response to finish generating
            prev_length = 0
            stable_count = 0
            start_time = time.time()

            # Fast stability check with generation detection
            while (time.time() - start_time) < remaining_timeout:
                time.sleep(0.35)

                try:
                    response_elements = self.driver.find_elements(By.CSS_SELECTOR, working_selector)
                except Exception:
                    break

                if not response_elements:
                    continue

                current_text = response_elements[-1].text
                current_length = len(current_text)

                if current_length > 0:
                    if current_length == prev_length:
                        stable_count += 1
                    else:
                        stable_count = 0

                    prev_length = current_length

                    if stable_count >= 1 and not generation_active():
                        break
                    if stable_count >= 3:  # fallback if stop indicator not detected
                        break

            # Get the final response
            final_response = None
            if response_elements and len(response_elements) > 0:
                final_response = response_elements[-1].text

            if final_response:
                if self.provider == 'claude' and claude_response_is_reasoning(final_response):
                    final_response = self._wait_for_claude_answer(
                        working_selector,
                        final_response,
                        max(6, timeout // 2),
                    )
                elif self.provider == 'deepseek' and deepseek_response_is_reasoning(final_response):
                    final_response = self._wait_for_deepseek_answer(
                        working_selector,
                        final_response,
                        max(6, timeout // 2),
                    )
                # Clean up UI elements from the response
                ui_elements = [
                    'Retry',
                    'Copy',
                    'Copy code',
                    'Regenerate',
                    'Continue',
                    'Show thinking',
                    'Hide thinking',
                    'ChatGPT said:',
                    'ChatGPT said',
                ]
                for element in ui_elements:
                    final_response = final_response.replace(element, '').strip()

                # Remove multiple newlines that might be left over
                while '\n\n\n' in final_response:
                    final_response = final_response.replace('\n\n\n', '\n\n')

                final_response = final_response.strip()

                if self.provider == 'deepseek':
                    final_response = strip_deepseek_thinking(final_response)
                elif self.provider == 'claude':
                    final_response = strip_claude_reasoning_lines(final_response)

                final_response = final_response.strip()

                if self.provider == 'deepseek' and deepseek_response_is_reasoning(final_response):
                    print("❌ DeepSeek response still looks like reasoning; giving up")
                    return None

                if not final_response:
                    print("❌ Response element exists but only contained status text")
                    return None

                print(f"✓ Response received ({len(final_response)} chars)")

                if self.provider == 'claude':
                    self.dismiss_claude_errors()

                return final_response
            else:
                print(f"❌ Response element exists but no text found")
                return None

        except TimeoutException:
            print(f"❌ Timeout waiting for response")
            return None
        except Exception as e:
            print(f"❌ Failed to get response: {e}")
            return None

    def try_new_chat(self):
        """Try to start a new chat (not critical if it fails)"""
        try:
            selectors = self.selectors.get(self.provider, {})
            new_chat_selector = selectors.get('new_chat')

            if new_chat_selector and self.driver:
                new_chat = self.driver.find_element(By.CSS_SELECTOR, new_chat_selector)
                if new_chat.is_displayed():
                    new_chat.click()
                    time.sleep(0.6)
        except:
            pass  # Not critical

    def get_trading_decision(self, token: str, context: Dict) -> Optional[Dict]:
        """
        Get a trading decision for a token

        Args:
            token: The token to analyze
            context: Market data context

        Returns:
            Trading decision dict or None
        """
        # Build a simple prompt
        quick = context.get('quick_summary', {})

        prompt = f"""Analyze {token} for trading.

Current Price: ${quick.get('price', 0):.6f}
1h Change: {quick.get('price_change_1h', 0):.2f}%
Volume Spike: {quick.get('volume_spike', 1):.1f}x
Sentiment: {quick.get('sentiment_1h', 0):.3f}
Market: {context.get('market_regime', 'UNKNOWN')}

Respond with ONLY these lines:
ACTION: BUY or SHORT or SELL or HOLD
CONFIDENCE: 0.0 to 1.0
SIZE: 0.5 to 3.0
STOP: percentage
PROFIT: percentage
REASON: one sentence"""

        # Get response from AI
        response = self.send_prompt(prompt)

        if not response:
            return None

        # Parse the response
        try:
            decision = {
                'token': token,
                'provider': self.provider,
                'timestamp': time.time()
            }

            lines = response.upper().split('\n')

            for line in lines:
                if 'ACTION:' in line:
                    for action in ['BUY', 'SHORT', 'SELL', 'HOLD']:
                        if action in line:
                            decision['action'] = action
                            break

                elif 'CONFIDENCE:' in line:
                    try:
                        num = ''.join(c for c in line.split(':')[1] if c.isdigit() or c == '.')
                        decision['confidence'] = float(num)
                        if decision['confidence'] > 1:
                            decision['confidence'] /= 100
                    except:
                        pass

                elif 'SIZE:' in line:
                    try:
                        num = ''.join(c for c in line.split(':')[1] if c.isdigit() or c == '.')
                        decision['position_size'] = float(num) / 100
                    except:
                        pass

                elif 'STOP:' in line:
                    try:
                        num = ''.join(c for c in line.split(':')[1] if c.isdigit() or c == '.')
                        decision['stop_loss_pct'] = float(num)
                    except:
                        pass

                elif 'PROFIT:' in line:
                    try:
                        num = ''.join(c for c in line.split(':')[1] if c.isdigit() or c == '.')
                        decision['take_profit_pct'] = float(num)
                    except:
                        pass

                elif 'REASON:' in line:
                    decision['reasoning'] = line.split(':', 1)[1].strip()

            # Check we got the required fields
            if 'action' in decision and 'confidence' in decision:
                # Set defaults for missing fields
                if 'position_size' not in decision:
                    decision['position_size'] = 0.01
                if 'stop_loss_pct' not in decision:
                    decision['stop_loss_pct'] = 3.0
                if 'take_profit_pct' not in decision:
                    decision['take_profit_pct'] = 6.0

                print(f"📊 {self.provider.upper()}: {decision['action']} @ {decision['confidence']:.0%} confidence")
                return decision

        except Exception as e:
            print(f"⚠️  Failed to parse response: {e}")

        return None

    def cleanup(self):
        """Close the browser"""
        if self.driver:
            try:
                self.save_cookies()
                self.save_storage()
            except:
                pass

            try:
                # Properly quit the driver
                self.driver.quit()
            except:
                pass

            try:
                # Force kill the process if still running
                if hasattr(self.driver, 'service') and self.driver.service.process:
                    self.driver.service.process.kill()
            except:
                pass

            self.driver = None
            self.is_initialized = False
            print(f"✓ {self.provider.upper()} closed")

    def __del__(self):
        """Cleanup on deletion"""
        try:
            if hasattr(self, 'driver') and self.driver:
                # Suppress all output during __del__
                import sys
                import os
                old_stderr = sys.stderr
                try:
                    sys.stderr = open(os.devnull, 'w')
                    self.cleanup()
                finally:
                    try:
                        sys.stderr.close()
                    except:
                        pass
                    sys.stderr = old_stderr
        except:
            pass


# Simple singleton management
_browser_instances = {}

def get_browser_ai(provider: str = 'claude') -> BrowserAI:
    """
    Get a browser AI instance for a specific provider

    Args:
        provider: 'claude', 'chatgpt', 'deepseek', or 'gemini'

    Returns:
        BrowserAI instance
    """
    global _browser_instances

    if provider not in _browser_instances:
        _browser_instances[provider] = BrowserAI(provider)

    return _browser_instances[provider]

def cleanup_all_browsers():
    """Close all browser instances"""
    global _browser_instances

    for instance in _browser_instances.values():
        instance.cleanup()

    _browser_instances.clear()
    print("✓ All browsers closed")
def deepseek_line_is_reasoning(line: str) -> bool:
    """Heuristic to determine if a single line is intermediate reasoning."""
    if not line:
        return True
    stripped = line.strip()
    if not stripped:
        return True
    lowered = stripped.lower()
    if any(marker in lowered for marker in DEEPSEEK_THINKING_MARKERS):
        return True
    if any(keyword in lowered for keyword in DEEPSEEK_REASONING_KEYWORDS):
        return True
    for pattern in DEEPSEEK_REASONING_PATTERNS:
        if pattern.search(stripped):
            return True
    if len(stripped) <= 4:
        if stripped.lower() not in DEEPSEEK_SHORT_ANSWER_WHITELIST and not stripped.isdigit():
            return True
    return False


def deepseek_response_is_reasoning(text: str) -> bool:
    """Determine if the whole DeepSeek response still looks like reasoning."""
    if not text:
        return True
    stripped = text.strip()
    if not stripped:
        return True
    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    if not lines:
        return True
    reasoning_lines = sum(1 for line in lines if deepseek_line_is_reasoning(line))
    if reasoning_lines == len(lines):
        return True
    if len(lines) <= 2 and reasoning_lines >= 1:
        return True
    if len(stripped) < 8 and stripped.lower() not in DEEPSEEK_SHORT_ANSWER_WHITELIST:
        return True
    return False
