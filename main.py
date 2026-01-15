from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import re
import json
from typing import List, Dict
import uvicorn
import os

app = FastAPI(title="Micro Center Scraper API")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def setup_driver():
    """Setup Chrome driver with options"""
    chrome_options = Options()
    
    # Render-friendly settings
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--headless')  # Run in background
    chrome_options.add_argument('--window-size=1920,1080')
    
    # Anti-detection settings
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # User agent
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Additional arguments
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-popup-blocking')
    chrome_options.add_argument('--disable-notifications')
    
    # Set up Chrome driver
    service = Service(executable_path='/usr/local/bin/chromedriver')
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Execute CDP commands to prevent detection
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver

def extract_price(text):
    """Extract price from text"""
    if not text:
        return 0
    match = re.search(r'\$?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', str(text))
    return float(match.group(1).replace(',', '')) if match else 0

@app.get("/")
async def root():
    return {
        "message": "Micro Center Scraper API (Selenium)",
        "endpoints": {
            "scrape": "GET /scrape?q=search+query",
            "test": "GET /test?q=search+query",
            "health": "GET /health"
        }
    }

@app.get("/scrape")
async def scrape(q: str = Query(..., min_length=1)):
    """Scrape Micro Center using Selenium"""
    driver = None
    try:
        print(f"Starting scrape for: {q}")
        
        # Setup driver
        driver = setup_driver()
        
        # Build search URL
        search_url = f"https://www.microcenter.com/search/search_results.aspx?Ntt={q.replace(' ', '+')}"
        print(f"Fetching URL: {search_url}")
        
        # Navigate to page
        driver.get(search_url)
        
        # Wait for page to load (wait for search results)
        try:
            # Wait for any product to appear or for page to load
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".product_wrapper, .product, [data-product-id], .search-result"))
            )
            print("Page loaded successfully")
        except TimeoutException:
            # Try to get page source anyway
            print("Timeout waiting for products, but continuing...")
        
        # Add human-like delay
        time.sleep(2)
        
        # Scroll a bit to trigger lazy loading
        driver.execute_script("window.scrollTo(0, 500);")
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, 1000);")
        time.sleep(1)
        
        # Get page source
        page_source = driver.page_source
        
        # Save for debugging (optional)
        # with open('selenium_debug.html', 'w', encoding='utf-8') as f:
        #     f.write(page_source)
        
        # Check if blocked
        if "Just a moment" in page_source or "Enable JavaScript" in page_source:
            print("Still blocked by Cloudflare")
            return {
                "query": q,
                "count": 0,
                "results": [],
                "error": "Cloudflare block - Selenium detected",
                "page_title": driver.title
            }
        
        # Try multiple approaches to find products
        
        items = []
        
        # Approach 1: Use Selenium to find elements directly
        try:
            # Look for product containers
            product_elements = driver.find_elements(By.CSS_SELECTOR, ".product_wrapper, .product, .search-result, .result")
            print(f"Found {len(product_elements)} product elements via Selenium")
            
            for element in product_elements[:15]:  # Limit to 15
                try:
                    # Get element HTML
                    html = element.get_attribute('outerHTML')
                    
                    # Extract title
                    title = ""
                    try:
                        title_elem = element.find_element(By.CSS_SELECTOR, "h2, h3, .pDescription, .description")
                        title = title_elem.text.strip() if title_elem else ""
                    except:
                        pass
                    
                    # Extract price
                    price = 0
                    try:
                        price_elem = element.find_element(By.CSS_SELECTOR, ".price, .yourPrice, [data-price]")
                        price_text = price_elem.text.strip() if price_elem else ""
                        price = extract_price(price_text)
                    except:
                        # Try to find price in element text
                        full_text = element.text
                        price_match = re.search(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', full_text)
                        if price_match:
                            price = extract_price(price_match.group(0))
                    
                    # Skip if no price
                    if price < 10:
                        continue
                    
                    # Extract link
                    link = ""
                    try:
                        link_elem = element.find_element(By.CSS_SELECTOR, "a[href*='/product/']")
                        link = link_elem.get_attribute('href')
                    except:
                        pass
                    
                    # Check stock status
                    full_text = element.text.lower()
                    out_of_stock = any(phrase in full_text for phrase in [
                        'out of stock', 'out-of-stock', 'not available', 'unavailable',
                        'sold out', 'no longer available'
                    ])
                    
                    if out_of_stock:
                        continue
                    
                    # Skip in-store only
                    if 'in-store only' in full_text or 'store only' in full_text:
                        continue
                    
                    # Condition
                    condition = "New"
                    if 'refurbished' in full_text:
                        condition = "Refurbished"
                    elif 'open box' in full_text or 'open-box' in full_text:
                        condition = "Open Box"
                    
                    # Shipping
                    shipping = "In-store pickup"
                    if 'free shipping' in full_text:
                        shipping = "Free shipping"
                    elif 'shipping available' in full_text:
                        shipping = "Shipping available"
                    
                    if title and link and price > 0:
                        items.append({
                            'title': title[:200],
                            'price': price,
                            'link': link,
                            'image': '',  # Can extract if needed
                            'source': 'Micro Center',
                            'condition': condition,
                            'shipping': shipping,
                            'in_stock': True
                        })
                        
                except Exception as e:
                    print(f"Error parsing element: {e}")
                    continue
                    
        except Exception as e:
            print(f"Selenium element finding failed: {e}")
        
        # Approach 2: If no items found, try regex on page source
        if len(items) == 0:
            print("Trying regex approach on page source")
            # Look for product patterns in HTML
            import re
            from bs4 import BeautifulSoup
            
            soup = BeautifulSoup(page_source, 'html.parser')
            
            # Look for product listings
            for div in soup.find_all(['div', 'li', 'article']):
                text = div.get_text()
                if '$' in text and len(text) < 1000:
                    # Try to extract info
                    title_match = re.search(r'<h[2-4][^>]*>(.*?)</h[2-4]>', str(div), re.IGNORECASE)
                    title = title_match.group(1).strip() if title_match else ""
                    
                    price_match = re.search(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', text)
                    price = extract_price(price_match.group(0)) if price_match else 0
                    
                    link_match = re.search(r'href="([^"]*?/product/[^"]*?)"', str(div))
                    link = link_match.group(1) if link_match else ""
                    
                    if title and price > 10 and link:
                        full_link = f"https://www.microcenter.com{link}" if not link.startswith('http') else link
                        
                        items.append({
                            'title': title[:200],
                            'price': price,
                            'link': full_link,
                            'source': 'Micro Center',
                            'condition': 'New',
                            'shipping': 'Check website'
                        })
        
        # Sort by price
        items.sort(key=lambda x: x['price'])
        
        print(f"Found {len(items)} valid products")
        
        return {
            "query": q,
            "count": len(items),
            "results": items[:10],
            "page_title": driver.title,
            "method": "selenium"
        }
        
    except Exception as e:
        print(f"Scraping error: {e}")
        return {
            "query": q,
            "count": 0,
            "results": [],
            "error": str(e)
        }
    finally:
        if driver:
            driver.quit()

@app.get("/test")
async def test(q: str = "rtx 4090"):
    """Test endpoint to see what Selenium can see"""
    driver = None
    try:
        driver = setup_driver()
        search_url = f"https://www.microcenter.com/search/search_results.aspx?Ntt={q.replace(' ', '+')}"
        
        driver.get(search_url)
        time.sleep(3)
        
        # Take screenshot for debugging
        screenshot_path = "/tmp/screenshot.png"
        driver.save_screenshot(screenshot_path)
        
        # Get page info
        page_source = driver.page_source
        
        # Check for common elements
        elements_found = {}
        selectors_to_check = [
            '.product_wrapper', '.product', '.search-result',
            '.result', '[data-product-id]', '.price'
        ]
        
        for selector in selectors_to_check:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                elements_found[selector] = len(elements)
            except:
                elements_found[selector] = 0
        
        return {
            "status": "success",
            "page_title": driver.title,
            "url": driver.current_url,
            "elements_found": elements_found,
            "page_size": len(page_source),
            "contains_cloudflare": "Just a moment" in page_source or "Enable JavaScript" in page_source,
            "contains_products": "product" in page_source.lower(),
            "sample_text": page_source[:500]
        }
        
    except Exception as e:
        return {"error": str(e)}
    finally:
        if driver:
            driver.quit()

@app.get("/health")
async def health():
    return {"status": "healthy", "method": "selenium"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
