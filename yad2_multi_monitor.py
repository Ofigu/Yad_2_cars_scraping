#!/usr/bin/env python3
"""
Yad2 Multi-URL Car Monitor
Monitors multiple car searches in a single job
"""

import os
import sys
import json
import requests
import time
import re
from datetime import datetime
from typing import Dict, List, Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

class Yad2MultiMonitor:
    def __init__(self, config: Dict):
        self.urls = self.parse_urls(config['urls'])
        self.telegram_bot_token = config['telegram_bot_token']
        self.telegram_chat_id = config['telegram_chat_id']
        self.storage_file = config.get('storage_file', 'yad2_multi_data.json')
        self.driver = None
        self.data = self.load_data()
        
    def parse_urls(self, urls_string: str) -> List[Dict]:
        """Parse URLs from environment variable"""
        urls_list = []
        
        # URLs can be separated by semicolon or newline
        # Format: "URL1;URL2" or "NAME1|URL1;NAME2|URL2"
        url_entries = urls_string.replace('\n', ';').split(';')
        
        for entry in url_entries:
            entry = entry.strip()
            if not entry:
                continue
                
            # Check if name is provided (NAME|URL format)
            if '|' in entry:
                name, url = entry.split('|', 1)
                urls_list.append({
                    'name': name.strip(),
                    'url': url.strip()
                })
            else:
                # Auto-generate name from URL parameters
                url = entry
                name = self.generate_name_from_url(url)
                urls_list.append({
                    'name': name,
                    'url': url
                })
        
        return urls_list
    
    def generate_name_from_url(self, url: str) -> str:
        """Generate a descriptive name from URL parameters"""
        # Try to extract meaningful parameters from Yad2 URL
        name_parts = []
        
        # Extract manufacturer
        if 'manufacturer=' in url:
            manufacturer_match = re.search(r'manufacturer=(\d+)', url)
            if manufacturer_match:
                # Common manufacturer codes (expand as needed)
                manufacturers = {
                    '40': 'מאזדה',
                    '21': 'טויוטה',
                    '28': 'יונדאי',
                    '32': 'קיה',
                    '55': 'סקודה',
                    '18': 'ניסאן'
                }
                code = manufacturer_match.group(1)
                name_parts.append(manufacturers.get(code, f'יצרן {code}'))
        
        # Extract price range
        if 'price=' in url:
            price_match = re.search(r'price=([\d-]+)', url)
            if price_match:
                name_parts.append(f'מחיר {price_match.group(1)}')
        
        # Extract year
        if 'year=' in url:
            year_match = re.search(r'year=([\d-]+)', url)
            if year_match:
                name_parts.append(f'שנה {year_match.group(1)}')
        
        return ' '.join(name_parts) if name_parts else 'חיפוש כללי'
    
    def load_data(self) -> Dict:
        """Load previous monitoring data"""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading data: {e}")
        
        return {'searches': {}}
    
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
        if self.driver:
            return
            
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--lang=he-IL')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        # Disable images for faster loading
        prefs = {
            "profile.managed_default_content_settings.images": 2,
            "profile.default_content_setting_values.notifications": 2
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.implicitly_wait(10)
    
    def close_driver(self):
        """Clean up driver"""
        if self.driver:
            self.driver.quit()
            self.driver = None
    
    def get_total_for_url(self, url: str) -> Optional[int]:
        """Get total results count for a specific URL"""
        try:
            print(f"  Loading: {url[:80]}...")
            self.driver.get(url)
            
            # Wait for results to load
            wait = WebDriverWait(self.driver, 20)
            
            # Try multiple selectors for total count
            total_selectors = [
                "span.results-feed_sortAndTotalBox__lFFyS",
                "span[class*='sortAndTotalBox']",
                "span[class*='totalResults']",
                "//span[contains(text(),'נמצאו')]",
                "//span[contains(text(),'מודעות')]",
            ]
            
            total_text = None
            for selector in total_selectors:
                try:
                    if selector.startswith('//'):
                        element = wait.until(EC.presence_of_element_located((By.XPATH, selector)))
                    else:
                        element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
                    
                    total_text = element.text
                    break
                except:
                    continue
            
            if total_text:
                numbers = re.findall(r'\d+', total_text)
                if numbers:
                    return int(numbers[0])
            
            return None
            
        except Exception as e:
            print(f"  Error: {e}")
            return None
    
    def send_telegram_message(self, message: str) -> bool:
        """Send Telegram notification"""
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
            return True
            
        except Exception as e:
            print(f"Error sending Telegram: {e}")
            return False
    
    def format_changes_message(self, all_changes: List[Dict]) -> str:
        """Format a message for all changes"""
        if not all_changes:
            return None
        
        # Count total new and removed
        total_new = sum(c['diff'] for c in all_changes if c['diff'] > 0)
        total_removed = sum(c['diff'] for c in all_changes if c['diff'] < 0)
        
        message = "🚗 <b>עדכון מיד2</b>\n\n"
        
        # Summary
        if total_new > 0:
            message += f"✅ סה״כ חדשים: +{total_new}\n"
        if total_removed < 0:
            message += f"📉 סה״כ הוסרו: {total_removed}\n"
        
        message += "\n<b>פירוט לפי חיפוש:</b>\n"
        
        # Details for each search
        for change in all_changes:
            message += f"\n📍 <b>{change['name']}</b>\n"
            message += f"   כעת: {change['current']} "
            
            if change['diff'] > 0:
                message += f"(+{change['diff']} חדשים)\n"
            else:
                message += f"({change['diff']})\n"
            
            message += f"   <a href=\"{change['url']}\">לצפייה →</a>\n"
        
        message += f"\n⏰ {datetime.now().strftime('%H:%M - %d/%m')}"
        
        return message
    
    def run(self):
        """Main monitoring logic for all URLs"""
        print(f"=== Yad2 Multi-Monitor Started ===")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Monitoring {len(self.urls)} searches")
        
        try:
            self.setup_driver()
            
            all_changes = []
            first_run_searches = []
            errors = []
            
            # Check each URL
            for url_config in self.urls:
                name = url_config['name']
                url = url_config['url']
                search_key = url[:100]  # Use first 100 chars as key
                
                print(f"\nChecking: {name}")
                
                # Get current total
                current_total = self.get_total_for_url(url)
                
                if current_total is None:
                    errors.append(name)
                    print(f"  ❌ Could not get total")
                    continue
                
                print(f"  Total: {current_total}")
                
                # Initialize search data if first time
                if search_key not in self.data['searches']:
                    self.data['searches'][search_key] = {
                        'name': name,
                        'url': url,
                        'last_total': current_total,
                        'history': []
                    }
                    first_run_searches.append({
                        'name': name,
                        'total': current_total,
                        'url': url
                    })
                    print(f"  ✅ Initialized with {current_total} listings")
                else:
                    # Check for changes
                    last_total = self.data['searches'][search_key]['last_total']
                    diff = current_total - last_total
                    
                    if diff != 0:
                        print(f"  🔄 Change: {diff:+d}")
                        all_changes.append({
                            'name': name,
                            'url': url,
                            'previous': last_total,
                            'current': current_total,
                            'diff': diff
                        })
                        
                        # Update data
                        self.data['searches'][search_key]['last_total'] = current_total
                        self.data['searches'][search_key]['history'].append({
                            'time': datetime.now().isoformat(),
                            'total': current_total,
                            'change': diff
                        })
                        
                        # Keep only last 50 history entries per search
                        if len(self.data['searches'][search_key]['history']) > 50:
                            self.data['searches'][search_key]['history'] = \
                                self.data['searches'][search_key]['history'][-50:]
                    else:
                        print(f"  ✓ No change ({current_total})")
                
                # Small delay between checks
                time.sleep(2)
            
            # Save data
            self.save_data()
            
            # Send notifications
            if first_run_searches:
                # First run notification
                message = "✅ <b>ניטור מרובה הופעל!</b>\n\n"
                message += f"📊 עוקב אחר {len(first_run_searches)} חיפושים:\n\n"
                
                for search in first_run_searches:
                    message += f"• <b>{search['name']}</b>\n"
                    message += f"  סה״כ: {search['total']} רכבים\n"
                    message += f"  <a href=\"{search['url']}\">קישור</a>\n\n"
                
                message += "⏱️ בודק כל 20 דקות\n"
                message += "🔔 תקבל התראה על שינויים"
                
                self.send_telegram_message(message)
            
            if all_changes:
                # Send changes notification
                message = self.format_changes_message(all_changes)
                if message:
                    self.send_telegram_message(message)
            
            if errors:
                # Send error notification
                error_msg = f"⚠️ <b>בעיה בחלק מהחיפושים</b>\n\n"
                error_msg += "לא הצלחתי לבדוק:\n"
                for name in errors:
                    error_msg += f"• {name}\n"
                error_msg += "\nאנסה שוב בבדיקה הבאה."
                
                self.send_telegram_message(error_msg)
            
            # Status update every 50 checks
            total_checks = sum(
                len(s.get('history', [])) 
                for s in self.data['searches'].values()
            )
            
            if total_checks > 0 and total_checks % 50 == 0:
                status_msg = "📊 <b>סטטוס ניטור</b>\n\n"
                status_msg += f"✅ המערכת פעילה\n"
                status_msg += f"🔍 {len(self.urls)} חיפושים במעקב\n"
                status_msg += f"🔄 {total_checks} בדיקות בוצעו\n"
                
                self.send_telegram_message(status_msg)
            
        except Exception as e:
            print(f"Error in monitoring: {e}")
            self.send_telegram_message(
                f"❌ <b>שגיאה כללית</b>\n\n{str(e)[:200]}"
            )
        finally:
            self.close_driver()
            print("\n=== Monitor Completed ===")

def main():
    """Main entry point"""
    # Get URLs - can be multiple separated by semicolon
    urls_string = os.environ.get('CAR_LISTING_URLS') or os.environ.get('CAR_LISTING_URL', '')
    
    if not urls_string:
        print("Error: No URLs provided")
        print("Set CAR_LISTING_URLS with semicolon-separated URLs")
        print("Format: URL1;URL2 or NAME1|URL1;NAME2|URL2")
        sys.exit(1)
    
    config = {
        'urls': urls_string,
        'telegram_bot_token': os.environ.get('TELEGRAM_BOT_TOKEN'),
        'telegram_chat_id': os.environ.get('TELEGRAM_CHAT_ID'),
        'storage_file': os.environ.get('STORAGE_FILE', 'yad2_multi_data.json')
    }
    
    # Validate
    if not all([config['telegram_bot_token'], config['telegram_chat_id']]):
        print("Error: Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        sys.exit(1)
    
    monitor = Yad2MultiMonitor(config)
    monitor.run()

if __name__ == "__main__":
    main()