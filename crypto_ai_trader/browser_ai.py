"""
Browser AI System for Free AI Model Access
Uses Selenium to interact with AI chat interfaces (Claude, ChatGPT, DeepSeek)
"""

import time
import os
from typing import Dict, Optional
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


class BrowserAI:
    """Browser interface for AI chat services"""

    def __init__(self, provider: str = 'claude'):
        """
        Initialize browser AI for a specific provider

        Args:
            provider: 'claude', 'chatgpt', or 'deepseek'
        """
        self.provider = provider
        self.driver = None
        self.is_initialized = False
        self.cookies_file = f"cookies_{provider}.pkl"

        # URLs for each provider
        self.urls = {
            'claude': 'https://claude.ai/new',
            'chatgpt': 'https://chat.openai.com',
            'deepseek': 'https://chat.deepseek.com'
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
                'response': 'div[data-message-author-role="assistant"], div.markdown, article',
                'new_chat': 'button[aria-label*="New chat"], a[href="/"]'
            },
            'deepseek': {
                'input': 'textarea[placeholder*="Ask"], div[contenteditable="true"], textarea',
                'send': 'button[type="submit"], button[aria-label*="Send"]',
                'response': 'div.markdown, div[class*="message"], div[class*="response"], article',
                'new_chat': 'button[aria-label*="New"], a[href*="chat"]'
            }
        }

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
            if self.load_cookies():
                print(f"✓ Loaded saved session")
                self.driver.refresh()
                time.sleep(3)

            # Check if we need to login
            if self.needs_login():
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

                # Save cookies for next time
                self.save_cookies()
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

    def needs_login(self) -> bool:
        """Check if login is needed"""
        if not self.driver:
            return True

        try:
            # Simple check - can we find the input field?
            selectors = self.selectors.get(self.provider, {})
            input_selector = selectors.get('input')

            if input_selector:
                WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, input_selector))
                )
                return False  # Found input, no login needed
        except:
            pass

        # Check for login keywords
        try:
            page_text = self.driver.find_element(By.TAG_NAME, 'body').text.lower()
            login_words = ['sign in', 'log in', 'sign up', 'welcome to']

            for word in login_words:
                if word in page_text:
                    return True
        except:
            pass

        return False

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

            # Find the input field
            input_selector = selectors.get('input')
            if not input_selector:
                print(f"❌ No input selector for {self.provider}")
                return None

            # Wait for and find the input - try multiple selectors
            input_element = None
            print(f"⏳ Sending prompt...")

            for selector in input_selector.split(','):
                try:
                    input_element = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, selector.strip()))
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
            input_element.click()
            time.sleep(0.2)

            # Clear any existing text
            input_element.send_keys(Keys.CONTROL + "a")
            input_element.send_keys(Keys.DELETE)
            time.sleep(0.15)

            # Type the prompt
            input_element.send_keys(prompt)

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
            working_selector, response_elements = wait_for_new_response(previous_counts, timeout)
            elapsed = time.time() - wait_start
            remaining_timeout = max(5, timeout - int(elapsed))

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
                # Clean up UI elements from the response
                ui_elements = ['Retry', 'Copy', 'Copy code', 'Regenerate', 'Continue']
                for element in ui_elements:
                    final_response = final_response.replace(element, '').strip()

                # Remove multiple newlines that might be left over
                while '\n\n\n' in final_response:
                    final_response = final_response.replace('\n\n\n', '\n\n')

                final_response = final_response.strip()

                print(f"✓ Response received ({len(final_response)} chars)")
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
        provider: 'claude', 'chatgpt', or 'deepseek'

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
