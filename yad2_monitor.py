#!/usr/bin/env python3
"""
Yad2 Monitor - Detects new listings by calling the gw.yad2.co.il JSON API directly.
Tracks listing tokens; notifies on new ones via Telegram.
"""

import os
import sys
import json
import requests
from datetime import datetime
from typing import Dict, List, Optional


API_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Origin': 'https://www.yad2.co.il',
    'Referer': 'https://www.yad2.co.il/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
}


class Yad2Monitor:
    def __init__(self, config: Dict):
        self.api_url = config['api_url']
        self.listing_url = config.get('listing_url', 'https://www.yad2.co.il')
        self.telegram_bot_token = config['telegram_bot_token']
        self.telegram_chat_id = config['telegram_chat_id']
        self.storage_file = config.get('storage_file', 'yad2_data.json')
        self.data = self.load_data()

    def load_data(self) -> Dict:
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading data: {e}")
        return {
            'seen_listing_ids': [],
            'last_check': None,
        }

    def save_data(self):
        try:
            self.data['last_check'] = datetime.now().isoformat()
            with open(self.storage_file, 'w') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving data: {e}")

    def fetch_markers(self) -> Optional[List[Dict]]:
        try:
            print(f"Calling API: {self.api_url}")
            resp = requests.get(self.api_url, headers=API_HEADERS, timeout=15)
            print(f"Status: {resp.status_code}")
            resp.raise_for_status()
            markers = resp.json()['data']['markers']
            print(f"Got {len(markers)} listings from API")
            return markers
        except Exception as e:
            print(f"Error fetching from API: {e}")
            return None

    def _format_listing(self, marker: Dict) -> str:
        addr = marker.get('address', {})
        city = addr.get('city', {}).get('text', '')
        neighborhood = addr.get('neighborhood', {}).get('text', '')
        street = addr.get('street', {}).get('text', '')
        house = addr.get('house', {}).get('number', '')
        floor = addr.get('house', {}).get('floor', '')

        details = marker.get('additionalDetails', {})
        rooms = details.get('roomsCount', '')
        sqm = details.get('squareMeter', '')
        prop_type = details.get('property', {}).get('text', '')

        price = marker.get('price', 0)
        token = marker.get('token', '')

        lines = []
        location_parts = [p for p in [street, str(house) if house else '', city] if p]
        if neighborhood:
            location_parts.append(f"({neighborhood})")
        lines.append(' '.join(location_parts))

        details_parts = []
        if prop_type:
            details_parts.append(prop_type)
        if rooms:
            details_parts.append(f"{rooms} חדרים")
        if sqm:
            details_parts.append(f"{sqm} מ״ר")
        if floor != '':
            details_parts.append(f"קומה {floor}")
        if details_parts:
            lines.append(' | '.join(details_parts))

        if price:
            lines.append(f"₪{price:,}/חודש")
        else:
            lines.append("מחיר לא צוין")

        if token:
            lines.append(f'<a href="https://www.yad2.co.il/realestate/rent/item/{token}">לצפייה במודעה</a>')

        return '\n'.join(lines)

    def send_telegram_message(self, message: str) -> bool:
        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            payload = {
                'chat_id': self.telegram_chat_id,
                'text': message,
                'parse_mode': 'HTML',
                'disable_web_page_preview': False,
            }
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            print("Telegram notification sent")
            return True
        except Exception as e:
            print(f"Error sending Telegram: {e}")
            return False

    def run(self):
        print("=== Yad2 Monitor Started ===")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        try:
            markers = self.fetch_markers()

            if markers is None:
                self.send_telegram_message(
                    "<b>בעיה בניטור יד2</b>\n\n"
                    "לא הצלחתי לקרוא את המודעות מה-API.\n"
                    "הניטור ימשיך בבדיקה הבאה.\n\n"
                    f'<a href="{self.listing_url}">בדוק ידנית</a>'
                )
                return

            current_tokens = {m['token'] for m in markers if m.get('token')}
            seen_tokens = set(self.data.get('seen_listing_ids', []))

            # First run
            if not seen_tokens:
                print(f"First run — storing {len(current_tokens)} listings")
                self.data['seen_listing_ids'] = list(current_tokens)
                self.save_data()
                self.send_telegram_message(
                    f"<b>ניטור יד2 הופעל</b>\n\n"
                    f"נמצאו {len(current_tokens)} מודעות כרגע\n"
                    f"בודק כל 20 דקות (06:00-00:00)\n"
                    f'<a href="{self.listing_url}">קישור לחיפוש</a>\n\n'
                    "תקבל התראה כשיתווספו מודעות חדשות"
                )
                return

            new_tokens = current_tokens - seen_tokens
            print(f"Current: {len(current_tokens)} | Seen: {len(seen_tokens)} | New: {len(new_tokens)}")

            if new_tokens:
                new_markers = [m for m in markers if m.get('token') in new_tokens]
                print(f"New listings detected: {len(new_markers)}")

                message = f"<b>🏠 {len(new_markers)} מודעות חדשות ביד2!</b>\n"
                message += f'<a href="{self.listing_url}">לצפייה בכל המודעות</a>\n'

                for i, marker in enumerate(new_markers[:5], 1):
                    message += f"\n<b>מודעה {i}:</b>\n"
                    message += self._format_listing(marker)
                    message += "\n"

                if len(new_markers) > 5:
                    message += f"\n...ועוד {len(new_markers) - 5} מודעות נוספות"

                message += f"\n\n{datetime.now().strftime('%H:%M - %d/%m/%Y')}"
                self.send_telegram_message(message)

                # Add new tokens to seen set
                self.data['seen_listing_ids'] = list(seen_tokens | current_tokens)
                self.save_data()
            else:
                print("No new listings")

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
    parser.add_argument('--test', action='store_true', help='Test mode: print results, skip Telegram')
    parser.add_argument('--api-url', help='gw.yad2.co.il API URL (overrides API_URL env var)')
    args = parser.parse_args()

    config = {
        'api_url': args.api_url or os.environ.get('API_URL'),
        'listing_url': os.environ.get('LISTING_URL', 'https://www.yad2.co.il'),
        'telegram_bot_token': os.environ.get('TELEGRAM_BOT_TOKEN', 'test'),
        'telegram_chat_id': os.environ.get('TELEGRAM_CHAT_ID', 'test'),
        'storage_file': os.environ.get('STORAGE_FILE', 'yad2_data.json'),
    }

    if not config['api_url']:
        print("Error: Provide --api-url or set API_URL environment variable")
        sys.exit(1)

    if args.test:
        print("=== TEST MODE ===")
        monitor = Yad2Monitor(config)
        markers = monitor.fetch_markers()
        if markers:
            print(f"\nTotal listings: {len(markers)}")
            print("\nSample listings:")
            for m in markers[:3]:
                print("---")
                print(monitor._format_listing(m))
        return

    monitor = Yad2Monitor(config)
    monitor.run()


if __name__ == "__main__":
    main()
