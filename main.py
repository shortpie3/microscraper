from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
import re
import json
from typing import List, Dict
import uvicorn
import time

app = FastAPI(title="Micro Center Scraper API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MICROCENTER_COOKIES = "asusSP=; lat=0; long=0; charlotteDistance=5708.84528339399; miamiDistance=5621.65802888577; santaclaraDistance=7944.2355928346; c_clientId=null; geolocated=true; bcu2=set; optimizelyEndUserId=oeu1768498193507r0.3999026925850696; Mlogin=closed; viewtype=grid; asusSP=; AMP_MKTG_8f1ede8e9c=JTdCJTdE; isOnWeb=False; myStore=true; optimizelySession=0; storeSelected=029; ipaddr=104.28.214.73; AMP_8f1ede8e9c=JTdCJTIyZGV2aWNlSWQlMjIlM0ElMjI4ZjJmYmZlZi05ZTAzLTQ3MzktOWE3Yy02NDU4MDE3Y2YyYTglMjIlMkMlMjJzZXNzaW9uSWQlMjIlM0ExNzY4NTAzOTg0OTg0JTJDJTIyb3B0T3V0JTIyJTNBZmFsc2UlN0Q="

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"

def create_session_with_cookies():
    """Create a requests session with browser-like headers and cookies"""
    session = requests.Session()

    session.headers.update({
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Cache-Control': 'max-age=0',
        'Referer': 'https://www.google.com/',
    })

    if MICROCENTER_COOKIES:
        cookies_dict = {}
        for cookie in MICROCENTER_COOKIES.split('; '):
            if '=' in cookie:
                key, value = cookie.split('=', 1)
                cookies_dict[key] = value
        session.cookies.update(cookies_dict)

    return session

def extract_price(text):
    """Extract price from text"""
    if not text:
        return 0
    match = re.search(r'\$?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', str(text))
    return float(match.group(1).replace(',', '')) if match else 0

@app.get("/")
async def root():
    return {
        "message": "Micro Center Scraper API",
        "endpoints": {
            "scrape": "GET /scrape?q=search+query",
            "test-cookies": "GET /test-cookies",
            "get-cookies": "GET /get-cookies-example"
        }
    }

@app.get("/test-cookies")
async def test_cookies():
    """Test if cookies work"""
    try:
        session = create_session_with_cookies()
        test_url = "https://www.microcenter.com"

        response = session.get(test_url, timeout=10)

        if "Just a moment" in response.text or "Enable JavaScript" in response.text:
            return {
                "status": "blocked",
                "message": "Still getting Cloudflare block",
                "title": BeautifulSoup(response.text, 'html.parser').title.string if BeautifulSoup(response.text, 'html.parser').title else "No title",
                "cookies_used": dict(session.cookies)
            }

        return {
            "status": "success",
            "message": "Cookies working!",
            "title": BeautifulSoup(response.text, 'html.parser').title.string,
            "cookies_count": len(session.cookies),
            "sample_cookies": dict(list(session.cookies.items())[:3])
        }

    except Exception as e:
        return {"error": str(e)}

@app.get("/get-cookies-example")
async def get_cookies_example():
    """Show how to get cookies"""
    return {
        "instructions": "Get cookies from your browser:",
        "chrome": "1. Go to microcenter.com, 2. F12 → Application → Cookies",
        "firefox": "1. Go to microcenter.com, 2. F12 → Storage → Cookies",
        "javascript": "Run 'document.cookie' in browser console",
        "cookie_format": "cookie1=value1; cookie2=value2; ...",
        "important_cookies": [
            "__cf_bm",

            "_cfuvid",

            "PHPSESSID",

            "storeSelected",

            "micro-authenticated",

        ]
    }

@app.get("/scrape")
async def scrape(q: str = Query(..., min_length=1)):
    """Scrape Micro Center with cookies"""
    try:
        session = create_session_with_cookies()

        search_url = f"https://www.microcenter.com/search/search_results.aspx?Ntt={requests.utils.quote(q)}"

        print(f"Fetching: {search_url}")

        time.sleep(1)

        response = session.get(search_url, timeout=15)

        if response.status_code == 403 or "Just a moment" in response.text:
            return {
                "query": q,
                "count": 0,
                "results": [],
                "error": "Cloudflare block - cookies may be invalid",
                "status_code": response.status_code,
                "title": BeautifulSoup(response.text, 'html.parser').title.string if BeautifulSoup(response.text, 'html.parser').title else "Blocked"
            }

        soup = BeautifulSoup(response.content, 'html.parser')

        items = []

        product_selectors = [
            'div.product_wrapper',
            'li.product',
            'div.product',
            'article.product',
            'div[data-product-id]',
            'div.search-result',
            'div.result'
        ]

        all_products = []
        for selector in product_selectors:
            found = soup.select(selector)
            if found:
                all_products.extend(found)

        if not all_products:

            for div in soup.find_all(['div', 'li', 'article']):
                text = div.get_text()
                if '$' in text and len(text) < 1000:

                    all_products.append(div)

        print(f"Found {len(all_products)} potential products")

        for product in all_products[:20]:

            try:
                product_html = str(product)
                product_soup = BeautifulSoup(product_html, 'html.parser')

                title = ""
                title_selectors = ['h2', 'h3', 'h4', '.pDescription', '.description', '.productName', '[data-name]']
                for selector in title_selectors:
                    elem = product_soup.select_one(selector)
                    if elem:
                        title = elem.get_text(strip=True)
                        if title:
                            break

                link = ""
                link_elem = product_soup.select_one('a[href*="/product/"]')
                if link_elem and 'href' in link_elem.attrs:
                    link = link_elem['href']
                    if not link.startswith('http'):
                        link = f"https://www.microcenter.com{link}"

                price = 0
                price_text = ""
                price_selectors = ['.price', '.yourPrice', '[data-price]', '.priceLabel']
                for selector in price_selectors:
                    elem = product_soup.select_one(selector)
                    if elem:
                        price_text = elem.get_text(strip=True)
                        if price_text:
                            break

                if not price_text:
                    full_text = product_soup.get_text()
                    price_match = re.search(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', full_text)
                    if price_match:
                        price_text = price_match.group(0)

                if price_text:
                    price = extract_price(price_text)

                if price < 10:
                    continue

                full_text_lower = product_soup.get_text().lower()
                out_of_stock = any(phrase in full_text_lower for phrase in [
                    'out of stock', 'out-of-stock', 'not available', 'unavailable',
                    'sold out', 'no longer available'
                ])

                if out_of_stock:
                    continue

                image = ""
                img_elem = product_soup.select_one('img')
                if img_elem:
                    image = img_elem.get('src') or img_elem.get('data-src', '')
                    if image and not image.startswith('http'):
                        image = f"https://www.microcenter.com{image}"

                condition = "New"
                if 'refurbished' in full_text_lower:
                    condition = "Refurbished"
                elif 'open box' in full_text_lower or 'open-box' in full_text_lower:
                    condition = "Open Box"

                shipping = "In-store pickup"
                if 'free shipping' in full_text_lower:
                    shipping = "Free shipping"
                elif 'shipping available' in full_text_lower:
                    shipping = "Shipping available"

                if title and link and price > 0:
                    items.append({
                        'title': title[:200],
                        'price': price,
                        'link': link,
                        'image': image,
                        'source': 'Micro Center',
                        'condition': condition,
                        'shipping': shipping,
                        'in_stock': True
                    })

            except Exception as e:
                print(f"Error parsing product: {e}")
                continue

        items.sort(key=lambda x: x['price'])

        return {
            "query": q,
            "count": len(items),
            "results": items[:15],
            "raw_html_size": len(response.text),
            "status": "success"
        }

    except Exception as e:
        print(f"Scraping error: {e}")
        return {
            "query": q,
            "count": 0,
            "results": [],
            "error": str(e)
        }

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

