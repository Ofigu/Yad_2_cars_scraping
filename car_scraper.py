#!/usr/bin/env python3
"""
Car Market Scraper with Telegram Notifications
Monitors a car listing website for new vehicles and sends notifications via Telegram
"""

import os
import sys
import json
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Dict, List, Set
import time

class CarScraper:
    def __init__(self, config: Dict):
        self.url = config['url']
        self.telegram_bot_token = config['telegram_bot_token']
        self.telegram_chat_id = config['telegram_chat_id']
        self.storage_file = config.get('storage_file', 'seen_cars.json')
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        self.seen_cars = self.load_seen_cars()
        
    def load_seen_cars(self) -> Set[str]:
        """Load previously seen car IDs from storage"""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, 'r') as f:
                    data = json.load(f)
                    return set(data.get('seen_ids', []))
            except Exception as e:
                print(f"Error loading storage: {e}")
        return set()
    
    def save_seen_cars(self):
        """Save seen car IDs to storage"""
        try:
            with open(self.storage_file, 'w') as f:
                json.dump({
                    'seen_ids': list(self.seen_cars),
                    'last_updated': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            print(f"Error saving storage: {e}")
    
    def scrape_cars(self) -> List[Dict]:
        """Scrape car listings from the website"""
        cars = []
        
        try:
            response = requests.get(self.url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # IMPORTANT: Customize these selectors based on your target website
            # These are common patterns - you'll need to inspect the actual site
            
            # Try different common listing selectors
            listing_selectors = [
                'article[data-testid*="listing"]',
                'div[class*="listing-item"]',
                'div[class*="car-item"]',
                'div[class*="vehicle-card"]',
                'div[class*="result-item"]',
                'div[class*="ad-listing"]',
                'li[class*="listing"]',
                'div[class*="offer-item"]',
                'article[class*="car"]',
                'div[data-qa*="listing"]'
            ]
            
            listings = []
            for selector in listing_selectors:
                listings = soup.select(selector)
                if listings:
                    print(f"Found {len(listings)} listings using selector: {selector}")
                    break
            
            # If no specific selector worked, try generic approach
            if not listings:
                # Look for repeated structures that might be listings
                possible_containers = soup.find_all('div', class_=True)
                for container in possible_containers:
                    if any(keyword in str(container.get('class', [])).lower() 
                           for keyword in ['listing', 'item', 'card', 'result', 'offer', 'vehicle', 'car']):
                        listings.append(container)
            
            for listing in listings:
                car_data = self.extract_car_data(listing)
                if car_data and car_data['id']:
                    cars.append(car_data)
                    
        except requests.RequestException as e:
            print(f"Error fetching URL: {e}")
        except Exception as e:
            print(f"Error scraping: {e}")
        
        return cars
    
    def extract_car_data(self, listing_element) -> Dict:
        """Extract car information from a listing element"""
        # Generate unique ID from the listing content
        text_content = listing_element.get_text(strip=True)
        unique_id = hashlib.md5(text_content.encode()).hexdigest()
        
        # Try to extract common fields (customize based on your site)
        car_data = {
            'id': unique_id,
            'raw_text': text_content[:500],  # Store first 500 chars for reference
        }
        
        # Try to extract title
        title_selectors = ['h2', 'h3', 'h4', 'a[class*="title"]', 'a[class*="name"]', '.title', '.name']
        for selector in title_selectors:
            title_elem = listing_element.select_one(selector)
            if title_elem:
                car_data['title'] = title_elem.get_text(strip=True)
                break
        
        # Try to extract price
        price_selectors = ['[class*="price"]', '[class*="cost"]', '[class*="amount"]', 'span[data-testid*="price"]']
        for selector in price_selectors:
            price_elem = listing_element.select_one(selector)
            if price_elem:
                car_data['price'] = price_elem.get_text(strip=True)
                break
        
        # Try to extract link
        link_elem = listing_element.find('a', href=True)
        if link_elem:
            car_data['link'] = link_elem['href']
            # Make absolute URL if relative
            if car_data['link'].startswith('/'):
                from urllib.parse import urljoin
                car_data['link'] = urljoin(self.url, car_data['link'])
        
        # Try to extract year
        year_patterns = ['20[0-2][0-9]', '19[5-9][0-9]']
        import re
        for pattern in year_patterns:
            year_match = re.search(pattern, text_content)
            if year_match:
                car_data['year'] = year_match.group()
                break
        
        # Try to extract mileage/km
        km_pattern = r'(\d{1,3}[,.\s]?\d{0,3})\s*[kK][mM]'
        km_match = re.search(km_pattern, text_content)
        if km_match:
            car_data['mileage'] = km_match.group()
        
        return car_data
    
    def send_telegram_message(self, message: str):
        """Send notification via Telegram"""
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
            print(f"Telegram notification sent successfully")
            return True
            
        except Exception as e:
            print(f"Error sending Telegram message: {e}")
            return False
    
    def format_car_message(self, car: Dict) -> str:
        """Format car data for Telegram message"""
        message_parts = ["🚗 <b>New Car Listed!</b>\n"]
        
        if car.get('title'):
            message_parts.append(f"📋 <b>{car['title']}</b>")
        
        if car.get('price'):
            message_parts.append(f"💰 Price: {car['price']}")
        
        if car.get('year'):
            message_parts.append(f"📅 Year: {car['year']}")
        
        if car.get('mileage'):
            message_parts.append(f"🛣️ Mileage: {car['mileage']}")
        
        if car.get('link'):
            message_parts.append(f"\n🔗 <a href=\"{car['link']}\">View Listing</a>")
        
        # Add timestamp
        message_parts.append(f"\n⏰ Found at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return "\n".join(message_parts)
    
    def run(self):
        """Main execution method"""
        print(f"Starting car scraper at {datetime.now()}")
        print(f"Monitoring URL: {self.url}")
        print(f"Previously seen cars: {len(self.seen_cars)}")
        
        # Scrape current listings
        cars = self.scrape_cars()
        print(f"Found {len(cars)} total listings")
        
        # Find new cars
        new_cars = []
        for car in cars:
            if car['id'] not in self.seen_cars:
                new_cars.append(car)
                self.seen_cars.add(car['id'])
        
        print(f"Found {len(new_cars)} new cars")
        
        # Send notifications for new cars
        if new_cars:
            # Send individual notifications for each car (max 5 to avoid spam)
            for car in new_cars[:5]:
                message = self.format_car_message(car)
                self.send_telegram_message(message)
                time.sleep(1)  # Avoid rate limiting
            
            # If more than 5 new cars, send summary
            if len(new_cars) > 5:
                summary = f"📊 Found {len(new_cars)} new cars total! Check the website for all listings.\n🔗 {self.url}"
                self.send_telegram_message(summary)
            
            # Save updated seen cars
            self.save_seen_cars()
        else:
            print("No new cars found")
        
        # First run notification
        if len(self.seen_cars) <= len(cars):
            summary_msg = f"✅ Car monitor initialized!\n📊 Tracking {len(cars)} current listings\n🔗 Monitoring: {self.url}"
            self.send_telegram_message(summary_msg)
        
        print(f"Scraping completed at {datetime.now()}")
        return len(new_cars)

def main():
    """Main entry point"""
    # Get configuration from environment variables
    config = {
        'url': os.environ.get('CAR_LISTING_URL'),
        'telegram_bot_token': os.environ.get('TELEGRAM_BOT_TOKEN'),
        'telegram_chat_id': os.environ.get('TELEGRAM_CHAT_ID'),
        'storage_file': os.environ.get('STORAGE_FILE', 'seen_cars.json')
    }
    
    # Validate configuration
    if not config['url']:
        print("Error: CAR_LISTING_URL environment variable not set")
        sys.exit(1)
    
    if not config['telegram_bot_token']:
        print("Error: TELEGRAM_BOT_TOKEN environment variable not set")
        sys.exit(1)
    
    if not config['telegram_chat_id']:
        print("Error: TELEGRAM_CHAT_ID environment variable not set")
        sys.exit(1)
    
    # Run scraper
    scraper = CarScraper(config)
    new_cars_count = scraper.run()
    
    # Exit with status code indicating if new cars were found
    sys.exit(0 if new_cars_count >= 0 else 1)

if __name__ == "__main__":
    main()