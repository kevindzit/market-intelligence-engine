"""
Simple Health Monitor for Twitter Scrapers
Tracks consecutive empty cycles and sends alerts
"""
import os
from datetime import datetime
from pathlib import Path

class HealthMonitor:
    def __init__(self, scraper_name, alert_threshold=3, log_dir="logs"):
        self.scraper_name = scraper_name
        self.alert_threshold = alert_threshold
        self.consecutive_empty_cycles = 0
        self.total_cycles = 0
        self.total_tweets_collected = 0
        self.last_successful_cycle = datetime.now()
        self.alerted = False

        # Create logs directory
        Path(log_dir).mkdir(exist_ok=True)
        self.alert_log = os.path.join(log_dir, f"{scraper_name}_alerts.log")

    def record_cycle(self, tweets_saved):
        """Record the result of a scraping cycle"""
        self.total_cycles += 1
        self.total_tweets_collected += tweets_saved

        if tweets_saved > 0:
            self.consecutive_empty_cycles = 0
            self.last_successful_cycle = datetime.now()
            self.alerted = False  # Reset alert flag on successful cycle
        else:
            self.consecutive_empty_cycles += 1

            # Alert if threshold reached
            if self.consecutive_empty_cycles >= self.alert_threshold and not self.alerted:
                self._send_alert()
                self.alerted = True

    def _send_alert(self):
        """Send alert when scraper appears to be down"""
        alert_msg = f"""
{'='*70}
ALERT: {self.scraper_name} HEALTH CHECK FAILED
{'='*70}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Issue: No new tweets for {self.consecutive_empty_cycles} consecutive cycles
Last successful cycle: {self.last_successful_cycle.strftime('%Y-%m-%d %H:%M:%S')}
Time since last success: {(datetime.now() - self.last_successful_cycle).total_seconds() / 60:.1f} minutes

Possible causes:
- Rate limit hit (check Twitter API limits)
- Cookies expired (refresh cookies.json)
- No new tweets from sources (less likely if multiple sources)
- Network/API issues

Action: Check scraper logs and restart if needed
{'='*70}
"""

        # Print to console
        print(alert_msg)

        # Log to file
        with open(self.alert_log, 'a') as f:
            f.write(alert_msg + '\n')

        # Optional: Send to Discord webhook (if configured)
        discord_webhook = os.getenv('DISCORD_WEBHOOK_URL')
        if discord_webhook:
            self._send_discord_alert(alert_msg, discord_webhook)

    def _send_discord_alert(self, message, webhook_url):
        """Send alert to Discord webhook (optional)"""
        try:
            import requests
            payload = {
                "content": f"🚨 **Scraper Alert**\n```\n{message}\n```"
            }
            requests.post(webhook_url, json=payload, timeout=5)
        except:
            pass  # Fail silently if Discord not configured

    def get_stats(self):
        """Get current health stats"""
        return {
            'total_cycles': self.total_cycles,
            'total_tweets': self.total_tweets_collected,
            'avg_tweets_per_cycle': self.total_tweets_collected / self.total_cycles if self.total_cycles > 0 else 0,
            'consecutive_empty': self.consecutive_empty_cycles,
            'last_success': self.last_successful_cycle,
            'health_status': 'HEALTHY' if self.consecutive_empty_cycles < self.alert_threshold else 'WARNING'
        }

    def print_health_summary(self):
        """Print a simple health summary"""
        stats = self.get_stats()
        status_emoji = "OK" if stats['health_status'] == 'HEALTHY' else "WARN"

        print(f"\n[{status_emoji}] Health: {stats['health_status']} | Cycles: {stats['total_cycles']} | Tweets: {stats['total_tweets']} | Avg: {stats['avg_tweets_per_cycle']:.1f} | Empty: {stats['consecutive_empty']}/{self.alert_threshold}")
