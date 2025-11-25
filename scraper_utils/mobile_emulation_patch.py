"""
Mobile Emulation Patch for Twitter Scrapers
Automatically applied when ENABLE_MOBILE_EMULATION env var is set by orchestrator
Simple and lightweight - just changes user agents
"""

import os

# Check if mobile emulation is enabled by orchestrator
if os.getenv('ENABLE_MOBILE_EMULATION') == 'true':
    mobile_ua = os.getenv('MOBILE_USER_AGENT', '')

    if mobile_ua:
        # Patch httpx which is used by twikit
        try:
            import httpx
            _original_client = httpx.Client
            _original_async_client = httpx.AsyncClient

            class MobileClient(_original_client):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    if self.headers:
                        self.headers['user-agent'] = mobile_ua
                    else:
                        self.headers = httpx.Headers({'user-agent': mobile_ua})

            class MobileAsyncClient(_original_async_client):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
                    if self.headers:
                        self.headers['user-agent'] = mobile_ua
                    else:
                        self.headers = httpx.Headers({'user-agent': mobile_ua})

            # Replace the original classes
            httpx.Client = MobileClient
            httpx.AsyncClient = MobileAsyncClient

            # Short message to confirm it's working
            device = 'iPhone' if 'iPhone' in mobile_ua else 'Android' if 'Android' in mobile_ua else 'Mobile'
            print(f"[MOBILE] Emulating {device} device")

        except ImportError:
            pass  # httpx not available, that's okay