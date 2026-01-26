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
    shop_url, token = select_store(1)
    
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
        "7251350388894",
        "7612498575518",
        "8138841096350",
        "7044310925470",
        "8055052763294",
        "8138840244382",
        "7065288179870",
        "8138837328030",
        "8138839031966",
        "7253496332446",
        "7044263968926",
        "7306517315742",
        "7076600217758",
        "7138215264414",
        "8055057252510",
        "8138841718942",
        "7044309713054",
        "8138835853470",
        "8138836312222",
        "8314201800862",
        "8138840670366",
        "8138840473758",
        "8138837295262",
        "8138836377758",
        "7061626355870",
        "7256712675486",
        "7241416278174",
        "7048878686366",
        "8359437435038",
        "8138840637598",
        "8138838737054",
        "8138840211614",
        "7696513433758",
        "8138837950622",
        "7044269277342",
        "8138840539294",
        "8055063707806",
        "8138837590174",
        "7044310696094",
        "7630299758750",
        "8138841751710",
        "8199928676510",
        "8138838605982",
        "7048877146270",
        "8138836902046",
        "8055059742878",
        "8138841522334",
        "8138841424030",
        "8138837164190",
        "8055059054750",
        "8138837885086",
        "7076935532702",
        "7065286115486",
        "8358405439646",
        "7061624619166",
        "8138836639902",
        "7065266815134",
        "7061626618014",
        "7076817797278",
        "7137531297950",
        "8138840277150",
        "8138838671518",
        "8138840178846",
        "8055065968798",
        "8138835886238",
        "7044313317534",
        "8138839752862",
        "8556239323294",
        "8556238766238",
        "8055063576734",
        "8138837852318",
        "8138838638750",
        "8138835951774",
        "7669801222302",
        "8138836410526",
        "8138836213918",
        "8138840408222",
        "7044269080734",
        "8138837459102",
        "8138803249310",
        "7308386828446",
        "8138836836510",
        "7308396560542",
        "8138838769822",
        "7379066093726",
        "7044310499486",
        "8138841850014",
        "8050648842398",
        "8050648350878",
        "8138839851166",
        "7083122786462",
        "8367444525214",
        "8138837262494",
        "7081616638110",
        "8113029742750",
        "8421163008158",
        "7076905091230",
        "8055065706654",
        "8138836770974",
        "8055064789150",
        "8055060070558",
        "8138839949470",
        "8138805870750",
        "8138841194654",
        "7076877533342",
        "7044313874590",
        "8329401073822",
        "8138842734750",
        "7668880605342",
        "8075436720286",
        "8138835787934",
        "7251358810270",
        "8138835689630",
        "8138839785630",
        "8199929036958",
        "7138221916318",
        "7630261059742",
        "7630258274462",
        "7630258012318",
        "8138838507678",
        "7076871635102",
        "8138842603678",
        "8050974130334",
        "7061624979614",
        "7062688628894",
        "8055074095262",
        "8055073472670",
        "7309061292190",
        "8138837393566",
        "7668879327390",
        "8138836050078",
        "8055069474974",
        "7308404162718",
        "7076943757470",
        "7603259474078",
        "8138836476062",
        "7308435226782",
        "8138843160734",
        "7502425260190",
        "7394484125854",
        "7308399640734",
        "7673717391518",
        "7061627895966",
        "7669791162526",
        "8138837098654",
        "8050647203998",
        "8138842505374",
        "8047829942430",
        "7306647208094",
        "8138836869278",
        "8055059021982",
        "8138841784478",
        "7891120685214",
        "7597688488094",
        "7308439617694",
        "8138837000350",
        "7253323939998",
        "8138837229726",
        "8602666664094",
        "7516629958814",
        "7578792394910",
        "8138842898590",
        "8050401607838",
        "7241927032990",
        "7670385639582",
        "7387409481886",
        "8138842931358",
        "8055058333854",
        "8055055417502",
        "8050646384798",
        "7309437173918",
        "7241923952798",
        "7240431468702",
        "7310063894686",
        "7061628780702",
        "7241926541470",
        "8138805739678",
        "7241927622814",
        "7306637672606",
        "7502600536222",
        "7048873181342",
        "7668885487774",
        "7291248836766",
        "7241927753886",
        "7241923297438",
        "7048871084190",
        "7622267830430",
        "7519675580574",
        "7253477032094",
        "7519985565854",
        "8049970741406",
        "7519677317278",
        "7312888004766",
        "7296568852638",
        "8113027907742",
        "7241926607006",
        "8055062003870",
        "8138842177694",
        "7309087342750",
        "7521137098910",
        "8451947200670",
        "7044313055390",
        "7069278797982",
        "7318751183006",
        "8204237078686",
        "7523775119518",
        "7315585990814",
        "7241923264670",
        "8138828710046",
        "8050647498910",
        "8550720110750",
        "7622270910622",
        "7519984648350",
        "7069180526750",
        "7630292385950",
        "7696126410910",
        "7630301331614",
        "7519677350046",
        "8138842833054",
        "7519949717662",
        "8383139840158",
        "7664690233502",
        "7240502313118",
        "7307522113694",
        "7672201379998",
        "7241927164062",
        "8433266196638",
        "7241927524510",
        "7361434157214",
        "7673714540702",
        "7696500719774",
        "7240441626782",
        "8049967399070",
        "8055069638814",
        "7502499348638",
        "7502603288734",
        "7241924116638",
        "7308415664286",
        "8050424905886",
        "7253688385694",
        "7502497218718",
        "7502440890526",
        "7307503992990",
        "7523777740958",
        "7668879589534",
        "7294081564830",
        "8257258094750",
        "7523778625694",
        "7311177056414",
        "7502495121566",
        "7313696063646",
        "7502608040094",
        "8138840113310",
        "7241926869150",
        "7519676203166",
        "7520439861406",
        "8050425888926",
        "7502424211614",
        "7241927721118",
        "7309461618846",
        "7519988056222",
        "7069213950110",
        "7502425489566",
        "7263827886238",
        "8082099077278",
        "8138836082846",
        "8138842079390",
        "7603485737118",
        "7519989137566",
        "7069152739486",
        "7672205017246",
        "7891124289694",
        "7309434552478",
        "7250785435806",
        "7516630057118",
        "7502422212766",
        "7044314890398",
        "7669790900382",
        "7048874033310",
        "7076904403102",
        "7076871405726",
        "7519943524510",
        "7519989072030",
        "7313468948638",
        "7076598055070",
        "7519727452318",
        "7251521798302",
        "7519992381598",
        "7616288981150",
        "7803254243486",
        "7802735591582",
        "8138839589022",
        "8069874024606",
        "7241923723422",
        "7048883110046",
        "7306604347550",
        "7395696541854",
        "7310168719518",
        "7251358646430",
        "7241923690654",
        "7891122520222",
        "7065469812894",
        "7076923605150",
        "7253696512158",
        "8138836148382",
        "7519989792926",
        "7312708436126",
        "7318818848926",
        "8138842472606",
        "7306639147166",
        "7306634330270",
        "7306609328286",
        "7306609066142",
        "7306565845150",
        "7293933125790",
        "7308576260254",
        "7695540191390",
        "7523851174046",
        "7251587858590",
        "8454260293790",
        "8055059677342",
        "8138842865822",
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