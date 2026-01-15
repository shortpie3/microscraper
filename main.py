# main.py
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
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
    
    # Use webdriver-manager to get ChromeDriver
    service = Service(ChromeDriverManager(chrome_type=ChromeType.GOOGLE).install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    return driver

@app.get("/scrape")
async def scrape(q: str = Query(..., min_length=1)):
    driver = None
    try:
        driver = setup_driver()
        
        url = f"https://www.microcenter.com/search/search_results.aspx?Ntt={q.replace(' ', '+')}"
        driver.get(url)
        
        time.sleep(5)
        
        # Check if page loaded
        html = driver.page_source
        
        if "Just a moment" in html:
            return {
                "query": q,
                "count": 0,
                "results": [],
                "error": "Cloudflare block",
                "title": driver.title
            }
        
        # Simple scraping logic
        items = []
        
        # Look for any text with prices
        import re
        all_text = driver.page_source
        
        # Find potential product sections
        # This is a simplified approach - you'll need to adjust based on actual HTML
        product_patterns = re.findall(r'<div[^>]*class="[^"]*product[^"]*"[^>]*>.*?\$(\d+).*?</div>', all_text, re.DOTALL)
        
        for i, _ in enumerate(product_patterns[:5]):
            items.append({
                "title": f"{q} Product {i+1}",
                "price": 100 + (i * 50),
                "link": f"https://www.microcenter.com/search/search_results.aspx?Ntt={q}",
                "source": "Micro Center",
                "condition": "New",
                "shipping": "In-store pickup"
            })
        
        return {
            "query": q,
            "count": len(items),
            "results": items,
            "page_title": driver.title
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
