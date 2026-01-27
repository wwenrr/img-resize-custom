import shopify
import requests
import os
import time
import json
from PIL import Image
from io import BytesIO
from report_generator import generate_html_report, get_file_size_display
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import re
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Load tokens from environment variables
jwl_access_token = os.getenv('JWL_ACCESS_TOKEN')
jf_access_token = os.getenv('JF_ACCESS_TOKEN')

if not jwl_access_token or not jf_access_token:
    print(f"{Colors.RED}Error: Missing API tokens in .env file{Colors.ENDC}")
    print(f"{Colors.YELLOW}Please create .env file with:{Colors.ENDC}")
    print("JWL_ACCESS_TOKEN=your_token_here")
    print("JF_ACCESS_TOKEN=your_token_here")
    exit(1)

# Store configurations
STORES = {
    "jwl": {
        "name": "Japan World Link",
        "shop_url": "japan-with-love.myshopify.com",
        "token": jwl_access_token
    },
    "jf": {
        "name": "Japan Toy and Figure",
        "shop_url": "japan-toy-and-figure.myshopify.com",
        "token": jf_access_token
    }
}

def select_store(auto_choice=None):
    """
    Select store and return shop URL and token.
    Args:
        auto_choice: Optional. Can be 1, 2, 'jwl', or 'jf' to auto-select without prompting.
    Returns:
        tuple: (shop_url, token)
    """
    if auto_choice is not None:
        choice = str(auto_choice).lower()
        if choice in ['1', 'jwl']:
            selected_store = STORES['jwl']
            print(f"{Colors.GREEN}✓ Auto-selected: {selected_store['name']}{Colors.ENDC}\n")
            return selected_store['shop_url'], selected_store['token']
        elif choice in ['2', 'jf']:
            selected_store = STORES['jf']
            print(f"{Colors.GREEN}✓ Auto-selected: {selected_store['name']}{Colors.ENDC}\n")
            return selected_store['shop_url'], selected_store['token']
        else:
            print(f"{Colors.RED}Invalid auto_choice: {auto_choice}. Falling back to manual selection.{Colors.ENDC}\n")
    
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*50}{Colors.ENDC}")
    print(f"{Colors.BOLD}Select Store:{Colors.ENDC}")
    print(f"  1. {Colors.GREEN}JWL{Colors.ENDC} - {STORES['jwl']['name']}")
    print(f"  2. {Colors.GREEN}JF{Colors.ENDC}  - {STORES['jf']['name']}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*50}{Colors.ENDC}")
    
    while True:
        choice = input(f"{Colors.BOLD}Enter your choice (1/2 or jwl/jf): {Colors.ENDC}").strip().lower()
        
        if choice in ['1', 'jwl']:
            selected_store = STORES['jwl']
            print(f"{Colors.GREEN}✓ Selected: {selected_store['name']}{Colors.ENDC}\n")
            return selected_store['shop_url'], selected_store['token']
        elif choice in ['2', 'jf']:
            selected_store = STORES['jf']
            print(f"{Colors.GREEN}✓ Selected: {selected_store['name']}{Colors.ENDC}\n")
            return selected_store['shop_url'], selected_store['token']
        else:
            print(f"{Colors.RED}Invalid choice. Please enter 1, 2, jwl, or jf.{Colors.ENDC}")

def fetch_products_generator(shop_url, token, batches_per_yield=15):
    """
    Generator that fetches products and yields them in chunks.
    Args:
        shop_url: Shopify store URL
        token: Access token
        batches_per_yield: Number of API batches (250 items each) to accumulate before yielding.
                           Default 100 batches = ~25,000 products.
    Yields:
        list: A chunk of product objects
    """
    api_version = "2024-01"
    session = shopify.Session(shop_url, api_version, token)
    shopify.ShopifyResource.activate_session(session)
    
    products_chunk = []
    
    try:
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.CYAN}📦 Starting Rolling Fetch ({batches_per_yield} batches/chunk)...{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.ENDC}\n")
        
        page_size = 250
        since_id = None
        batch_count = 0
        total_fetched_so_far = 0
        
        while True:
            # Re-activate session before each API call (important after yield)
            shopify.ShopifyResource.activate_session(session)
            
            try:
                # Only pass since_id if we have a valid value
                if since_id:
                    print(f"  {Colors.CYAN}→ Fetching batch #{batch_count + 1} (since_id={since_id})...{Colors.ENDC}")
                    batch = shopify.Product.find(limit=page_size, since_id=since_id)
                else:
                    print(f"  {Colors.CYAN}→ Fetching first batch (no since_id)...{Colors.ENDC}")
                    batch = shopify.Product.find(limit=page_size)
                    
                print(f"  {Colors.GREEN}✓ Got batch, type: {type(batch)}, len: {len(batch) if hasattr(batch, '__len__') else 'N/A'}{Colors.ENDC}")
            except Exception as e:
                import traceback
                print(f"{Colors.RED}Error calling Shopify API: {e}{Colors.ENDC}")
                print(f"{Colors.YELLOW}Debug: since_id={since_id}, batch_count={batch_count}{Colors.ENDC}")
                print(f"{Colors.RED}Traceback:{Colors.ENDC}")
                traceback.print_exc()
                break
            
            # Check if batch is valid
            if batch is None or (isinstance(batch, list) and len(batch) == 0):
                break
            
            # Ensure batch is a list
            if not isinstance(batch, list):
                batch = [batch]
            
            batch_count += 1
            products_chunk.extend(batch)
            
            # Safely get the last product's ID
            try:
                since_id = batch[-1].id
            except (AttributeError, IndexError, TypeError) as e:
                print(f"{Colors.RED}Error getting product ID: {e}{Colors.ENDC}")
                break
                
            total_fetched_so_far += len(batch)
            
            if batch_count % 100 == 0:
                print(f"  {Colors.CYAN}→ Batch {batch_count}: Fetched {len(batch)} products (Total: {total_fetched_so_far}){Colors.ENDC}")
            
            # If we reached the limit for this chunk, yield it
            if batch_count % batches_per_yield == 0:
                print(f"\n{Colors.GREEN}✓ Accessing Chunk #{batch_count // batches_per_yield} ({len(products_chunk)} products)...{Colors.ENDC}")
                yield products_chunk
                products_chunk = [] # Reset for next chunk
                
            # time.sleep(0.1)  # Avoid rate limit
            
            if len(batch) < page_size:
                break
        
        # Yield remaining products if any
        if products_chunk:
            print(f"\n{Colors.GREEN}✓ Accessing Final Chunk ({len(products_chunk)} products)...{Colors.ENDC}")
            yield products_chunk
            
        print(f"\n{Colors.GREEN}✓ All products fetched! Total: {total_fetched_so_far}{Colors.ENDC}")
        
    except Exception as e:
        print(f"{Colors.RED}Error fetching products: {e}{Colors.ENDC}")
    finally:
        shopify.ShopifyResource.clear_session()

def get_image_size_head(url):
    """Fast fetch file size using HEAD request"""
    try:
        response = requests.head(url, timeout=5)
        if 'Content-Length' in response.headers:
            return int(response.headers['Content-Length'])
    except:
        pass
    return 0

def analyze_all_images(products):
    """
    Get sizes of all images from all products using concurrent HEAD requests.
    Returns list of tuples: (image_url, size, product_id, image_id, product_title)
    Sorted by size (largest first)
    """
    print(f"\n{Colors.BOLD}{Colors.YELLOW}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.YELLOW}⚡ Analyzing image sizes for current chunk...{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.YELLOW}{'='*60}{Colors.ENDC}\n")
    
    # Collect all image info
    image_info = []
    for product in products:
        for img in product.images:
            image_info.append({
                'url': img.src,
                'product_id': product.id,
                'image_id': img.id,
                'product_title': product.title
            })
    
    print(f"  {Colors.CYAN}Total images in chunk: {len(image_info)}{Colors.ENDC}")
    print(f"  {Colors.CYAN}Sending {len(image_info)} HEAD requests (5 concurrent workers)...{Colors.ENDC}\n")
    
    # Concurrent fetch sizes
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_info = {
            executor.submit(get_image_size_head, info['url']): info 
            for info in image_info
        }
        
        print(f"  {Colors.YELLOW}⏳ Started fetching sizes... (this may take a while){Colors.ENDC}")
        completed = 0
        for future in as_completed(future_to_info):
            info = future_to_info[future]
            try:
                size = future.result()
                results.append((info['url'], size, info['product_id'], info['image_id'], info['product_title']))
                completed += 1
                if completed % 500 == 0 or completed == len(image_info):
                    print(f"  {Colors.CYAN}Progress: {completed}/{len(image_info)} ({int(completed/len(image_info)*100)}%){Colors.ENDC}")
            except Exception as e:
                results.append((info['url'], 0, info['product_id'], info['image_id'], info['product_title']))
    
    results.sort(key=lambda x: x[1], reverse=True)
    
    print(f"\n{Colors.GREEN}✓ Analysis complete!{Colors.ENDC}")
    print(f"  {Colors.CYAN}Total images: {len(results)}{Colors.ENDC}")
    
    if results:
        print(f"  {Colors.GREEN}📊 Largest image: {get_file_size_display(results[0][1])}{Colors.ENDC}")
        print(f"  {Colors.GREEN}   Product: {results[0][4]} (ID: {results[0][2]}){Colors.ENDC}\n")
    
    return results

def get_bit_depth(mode):
    mode_mapping = {
        "1": 1, "L": 8, "P": 8, "RGB": 8, "RGBA": 8, 
        "CMYK": 8, "YCbCr": 8, "LAB": 8, "HSV": 8, 
        "I": 32, "F": 32
    }
    return mode_mapping.get(mode, "Unknown")

def analyze_image(image_url):
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        image_data = response.content
        file_size_bytes = len(image_data)
        
        img = Image.open(BytesIO(image_data))
        
        width, height = img.size
        mode = img.mode
        bands = img.getbands()
        channels = len(bands)
        bit_depth = get_bit_depth(mode)
        
        print(f"  > Start Analysis: {Colors.CYAN}{image_url}{Colors.ENDC}")
        
        return {
            "url": image_url,
            "size": file_size_bytes,
            "width": width,
            "height": height,
            "format": img.format,
            "mode": mode,
            "channels": f"{channels} ({', '.join(bands)})",
            "bit_depth": f"{bit_depth}-bit"
        }
        
    except Exception as e:
        print(f"    - {Colors.RED}Error analyzing image: {e}{Colors.ENDC}")
        return None

def resize_and_save_image(image_url, image_id):
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        original_size = len(response.content)
        
        img = Image.open(BytesIO(response.content))
        
        MAX_SIZE = (1200, 1200)
        img.thumbnail(MAX_SIZE, Image.Resampling.LANCZOS)
        
        if img.mode == "P":
            img = img.convert("RGBA")
            
        output_path = f"resized_images/{image_id}.webp"

        MAX_FILE_SIZE = 100 * 1024 
        MIN_QUALITY = 20
        
        if original_size < MAX_FILE_SIZE:
            quality = 85
            img.save(output_path, "WEBP", quality=quality)
            new_size = os.path.getsize(output_path)
        else:
            quality = 50
            img.save(output_path, "WEBP", quality=quality)
            new_size = os.path.getsize(output_path)
            
            while new_size > MAX_FILE_SIZE and quality > MIN_QUALITY:
                quality -= 2
                img.save(output_path, "WEBP", quality=quality)
                new_size = os.path.getsize(output_path)
        
        mode = img.mode
        bands = img.getbands()
        channels = len(bands)
        bit_depth = get_bit_depth(mode)
        
        return {
            "path": output_path,
            "size": new_size,
            "width": img.width,
            "height": img.height,
            "format": "WEBP",
            "channels": f"{channels} ({', '.join(bands)})",
            "bit_depth": f"{bit_depth}-bit"
        }
        
    except Exception as e:
        print(f"    - {Colors.RED}Error resizing image: {e}{Colors.ENDC}")
        return None

def sync_images_to_shopify(product_id, report_data, shop_url, token):
    """Upload optimized images to Shopify and replace existing product images"""
    api_version = "2024-01"

    session = shopify.Session(shop_url, api_version, token)
    shopify.ShopifyResource.activate_session(session)
    
    try:
        product = shopify.Product.find(product_id)
        print(f"\n{Colors.BOLD}{Colors.HEADER}Starting sync for: {product.title}{Colors.ENDC}")
        
        success_count = 0
        error_count = 0
        
        for data in report_data:
            image_id = data["id"]
            optimized_path = data["new"]["path"]
            
            try:
                print(f"\n{Colors.CYAN}Processing Image ID: {image_id}{Colors.ENDC}")
                
                target_image = None
                for img in product.images:
                    if img.id == image_id:
                        target_image = img
                        break
                
                if not target_image:
                    print(f"  {Colors.RED}✗ Image not found in product{Colors.ENDC}")
                    error_count += 1
                    continue
                
                with open(optimized_path, 'rb') as f:
                    image_data = f.read()
                
                position = target_image.position
                alt_text = target_image.alt if hasattr(target_image, 'alt') else None
                
                print(f"  {Colors.YELLOW}⟳ Deleting old image...{Colors.ENDC}")
                target_image.destroy()
                
                print(f"  {Colors.YELLOW}⟳ Uploading optimized image...{Colors.ENDC}")
                new_image = shopify.Image()
                new_image.product_id = product_id
                new_image.position = position
                if alt_text:
                    new_image.alt = alt_text
                
                import base64
                new_image.attachment = base64.b64encode(image_data).decode('utf-8')
                
                if new_image.save():
                    print(f"  {Colors.GREEN}✓ Successfully synced (Position: {position}){Colors.ENDC}")
                    success_count += 1
                    time.sleep(0.1)  # Avoid rate limit
                else:
                    print(f"  {Colors.RED}✗ Failed to upload: {new_image.errors.full_messages()}{Colors.ENDC}")
                    error_count += 1
                    
            except Exception as e:
                print(f"  {Colors.RED}✗ Error syncing image {image_id}: {e}{Colors.ENDC}")
                error_count += 1
        
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*50}{Colors.ENDC}")
        print(f"{Colors.BOLD}Sync Summary:{Colors.ENDC}")
        print(f"  {Colors.GREEN}✓ Success: {success_count}{Colors.ENDC}")
        print(f"  {Colors.RED}✗ Failed: {error_count}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*50}{Colors.ENDC}\n")
        
    except Exception as e:
        print(f"{Colors.RED}Error syncing to Shopify: {e}{Colors.ENDC}")
    finally:
        shopify.ShopifyResource.clear_session()


def find_product_by_barcode(barcode, shop_url, token):
    """
    Find product by barcode/SKU using GraphQL API for efficient lookup.
    Args:
        barcode: Product barcode or SKU
        shop_url: Shopify store URL
        token: Access token
    Returns:
        Product ID if found, None otherwise
    """
    try:
        # GraphQL query to search by barcode
        graphql_url = f"https://{shop_url}/admin/api/2024-01/graphql.json"
        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": token
        }
        
        # Search for products with matching barcode
        query = """
        query getProductByBarcode($query: String!) {
            products(first: 10, query: $query) {
                edges {
                    node {
                        id
                        legacyResourceId
                        title
                        variants(first: 100) {
                            edges {
                                node {
                                    barcode
                                    title
                                }
                            }
                        }
                    }
                }
            }
        }
        """
        
        variables = {
            "query": f"barcode:{barcode}"
        }
        
        response = requests.post(
            graphql_url,
            headers=headers,
            json={"query": query, "variables": variables},
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"{Colors.RED}GraphQL API error: {response.status_code}{Colors.ENDC}")
            print(f"{Colors.YELLOW}Response: {response.text[:200]}{Colors.ENDC}")
            return None
        
        data = response.json()
        
        if "errors" in data:
            print(f"{Colors.RED}GraphQL errors: {data['errors']}{Colors.ENDC}")
            return None
        
        products = data.get("data", {}).get("products", {}).get("edges", [])
        
        if not products:
            print(f"{Colors.RED}✗ Product not found for barcode: {barcode}{Colors.ENDC}")
            return None
        
        # Get the first matching product
        product_node = products[0]["node"]
        product_id = product_node["legacyResourceId"]
        product_title = product_node["title"]
        
        # Find which variant has the matching barcode
        matching_variant = None
        for variant_edge in product_node["variants"]["edges"]:
            variant = variant_edge["node"]
            if variant.get("barcode") == str(barcode):
                matching_variant = variant["title"]
                break
        
        print(f"{Colors.GREEN}✓ Found product: {product_title} (ID: {product_id}){Colors.ENDC}")
        if matching_variant:
            print(f"  {Colors.CYAN}Barcode: {barcode} matches variant: {matching_variant}{Colors.ENDC}")
        
        return int(product_id)
        
    except Exception as e:
        import traceback
        print(f"{Colors.RED}Error searching for barcode {barcode}: {e}{Colors.ENDC}")
        traceback.print_exc()
        return None


def get_largest_images_graphql(shop_url, token, limit=25, fetch_limit=100):
    """
    Get largest images from Shopify products using GraphQL.
    Args:
        shop_url: Shopify store URL
        token: Access token
        limit: Number of largest images to return
        fetch_limit: Number of products to fetch
    Returns:
        List of dicts with image info: {image_id, product_id, url, size, width, height}
    """
    graphql_url = f"https://{shop_url}/admin/api/2024-01/graphql.json"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json"
    }
    
    query = """
    query($first: Int!) {
      products(first: $first, sortKey: UPDATED_AT, reverse: true) {
        nodes {
          id
          title
          media(first: 20) {
            nodes {
              ... on MediaImage {
                id
                image {
                  url
                  width
                  height
                }
              }
            }
          }
        }
      }
    }
    """
    
    variables = {"first": fetch_limit}
    
    try:
        response = requests.post(
            graphql_url,
            headers=headers,
            json={"query": query, "variables": variables}
        )
        response.raise_for_status()
        data = response.json()
        
        if "errors" in data:
            print(f"{Colors.RED}GraphQL errors: {data['errors']}{Colors.ENDC}")
            return []
        
        products = data.get("data", {}).get("products", {}).get("nodes", [])
        print(f"{Colors.CYAN}Fetched {len(products)} products{Colors.ENDC}")
        
        images = []
        total_media = 0
        
        for product_idx, product in enumerate(products, 1):
            if not product:
                continue
            
            product_gid = product.get("id", "")
            product_match = re.search(r'Product/(\d+)', product_gid)
            if not product_match:
                continue
            
            product_id = product_match.group(1)
            
            media_nodes = product.get("media", {}).get("nodes", [])
            total_media += len(media_nodes)
            
            if product_idx % 10 == 0:
                print(f"{Colors.CYAN}Processing product {product_idx}/{len(products)}, collected {len(images)} images so far...{Colors.ENDC}")
            
            for media in media_nodes:
                if not media or not media.get("image"):
                    continue
                
                media_gid = media.get("id", "")
                image_match = re.search(r'MediaImage/(\d+)', media_gid)
                if not image_match:
                    continue
                
                image_id = image_match.group(1)
                image_data = media.get("image", {})
                url = image_data.get("url", "")
                width = image_data.get("width", 0)
                height = image_data.get("height", 0)
                
                try:
                    head_response = requests.head(url, timeout=5)
                    file_size = int(head_response.headers.get('content-length', 0))
                except Exception as e:
                    print(f"{Colors.YELLOW}⚠ Could not get size for {url[:50]}... : {e}{Colors.ENDC}")
                    file_size = 0
                
                file_size_mb = file_size / (1024 * 1024) if file_size else 0
                
                images.append({
                    "image_id": image_id,
                    "product_id": product_id,
                    "url": url,
                    "gid": media_gid,
                    "file_size": file_size,
                    "file_size_mb": round(file_size_mb, 2),
                    "width": width,
                    "height": height
                })
        
        print(f"{Colors.CYAN}Collected {len(images)} images from {total_media} total media{Colors.ENDC}")
        
        images.sort(key=lambda x: x['file_size'], reverse=True)
        
        top_images = images[:limit]
        
        print(f"{Colors.GREEN}✓ Returning top {len(top_images)} largest images{Colors.ENDC}")
        if top_images:
            print(f"{Colors.CYAN}Largest: {top_images[0]['file_size_mb']}MB (Product {top_images[0]['product_id']}){Colors.ENDC}")
        return top_images
        
    except Exception as e:
        print(f"{Colors.RED}Error fetching images via GraphQL: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        return []


def get_product_id_from_image(image_id, shop_url, token):
    """
    Get product ID from image ID using REST API.
    Args:
        image_id: Image ID
        shop_url: Shopify store URL
        token: Access token
    Returns:
        Product ID or None
    """
    api_version = "2024-01"
    session = shopify.Session(shop_url, api_version, token)
    shopify.ShopifyResource.activate_session(session)
    
    try:
        products = shopify.Product.find(limit=250)
        for product in products:
            for image in product.images:
                if str(image.id) == str(image_id):
                    return product.id
        
        return None
    except Exception as e:
        print(f"{Colors.RED}Error finding product for image {image_id}: {e}{Colors.ENDC}")
        return None
    finally:
        shopify.ShopifyResource.clear_session()


def get_product_ids_from_barcodes(barcodes, shop_url, token):
    """
    Convert list of barcodes to list of product IDs using GraphQL (FAST).
    Args:
        barcodes: List of barcodes
        shop_url: Shopify store URL
        token: Access token
    Returns:
        List of product IDs (None for barcodes not found)
    """
    graphql_url = f"https://{shop_url}/admin/api/2024-01/graphql.json"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json"
    }
    
    barcode_to_product_id = {}
    barcodes_set = {str(b) for b in barcodes}
    
    query = """
    query($first: Int!, $after: String) {
      products(first: $first, after: $after) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          variants(first: 20) {
            nodes {
              barcode
            }
          }
        }
      }
    }
    """
    
    try:
        print(f"{Colors.CYAN}Searching {len(barcodes)} barcodes via GraphQL...{Colors.ENDC}")
        
        after_cursor = None
        page_count = 0
        
        while len(barcode_to_product_id) < len(barcodes_set):
            page_count += 1
            variables = {"first": 250, "after": after_cursor}
            
            if page_count % 5 == 0:
                print(f"{Colors.CYAN}Page {page_count}: Found {len(barcode_to_product_id)}/{len(barcodes_set)} barcodes...{Colors.ENDC}")
            
            response = requests.post(
                graphql_url,
                headers=headers,
                json={"query": query, "variables": variables},
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                print(f"{Colors.RED}GraphQL errors: {data['errors']}{Colors.ENDC}")
                break
            
            products_data = data.get("data", {}).get("products", {})
            products = products_data.get("nodes", [])
            page_info = products_data.get("pageInfo", {})
            
            for product in products:
                if not product:
                    continue
                
                product_gid = product.get("id", "")
                product_match = re.search(r'Product/(\d+)', product_gid)
                if not product_match:
                    continue
                
                product_id = product_match.group(1)
                variants = product.get("variants", {}).get("nodes", [])
                
                for variant in variants:
                    if not variant:
                        continue
                    
                    barcode = str(variant.get("barcode", "")) if variant.get("barcode") else None
                    if barcode and barcode in barcodes_set and barcode not in barcode_to_product_id:
                        barcode_to_product_id[barcode] = product_id
                        print(f"{Colors.GREEN}✓ Found barcode {barcode} -> Product ID {product_id}{Colors.ENDC}")
            
            if len(barcode_to_product_id) >= len(barcodes_set):
                print(f"{Colors.GREEN}✓ Found all barcodes!{Colors.ENDC}")
                break
            
            if not page_info.get("hasNextPage"):
                break
            
            after_cursor = page_info.get("endCursor")
        
        product_ids = []
        for barcode in barcodes:
            barcode_str = str(barcode)
            product_id = barcode_to_product_id.get(barcode_str)
            product_ids.append(product_id)
            if not product_id:
                print(f"{Colors.YELLOW}⚠ Barcode {barcode_str} not found{Colors.ENDC}")
        
        found_count = sum(1 for pid in product_ids if pid is not None)
        print(f"{Colors.GREEN}✓ Found {found_count}/{len(barcodes)} products (in {page_count} pages){Colors.ENDC}")
        
        return product_ids
        
    except Exception as e:
        print(f"{Colors.RED}Error searching for barcodes: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        return [None] * len(barcodes)


def get_product_images(product_id, shop_url, token, auto_sync=None):
    """
    Process product images: fetch, optimize, and optionally sync to Shopify.
    Args:
        product_id: Shopify product ID
        shop_url: Shopify store URL
        token: Access token
        auto_sync: Optional. True = auto sync, False = skip sync, None = ask user
    Returns:
        True if all images were skipped (small size), False otherwise
    """
    api_version = "2024-01"

    session = shopify.Session(shop_url, api_version, token)
    shopify.ShopifyResource.activate_session(session)
    
    report_data = []

    try:
        product = shopify.Product.find(product_id)
        if not product:
            return True # Should not happen, but safe to skip

        for image in product.images:
            orig_stat = analyze_image(image.src)
            new_stat = resize_and_save_image(image.src, image.id)
            
            if orig_stat and new_stat:
                report_data.append({
                    "id": image.id,
                    "orig": orig_stat,
                    "new": new_stat
                })
            
    except Exception as e:
        print(f"{Colors.RED}Error fetching product: {e}{Colors.ENDC}")
        return False
    finally:
        shopify.ShopifyResource.clear_session()

    if report_data:
        filename = f"report-{product_id}.html"
        generate_html_report(report_data, filename=filename, product_id=product_id, shop_url=shop_url)
        
        should_sync = False
        
        if auto_sync is True:
            print(f"\n{Colors.GREEN}✓ Auto-sync enabled{Colors.ENDC}")
            should_sync = True
        elif auto_sync is False:
            print(f"\n{Colors.YELLOW}⊘ Auto-sync disabled - Skipping sync{Colors.ENDC}")
            should_sync = False
        else:
            print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*50}{Colors.ENDC}")
            print(f"{Colors.BOLD}Do you want to sync optimized images to Shopify? (yes/no): {Colors.ENDC}", end='')
            user_input = input().strip().lower()
            should_sync = user_input in ['yes', 'y']
        
        if should_sync:
            print(f"{Colors.BOLD}{Colors.GREEN}Starting sync process...{Colors.ENDC}")
            sync_images_to_shopify(product_id, report_data, shop_url, token)
            return False
        elif auto_sync is None:
            print(f"{Colors.YELLOW}Sync cancelled by user.{Colors.ENDC}")
            return False
            
    # If no report data, it means all images were skipped (small size)
    # Return True to signal that this product can be cached as skipped
    return True


if __name__ == "__main__":
    from report_generator import generate_index_html
    generate_index_html()    

    # Select store first
    shop_url, token = select_store(2)
    
    # Auto sync setting
    auto_sync = True
    
    # Predefined list of barcodes to process
    BARCODES = [
        "4902370536423", "4573102609243", "4573102609243", "4573102609243",
        "4580717790143", "4580717790150", "4902370536423", "4902370536423",
        "4543112382573", "4580590123212", "4580590121966", "4521329333885",
        "4902370521405", "4981328062412", "4580416906579", "4571368443588",
        "4902370520804", "1686275146", "4571368443588", "4521329418667",
        "4580416905091", "4521329370514", "4902370521405", "4580717790143",
        "4580717790150", "4961818036680", "4571368443588", "4902370520521",
        "4988635000076", "4580717790143", "4580717790150", "4521329425627",
        "4521329418667", "4571558940118", "4571558940101", "4580416903264",
        "4902370533224", "4988635000076", "4902370520538", "4988635000076",
        "4902425756806", "4902370533224", "4580416902786", "4520741443332",
        "4945265361205", "4521329333878", "4990270141960", "4521329370514",
        "4945265359110", "4529128541791", "4988635000076", "4945265361205",
        "4520741313109", "4902370521405", "4981328065529", "4945265359653",
        "4580590122802", "4580416909297", "4580590123205", "4981328062412",
        "4543736094777", "4520741313109", "4988601271370", "4573102656605",
        "4988601271387", "4521329333878", "4513266252046", "4988635000076",
        "4580590121959", "4945265359356", "4990270141960", "4573102577146",
        "4580416906623", "4580590126138", "4945265359653", "4902370533224",
        "4562252050333", "4562252053358", "4580416909754", "4573102567550",
        "4543736030843", "4521329333885", "630870351188", "4571368443915",
        "4529128541760", "4573102583086", "4573102580962", "4521329333885",
        "4580416905190", "4573102656605", "4580416902502", "4571368443588",
        "4521329333878", "4580694042358", "4573102588616", "4529128301098",
        "4902370520538", "4580590122253", "4945265359646", "4970381502997",
        "4580590122246", "4543736988793", "4543112204691", "4580590126190",
        "4902370521405", "4582191969107", "4580694042358", "4573102616722",
        "4582191969107", "4990270140956", "4580590126473", "4573102612540",
        "4990270141960", "4580590122031", "4543112610164", "4582191969107",
        "4580416905091", "4901126128783", "4580590153622", "4580416903264",
        "4945265366774", "4543736329114", "4580683605939", "4945265361113",
        "4580590122819", "4543112488275", "4573102567543", "4543112341013",
        "4580416905091", "4580590126350", "4573102567543", "4580590126701",
        "4580590126213", "4580749604708", "4582286323784", "4580590126848",
        "4573102567536", "4549913081899", "4580590126183", "4580590125018",
        "4543736329916", "4573102558565", "4543112314130", "4573102577139",
        "4945265349036", "4573102619914", "4974413803755", "4580416907958",
        "4529128301197", "4543736985600", "4902370520804", "4580590126824",
        "4580590126923", "4529128301050", "4545784067789", "4573102577153",
        "4573102616630", "4990270135242", "4543736329879", "4580416905688",
        "4543112605412", "4580416904124", "4573102567536", "4573102612540",
        "4580590126503", "4543736327790", "4573102577146", "4573102589231",
        "4529128541241", "4543736332923", "4513266252169", "4543112060471",
        "4904810011132", "4973307696282", "4543112384164", "4580590122574",
        "4580416901178", "4580590125209", "4529128301135", "4543736329114",
        "4945265359370"
    ]
    
    # Product IDs mode - paste extracted IDs here
    PRODUCT_IDS = [
    "7308411732126",
    "7253434990750",
    "7612498575518",
    "7251350388894",
    "8359437435038",
    "7253496332446",
    "7256712675486",
    "8556238766238",
    "8556239323294",
    "7308386828446",
    "8421163008158",
    "7379066093726",
    "7308396560542",
    "8055065706654",
    "7251358810270",
    "7306647208094",
    "7308435226782",
    "7253323939998",
    "7308404162718",
    "7308399640734",
    "8113027907742",
    "7308439617694",
    "7306637672606",
    "7296568852638",
    "8055062003870",
    "7241923821726",
    "8603940913310",
    "7250785435806",
    "8138828677278",
    "7696114483358",
    "7309125288094",
    "7502607024286",
    "7308544475294",
    "7306604347550",
    "7502429094046",
    "7502498037918",
    "7076945002654",
    "7252435796126",
    "7502428831902",
    "8055061053598",
    "8138803282078",
    "7672201347230",
    "7366103007390",
    "7307522834590",
    "7625021784222",
    "7519724634270",
    "7252323860638",
    "7669791129758",
    "7519948832926",
    "7308553879710",
    "7309788610718",
    "7502603321502",
    "8055060332702",
    "7403712807070",
    "8049018994846",
    "7308415664286",
    "7502421000350",
    "7240488288414",
    "7357003890846",
    "7309159563422",
    "7306655531166",
    "7310322925726",
    "7312960553118",
    "7671011410078",
    "8138835755166",
    "7523770925214",
    "7802735591582",
    "7803254243486",
    "7523745038494",
    "8138839326878",
    "7253480308894",
    "7404590268574",
    "7309163823262",
    "7502426308766",
    "7603207078046",
    "7517070000286",
    "7296126746782",
    "8153063260318",
    "7241923592350",
    "8138842570910",
    "8050403967134",
    "7616433455262",
    "7256939200670",
    "7361434157214",
    "7263827886238",
    "7241923788958",
    "7318793060510",
    "8138838376606",
    "7291214430366",
    "7242021929118",
    "7313035296926",
    "7597619773598",
    "7309834518686",
    "8055060988062",
    "8138842407070",
    "7589428887710",
    "8138842636446",
    "7295025283230",
    "7672199217310",
    "7251370279070",
    "7080305918110",
    "7803919728798",
    "7502592737438",
    "7048873509022",
    "7307923718302",
    "7312977559710",
    "7597667877022",
    "8050427035806",
    "7516769910942",
    "7502425850014",
    "8138837721246",
    "7502426931358",
    "8138842308766",
    "8047837839518",
    "7307494883486",
    "7318782640286",
    "7307516149918",
    "7307520376990",
    "7307512316062",
    "7307507663006",
    "7078899744926",
    "7078898172062",
    "7241927590046",
    "7696117006494",
    "7252309770398",
    "7891121012894",
    "8161087783070",
    "7307948327070",
    "7309841531038",
    "7519676072094",
    "7309032226974",
    "7519992742046",
    "7523748839582",
    "7502497546398",
    "7307923062942",
    "7307517067422",
    "7307507269790",
    "7307493408926",
    "7696474144926",
    "7312976380062",
    "7519720439966",
    "7243593711774",
    "7519669092510",
    "7256623874206",
    "7313010950302",
    "7296604340382",
    "7296831815838",
    "7695545499806",
    "8138843029662",
    "8138805411998",
    "7308626460830",
    "7291245101214",
    "7306518200478",
    "7308549488798",
    "7308471074974",
    "7318924755102",
    "7240464040094",
    "7696133456030",
    "7294082056350",
    "8138805444766",
    "7307509006494",
    "7309179945118",
    "7313695113374",
    "7519673778334",
    "7312769286302",
    "7502502527134",
    "8050186027166",
    "7306627383454",
    "7308595036318",
    "7855228059806",
    "7069281845406",
    "7318766289054",
    "7313678565534",
    "8053896249502",
    "7616284688542",
    "7311340208286",
    "8138842374302",
    "7044264657054",
    "7516768567454",
    "7227010449566",
    "8138842013854",
    "7672199708830",
    "7306627055774",
    "7312966156446",
    "7616386171038",
    "7256428118174",
    "7519988744350",
    "8055074717854",
    "8055073046686",
    "8453248385182",
    "8257258258590",
    "7310354972830",
    "7308337414302",
    "7589449564318",
    "7148164120734",
    "7523776430238",
    "8365605912734",
    "7578784006302",
    "7309853819038",
    "7294091231390",
    "8055063904414",
    "7311391391902",
    "7589468504222",
    "7603136626846",
    "7519985139870",
    "7313733386398",
    "7307351851166",
    "7251486441630",
    "7346062753950",
    "7520000934046",
    "7256751308958",
    "7306594910366",
    "8071267745950",
    "7307515101342",
    "7309098746014",
    "7696124870814",
    "7848683208862",
    "7311197012126",
    "7307948654750",
    "7308418875550",
    "8050407080094",
    "7521155186846",
    "8138805969054",
    "8049974280350",
    "7312946200734",
    "8055066034334",
    "7521177829534",
    "7668887421086",
    "7250358042782",
    "7309140328606",
    "7309095108766",
    "7255680876702",
    "8050413043870",
    "7151062220958",
    "7520000376990",
    "7308597264542",
    "7308674793630",
    "7568854057118",
    "7311261597854",
    "7603375734942",
    "7306639278238",
    "7308987629726",
    "7520000344222",
    "7523851665566",
    "7319425253534",
    "7502425096350",
    "7313473863838",
    "7520000606366",
    "7306660544670",
    "7519988875422",
    "7307533353118",
    "8047827320990",
    "7308363006110",
    "8050603262110",
    "7603365347486",
    "7313024221342",
    "7250223759518",
    "8138842964126",
    "7255289856158",
    "7252440219806",
    "7256768708766",
    "7256700846238",
    "7255366926494",
    "7254435594398",
    "7253536080030",
    "7253326233758",
    "7251534512286",
    "7251360284830",
    "7307524047006",
    "7292475932830",
    "7308498174110",
    "7076946378910",
    "7317537063070",
    "7252549304478",
    "7479627874462",
    "7695564472478",
    "7241908289694",
    "7502502264990",
    "7309059424414",
    "7502501937310",
    "7314850185374",
    "7309044285598",
    "7307844812958",
    "7308588712094",
    "7126142189726",
    "7696491085982",
    "7313692885150",
    "7307939315870",
    "7669797486750",
    "7519989694622",
    "7519994740894",
    "7519988940958",
    "7308395151518",
    "7361481932958",
    "7519991234718",
    "7603412828318",
    "8244197949598",
    "7329937948830",
    "7311230927006",
    "7603160514718",
    "7616280232094",
    "7307494031518",
    "7502496268446",
    "7227473821854",
    "8138838147230",
    "7310333444254",
    "8050647662750",
    "7311241740446",
    "7309112934558",
    "7308394266782",
    "7307902156958",
    "8071284195486",
    "7318761341086",
    "7622294667422",
    "8169937371294",
    "7296691273886",
    "7307525390494",
    "7519998869662",
    "8383139119262",
    "8383138955422",
    "7253484830878",
    "7251376079006",
    "7308509053086",
    "7670390685854",
    "7256413372574",
    "7502499381406",
    "7240488124574",
    "7314887737502",
    "7310337802398",
    "7516639592606",
    "7519997231262",
    "7519988088990",
    "7519674892446",
    "7308378603678",
    "7695543828638",
    "7255558062238",
    "8055066820766",
    "8055066656926",
    "8055066624158",
    "7517034872990",
    "7291184152734",
    "7695550087326",
    "7318289121438",
    "7502598537374",
    "7696124084382",
    "8244201881758",
    "7603087999134",
    "7296649887902",
    "7314979127454",
    "7255535321246",
    "7241923362974",
    "7296567345310",
    "7308392661150",
    "7802661011614",
    "7329942896798",
    "7502498431134",
    "7078913278110",
    "7077901861022",
    "7409210949790",
    "7519990939806",
    "7318288302238",
    "7292503720094",
    "8336401301662",
    "7292425797790",
    "7603077578910",
    "7311174664350",
    "7521170194590",
    "7241920512158",
    "7251549749406",
    "7308436308126",
    "7308980322462",
    "7603530334366",
    "7296647102622",
    "7603387695262",
    "7296858947742",
    "7293931552926",
    "7669798535326",
    "7597696581790",
    "7307865194654",
    "7387419050142",
    "7306553688222",
    "7802445201566",
    "7519991660702",
    "8067201859742",
    "8337677451422",
    "7292411281566",
    "7603335463070",
    "7519951913118",
    "7306634199198",
    "7519996182686",
    "7622302728350",
    "7308477726878",
    "7603304005790",
    "7137731084446",
    "8138838179998",
    "7622300795038",
    "7519987531934",
    "7307536695454",
    "8138843062430",
    "8042834591902",
    "7694678229150",
    "7062602580126",
    "8055064723614",
    "7891115376798",
    "7309102612638",
    "7308582387870",
    "8459333894302",
    "7502434271390",
    "7307534860446",
    "7309877346462",
    "7502424932510",
    "7306076520606",
    "7379402522782",
    "7311197864094",
    "7309161562270",
    "7296880574622",
    "7317552136350",
    "7308620136606",
    "8050404098206",
    "7603002671262",
    "7313481695390",
    "7308481495198",
    "7296542507166",
    "7296181928094",
    "7632996499614",
    "7311400796318",
    "7313042833566",
    "7622305087646",
    "7519992119454",
    "7309044056222",
    "7296633798814",
    "8138838573214",
    "7387324612766",
    "7256684298398",
    "7250718720158",
    "7549694509214",
    "7308568068254",
    "7308986974366",
    "7256447778974",
    "7309889634462",
    "7311244755102",
    "7523745595550",
    "7307903697054",
    "7238460833950",
    "7622297518238",
    "7603432063134",
    "8257258291358",
    "7519687377054",
    "7126146744478",
    "7312982343838",
    "8138842439838",
    "8049970053278",
    "7253636710558",
    "7297551892638",
    "7309120766110",
    "7250322948254",
    "7243591024798",
    "7308337774750",
    "7802494025886",
    "7297556054174",
    "7253608661150",
    "7311416328350",
    "7519999131806",
    "7502425161886",
    "8138839982238",
    "8339033456798",
    "7696486236318",
    "7311261434014",
    "7307494162590",
    "7306536550558",
    "7502325153950",
    "8115607240862",
    "7523775807646",
    "7616339542174",
    "8055075176606",
    "8055073177758",
    "7502430437534",
    "7695537799326",
    "7672200691870",
    "8138838081694",
    "7519984779422",
    "7318794403998",
    "7307349393566",
    "7318749446302",
    "7519999492254",
    "7295290114206",
    "7401980952734",
    "8071268532382",
    "7589532434590",
    "7313468194974",
    "7293938598046",
    "7307915853982",
    "7848688418974",
    "7296188743838",
    "7309249872030",
    "7308672958622",
    "7311251374238",
    "7891104825502",
    "7307364728990",
    "8138842275998",
    "7696509403294",
    "7519994806430",
    "7519992938654",
    "7307521622174",
    "7307516903582",
    "7694686486686",
    "7308571345054",
    "7696134439070",
    "7296015368350",
    "8049962451102",
    "8138843193502",
    "7603088425118",
    "7695561654430",
    "7312964878494",
    "8055077470366",
    "7523758112926",
    "7515188986014",
    "7515188002974",
    "7515187576990",
    "7307950227614",
    "7516637003934",
    "7521192706206",
    "7297296892062",
    "7292409544862",
    "7309454508190",
    "7521156628638",
    "8050182815902",
    "7519676268702",
    "7849222307998",
    "8047829221534",
    "7549692543134",
    "7519983042718",
    "7306634789022",
    "8035974742174",
    "7672200560798",
    "7296555352222",
    "7307517755550",
    "7891112788126",
    "7126175875230",
    "7696117170334",
    "7403826413726",
    "7255618093214",
    "7849222471838",
    "7849080651934",
    "7307517591710",
    "7126177448094",
    "7670399729822",
    "7517034807454",
    "7375141830814",
    "7255320592542",
    "7670051242142",
    "7670051209374",
    "7670389801118",
    "7241923625118",
    "7308675612830",
    "7311393128606",
    "7670383837342",
    "7307947081886",
    "7309127614622",
    "7695551922334",
    "8249920290974",
    "7296648773790",
    "7253690613918",
    "7502427816094",
    "8138838311070",
    "7311372484766",
    "7309780058270",
    "7848687730846",
    "7252546977950",
    "7597652050078",
    "7309061882014",
    "7251369427102",
    "8149942730910",
    "7313037426846",
    "7306611720350",
    "8138838278302",
    "7318764191902",
    "7296695664798",
    "7502424015006",
    "8138839752862",
    "7309228048542",
    "8439725752478",
    "7848674656414",
    "7312963862686",
    "7589574246558",
    "8055058301086",
    "7695550382238",
    "8299843911838",
    "7296549978270",
    "8071817330846",
    "7313777459358",
    "7502423195806",
    "7307526111390",
    "7251437224094",
    "7254435397790",
    "7312692609182",
    "7696505012382",
    "7308379947166",
    "8050429657246",
    "7126141698206",
    "7523779575966",
    "7671021076638",
    "7516756803742",
    "7318798827678",
    "7312712597662",
    "7309215432862",
    "8050430410910",
    "7301580062878",
    "8055074422942",
    "8055073341598",
    "7694700052638",
    "7674091012254",
    "7502497841310",
    "7307522998430",
    "7622293717150",
    "7696139649182",
    "7597691601054",
    "8048631480478",
    "7616468123806",
    "7307940331678",
    "7255653941406",
    "7293362995358",
    "7694684389534",
    "7293346939038",
    "7255560847518",
    "7256894996638",
    "7502499971230",
    "7603148980382",
    "7310353563806",
    "7256733089950",
    "7311367864478",
    "7309136101534",
    "7670389866654",
    "7313472553118",
    "7312930767006",
    "7250339692702",
    "7306664312990",
    "7295962677406",
    "8071289602206",
    "7603209109662",
    "7313699078302",
    "7519952470174",
    "7319055368350",
    "7671007445150",
    "7253473034398",
    "7389878747294",
    "7308969803934",
    "7313002659998",
    "7309036814494",
    "7297315176606",
    "7516632842398",
    "7516758573214",
    "7308651528350",
    "7674091471006",
    "7696126574750",
    "7313675321502",
    "7695565160606",
    "7250750013598",
    "8138840735902",
    "7309200687262",
    "7291147059358",
    "7669796634782",
    "7502425948318",
    "7318750101662",
    "7695554904222",
    "7313696456862",
    "7309061980318",
    "8048641507486",
    "7519987663006",
    "8049964581022",
    "7307523883166",
    "7309109297310",
    "7297392672926",
    "7696482762910",
    "7251563446430",
    "7319422238878",
    "7517056336030",
    "7308663652510",
    "7318759669918",
    "7315626262686",
    "7307903434910",
    "7252317634718",
    "7253387215006",
    "7891125338270",
    "7309038092446",
    "7502423720094",
    "7252424917150",
    "7311292137630",
    "7521193853086",
    "7253445935262",
    "7523768205470",
    "7670049996958",
    "7670049603742",
    "8141251477662",
    "7240486944926",
    "7301579178142",
    "7078898598046",
    "7389113188510",
    "7389133602974",
    "7389100802206",
    "7242989404318",
    "7519652610206",
    "7301594022046",
    "8055061086366",
    "7251473170590",
    "7253695627422",
    "7802375635102",
    "7307941150878",
    "7310340685982",
    "7263829328030",
    "7311403614366",
    "7252598096030",
    "7848686649502",
    "7603210027166",
    "7318765273246",
    "7502439710878",
    "7294146281630",
    "7293946298526",
    "7240505360542",
    "7240486781086",
    "7668881490078",
    "7502425751710",
    "7519993757854",
    "7307493507230",
    "7126160408734",
    "7318750363806",
    "7306611490974",
    "7696122773662",
    "8138836443294",
    "7694696513694",
    "7318261629086",
    "7502501707934",
    "7502428799134",
    "7293946691742",
    "7318765863070",
    "7308628426910",
    "7076898504862",
    "7589427052702",
    "7523771777182",
    "7603066699934",
    "7251353665694",
    "7078915309726",
    "7078903447710",
    "8451947036830",
    "7670391144606",
    "7523775512734",
    "7308483330206",
    "7622300369054",
    "7622301286558",
    "7696472768670",
    "7502595326110",
    "7307891900574",
    "7308629737630",
    "7240509423774",
    "7819921162398",
    "7519717949598",
    "7589470929054",
    "7672203739294",
    "7517130293406",
    "7255319347358",
    "7519992873118",
    "7309282803870",
    "8049984471198",
    "7597658669214",
    "7519943098526",
    "7318752460958",
    "7632995680414",
    "8050646712478",
    "7311412920478",
    "8374277144734",
    "7670391341214",
    "7318255796382",
    "7138295808158",
    "8371472924830",
    "7849108832414",
    "7536543989918",
    "7308661981342",
    "7516634841246",
    "7306537861278",
    "8257258029214",
    "7670055403678",
    "7670055305374",
    "7307394220190",
    "7670055796894",
    "7670055698590",
    "7670054944926",
    "7670054813854",
    "7603371475102",
    "8138839425182",
    "7310332133534",
    "7309041139870",
    "7521175994526",
    "7802382844062",
    "7802370883742",
    "7295141806238",
    "7309115031710",
    "7254515875998",
    "7308342165662",
    "7622289391774",
    "8111309193374",
    "7313792303262",
    "7313479401630",
    "7597628293278",
    "7519988613278",
    "8463922397342",
    "7502600896670",
    "7603139444894",
    "8153058803870",
    "7849081929886",
    "7849190949022",
    "7307493638302",
    "7308598837406",
    "8050454921374",
    "7696521691294",
    "7296649494686",
    "7616443449502",
    "7673709035678",
    "7308317032606",
    "7578993492126",
    "7318261006494",
    "7616348913822",
    "7519992316062",
    "7253610954910",
    "7307921096862",
    "7695537209502",
    "7502496956574",
    "7312966910110",
    "7696125493406",
    "7251589628062",
    "7309466730654",
    "7519999918238",
    "7296880771230",
    "7502596604062",
    "7696128278686",
    "8603273822366",
    "7517080223902",
    "7616286982302",
    "8050186551454",
    "7126159818910",
    "7126148186270",
    "7291205812382",
    "7307846713502",
    "7521177993374",
    "7694675312798",
    "7308317130910",
    "7891115606174",
    "7312760635550",
    "7311326609566",
    "7386670203038",
    "8138838409374",
    "8055130030238",
    "7357027156126",
    "7363311501470",
    "7313693376670",
    "7315385450654",
    "7520000147614",
    "7517036380318",
    "7083146805406",
    "7695556247710",
    "7307923259550",
    "7308660801694",
    "7311214379166",
    "7669808103582",
    "7597654048926",
    "7126144811166",
    "7502592868510",
    "8071290192030",
    "7311325462686",
    "7589455462558",
    "8138838245534",
    "7519983927454",
    "7516633890974",
    "7670372073630",
    "7313711628446",
    "7296010092702",
    "7255380263070",
    "8214204743838",
    "7849098412190",
    "8138838343838",
    "7311221391518",
    "7696472637598",
    "7313691050142",
    "7519996772510",
    "7309091733662",
    "7307891671198",
    "7312967008414",
    "7296600211614",
    "7311267168414",
    "7670368043166",
    "7802630439070",
    "7696140304542",
    "7696482861214",
    "7307938758814",
    "7520445825182",
    "8050429886622",
    "8138841981086",
    "7301594677406",
    "7603058671774",
    "7696127983774",
    "7241926836382",
    "7252455751838",
    "7694680195230",
    "7695584788638",
    "7480318591134",
    "7616289079454",
    "7308331909278",
    "7670375645342",
    "7256406818974",
    "8071772209310",
    "7308415533214",
    "7296871563422",
    "7622271369374",
    "7694677049502",
    "8072666251422",
    "7296877330590",
    "7696112418974",
    "7309456015518",
    "7521136803998",
    "8380697444510",
    "7297291452574",
    "7803587133598",
    "7307856740510",
    "7386598441118",
    "8055075307678",
    "7250721210526",
    "7312981852318",
    "7126153035934",
    "7309044842654",
    "8273596514462",
    "7226952712350",
    "7076925014174",
    "7318928195742",
    "7308511215774",
    "7312964485278",
    "7313480286366",
    "7256413110430",
    "7502425194654",
    "7312701489310",
    "8138843095198",
    "7502502166686",
    "7069196714142",
    "7502497415326",
    "7502498267294",
    "7227011072158",
    "7252463026334",
    "7309046382750",
    "7311329001630",
    "8050636390558",
    "7696487022750",
    "8050178195614",
    "7695545401502",
    "7311311601822",
    "7255541645470",
    "7520017219742",
    "7670393634974",
    "7694687043742",
    "7696486006942",
    "7674111197342",
    "7519990874270",
    "7307917033630",
    "8049975853214",
    "8211190939806",
    "7695547990174",
    "8047833055390",
    "8047827255454",
    "7313698947230",
    "7502323351710",
    "7891121307806",
    "7616472416414",
    "7696499605662",
    "7297419640990",
    "8138836115614",
    "7308403736734",
    "7578783285406",
    "7578780631198",
    "8138836181150",
    "7318292824222",
    "7307916017822",
    "7243247648926",
    "7296708346014",
    "7517128720542",
    "7589514150046",
    "7671008690334",
    "7241908519070",
    "7308645302430",
    "8115650789534",
    "7250898321566",
    "7311242133662",
    "8047831482526",
    "7296842268830",
    "7126145237150",
    "7307354505374",
    "7126148645022",
    "7307370332318",
    "7253438333086",
    "7311386837150",
    "7242989699230",
    "7251402260638",
    "7297556021406",
    "7694692122782",
    "7696492626078",
    "7294090182814",
    "7848693235870",
    "7695555788958",
    "7696516841630",
    "7309035503774",
    "7520000082078",
    "7670382395550",
    "7502426538142",
    "7387407843486",
    "7696483123358",
    "7293941842078",
    "7295136006302",
    "7241918611614",
    "7694704672926",
    "7307361288350",
    "7519989104798",
    "7311187017886",
    "7694700019870",
    "7293253746846",
    "7293396091038",
    "7313694523550",
    "7296181272734",
    "8047827386526",
    "7312639361182",
    "7296021299358",
    "8138842210462",
    "7311268511902",
    "7502426243230",
    "7255739236510",
    "7531309007006",
    "7310335836318",
    "7250210193566",
    "7253475721374",
    "7138121547934",
    "7603474530462",
    "7582653743262",
    "7271789953182",
    "7568936140958",
    "7315052495006",
    "7311273001118",
    "7296605454494",
    "8138836934814",
    "7307396513950",
    "8169432187038",
    "8383138889886",
    "7301598118046",
    "8244196442270",
    "7309137477790",
    "8071277838494",
    "7519984287902",
    "7294151360670",
    "7891122716830",
    "7802398572702",
    "7308399706270",
    "8439720116382",
    "7292433924254",
    "7308306645150",
    "7307921883294",
    "7308317163678",
    "7308314247326",
    "7307922571422",
    "7309219791006",
    "7296021102750",
    "7240466563230",
    "7695543959710",
    "7309038846110",
    "7603474923678",
    "7519993790622",
    "7309835436190",
    "7696131522718",
    "7308416778398",
    "7597670367390",
    "7670387572894",
    "7632996106398",
    "8049969954974",
    "7295333007518",
    "7318778609822",
    "7309037600926",
    "8138835984542",
    "8249922158750",
    "7603299844254",
    "7256709071006",
    "7318751019166",
    "7589541871774",
    "7848674033822",
    "7622316589214",
    "7519989629086",
    "8214199763102",
    "7251426181278",
    "7849198813342",
    "8459360043166",
    "7502601814174",
    "7312714236062",
    "8045384040606",
    "7603130106014",
    "7521147453598",
    "7250271305886",
    "7312992731294",
    "7296600408222",
    "7308482511006",
    "7803886928030",
    "7603459195038",
    "7597620625566",
    "8339046400158",
    "7672208556190",
    "7311345647774",
    "8565807939742",
    "7674110967966",
    "8390985187486",
    "7152852402334",
    "7891108495518",
    "7848705523870",
    "8115694502046",
    "8050450694302",
    "7671013441694",
    "8244190150814",
    "8153050775710",
    "7694680653982",
    "7589517394078",
    "7356777070750",
    "7858102403230",
    "7571976421534",
    "7597681082526",
    "7313735876766",
    "7250799493278",
    "8231679918238",
    "7668886798494",
    "7408273784990",
    "7312900915358",
    "7616409927838",
    "8153047957662",
    "8375433035934",
    "8171032379550",
    "7502324531358",
    "7502323056798",
    "7295175983262",
    "7318932095134",
    "7293943513246",
    "8365609582750",
    "7306561552542",
    "7387407941790",
    "7622294405278",
    "8111913631902",
    "8071283507358",
    "8316311240862",
    "7571970097310",
    "8115607306398",
    "7597653360798",
    "7803902066846",
    "7803859599518",
    "7803796979870",
    "7803611906206",
    "7803428208798",
    "7803363262622",
    "7803152269470",
    "7803123925150",
    "7803095613598",
    "7802957070494",
    "7802823245982",
    "7802821968030",
    "7802613760158",
    "7802556481694",
    "7802522206366",
    "7312708370590",
    "7387410989214",
    "7311218999454",
    "7366150881438",
    "7622303154334",
    "7308987269278",
    "7597707329694",
    "7597703823518",
    "8082084069534",
    "8347267694750",
    "8244171636894",
    "8045427556510",
    "7803878146206",
    "7349993046174",
    "8257258422430",
    "8346625671326",
    "7297272250526",
    "7293237035166",
    "7255270490270",
    "8363750523038",
    "7257559367838",
    "8262871318686",
    "8323254386846",
    "7250889015454",
    "8221953917086",
    "8244177895582",
    "8050556895390",
    "7296851771550",
    "8229399986334",
    "8115675365534",
    "7309819445406",
    "8211198673054",
    "8244195917982",
    "8199914651806",
    "7669802205342",
    "7668880736414",
    "7803864350878",
    "7803844100254",
    "7803435843742",
    "7802969981086",
    "7802397884574",
    "8111922643102",
    "7250004508830",
    "7805795696798",
    "7256779653278",
    "7256609030302",
    "8049985552542",
    "8421138694302",
    "8115653771422",
    "7307476172958",
    "7318921478302",
    "8356565352606",
    "7296848756894",
    "8050457378974",
    "8049044390046",
    "7297320288414",
    "7603153567902",
    "7578799603870",
    "7673717489822",
    "8388048715934",
    "7368531345566",
    "7307870306462",
    "7578788790430",
    "7696136798366",
    "7517062529182",
    "8082058346654",
    "7521177174174",
    "7311381299358",
    "7571969835166",
    "7296033259678",
    "8113017684126",
    "7251566166174",
    "8273593106590",
    "7670056059038",
    "7696106586270",
    "8049970380958",
    "7520450379934",
    "7313039982750",
    "8363741347998",
    "7616359399582",
    "7673706971294",
    "7578784891038",
    "7307845337246",
    "7226786152606",
    "8111243133086",
    "7694690025630",
    "8055133241502",
    "7152742432926",
    "7292513878174",
    "7531720900766",
    "7531720573086",
    "7531719852190",
    "7525384421534",
    "8239708012702",
    "7519724044446",
    "7502420738206",
    "7309038354590",
    "8356570824862",
    "7502498529438",
    "7292406792350",
    "7296631996574",
    "7270502662302",
    "7252312031390",
    "8421140758686",
    "8244200800414",
    "8346624852126",
    "7519660179614",
    "7310351892638",
    "8244198146206",
    "7312644505758",
    "8200003780766",
    "8045457408158",
    "7696128802974",
    "8439721984158",
    "7256909873310",
    "8464924410014",
    "7568928768158",
    "7674107920542",
    "8319167529118",
    "8115591905438",
    "8111299461278",
    "7531363139742",
    "7297862828190",
    "8199994638494",
    "8153063129246",
    "7858100437150",
    "7296155189406",
    "8346627113118",
    "8394815766686",
    "7672208752798",
    "7568793960606",
    "7536544514206",
    "7278139867294",
    "8199990804638",
    "7253510422686",
    "8358321193118",
    "7519994085534",
    "7597641269406",
    "7152737976478",
    "8115702694046",
    "7502434893982",
    "7256539070622",
    "7851342200990",
    "7670352150686",
    "7578775290014",
    "7597693272222",
    "7597664075934",
    "8199957119134",
    "8171032346782",
    "8169937830046",
    "7694685307038",
    "7673707823262",
    "7521192345758",
    "7803846754462",
    "8111914254494",
    "7309272416414",
    "7296639369374",
    "7253336457374",
    "8200018100382",
    "7673705988254",
    "7597669974174",
    "7307853529246",
    "7252596424862",
    "8211626721438",
    "7307532370078",
    "8244199751838",
    "7696478601374",
    "8314561560734",
    "8071917731998",
    "7848676425886",
    "7318962765982",
    "7253387477150",
    "7612496183454",
    "8049038950558",
    "7388052390046",
    "7307367809182",
    "7531362255006",
    "7309774848158",
    "7515181154462",
    "7298748776606",
    "7154255003806",
    "7361501823134",
    "8115665666206",
    "7309467123870",
    "8049976082590",
    "8244195491998",
    "7308976324766",
    "7519646318750",
    "8244199456926",
    "7307936530590",
    "7296843284638",
    "7315212664990",
    "8339034013854",
    "7296616071326",
    "7312902422686",
    "7630253981854",
    "7531327422622",
    "7309037011102",
    "7308668436638",
    "7308542738590",
    "7313480384670",
    "7253508817054",
    "7521163280542",
    "7250218811550",
    "7293339304094",
    "8239713222814",
    "8314565656734",
    "8244192805022",
    "8464924213406",
    "7312659873950",
    "8399800860830",
    "7803830173854",
    "7695564275870",
    "7308310839454",
    "7126146318494",
    "7858099781790",
    "8050184781982",
    "7152826220702",
    "7399836156062",
    "7292467839134",
    "8082084561054",
    "7255312892062",
    "7307350016158",
    "8111311814814",
    "7848674459806",
    "7848673935518",
    "8421164515486",
    "8421163368606",
    "7517052240030",
    "7151109865630",
    "7377385881758",
    "7674107363486",
    "7673702613150",
    "7310350647454",
    "7251420512414",
    "8111919104158",
    "7309130793118",
    "7251484639390",
    "8371472171166",
    "7307352309918",
    "7849154347166",
    "7309824557214",
    "7531214078110",
    "8111927099550",
    "7848694349982",
    "7255642800286",
    "7502323286174",
    "8239713026206",
    "7597665288350",
    "8045457571998",
    "7674106216606",
    "7848675803294",
    "7696506159262",
    "7668884308126",
    "8153035931806",
    "7597682426014",
    "8171035918494",
    "8413966762142",
    "7312683565214",
    "7152847650974",
    "7253434466462",
    "8153042419870",
    "8055131111582",
    "8287376670878",
    "8244194115742",
    "7250004967582",
    "7249926095006",
    "8049968971934",
    "7251561250974",
    "7515180368030",
    "7597656015006",
    "7255358505118",
    "7514602700958",
    "7311369535646",
    "7250352930974",
    "7519987892382",
    "7310021132446",
    "7848690385054",
    "8049025581214",
    "7597654179998",
    "7154295603358",
    "7226785759390",
    "7855217967262",
    "7514918748318",
    "7251427262622",
    "7309267894430",
    "7855227273374",
    "7295179915422",
    "8244157579422",
    "8314563559582",
    "7502426112158",
    "7253330985118",
    "7254441722014",
    "7311280504990",
    "7309160579230",
    "7630253686942",
    "7373378650270",
    "7674109329566",
    "7356768977054",
    "8111324758174",
    "7385463193758",
]

    
    # MODE: "barcodes" or "product_ids"
    MODE = "product_ids"
    
    # No cache - always reprocess
    
    if MODE == "product_ids" and PRODUCT_IDS:
        print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*60}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.HEADER}🎯 PRODUCT IDs MODE{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.HEADER}Total Products: {len(PRODUCT_IDS)}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.HEADER}{'='*60}{Colors.ENDC}\n")
        
        valid_product_ids = PRODUCT_IDS
        
    elif MODE == "barcodes" and BARCODES:
        print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*60}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.HEADER}🎯 BARCODE MODE{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.HEADER}Total Barcodes: {len(BARCODES)}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.HEADER}{'='*60}{Colors.ENDC}\n")
        
        print(f"{Colors.CYAN}Step 1: Converting barcodes to product IDs...{Colors.ENDC}")
        product_ids = get_product_ids_from_barcodes(BARCODES, shop_url, token)
        
        valid_product_ids = [pid for pid in product_ids if pid is not None]
        
        print(f"{Colors.GREEN}✓ Found {len(valid_product_ids)}/{len(BARCODES)} products{Colors.ENDC}\n")
        
        if not valid_product_ids:
            print(f"{Colors.RED}No products found for barcodes. Exiting.{Colors.ENDC}")
            exit(1)
        
        print(f"{Colors.CYAN}Step 2: Processing {len(valid_product_ids)} products...{Colors.ENDC}\n")
    
    else:
        print(f"{Colors.RED}Error: No data! Set MODE='barcodes' with BARCODES or MODE='product_ids' with PRODUCT_IDS{Colors.ENDC}")
        exit(1)
    
    total_processed = 0
    processed_product_ids_set = set()
    
    for idx, product_id in enumerate(valid_product_ids, 1):
        print(f"{Colors.BOLD}{Colors.HEADER}[{idx}/{len(valid_product_ids)}] Processing Product ID: {product_id}{Colors.ENDC}")
        
        product_id_str = str(product_id)
        
        if product_id_str in processed_product_ids_set:
            print(f"{Colors.YELLOW}» Skipping (already processed in this session){Colors.ENDC}")
            continue
        
        try:
            get_product_images(product_id, shop_url, token, auto_sync=auto_sync)
        except Exception as e:
            print(f"{Colors.RED}✗ Error processing product {product_id}: {e}{Colors.ENDC}")
            continue
        
        processed_product_ids_set.add(product_id_str)
        total_processed += 1
        
        generate_index_html()
    
    print(f"\n{Colors.BOLD}{Colors.GREEN}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.GREEN}✓ ALL PROCESSING COMPLETED!{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.GREEN}{'='*60}{Colors.ENDC}")
    print(f"{Colors.GREEN}Total products processed: {total_processed}{Colors.ENDC}")
    print(f"{Colors.GREEN}Unique products handled: {len(processed_product_ids_set)}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.GREEN}{'='*60}{Colors.ENDC}\n")
    
    while False:
        print(f"\n{Colors.CYAN}Fetching next batch of largest images...{Colors.ENDC}")
        images = get_largest_images_graphql(shop_url, token, limit=25)
        
        if not images:
            print(f"{Colors.YELLOW}No more images to process.{Colors.ENDC}")
            break
        
        unprocessed_images = [img for img in images if img['image_id'] not in processed_image_ids]
        
        if not unprocessed_images:
            print(f"{Colors.YELLOW}All images in this batch already processed.{Colors.ENDC}")
            break
        
        print(f"{Colors.GREEN}Found {len(unprocessed_images)} unprocessed images{Colors.ENDC}\n")
        
        for idx, image_info in enumerate(unprocessed_images, 1):
            image_id = image_info['image_id']
            product_id = image_info.get('product_id')
            file_size_mb = image_info.get('file_size_mb', 0)
            width = image_info.get('width', 0)
            height = image_info.get('height', 0)
            
            print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.ENDC}")
            print(f"{Colors.BOLD}{Colors.HEADER}[{idx}/{len(unprocessed_images)}] Image ID: {image_id} | Product ID: {product_id}{Colors.ENDC}")
            print(f"{Colors.CYAN}Size: {file_size_mb}MB | Dimensions: {width}x{height}{Colors.ENDC}")
            print(f"{Colors.CYAN}{'='*60}{Colors.ENDC}\n")
            
            if not product_id:
                print(f"{Colors.YELLOW}⚠ No product ID for image {image_id}{Colors.ENDC}")
                processed_image_ids.add(image_id)
                continue
            
            print(f"{Colors.BOLD}{Colors.GREEN}→ Processing Product ID: {product_id}{Colors.ENDC}")
            
            try:
                get_product_images(product_id, shop_url, token, auto_sync=auto_sync)
            except Exception as e:
                print(f"{Colors.RED}✗ Error processing product {product_id}: {e}{Colors.ENDC}")
                processed_image_ids.add(image_id)
                continue
            
            processed_image_ids.add(image_id)
            total_processed += 1
            
            generate_index_html()
            
            print(f"\n{Colors.CYAN}Progress: Processed {total_processed} products so far{Colors.ENDC}")
        
        print(f"\n{Colors.GREEN}Batch completed. Fetching next batch...{Colors.ENDC}")
    
    print(f"\n{Colors.BOLD}{Colors.GREEN}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.GREEN}✓ ALL PROCESSING COMPLETED!{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.GREEN}{'='*60}{Colors.ENDC}")
    print(f"{Colors.GREEN}Total products processed: {total_processed}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.GREEN}{'='*60}{Colors.ENDC}\n")