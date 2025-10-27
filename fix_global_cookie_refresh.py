#!/usr/bin/env python3
"""
Apply global cookie refresh fix to all token-based scrapers.
This ensures cookies are refreshed ONCE globally (with 10 retries)
rather than once per token (with 1 retry).
"""

import re

files_to_fix = [
    'crypto_scrapers/twitter_memecoins.py',
    'crypto_scrapers/twitter_largecaps.py',
    'crypto_scrapers/twitter_defi.py',
    'crypto_scrapers/twitter_layer1s.py',
    'crypto_scrapers/twitter_layer2s.py'
]

def fix_scraper(filepath):
    """Apply global cookie refresh fix to a scraper"""
    print(f"Fixing {filepath}...")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Remove retry parameters from function signature
    content = re.sub(
        r'async def get_tweets_for_token\(self, token, retry_count=0, max_retries=1\):',
        r'async def get_tweets_for_token(self, token):',
        content
    )

    # 2. Simplify exception handler - just raise on auth errors
    old_handler = r'''# Check if we've hit max retries
                if retry_count >= max_retries:
                    print\(f"\[ERROR\] Max retries \(\{max_retries\}\) reached for \{token\}\. Skipping\.\.\."\)
                    return collected
                # Try to refresh cookies
                if auto_refresh_cookies\(self\.client\):
                    print\(f"\[RETRY\] Cookies refreshed successfully, retrying search for \{token\} \(attempt \{retry_count \+ 1\}/\{max_retries\}\)\.\.\."\)
                    return await self\.get_tweets_for_token\(token, retry_count \+ 1, max_retries\)
                else:
                    print\(f"\[ERROR\] Cookie refresh failed for \{token\}"\)
                    return collected'''

    new_handler = r'''raise  # Raise to trigger global cookie refresh in main loop'''

    content = re.sub(old_handler, new_handler, content, flags=re.DOTALL)

    # 3. Update run_cycle to handle global cookie refresh
    old_run_cycle = r'''    async def run_cycle\(self\):
        """Run one collection cycle"""
        print\(f"\\n\[\{datetime\.now\(\)\.strftime\('%H:%M:%S'\)\}\] Starting collection cycle"\)

        all_tweets = \[\]

        # Collect .+ tweets
        for token in TOKENS_TO_TRACK:
            tweets = await self\.get_tweets_for_token\(token\)
            all_tweets\.extend\(tweets\)'''

    new_run_cycle = r'''    async def run_cycle(self):
        """Run one collection cycle"""
        print(f"\\n[{datetime.now().strftime('%H:%M:%S')}] Starting collection cycle")

        all_tweets = []

        # Collect tweets - retry once with fresh cookies if auth fails
        for attempt in range(2):  # Max 2 attempts: original + 1 retry after cookie refresh
            try:
                for token in TOKENS_TO_TRACK:
                    tweets = await self.get_tweets_for_token(token)
                    all_tweets.extend(tweets)
                break  # Success - exit retry loop

            except Exception as e:
                error_msg = str(e).lower()
                if '404' in error_msg or 'unauthorized' in error_msg or 'forbidden' in error_msg:
                    if attempt == 0:  # First attempt failed
                        print(f"\\n[AUTH ERROR] Authentication failed. Refreshing cookies...")
                        new_client = auto_refresh_cookies(self.client)
                        if new_client:
                            self.client = new_client
                            print(f"[RETRY] Retrying all tokens with fresh client...")
                            all_tweets = []  # Clear any partial results
                            continue  # Retry the loop
                        else:
                            print(f"[FATAL] Cookie refresh failed after 10 attempts. Skipping this cycle.")
                            break
                    else:  # Second attempt also failed
                        print(f"[FATAL] Still failing after cookie refresh. Skipping this cycle.")
                        break
                else:
                    # Non-auth error - just log and continue
                    print(f"[ERROR] Unexpected error: {e}")
                    break'''

    content = re.sub(old_run_cycle, new_run_cycle, content, flags=re.DOTALL)

    # Write fixed content
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"OK Fixed {filepath}")

if __name__ == "__main__":
    for filepath in files_to_fix:
        try:
            fix_scraper(filepath)
        except Exception as e:
            print(f"ERROR fixing {filepath}: {e}")

    print("\\nDone! All scrapers fixed.")
