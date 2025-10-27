#!/usr/bin/env python3
"""
Fix all token-based scrapers with the correct changes:
1. Add shared function imports
2. Add influence_weight to INSERT
3. Add retry logic
4. Remove duplicate methods
"""

import re
from pathlib import Path

files_to_fix = [
    'crypto_scrapers/twitter_memecoins.py',
    'crypto_scrapers/twitter_largecaps.py',
    'crypto_scrapers/twitter_defi.py',
    'crypto_scrapers/twitter_layer1s.py',
    'crypto_scrapers/twitter_ai.py'
]

def fix_file(filepath):
    """Apply all fixes to a single scraper file"""
    print(f"Fixing {filepath}...")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # 1. Update imports
    content = re.sub(
        r'(from nice_funcs\.twitter_funcs import \(\n.*?analyze_sentiment,\n)(.*?SPAM_KEYWORDS\n\))',
        r'\1    calculate_volume_spike,\n    calculate_token_velocity_metrics,\n    update_token_sentiment_history,\n\2',
        content,
        flags=re.DOTALL
    )

    # 2. Add influence_weight to INSERT (find the line with pump_score, source)
    content = re.sub(
        r'(\s+is_whale, volume_spike, bot_probability, pump_score,) source,',
        r'\1 influence_weight, source,',
        content
    )

    # Also update the VALUES placeholder count
    content = re.sub(
        r'(VALUES \(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,) %s\)',
        r'\1 %s, %s)',
        content
    )

    # Add influence_weight value (after pump_score)
    content = re.sub(
        r"(round\(pump_score, 3\) if pump_score > 0\.5 else None,\n\s+)'(general_search|largecaps|defi|layer1s|ai)',",
        r"\1round(influence_weight, 4),\n                        '\2',",
        content
    )

    # 3. Add retry_count parameter to get_tweets_for_token
    content = re.sub(
        r'async def get_tweets_for_token\(self, token\):',
        r'async def get_tweets_for_token(self, token, retry_count=0, max_retries=1):',
        content
    )

    # 4. Fix the exception handler for retry logic
    # Find the pattern and replace it
    pattern = r"(if '404' in error_msg or 'unauthorized' in error_msg or 'forbidden' in error_msg:\n\s+print\(f\"\[WARN\] Authentication error detected: \{e\}\"\)\n\s+)# auto_refresh_cookies now retries up to 10 times internally\n\s+if auto_refresh_cookies\(self\.client\):\n\s+print\(f\"\[RETRY\] Cookies refreshed successfully, retrying search for \{token\}\.\.\.\"\)\n\s+return await self\.get_tweets_for_token\(token\)\n\s+else:\n\s+print\(f\"\[FATAL\] Cookie refresh failed after all attempts for \{token\}\"\)\n\s+raise Exception\(f\"Unable to refresh cookies after 10 attempts\"\)"

    replacement = r'''\1# Check if we've hit max retries
                if retry_count >= max_retries:
                    print(f"[ERROR] Max retries ({max_retries}) reached for {token}. Skipping...")
                    return collected
                # Try to refresh cookies
                if auto_refresh_cookies(self.client):
                    print(f"[RETRY] Cookies refreshed successfully, retrying search for {token} (attempt {retry_count + 1}/{max_retries})...")
                    return await self.get_tweets_for_token(token, retry_count + 1, max_retries)
                else:
                    print(f"[ERROR] Cookie refresh failed for {token}")
                    return collected'''

    content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    # 5. Remove duplicate method definitions
    # Remove calculate_volume_spike
    content = re.sub(
        r'\n    def calculate_volume_spike\(self, token, current_count\):.*?return spike_ratio\n',
        '\n',
        content,
        flags=re.DOTALL
    )

    # Remove calculate_velocity_metrics
    content = re.sub(
        r'\n    def calculate_velocity_metrics\(self, token, current_sentiment, current_volume_spike\):.*?\'time_delta\': time_delta\n        \}\n',
        '\n',
        content,
        flags=re.DOTALL
    )

    # Remove update_sentiment_history
    content = re.sub(
        r'\n    def update_sentiment_history\(self, token, sentiment, volume_spike\):.*?self\.sentiment_history\[token\] = self\.sentiment_history\[token\]\[-3:\]\n',
        '\n',
        content,
        flags=re.DOTALL
    )

    # 6. Update method calls to use shared functions
    content = re.sub(
        r'self\.calculate_volume_spike\(token, len\(tweets\)\)',
        r'calculate_volume_spike(self.volume_baseline, token, len(tweets))',
        content
    )

    content = re.sub(
        r'self\.calculate_velocity_metrics\((.*?)\)',
        r'calculate_token_velocity_metrics(self.sentiment_history, \1)',
        content
    )

    content = re.sub(
        r'self\.update_sentiment_history\((.*?)\)',
        r'update_token_sentiment_history(self.sentiment_history, \1)',
        content
    )

    # Write fixed content
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"OK Fixed {filepath}")

if __name__ == "__main__":
    for filepath in files_to_fix:
        try:
            fix_file(filepath)
        except Exception as e:
            print(f"ERROR Error fixing {filepath}: {e}")

    print("\nDone All files fixed!")
