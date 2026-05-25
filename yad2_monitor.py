#!/usr/bin/env python3
"""
Yad2 Monitor - Monitors total results counter for new listing detection
Uses plain HTTP requests + __NEXT_DATA__ parsing to avoid bot detection.
"""

import os
import sys
import json
import re
import time
import requests
import cloudscraper
from datetime import datetime
from typing import Dict, List, Optional


def _make_scraper():
    return cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )


class Yad2Monitor:
    def __init__(self, config: Dict):
        self.url = config['url']
        self.telegram_bot_token = config['telegram_bot_token']
        self.telegram_chat_id = config['telegram_chat_id']
        self.storage_file = config.get('storage_file', 'yad2_data.json')
        self.scraper = _make_scraper()
        self._consecutive_failures = 0
        self.data = self.load_data()

    def load_data(self) -> Dict:
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading data: {e}")
        return {
            'last_total': 0,
            'last_check': None,
            'history': [],
            'seen_listing_ids': []
        }

    def save_data(self):
        try:
            self.data['last_check'] = datetime.now().isoformat()
            with open(self.storage_file, 'w') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving data: {e}")

    def fetch_page(self) -> Optional[str]:
        """Fetch the Yad2 search page HTML."""
        try:
            sep = '&' if '?' in self.url else '?'
            url = f"{self.url}{sep}_t={int(time.time() * 1000)}"
            print(f"Fetching: {self.url}")
            resp = self.scraper.get(url, timeout=20)
            print(f"Status: {resp.status_code}")
            if resp.status_code != 200:
                print(f"Non-200 response. Body start:\n{resp.text[:500]}")
                self._consecutive_failures += 1
                if self._consecutive_failures >= 3:
                    print("3 consecutive failures — recreating scraper")
                    self.scraper = _make_scraper()
                    self._consecutive_failures = 0
                return None
            if len(resp.text) < 5000:
                print("Response too small — likely a block page")
                self._consecutive_failures += 1
                if self._consecutive_failures >= 3:
                    print("3 consecutive failures — recreating scraper")
                    self.scraper = _make_scraper()
                    self._consecutive_failures = 0
                return None
            self._consecutive_failures = 0
            return resp.text
        except Exception as e:
            print(f"Error fetching page: {e}")
            return None

    def extract_next_data(self, html: str) -> Optional[Dict]:
        """Extract the __NEXT_DATA__ JSON blob embedded by Next.js."""
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
        if not match:
            print("__NEXT_DATA__ not found in page")
            # Check if blocked
            if 'ShieldSquare' in html or 'captcha' in html.lower():
                print("Blocked by ShieldSquare / CAPTCHA")
            return None
        try:
            return json.loads(match.group(1))
        except Exception as e:
            print(f"Failed to parse __NEXT_DATA__: {e}")
            return None

    def get_total_and_listings(self) -> tuple[Optional[int], List[Dict]]:
        """
        Returns (total_count, listings[]).
        Walks common paths inside __NEXT_DATA__ where Yad2 stores feed data.
        """
        html = self.fetch_page()
        if not html:
            return None, []

        next_data = self.extract_next_data(html)
        if not next_data:
            # Dump first 2000 chars for debugging
            print(f"DEBUG page start:\n{html[:2000]}")
            return None, []

        # Save raw next_data for debugging on first failure
        try:
            with open('debug_next_data.json', 'w', encoding='utf-8') as f:
                json.dump(next_data, f, ensure_ascii=False, indent=2)
            print("Saved __NEXT_DATA__ to debug_next_data.json")
        except Exception:
            pass

        total = self._find_total(next_data)
        listings = self._find_listings(next_data)
        return total, listings

    def _find_total(self, data: Dict) -> Optional[int]:
        """Try multiple known paths for the total results count."""
        # Common paths seen in Yad2 Next.js structure
        paths = [
            # dehydrated query results
            lambda d: d['props']['pageProps']['dehydratedState']['queries'][0]['state']['data']['data']['pagination']['total'],
            lambda d: d['props']['pageProps']['dehydratedState']['queries'][0]['state']['data']['pagination']['total'],
            lambda d: d['props']['pageProps']['data']['pagination']['total'],
            lambda d: d['props']['pageProps']['feedData']['pagination']['total'],
            lambda d: d['props']['pageProps']['initialData']['pagination']['total'],
            lambda d: d['props']['pageProps']['totalItems'],
            lambda d: d['props']['pageProps']['total'],
        ]
        for path_fn in paths:
            try:
                val = path_fn(data)
                if isinstance(val, int):
                    print(f"Found total: {val}")
                    return val
            except (KeyError, IndexError, TypeError):
                continue

        # Generic deep search for a 'total' key near 'pagination'
        total = self._deep_search(data, 'total')
        if total is not None:
            print(f"Found total via deep search: {total}")
        return total

    def _find_listings(self, data: Dict) -> List[Dict]:
        """Try multiple known paths for the listing items array."""
        paths = [
            lambda d: d['props']['pageProps']['dehydratedState']['queries'][0]['state']['data']['data']['feed']['feed_items'],
            lambda d: d['props']['pageProps']['dehydratedState']['queries'][0]['state']['data']['feed']['feed_items'],
            lambda d: d['props']['pageProps']['data']['feed']['feed_items'],
            lambda d: d['props']['pageProps']['feedData']['feed_items'],
            lambda d: d['props']['pageProps']['initialData']['feed_items'],
            lambda d: d['props']['pageProps']['listings'],
            lambda d: d['props']['pageProps']['items'],
        ]
        for path_fn in paths:
            try:
                items = path_fn(data)
                if isinstance(items, list) and items:
                    print(f"Found {len(items)} listings")
                    return items
            except (KeyError, IndexError, TypeError):
                continue
        return []

    def _deep_search(self, obj, key: str, _depth=0):
        """Recursively search for a key in nested dicts/lists (max depth 8)."""
        if _depth > 8:
            return None
        if isinstance(obj, dict):
            if key in obj and isinstance(obj[key], int):
                return obj[key]
            for v in obj.values():
                result = self._deep_search(v, key, _depth + 1)
                if result is not None:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = self._deep_search(item, key, _depth + 1)
                if result is not None:
                    return result
        return None

    def _format_listing(self, item: Dict) -> Dict:
        """Extract useful fields from a raw feed item."""
        info = {}
        # Yad2 feed items vary; try common field names
        for title_key in ('title', 'heading', 'model', 'car_model'):
            if item.get(title_key):
                info['title'] = item[title_key]
                break
        for price_key in ('price', 'Price', 'priceOnly'):
            if item.get(price_key):
                info['price'] = str(item[price_key])
                break
        token = item.get('token') or item.get('id') or item.get('adNumber')
        if token:
            info['link'] = f"https://www.yad2.co.il/vehicles/cars/{token}"
            info['id'] = str(token)
        return info

    def send_telegram_message(self, message: str) -> bool:
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                'chat_id': self.telegram_chat_id,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': False
            }
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            print("Telegram notification sent")
            return True
        except Exception as e:
            print(f"Error sending Telegram: {e}")
            return False

    def format_notification(self, old_total: int, new_total: int, new_listings: List[Dict]) -> str:
        diff = new_total - old_total
        if diff > 0:
            message = "<b>מודעות חדשות ביד2!</b>\n\n"
            message += f"סה״כ עכשיו: {new_total} ({diff:+d} חדשים)\n"
        else:
            message = "<b>שינוי במספר המודעות</b>\n\n"
            message += f"סה״כ עכשיו: {new_total} ({diff:+d})\n"

        message += f'<a href="{self.url}">לצפייה בכל המודעות</a>\n'

        if new_listings and diff > 0:
            message += "\n<b>מודעות חדשות:</b>\n"
            for i, listing in enumerate(new_listings[:3], 1):
                if listing.get('title'):
                    message += f"\n{i}. {listing['title']}"
                if listing.get('price'):
                    message += f"\n   {listing['price']}"
                if listing.get('link'):
                    message += f'\n   <a href="{listing["link"]}">צפה במודעה</a>'
                message += "\n"

        message += f"\n{datetime.now().strftime('%H:%M - %d/%m/%Y')}"
        return message

    def run(self):
        print("=== Yad2 Monitor Started ===")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"URL: {self.url}")
        print(f"Last total: {self.data['last_total']}")

        try:
            current_total, raw_listings = self.get_total_and_listings()

            if current_total is None:
                print("Could not get total results count")
                self.send_telegram_message(
                    "<b>בעיה בניטור יד2</b>\n\n"
                    "לא הצלחתי לקרוא את מספר המודעות.\n"
                    "הניטור ימשיך בבדיקה הבאה.\n\n"
                    f'<a href="{self.url}">בדוק ידנית</a>'
                )
                return

            print(f"Current total: {current_total}")

            # First run - initialize
            if self.data['last_total'] == 0:
                print("First run - initializing")
                self.data['last_total'] = current_total
                self.data['history'].append({
                    'timestamp': datetime.now().isoformat(),
                    'total': current_total
                })
                self.save_data()
                self.send_telegram_message(
                    f"<b>ניטור יד2 הופעל</b>\n\n"
                    f"סה״כ מודעות כרגע: {current_total}\n"
                    f"בודק כל 20 דקות (06:00-00:00)\n"
                    f'<a href="{self.url}">קישור לחיפוש</a>\n\n'
                    "תקבל התראה כשיתווספו מודעות חדשות"
                )
                return

            diff = current_total - self.data['last_total']

            if diff != 0:
                print(f"Change detected: {diff:+d}")
                new_listings = []
                if diff > 0:
                    new_listings = [self._format_listing(item) for item in raw_listings[:5]]
                    new_listings = [l for l in new_listings if l]

                message = self.format_notification(self.data['last_total'], current_total, new_listings)
                self.send_telegram_message(message)

                self.data['last_total'] = current_total
                self.data['history'].append({
                    'timestamp': datetime.now().isoformat(),
                    'total': current_total,
                    'change': diff
                })
                if len(self.data['history']) > 100:
                    self.data['history'] = self.data['history'][-100:]
                self.save_data()
            else:
                print("No change in total listings")
                check_count = len(self.data.get('history', []))
                if check_count % 50 == 0 and check_count > 0:
                    self.send_telegram_message(
                        f"<b>סטטוס ניטור יד2</b>\n\n"
                        f"המערכת פעילה\n"
                        f"סה״כ מודעות: {current_total}\n"
                        f"בדיקות שבוצעו: {check_count}\n"
                        f"בדיקה אחרונה: {datetime.now().strftime('%H:%M')}"
                    )

        except Exception as e:
            print(f"Error in monitoring: {e}")
            self.send_telegram_message(
                f"<b>שגיאה בניטור</b>\n\n"
                f"Error: {str(e)[:200]}\n\n"
                "הניטור ימשיך בבדיקה הבאה."
            )
        finally:
            print("=== Monitor Completed ===")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', help='Test mode: print results to terminal, skip Telegram')
    parser.add_argument('--url', help='Yad2 search URL (overrides LISTING_URL env var)')
    args = parser.parse_args()

    config = {
        'url': args.url or os.environ.get('LISTING_URL'),
        'telegram_bot_token': os.environ.get('TELEGRAM_BOT_TOKEN', 'test'),
        'telegram_chat_id': os.environ.get('TELEGRAM_CHAT_ID', 'test'),
        'storage_file': os.environ.get('STORAGE_FILE', 'yad2_data.json'),
        'test_mode': args.test,
    }

    if not config['url']:
        print("Error: Provide --url or set LISTING_URL environment variable")
        sys.exit(1)

    if args.test:
        print("=== TEST MODE: Telegram notifications disabled ===")
        monitor = Yad2Monitor(config)
        total, raw_listings = monitor.get_total_and_listings()
        print(f"\n--- Results ---")
        print(f"Total listings found: {total}")
        print(f"Sample listings ({len(raw_listings[:5])}):")
        for item in raw_listings[:5]:
            print(json.dumps(monitor._format_listing(item), ensure_ascii=False, indent=2))
        return

    if 'yad2.co.il' not in config['url']:
        print("Warning: This scraper is optimized for Yad2.co.il")

    monitor = Yad2Monitor(config)
    monitor.run()


if __name__ == "__main__":
    main()
