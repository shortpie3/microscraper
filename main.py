from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By  # Was missing
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
    
    # Path for the Docker environment
    chrome_options.binary_location = "/usr/bin/google-chrome"
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

@app.get("/")
async def root():
    return {"message": "Micro Center Scraper API is running"}

@app.get("/scrape")
async def scrape(q: str = Query(..., min_length=1)):
    driver = None
    try:
        driver = setup_driver()

        # Micro Center search URL
        url = f"https://www.microcenter.com/search/search_results.aspx?Ntt={q.replace(' ', '+')}"
        driver.get(url)

        # Allow time for JavaScript to render product cards
        time.sleep(5)

        html = driver.page_source
        if "Just a moment" in html:
            return {
                "query": q,
                "count": 0,
                "results": [],
                "error": "Cloudflare block"
            }

        items = []
        # Target the actual list items containing products
        products = driver.find_elements(By.CSS_SELECTOR, "li.productDescription")

        for product in products:
            try:
                # 1. Extract Title and Link from the <a> tag
                title_element = product.find_element(By.CSS_SELECTOR, "h4 a")
                title = title_element.get_attribute("data-name") or title_element.text
                link = title_element.get_attribute("href")
                
                # 2. Extract Price from the itemprop span
                # Micro Center usually stores the numerical price in the 'content' attribute
                price_element = product.find_element(By.CSS_SELECTOR, "span[itemprop='price']")
                price_text = price_element.get_attribute("content")
                price = float(price_text) if price_text else 0.0

                if price > 0:
                    items.append({
                        'title': title.strip(),
                        'price': price,
                        'link': link,
                        'source': 'Micro Center',
                        'condition': 'New',
                        'store_availability': 'Check website'
                    })
            except Exception:
                # Skip products that are missing data (like ads or placeholders)
                continue

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
