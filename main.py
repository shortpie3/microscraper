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

app = FastAPI(title="microscraper")

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

def parse_microcenter_product(product_html: str, query: str) -> Dict:
    """Parse individual product HTML"""
    try:
        soup = BeautifulSoup(product_html, 'html.parser')

        title_elem = soup.select_one('h2 a, .pDescription a, .description a, [data-name], .productName a')
        title = title_elem.get_text(strip=True) if title_elem else ""

        clean_title = title.lower().replace(' ', '')
        clean_query = query.lower().replace(' ', '')
        if clean_query not in clean_title:
            return None

        link_elem = soup.select_one('a[href*="/product/"], a[data-id]')
        if link_elem and 'href' in link_elem.attrs:
            link = link_elem['href']
            if not link.startswith('http'):
                link = f"https://www.microcenter.com{link}"
        else:
            link = ""

        product_text = soup.get_text().lower()
        out_of_stock_indicators = [
            'out of stock', 'out-of-stock', 'not available', 'unavailable',
            'sold out', 'no longer available', 'discontinued'
        ]

        online_only_indicators = ['online only', 'web only', 'internet only']
        is_online_only = any(indicator in product_text for indicator in online_only_indicators)

        in_store_only_indicators = ['in-store only', 'store only', 'pickup only', 'not sold online']
        is_in_store_only = any(indicator in product_text for indicator in in_store_only_indicators)

        if is_in_store_only:
            return None

        is_out_of_stock = any(indicator in product_text for indicator in out_of_stock_indicators)
        if is_out_of_stock:
            return None

        price_elem = soup.select_one('.price, .yourPrice, [data-price], .priceLabel, .normalPrice')
        price_text = price_elem.get_text(strip=True) if price_elem else ""

        price_match = re.search(r'\$?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', price_text)
        price = float(price_match.group(1).replace(',', '')) if price_match else 0

        if price <= 0:
            return None

        img_elem = soup.select_one('img.productImage, img[data-src], img[src*="microcenter"]')
        image = ""
        if img_elem:
            image = img_elem.get('src') or img_elem.get('data-src', "")
            if image and not image.startswith('http'):
                image = f"https://www.microcenter.com{image}"

        condition = "New"
        if 'refurbished' in product_text:
            condition = "Refurbished"
        elif 'open box' in product_text or 'open-box' in product_text:
            condition = "Open Box"
        elif 'used' in product_text or 'pre-owned' in product_text:
            condition = "Used"

        shipping = "In-store pickup"
        if 'free shipping' in product_text:
            shipping = "Free shipping"
        elif 'shipping available' in product_text or 'ships' in product_text:
            shipping = "Shipping available"
        elif is_online_only:
            shipping = "Online only"

        return {
            'title': title,
            'price': price,
            'link': link,
            'image': image,
            'source': 'Micro Center',
            'condition': condition,
            'shipping': shipping,
            'in_stock': True
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
            'Accept-Encoding': 'gzip, deflate, br',
        }

        async with aiohttp.ClientSession() as session:
            html = await fetch_page(session, search_url, headers)

            if not html:
                return []

            soup = BeautifulSoup(html, 'html.parser')

            product_selectors = [
                '.product_wrapper',
                '.details',
                '.result',
                '.product',
                '.pImage',
                '[data-product-id]',
                '.product-list .item',
                '.search-results .product'
            ]

            all_products = []
            for selector in product_selectors:
                products = soup.select(selector)
                if products:
                    all_products.extend(products)
                    if len(all_products) >= 20:

                        break

            seen_links = set()
            unique_products = []
            for product in all_products:
                try:
                    link_elem = product.select_one('a[href*="/product/"]')
                    if link_elem and 'href' in link_elem.attrs:
                        link = link_elem['href']
                        if link not in seen_links:
                            seen_links.add(link)
                            unique_products.append(product)
                except:
                    continue

            parsed_products = []
            for container in unique_products[:15]:

                try:
                    product_data = parse_microcenter_product(str(container), query)
                    if product_data:
                        parsed_products.append(product_data)
                except Exception as e:
                    print(f"Error processing product: {e}")
                    continue

            parsed_products.sort(key=lambda x: x['price'])

            return parsed_products[:10]

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
async def scrape(q: str = Query(..., min_length=1, description="Search query for Micro Center")):
    """Scrape Micro Center for products"""
    try:
        results = await scrape_microcenter_async(q)
        return {
            "query": q,
            "count": len(results),
            "results": results
        }
    except Exception as e:
        return {
            "query": q,
            "count": 0,
            "results": [],
            "error": str(e)
        }

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

