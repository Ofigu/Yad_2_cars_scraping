#!/usr/bin/env python3
"""
Smart Auto-Deal Monitor - Monitors all Skoda but checks for Fabia specifically
"""

import os
import sys
import json
import requests
import time
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

class SmartAutoDealMonitor:
    def __init__(self, config: Dict):
        self.url = config.get('url')
        self.target_model = config.get('target_model', 'פאביה')
        self.telegram_bot_token = config.get('telegram_bot_token')
        self.telegram_chat_id = config.get('telegram_chat_id')
        self.storage_file = config.get('storage_file', 'autodeal_data.json')
        self.driver = None
        self.data = self.load_data()
        
    def load_data(self) -> Dict:
        """Load previous monitoring data"""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading data: {e}")
        
        return {
            'last_total': 0,
            'last_fabia_count': 0,
            'last_fabia_ids': [],
            'last_check': None,
            'history': []
        }
    
    def save_data(self):
        """Save monitoring data"""
        try:
            self.data['last_check'] = datetime.now().isoformat()
            with open(self.storage_file, 'w') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving data: {e}")
    
    def setup_driver(self):
        """Setup Selenium driver"""
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--lang=he-IL')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.implicitly_wait(10)
    
    def close_driver(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def send_telegram_message(self, message: str) -> bool:
        """Send Telegram notification"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("Telegram credentials missing, skipping notification")
            return False
            
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
    
    def get_total_count(self) -> Optional[int]:
        try:
            h1_elements = self.driver.find_elements(By.TAG_NAME, "h1")
            for h1 in h1_elements:
                text = h1.text.strip()
                if 'נמצאו' in text and any(char.isdigit() for char in text):
                    numbers = re.findall(r'\d+', text)
                    if numbers:
                        return int(numbers[0])
        except Exception as e:
            print(f"Error getting total count: {e}")
        return None
    
    def extract_car_listings(self) -> List[Dict]:
        listings = []
        try:
            listing_selectors = [
                "div.sc-kGhOqx.jdfRse",
                "div[class*='sc-kGhOqx']",
                "div[junction='true'][depth='2']",
                "article[class*='car']",
                "div[class*='product-card']"
            ]
            
            elements = []
            for selector in listing_selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    break
            
            if not elements:
                all_divs = self.driver.find_elements(By.TAG_NAME, "div")
                for div in all_divs:
                    text = div.text.strip()
                    if text and ('ק״מ' in text or '₪' in text) and len(text) < 500:
                        elements.append(div)
            
            for element in elements[:50]:
                try:
                    listing_text = element.text.strip()
                    if not listing_text or len(listing_text) < 10: continue
                    
                    car_info = {
                        'full_text': listing_text[:500],
                        'model': None,
                        'price': None,
                        'year': None,
                        'km': None,
                        'is_fabia': False
                    }
                    
                    if self.target_model in listing_text:
                        car_info['is_fabia'] = True
                    
                    # Basic Extraction logic
                    models = ['פאביה', 'אוקטביה', 'קודיאק', 'סופרב', 'קמיק', 'סקאלה', 'אניאק']
                    for model in models:
                        if model in listing_text:
                            car_info['model'] = model
                            break
                            
                    price_match = re.search(r'₪([\d,]+)', listing_text)
                    if price_match: car_info['price'] = price_match.group(1)
                    
                    year_match = re.search(r'20\d{2}', listing_text)
                    if year_match: car_info['year'] = year_match.group()
                    
                    km_match = re.search(r'([\d,]+)\s*ק״מ', listing_text)
                    if km_match: car_info['km'] = km_match.group(1)
                    
                    car_info['id'] = f"{car_info['model']}_{car_info['year']}_{car_info['price']}"
                    listings.append(car_info)
                except: continue
        except Exception as e:
            print(f"Error extracting listings: {e}")
        return listings

    def format_notification(self, new_fabias: List[Dict]) -> str:
        msg = f"🚗 <b>רכבי {self.target_model} חדשים ב-AutoDeal!</b>\n\n"
        for car in new_fabias:
             msg += f"📌 <b>{car.get('year', 'שנה?')}</b> | {car.get('km', 'ק״מ?')} | ₪{car.get('price', 'מחיר?')}\n"
        msg += f"\n🔗 <a href=\"{self.url}\">לצפייה בתוצאות</a>"
        return msg

    def run(self):
        print(f"=== Auto-Deal Monitor Started ===")
        try:
            self.setup_driver()
            self.driver.get(self.url)
            time.sleep(5)
            
            # 1. Get total count
            total_count = self.get_total_count()
            print(f"Total Skoda vehicles: {total_count}")
            
            # 2. Extract listings
            listings = self.extract_car_listings()
            
            # 3. Filter for target model (Fabia)
            fabia_listings = [l for l in listings if l['is_fabia'] or l['model'] == self.target_model]
            fabia_count = len(fabia_listings)
            print(f"Found {fabia_count} {self.target_model} vehicles")

            # 4. Compare with history
            current_fabia_ids = [f['id'] for f in fabia_listings]
            previous_fabia_ids = self.data.get('last_fabia_ids', [])
            
            new_ids = set(current_fabia_ids) - set(previous_fabia_ids)
            
            # 5. Handle Logic
            if self.data['last_fabia_count'] == 0 and len(self.data['history']) == 0:
                print("First run - initializing data")
                # ADDED LINK HERE:
                self.send_telegram_message(
                    f"✅ <b>ניטור AutoDeal הופעל!</b>\n"
                    f"נמצאו {fabia_count} רכבי {self.target_model}.\n"
                    f"🔗 <a href=\"{self.url}\">לצפייה בתוצאות</a>"
                )
            
            elif new_ids:
                print(f"Found {len(new_ids)} new listings!")
                new_fabias = [f for f in fabia_listings if f['id'] in new_ids]
                self.send_telegram_message(self.format_notification(new_fabias))
            else:
                print("No new specific listings found.")
                
            # 6. Save Data
            self.data['last_total'] = total_count
            self.data['last_fabia_count'] = fabia_count
            self.data['last_fabia_ids'] = current_fabia_ids
            self.data['history'].append({
                'timestamp': datetime.now().isoformat(),
                'total': total_count,
                'fabias': fabia_count
            })
            if len(self.data['history']) > 100:
                self.data['history'] = self.data['history'][-100:]
            self.save_data()

        except Exception as e:
            print(f"Error: {e}")
            self.send_telegram_message(f"❌ <b>Error in AutoDeal Monitor</b>\n{str(e)[:100]}")
        finally:
            self.close_driver()

def main():
    config = {
        'url': os.environ.get('AUTODEAL_LISTING_URL'),
        'telegram_bot_token': os.environ.get('TELEGRAM_BOT_TOKEN'),
        'telegram_chat_id': os.environ.get('TELEGRAM_CHAT_ID'),
        'storage_file': 'autodeal_data.json'
    }
    
    if not all([config['url'], config['telegram_bot_token'], config['telegram_chat_id']]):
        print("Error: Missing environment variables for AutoDeal monitor")
        # Don't exit(1) so we don't crash the whole GitHub workflow if just this script fails
        return 

    monitor = SmartAutoDealMonitor(config)
    monitor.run()

if __name__ == "__main__":
    main()