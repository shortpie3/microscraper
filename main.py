from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import undetected_chromedriver as uc
import time
import re
import os
from typing import List, Dict
import uvicorn

app = FastAPI(title="Micro Center Scraper API")
app.add_middleware(CORSMiddleware, allow_origins=["*"])

def setup_undetected_driver():
    """Setup undetected Chrome driver"""
    options = uc.ChromeOptions()

    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--headless')

    options.add_argument('--disable-blink-features=AutomationControlled')

    driver = uc.Chrome(options=options)

    return driver

@app.get("/scrape")
async def scrape(q: str = Query(..., min_length=1)):
    driver = None
    try:
        print(f"Starting undetected-chromedriver scrape for: {q}")

        driver = setup_undetected_driver()

        search_url = f"https://www.microcenter.com/search/search_results.aspx?Ntt={q.replace(' ', '+')}"
        print(f"Navigating to: {search_url}")

        driver.get(search_url)

        time.sleep(8)

        page_source = driver.page_source
        if "Just a moment" in page_source:
            return {
                "query": q,
                "count": 0,
                "results": [],
                "error": "Still blocked even with undetected-chromedriver",
                "title": driver.title
            }

        all_text = driver.page_source
        items = []

        price_matches = re.findall(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', all_text)

        for i, price_match in enumerate(set(price_matches[:20])):

            price = float(price_match.replace(',', ''))
            if price > 10:
                items.append({
                    'title': f"{q} - Found Item {i+1}",
                    'price': price,
                    'link': search_url,
                    'source': 'Micro Center',
                    'condition': 'New',
                    'shipping': 'Check website'
                })

        return {
            "query": q,
            "count": len(items),
            "results": items[:10],
            "method": "undetected-chromedriver"
        }

    except Exception as e:
        return {"query": q, "count": 0, "results": [], "error": str(e)}
    finally:
        if driver:
            driver.quit()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

