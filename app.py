# ============================================
# FILE 1: app.py
# Main bot application file
# ============================================

"""
Timepiece WhatsApp Bot - Auto Product Search
Automatically searches your website for products based on AI detection
"""

from flask import Flask, request, jsonify
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timedelta
import base64
from urllib.parse import urljoin, quote
import os

app = Flask(__name__)

# ========== CONFIGURATION FROM ENVIRONMENT VARIABLES ==========
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', 'AC23c49dc08fb32d3786e37620396d4c53')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '4e8778d197b0608cee3d491d956890f0')
TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', 'whatsapp:+14155238886')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', 'sk-abcdef1234567890abcdef1234567890abcdef12')
WEBSITE_URL = os.environ.get('WEBSITE_URL', 'https://timepiece.cartpe.in')

# Initialize Twilio client
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Cache for scraped products
product_cache = {
    'products': [],
    'last_updated': None
}


def scrape_website_products():
    """Scrape all products from website"""
    print("🔍 Scraping products from website...")
    products = []
    
    try:
        response = requests.get(WEBSITE_URL, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Common product selectors
        product_selectors = [
            {'container': 'div', 'class': 'product-item'},
            {'container': 'div', 'class': 'product-card'},
            {'container': 'div', 'class': 'product'},
            {'container': 'article', 'class': 'product'},
        ]
        
        elements = []
        for selector in product_selectors:
            elements = soup.find_all(selector['container'], class_=re.compile(selector['class']))
            if elements:
                break
        
        if not elements:
            elements = soup.find_all('a', href=True)
            elements = [e for e in elements if '/product' in e.get('href', '')]
        
        for elem in elements:
            try:
                link = elem.get('href') or elem.find('a', href=True)
                if not link:
                    continue
                
                product_url = link if isinstance(link, str) else link.get('href')
                
                if product_url and not product_url.startswith('http'):
                    product_url = urljoin(WEBSITE_URL, product_url)
                
                title = None
                for tag in ['h3', 'h4', 'h2', 'a', 'span']:
                    title_elem = elem.find(tag, class_=re.compile('title|name|product'))
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        break
                
                if not title:
                    title = elem.get_text(strip=True)[:100]
                
                if title and product_url and len(title) > 3:
                    brand, model = extract_brand_model(title)
                    
                    products.append({
                        'title': title,
                        'url': product_url,
                        'brand': brand,
                        'model': model,
                        'in_stock': True
                    })
                    
            except Exception as e:
                continue
        
        # Remove duplicates
        seen_urls = set()
        unique_products = []
        for p in products:
            if p['url'] not in seen_urls:
                seen_urls.add(p['url'])
                unique_products.append(p)
        
        print(f"✓ Successfully scraped {len(unique_products)} unique products")
        return unique_products
        
    except Exception as e:
        print(f"❌ Error scraping website: {e}")
        return get_fallback_products()


def get_fallback_products():
    """Fallback products"""
    brands = ['Rolex', 'Omega', 'Audemars Piguet', 'Patek Philippe',
              'Cartier', 'Tag Heuer', 'Hublot', 'Panerai', 'IWC', 'Breitling']
    
    return [{
        'title': f'{brand} Watch',
        'url': f'{WEBSITE_URL}/search?q={quote(brand)}',
        'brand': brand,
        'model': '',
        'in_stock': True
    } for brand in brands]


def extract_brand_model(title):
    """Extract brand and model from title"""
    title_lower = title.lower()
    
    brands = {
        'rolex': 'Rolex', 'omega': 'Omega', 'audemars piguet': 'Audemars Piguet',
        'ap ': 'Audemars Piguet', 'patek philippe': 'Patek Philippe',
        'cartier': 'Cartier', 'tag heuer': 'Tag Heuer', 'hublot': 'Hublot',
        'panerai': 'Panerai', 'iwc': 'IWC', 'breitling': 'Breitling'
    }
    
    brand = 'Unknown'
    for key, value in brands.items():
        if key in title_lower:
            brand = value
            break
    
    model = ''
    if brand != 'Unknown':
        brand_pos = title_lower.find(brand.lower())
        if brand_pos != -1:
            after_brand = title[brand_pos + len(brand):].strip()
            words = after_brand.split()[:3]
            model = ' '.join(words)
    
    return brand, model


def get_cached_products():
    """Get products from cache or refresh"""
    global product_cache
    
    if (product_cache['last_updated'] is None or 
        datetime.now() - product_cache['last_updated'] > timedelta(hours=6)):
        
        product_cache['products'] = scrape_website_products()
        product_cache['last_updated'] = datetime.now()
    
    return product_cache['products']


def search_product_on_website(brand, model):
    """Search for product on website"""
    print(f"🔍 Searching website for: {brand} {model}")
    
    products = get_cached_products()
    brand_lower = brand.lower() if brand else ''
    model_lower = model.lower() if model else ''
    
    # Exact match
    for product in products:
        product_title = product['title'].lower()
        if brand_lower in product_title and model_lower in product_title:
            print(f"✓ Found exact match: {product['title']}")
            return product
    
    # Brand match
    for product in products:
        if brand_lower in product['title'].lower():
            print(f"✓ Found brand match: {product['title']}")
            return product
    
    # Direct search
    if brand:
        search_url = f"{WEBSITE_URL}/search?q={quote(brand + ' ' + model)}"
        try:
            response = requests.get(search_url, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                if 'no results' not in soup.get_text().lower():
                    return {
                        'title': f'{brand} {model}',
                        'url': search_url,
                        'brand': brand,
                        'model': model,
                        'in_stock': True
                    }
        except:
            pass
    
    print("❌ No matching product found")
    return None


def analyze_watch_with_openai(image_url):
    """Analyze watch image with OpenAI"""
    try:
        img_response = requests.get(image_url, timeout=15)
        if img_response.status_code != 200:
            return None
        
        img_data = base64.b64encode(img_response.content).decode('utf-8')
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}"
        }
        
        payload = {
            "model": "gpt-4o",
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": """Identify this watch. Return ONLY JSON:
{
    "brand": "exact brand name",
    "model": "exact model name",
    "confidence": "high or low"
}"""
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img_data}"}
                    }
                ]
            }],
            "max_tokens": 300
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            return None
        
        result = response.json()
        content = result['choices'][0]['message']['content']
        
        json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        
        return None
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


@app.route('/webhook', methods=['POST'])
def whatsapp_webhook():
    """Handle incoming WhatsApp messages"""
    try:
        sender = request.values.get('From', '')
        media_url = request.values.get('MediaUrl0', None)
        num_media = request.values.get('NumMedia', '0')
        
        print(f"\n{'='*60}")
        print(f"📱 Message from: {sender}")
        print(f"Media: {media_url}")
        print(f"{'='*60}\n")
        
        response = MessagingResponse()
        
        if media_url and int(num_media) > 0:
            watch_info = analyze_watch_with_openai(media_url)
            
            if watch_info and watch_info.get('confidence') == 'high':
                brand = watch_info.get('brand', '')
                model = watch_info.get('model', '')
                
                product = search_product_on_website(brand, model)
                
                if product and product.get('in_stock'):
                    reply = f"Yes Timepiece\n{product['url']}"
                    response.message(reply)
                    print(f"✅ Sent: {reply}\n")
        
        return str(response)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return str(MessagingResponse())


@app.route('/test')
def test():
    """Test endpoint"""
    products = get_cached_products()
    return jsonify({
        'status': 'Bot running',
        'products_cached': len(products),
        'website': WEBSITE_URL
    })


@app.route('/products')
def list_products():
    """List cached products"""
    products = get_cached_products()
    return jsonify({'total': len(products), 'products': products[:50]})


@app.route('/refresh-cache')
def refresh_cache():
    """Refresh product cache"""
    global product_cache
    product_cache['products'] = scrape_website_products()
    product_cache['last_updated'] = datetime.now()
    return jsonify({'status': 'success', 'products': len(product_cache['products'])})


@app.route('/')
def home():
    """Home page"""
    products = get_cached_products()
    return f"""
    <html>
    <head><title>Timepiece Bot</title></head>
    <body style="font-family: Arial; max-width: 800px; margin: 50px auto; padding: 20px;">
        <h1>⌚ Timepiece WhatsApp Bot</h1>
        <h2>Status: ✅ Running</h2>
        <p><strong>Products Cached:</strong> {len(products)}</p>
        <p><strong>Website:</strong> {WEBSITE_URL}</p>
        <hr>
        <h3>Test Links:</h3>
        <p><a href="/test">Test Status</a> | <a href="/products">View Products</a> | <a href="/refresh-cache">Refresh Cache</a></p>
    </body>
    </html>
    """


if __name__ == '__main__':
    print("\n🚀 Starting Timepiece Bot...")
    get_cached_products()
    app.run(host='0.0.0.0', port=5000, debug=False)  
