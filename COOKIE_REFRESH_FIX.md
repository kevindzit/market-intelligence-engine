# Cookie Refresh Fix - Global Retry System

## Problem

The old system had these issues:
1. **Per-token retry** - Refreshed cookies once per token (inefficient)
2. **Only 1 retry per token** - Would give up too quickly
3. **Stale client state** - Reloading cookies into same client kept cached session data
4. **Reopening terminal worked** - Because it created a fresh client instance

## Solution

### 1. Global Cookie Refresh (twitter_funcs.py)

`auto_refresh_cookies()` now:
- **Returns a NEW client instance** instead of reloading cookies into old client
- This clears all cached session state
- **Retries up to 10 times** before giving up
- Waits 3 seconds between attempts

```python
def auto_refresh_cookies(client, cookies_path="cookies.json", max_attempts=10):
    """Returns a new Client with fresh cookies, or None if failed"""
    for attempt in range(1, max_attempts + 1):
        cookies = refresh_cookies(headless=False)
        if cookies and save_cookies(cookies):
            # Create FRESH client instance
            new_client = Client('en-US')
            new_client.load_cookies(cookies_path)
            return new_client
    return None
```

### 2. Per-Token Method Simplified

`get_tweets_for_token()` now:
- **No retry logic** - Just raises exception on auth error
- Simpler and cleaner code

```python
async def get_tweets_for_token(self, token):
    try:
        tweets = await self.client.search_tweet(f"${token}", product='Latest')
        # ... process tweets ...
    except Exception as e:
        if '404' in str(e) or 'unauthorized' in str(e):
            raise  # Let run_cycle handle it globally
        print(f"[ERROR] Failed to fetch {token}: {e}")
```

### 3. Global Retry in run_cycle()

`run_cycle()` now handles auth errors for ALL tokens at once:

```python
async def run_cycle(self):
    all_tweets = []

    for attempt in range(2):  # Max 2 attempts total
        try:
            # Try to fetch ALL tokens
            for token in TOKENS_TO_TRACK:
                tweets = await self.get_tweets_for_token(token)
                all_tweets.extend(tweets)
            break  # Success!

        except Exception as e:
            if 'auth error' and attempt == 0:
                print("[AUTH ERROR] Refreshing cookies (up to 10 attempts)...")
                new_client = auto_refresh_cookies(self.client)
                if new_client:
                    self.client = new_client  # Use fresh client
                    all_tweets = []  # Clear partial results
                    continue  # Retry ALL tokens with new client
                else:
                    print("[FATAL] Cookie refresh failed after 10 attempts")
                    break
```

## How It Works Now

### Old Behavior (Per-Token Retry):
```
Token 1: Try → 404 → Refresh cookies (1 attempt) → Retry → 404 → Skip
Token 2: Try → 404 → Refresh cookies (1 attempt) → Retry → 404 → Skip
Token 3: Try → 404 → Refresh cookies (1 attempt) → Retry → 404 → Skip
...
Result: 7 tokens × 1 retry each = wasted effort
```

### New Behavior (Global Retry):
```
Token 1: Try → 404 → STOP and raise exception

▼ Global Handler Catches Exception ▼

Refresh cookies (up to 10 attempts) → Get fresh client → Clear all results

▼ Retry ALL tokens from start ▼

Token 1: Try → Success!
Token 2: Try → Success!
Token 3: Try → Success!
...
Result: 1 global refresh fixes all tokens
```

## Why Closing Terminal Worked

When you closed the terminal and reran the script:
- Created a **completely fresh Python process**
- Created a **new twikit Client instance**
- No cached session state

The fix replicates this by creating a fresh Client instance after refreshing cookies.

## Files Modified

1. `nice_funcs/twitter_funcs.py` - Returns new client instance
2. `crypto_scrapers/twitter_memecoins.py` - Global retry logic
3. `crypto_scrapers/twitter_largecaps.py` - Global retry logic
4. `crypto_scrapers/twitter_defi.py` - Global retry logic
5. `crypto_scrapers/twitter_layer1s.py` - Global retry logic
6. `crypto_scrapers/twitter_layer2s.py` - Global retry logic
7. `crypto_scrapers/twitter_ai.py` - Global retry logic

## Expected New Behavior

When you run a scraper now:
1. First auth error on ANY token → Trigger global refresh
2. Refresh cookies up to 10 times until success
3. Create fresh client with new cookies
4. Retry ALL tokens from the beginning
5. If still failing after fresh client → Skip this cycle and try again in 5 minutes

This matches what happens when you manually restart the script!
