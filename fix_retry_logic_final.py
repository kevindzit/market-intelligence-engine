#!/usr/bin/env python3
"""
Fix retry logic in all scrapers to retry up to 10 times at scraper level.
Each refresh cycle = 1 attempt to get cookies + retry all tokens.
"""

import re

files_to_fix = [
    'crypto_scrapers/twitter_largecaps.py',
    'crypto_scrapers/twitter_defi.py',
    'crypto_scrapers/twitter_layer1s.py',
    'crypto_scrapers/twitter_layer2s.py',
    'crypto_scrapers/twitter_ai.py',
    'crypto_scrapers/twitter_whales.py'
]

def fix_scraper(filepath):
    """Fix retry logic in a scraper"""
    print(f"Fixing {filepath}...")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace the old 2-attempt logic with 10-attempt logic
    old_pattern = r'''        all_tweets = \[\]

        # Collect .+ - retry once with fresh cookies if auth fails
        for attempt in range\(2\):  # Max 2 attempts: original \+ 1 retry after cookie refresh
            try:
                for (token|username) in (TOKENS_TO_TRACK|WHALE_ACCOUNTS\.keys\(\)):
                    (tweets = await self\.get_tweets_for_token\(token\)|tweets = await self\.get_whale_tweets\(username\))
                    all_tweets\.extend\(tweets\)
                break  # Success - exit retry loop

            except Exception as e:
                error_msg = str\(e\)\.lower\(\)
                if '404' in error_msg or 'unauthorized' in error_msg or 'forbidden' in error_msg:
                    if attempt == 0:  # First attempt failed
                        print\(f"\\n\[AUTH ERROR\] Authentication failed\. Refreshing cookies\.\.\."\)
                        new_client = auto_refresh_cookies\(self\.client\)
                        if new_client:
                            self\.client = new_client
                            print\(f"\[RETRY\] Retrying all .+ with fresh client\.\.\."\)
                            all_tweets = \[\]  # Clear any partial results
                            continue  # Retry the loop
                        else:
                            print\(f"\[FATAL\] Cookie refresh failed after 10 attempts\. Skipping this cycle\."\)
                            break
                    else:  # Second attempt also failed
                        print\(f"\[FATAL\] Still failing after cookie refresh\. Skipping this cycle\."\)
                        break
                else:
                    # Non-auth error - just log and continue
                    print\(f"\[ERROR\] Unexpected error: \{e\}"\)
                    break'''

    # Determine if this is token-based or whale-based
    if 'WHALE_ACCOUNTS' in content:
        iterator = 'username in WHALE_ACCOUNTS.keys()'
        get_method = 'tweets = await self.get_whale_tweets(username)'
        retry_msg = 'whale accounts'
    else:
        iterator = 'token in TOKENS_TO_TRACK'
        get_method = 'tweets = await self.get_tweets_for_token(token)'
        retry_msg = 'tokens'

    new_pattern = f'''        all_tweets = []

        # Collect tweets - retry up to 10 times with fresh cookies if auth fails
        max_refresh_attempts = 10
        for refresh_attempt in range(max_refresh_attempts):
            try:
                for {iterator}:
                    {get_method}
                    all_tweets.extend(tweets)
                break  # Success - exit retry loop

            except Exception as e:
                error_msg = str(e).lower()
                if '404' in error_msg or 'unauthorized' in error_msg or 'forbidden' in error_msg:
                    # Auth error - refresh cookies and retry
                    print(f"\\n[AUTH ERROR] Authentication failed (refresh cycle {{refresh_attempt + 1}}/{{max_refresh_attempts}})")
                    print(f"[REFRESH] Getting fresh cookies and creating new client...")

                    new_client = auto_refresh_cookies(self.client)
                    if new_client:
                        self.client = new_client
                        all_tweets = []  # Clear any partial results
                        print(f"[RETRY] Retrying all {retry_msg} with fresh client...")
                        continue  # Retry the loop with new client
                    else:
                        print(f"[FATAL] Failed to extract cookies from Firefox. Skipping this cycle.")
                        break
                else:
                    # Non-auth error - just log and continue
                    print(f"[ERROR] Unexpected error: {{e}}")
                    break
        else:
            # Loop completed without break = hit max attempts
            print(f"[FATAL] Still failing after {{max_refresh_attempts}} refresh attempts. Skipping this cycle.")'''

    content = re.sub(old_pattern, new_pattern, content, flags=re.DOTALL | re.MULTILINE)

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

    print("\\nDone! All scrapers fixed with 10-retry logic.")
