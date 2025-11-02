import time
import random
import pandas as pd
from typing import List, Dict
from urllib.parse import quote
import logging
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.keys import Keys
from bs4 import BeautifulSoup
import re

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log', mode='w'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class GoogleMapsScraper:
    def __init__(self):
        self.ua = UserAgent()
        self.driver = self.setup_selenium_driver()

    def setup_selenium_driver(self):
        """Sets up the Selenium WebDriver."""
        chrome_options = Options()
        chrome_options.add_argument(f'--user-agent={self.ua.random}')
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            driver = webdriver.Chrome(service=webdriver.chrome.service.Service(ChromeDriverManager().install()), options=chrome_options)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            logger.error(f"Failed to initialize Selenium WebDriver: {e}")
            raise

    def handle_consent(self):
        """Handles the cookie consent button if it appears."""
        try:
            consent_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//button[.//span[text()="Accept all"]]'))
            )
            consent_button.click()
            logger.info("Clicked the 'Accept all' cookie consent button.")
            time.sleep(random.uniform(1, 2))
        except Exception:
            logger.info("Cookie consent button not found or not clickable.")

    def search_and_scrape(self, keyword: str, district: str, pages: int = 5):
        """Searches Google Maps and scrapes the business listings."""
        businesses = []
        query = f"{keyword} in {district}, Bangladesh"
        encoded_query = quote(query)
        url = f"https://www.google.com/maps/search/{encoded_query}"
        
        logger.info(f"Navigating to: {url}")
        self.driver.get(url)
        self.handle_consent()

        try:
            # Wait for the results to load
            WebDriverWait(self.driver, 20).until(
                EC.url_contains("/maps/search/")
            )
            
            # Robust scrolling to load all results
            scrollable_element = None
            try:
                scrollable_element = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@aria-label, 'Results for')]" ))
                )
            except Exception:
                try:
                    scrollable_element = WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="feed"]'))
                    )
                except Exception:
                    logger.warning("Could not find a specific scrollable element, falling back to body.")
                    scrollable_element = self.driver.find_element(By.TAG_NAME, 'body')

            last_height = self.driver.execute_script("return arguments[0].scrollHeight", scrollable_element)
            scroll_attempts = 0
            max_scroll_attempts = 10 # Limit to prevent infinite loops

            while True:
                self.driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", scrollable_element)
                time.sleep(random.uniform(3, 5)) # Give time for new content to load

                new_height = self.driver.execute_script("return arguments[0].scrollHeight", scrollable_element)
                if new_height == last_height:
                    scroll_attempts += 1
                    if scroll_attempts > max_scroll_attempts:
                        logger.info(f"Reached end of scrollable content or max attempts ({max_scroll_attempts}).")
                        break
                else:
                    scroll_attempts = 0 # Reset if new content loaded
                last_height = new_height

            # Parse the results
            page_source = self.driver.page_source
            businesses = self.parse_results(page_source, district, keyword)
        
        except Exception as e:
            import traceback
            logger.error(f"An error occurred during scraping for '{query}':\n{traceback.format_exc()}")
        
        return businesses

    def parse_results(self, page_source: str, district: str, keyword: str):
        """Parses the business data from the page source using BeautifulSoup."""
        soup = BeautifulSoup(page_source, 'html.parser')
        businesses = []
        
        listings = soup.find_all('div', {'jsaction': re.compile(r'.*mouseover:pane.*')})
        logger.info(f"Found {len(listings)} potential business listings.")

        for listing in listings:
            business_data = {}
            try:
                name_tag = listing.find('div', class_='qBF1Pd')
                business_data['name'] = name_tag.text if name_tag else 'N/A'

                phone_tag = listing.find('span', class_='UsdlK')
                business_data['phone'] = phone_tag.text if phone_tag else ''

                # Address is still tricky, but we can try to get it from the same container as the phone
                address_container = listing.find('div', class_='W4Efsd')
                if address_container:
                    address_parts = address_container.text.split('·')
                    if len(address_parts) > 1:
                        business_data['address'] = address_parts[-1].strip()
                    else:
                        business_data['address'] = address_container.text
                else:
                    business_data['address'] = ''

                business_data.update({
                    'district': district,
                    'category': keyword,
                })
                
                if business_data.get('name') != 'N/A':
                    businesses.append(business_data)

            except Exception as e:
                logger.warning(f"Could not parse a listing: {e}")
                continue
        
        return businesses

    def save_to_csv(self, businesses: List[Dict], filename: str):
        """Saves the scraped data to a CSV file."""
        if not businesses:
            logger.warning("No data to save.")
            return
        
        df = pd.DataFrame(businesses)
        expected_columns = ['name', 'phone', 'address', 'district', 'category']
        for col in expected_columns:
            if col not in df.columns:
                df[col] = ''
        
        df = df[expected_columns]
        df_unique = df.drop_duplicates(subset=['name', 'address'], keep='first')
        
        df_unique.to_csv(filename, index=False, encoding='utf-8')
        logger.info(f"✅ Saved {len(df_unique)} unique businesses to {filename}")

    def close(self):
        """Closes the Selenium WebDriver."""
        if self.driver:
            self.driver.quit()

def main():
    """Main execution function."""
    
    scraper = GoogleMapsScraper()
    
    try:
        keywords = ["motorcycle", "motorcycle showroom", "bike repair", "motorcycle service"]
        districts = [
            "Dhaka"
        ]
        
        all_businesses = []
        
        for district in districts:
            logger.info(f"--- Starting search in: {district} ---")
            for keyword in keywords:
                logger.info(f"   Searching for: '{keyword}'")
                
                businesses = scraper.search_and_scrape(keyword, district, pages=5) # Scrape up to 5 pages
                if businesses:
                    all_businesses.extend(businesses)
                    logger.info(f"   -> Found {len(businesses)} results for '{keyword}' in {district}.")
                else:
                    logger.warning(f"   -> No results found for '{keyword}' in {district}.")
                
                time.sleep(random.uniform(3, 7))
        
        if all_businesses:
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            filename = f"bangladesh_motorcycle_businesses_{timestamp}.csv"
            scraper.save_to_csv(all_businesses, filename)
        else:
            logger.warning("Scraping finished, but no businesses were found.")
            
    except Exception as e:
        logger.critical(f"A critical error occurred in the main function: {e}")
    
    finally:
        scraper.close()
        logger.info("Browser closed. Script finished.")

if __name__ == "__main__":
    main()