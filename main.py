from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import re
import os

app = FastAPI(title="Micro Center Scraper API")
app.add_middleware(CORSMiddleware, allow_origins=["*"])

def setup_driver():
    """Setup Chrome driver with webdriver-manager"""
    chrome_options = Options()
    
    # Render settings
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    
    # Anti-detection
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # User agent
    chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    # Use webdriver-manager
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    return driver

@app.get("/")
async def root():
    return {"message": "Micro Center Scraper API"}

@app.get("/scrape")
async def scrape(q: str = Query(..., min_length=1)):
    driver = None
    try:
        driver = setup_driver()
        
        url = f"https://www.microcenter.com/search/search_results.aspx?Ntt={q.replace(' ', '+')}"
        driver.get(url)
        
        # Wait for page
        time.sleep(5)
        
        # Check if blocked
        html = driver.page_source
        if "Just a moment" in html:
            return {
                "query": q,
                "count": 0,
                "results": [],
                "error": "Cloudflare block"
            }
        
        # Simple scraping - look for prices
        items = []
        all_text = driver.page_source
        
        # Find prices
        price_matches = re.findall(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', all_text)
        
        for i, price_match in enumerate(set(price_matches[:10])):  # Unique prices
            price = float(price_match.replace(',', ''))
            if price > 10:
                items.append({
                    'title': f"{q} - Item {i+1}",
                    'price': price,
                    'link': url,
                    'source': 'Micro Center',
                    'condition': 'New',
                    'shipping': 'Check website'
                })
        
        return {
            "query": q,
            "count": len(items),
            "results": items
        }
        
    except Exception as e:
        return {"query": q, "count": 0, "results": [], "error": str(e)}
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)
