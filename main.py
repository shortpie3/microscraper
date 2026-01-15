from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import os

app = FastAPI(title="Micro Center Scraper API")
app.add_middleware(CORSMiddleware, allow_origins=["*"])

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    
    # CRITICAL: Set a real window size and User-Agent to prevent infinite loading
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Tells Chrome where the binary is located in your Docker container
    chrome_options.binary_location = "/usr/bin/google-chrome"
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

@app.get("/scrape")
async def scrape(q: str = Query(..., min_length=1)):
    driver = None
    try:
        driver = setup_driver()
        url = f"https://www.microcenter.com/search/search_results.aspx?Ntt={q.replace(' ', '+')}"
        
        # Set a page load timeout so it doesn't hang forever
        driver.set_page_load_timeout(30)
        driver.get(url)

        # Give the page 7 seconds to execute JavaScript and hide the "Just a moment" screen
        time.sleep(7)

        if "Just a moment" in driver.page_source:
            return {"query": q, "count": 0, "results": [], "error": "Blocked by Cloudflare"}

        items = []
        # Targeting actual product descriptors on the Micro Center site
        products = driver.find_elements(By.CSS_SELECTOR, "li.productDescription")

        for product in products:
            try:
                title_el = product.find_element(By.CSS_SELECTOR, "h4 a")
                items.append({
                    'title': title_el.get_attribute("data-name") or title_el.text.strip(),
                    'price': float(product.find_element(By.CSS_SELECTOR, "span[itemprop='price']").get_attribute("content")),
                    'link': title_el.get_attribute("href"),
                    'source': 'Micro Center'
                })
            except:
                continue

        return {"query": q, "count": len(items), "results": items}

    except Exception as e:
        return {"error": str(e)}
    finally:
        if driver:
            driver.quit()
