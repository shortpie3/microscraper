from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
import re
import json
import asyncio
import aiohttp
from typing import List, Dict
import uvicorn

app = FastAPI(title="Micro Center Scraper API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],

    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def fetch_page(session: aiohttp.ClientSession, url: str, headers: dict) -> str:
    """Fetch a page with retry logic"""
    for attempt in range(3):
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    return await response.text()
                elif response.status == 403:
                    raise Exception("Access forbidden - site blocking")
                else:
                    await asyncio.sleep(1)

        except Exception as e:
            if attempt == 2:

                raise e
            await asyncio.sleep(1)
    return ""

def parse_microcenter_product(product_html: str) -> Dict:
    """Parse individual product HTML"""
    try:
        soup = BeautifulSoup(product_html, 'html.parser')

        title_elem = soup.select_one('h2 a, .pDescription a, [data-name]')
        title = title_elem.get_text(strip=True) if title_elem else ""

        link_elem = soup.select_one('a[href*="/product/"]')
        if link_elem and 'href' in link_elem.attrs:
            link = link_elem['href']
            if not link.startswith('http'):
                link = f"https://www.microcenter.com{link}"
        else:
            link = ""

        price_elem = soup.select_one('.price, .yourPrice, [data-price]')
        price_text = price_elem.get_text(strip=True) if price_elem else ""

        price_match = re.search(r'\$?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', price_text)
        price = float(price_match.group(1).replace(',', '')) if price_match else 0

        img_elem = soup.select_one('img.productImage, img[data-src]')
        image = ""
        if img_elem:
            image = img_elem.get('src') or img_elem.get('data-src', "")
            if image and not image.startswith('http'):
                image = f"https://www.microcenter.com{image}"

        condition = "New"
        full_text = soup.get_text().lower()
        if 'refurbished' in full_text:
            condition = "Refurbished"
        elif 'open box' in full_text or 'open-box' in full_text:
            condition = "Open Box"
        elif 'used' in full_text or 'pre-owned' in full_text:
            condition = "Used"

        shipping = "In-store pickup"
        if 'shipping available' in full_text or 'ship' in full_text:
            shipping = "Shipping available"

        return {
            'title': title,
            'price': price,
            'link': link,
            'image': image,
            'source': 'Micro Center',
            'condition': condition,
            'shipping': shipping
        }

    except Exception as e:
        print(f"Error parsing product: {e}")
        return None

async def scrape_microcenter_async(query: str) -> List[Dict]:
    """Async version of the scraper"""
    try:
        search_url = f"https://www.microcenter.com/search/search_results.aspx?Ntt={requests.utils.quote(query)}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.microcenter.com/',
        }

        async with aiohttp.ClientSession() as session:
            html = await fetch_page(session, search_url, headers)

            if not html:
                return []

            soup = BeautifulSoup(html, 'html.parser')

            product_containers = soup.select('.product_wrapper, .details, .result, .product')
            products = []

            for container in product_containers[:10]:
                try:
                    product_data = parse_microcenter_product(str(container))
                    if product_data and product_data['price'] > 0 and product_data['link']:

                        clean_title = product_data['title'].lower().replace(' ', '')
                        clean_query = query.lower().replace(' ', '')

                        if clean_query in clean_title:
                            products.append(product_data)
                except Exception as e:
                    continue

            return products

    except Exception as e:
        print(f"Scraping error: {e}")
        return []

@app.get("/")
async def root():
    return {
        "message": "Micro Center Scraper API",
        "endpoints": {
            "scrape": "GET /scrape?q=search+query",
            "health": "GET /health"
        }
    }

@app.get("/scrape")
async def scrape(query: str = Query(..., min_length=1, description="Search query for Micro Center")):
    """Scrape Micro Center for products"""
    try:
        results = await scrape_microcenter_async(query)
        return {
            "query": query,
            "count": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

