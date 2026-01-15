from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from bs4 import BeautifulSoup
import re
import json
from typing import List, Dict
import uvicorn

app = FastAPI(title="Micro Center Scraper API")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def clean_text(text):
    """Clean and normalize text"""
    if not text:
        return ""
    return ' '.join(text.strip().split())

@app.get("/")
async def root():
    return {
        "message": "Micro Center Scraper API",
        "endpoints": {
            "scrape": "GET /scrape?q=search+query",
            "debug": "GET /debug?q=search+query"
        }
    }

@app.get("/scrape")
async def scrape(q: str = Query(..., min_length=1)):
    """Scrape Micro Center for products"""
    try:
        # Clean the query for searching
        query_clean = q.lower().strip()
        
        # Build search URL
        search_url = f"https://www.microcenter.com/search/search_results.aspx?Ntt={requests.utils.quote(q)}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.microcenter.com/',
        }
        
        # Fetch the page
        response = requests.get(search_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Debug: Save HTML for inspection (optional)
        # with open('debug.html', 'w', encoding='utf-8') as f:
        #     f.write(str(soup))
        
        # Strategy 1: Look for product containers - common Micro Center selectors
        products = []
        
        # Try multiple approaches to find products
        product_elements = []
        
        # Approach 1: Look for specific Micro Center classes
        selectors_to_try = [
            'div.product_wrapper',
            'li.product',
            'div.pImage',
            'div.details',
            'div.result',
            'article.product',
            'div[data-product-id]',
            'div.search-result',
            'div.product-item',
            'div.item'
        ]
        
        for selector in selectors_to_try:
            elements = soup.select(selector)
            product_elements.extend(elements)
        
        # Approach 2: Look for any elements with product-like classes
        all_divs = soup.find_all(['div', 'li', 'article'])
        for elem in all_divs:
            classes = elem.get('class', [])
            if classes:
                class_str = ' '.join(classes).lower()
                if any(keyword in class_str for keyword in ['product', 'item', 'result', 'detail', 'pimage']):
                    product_elements.append(elem)
        
        # Remove duplicates by tracking IDs or content
        seen = set()
        unique_elements = []
        for elem in product_elements:
            elem_str = str(elem)
            if len(elem_str) > 100 and elem_str not in seen:
                seen.add(elem_str)
                unique_elements.append(elem)
        
        print(f"Found {len(unique_elements)} potential product elements")
        
        # Parse each product element
        for element in unique_elements[:30]:  # Limit to 30
            try:
                # Get full text for analysis
                full_text = element.get_text().lower()
                
                # Skip out of stock items
                out_of_stock_keywords = ['out of stock', 'out-of-stock', 'not available', 'unavailable', 'sold out']
                if any(keyword in full_text for keyword in out_of_stock_keywords):
                    continue
                
                # Skip in-store only items
                in_store_only_keywords = ['in-store only', 'store only', 'pickup only', 'not available online']
                if any(keyword in full_text for keyword in in_store_only_keywords):
                    continue
                
                # Try to find title
                title = ""
                title_selectors = ['h2 a', 'h3 a', '.pDescription a', '.description a', '.productName a', 'a h2', 'a h3']
                for selector in title_selectors:
                    title_elem = element.select_one(selector)
                    if title_elem:
                        title = clean_text(title_elem.get_text())
                        if title:
                            break
                
                # If no title found, try other approaches
                if not title:
                    # Look for any h2, h3, h4 with text
                    for tag in ['h2', 'h3', 'h4', 'h5']:
                        header = element.find(tag)
                        if header:
                            title = clean_text(header.get_text())
                            if title:
                                break
                
                # Try to find link
                link = ""
                link_selectors = ['a[href*="/product/"]', 'a[href*="/search/"]', 'a[href*="microcenter.com"]']
                for selector in link_selectors:
                    link_elem = element.select_one(selector)
                    if link_elem and link_elem.get('href'):
                        link = link_elem['href']
                        if not link.startswith('http'):
                            link = f"https://www.microcenter.com{link}"
                        break
                
                # Try to find price
                price = 0
                price_text = ""
                price_selectors = ['.price', '.yourPrice', '[data-price]', '.priceLabel', '.normalPrice', '.salePrice']
                
                for selector in price_selectors:
                    price_elem = element.select_one(selector)
                    if price_elem:
                        price_text = clean_text(price_elem.get_text())
                        if price_text:
                            break
                
                # Also search in the entire element text
                if not price_text:
                    # Look for price patterns in the entire text
                    price_match = re.search(r'\$(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', element.get_text())
                    if price_match:
                        price_text = price_match.group(0)
                
                # Extract numeric price
                if price_text:
                    price_match = re.search(r'\$?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', price_text)
                    if price_match:
                        price = float(price_match.group(1).replace(',', ''))
                
                # Skip if no price or very low price (probably not a real product)
                if price < 10:
                    continue
                
                # Try to find image
                image = ""
                img_selectors = ['img.productImage', 'img[data-src]', 'img[src*="microcenter"]', 'img']
                for selector in img_selectors:
                    img_elem = element.select_one(selector)
                    if img_elem:
                        image = img_elem.get('src') or img_elem.get('data-src', '')
                        if image and not image.startswith('http'):
                            image = f"https://www.microcenter.com{image}"
                        break
                
                # Determine condition
                condition = "New"
                if 'refurbished' in full_text:
                    condition = "Refurbished"
                elif 'open box' in full_text or 'open-box' in full_text:
                    condition = "Open Box"
                elif 'used' in full_text or 'pre-owned' in full_text:
                    condition = "Used"
                
                # Determine shipping
                shipping = "Check availability"
                if 'free shipping' in full_text:
                    shipping = "Free shipping"
                elif 'shipping available' in full_text:
                    shipping = "Shipping available"
                elif 'in-store pickup' in full_text:
                    shipping = "In-store pickup"
                
                # Create product object
                product = {
                    'title': title[:200],  # Limit title length
                    'price': round(price, 2),
                    'link': link,
                    'image': image,
                    'source': 'Micro Center',
                    'condition': condition,
                    'shipping': shipping,
                    'raw_text_preview': full_text[:100]  # For debugging
                }
                
                # Add to results if we have minimum required info
                if product['title'] and product['price'] > 0:
                    products.append(product)
                    
            except Exception as e:
                print(f"Error parsing product: {e}")
                continue
        
        # Sort by price
        products.sort(key=lambda x: x['price'])
        
        # Limit results
        final_results = products[:15]
        
        return {
            "query": q,
            "count": len(final_results),
            "results": final_results
        }
        
    except Exception as e:
        print(f"Scraping error: {e}")
        return {
            "query": q,
            "count": 0,
            "results": [],
            "error": str(e)
        }

@app.get("/debug")
async def debug(q: str = "9070 xt"):
    """Debug endpoint to see what the scraper finds"""
    try:
        search_url = f"https://www.microcenter.com/search/search_results.aspx?Ntt={requests.utils.quote(q)}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(search_url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all div/li elements with classes
        elements_with_classes = []
        for tag in ['div', 'li', 'article', 'section']:
            for elem in soup.find_all(tag, class_=True):
                class_str = ' '.join(elem.get('class')).lower()
                elements_with_classes.append({
                    'tag': tag,
                    'classes': class_str,
                    'text_preview': elem.get_text()[:100].replace('\n', ' ').strip(),
                    'html_preview': str(elem)[:200]
                })
        
        # Get page info
        return {
            "url": search_url,
            "status": response.status_code,
            "title": soup.title.string if soup.title else "No title",
            "total_elements": len(elements_with_classes),
            "sample_elements": elements_with_classes[:10],
            "common_classes": list(set([e['classes'] for e in elements_with_classes]))[:20]
        }
        
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
