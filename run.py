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
        "9274143899906",
        "8085708341506",
        "8035492659458",
        "8094528766210",
        "8094568513794",
        "7738603602178",
        "8085603713282",
        "8099622715650",
        "8094526046466",
        "8094725636354",
        "9023390220546",
        "8005628690690",
        "8005628428546",
        "8005627347202",
        "9018463682818",
        "8099783442690",
        "8818292850946",
        "9131029725442",
        "8095487394050",
        "8099560292610",
        "8088530845954",
        "8099650208002",
        "8099647717634",
        "8099646832898",
        "8078939521282",
        "8078939357442",
        "8078939193602",
        "8094555504898",
        "8818292752642",
        "8078913798402",
        "8095601328386",
        "8095419990274",
        "8095416713474",
        "8095404916994",
        "8095402688770",
        "8095412093186",
        "6819943678142",
        "8071375716610",
        "8071376666882",
        "8094557962498",
        "8085729280258",
        "8088512102658",
        "8099712270594",
        "8099714269442",
        "8099721969922",
        "8099722297602",
        "8099711385858",
        "9094579716354",
        "7749315526914",
        "9050829684994",
        "8088214601986",
        "8818213323010",
        "8818185634050",
        "8818185535746",
        "8088213815554",
        "8095584715010",
        "8973221495042",
        "8088879137026",
        "8088217288962",
        "9098906534146",
        "7749316706562",
        "8078818738434",
        "8094730354946",
        "8094586634498",
        "8094586601730",
        "8094586568962",
        "9025788477698",
        "8953648251138",
        "6821214355646",
        "9025789362434",
        "9112157880578",
        "9025788576002",
        "8824670093570",
        "8818286690562",
        "7765099053314",
        "7765099020546",
        "8088249663746",
        "8885876064514",
        "8094519001346",
        "8094723670274",
        "8078919270658",
        "8088538480898",
        "8094567563522",
        "8818286100738",
        "9043041812738",
        "8088539562242",
        "8078896136450",
        "9025789395202",
        "8094564843778",
        "8078958690562",
        "8094543020290",
        "8088504205570",
        "8818189566210",
        "8094530273538",
        "8095403835650",
        "9089971978498",
        "8098740896002",
        "8826545373442",
        "8094530797826",
        "8094530142466",
        "8094524047618",
        "8088249008386",
        "8078937653506",
        "8094567891202",
        "8097060126978",
        "8094688116994",
        "8818296029442",
        "8078896627970",
        "8088248615170",
        "8094541840642",
        "8099523068162",
        "8095391580418",
        "8094698406146",
        "8924919333122",
        "8924919234818",
        "8924918841602",
        "8924918186242",
        "8924918022402",
        "8096946782466",
        "8096953139458",
        "8088251007234",
        "8078938800386",
        "8099767812354",
        "8088535728386",
        "9095101350146",
        "8095409930498",
        "8094518247682",
        "9025789264130",
        "8972796788994",
        "8097037254914",
        "8818282135810",
        "8924910518530",
        "8088544870658",
        "8096941965570",
        "8823667196162",
        "8085620392194",
        "7759268479234",
        "8088887951618",
        "6841344786622",
        "9131513151746",
        "8088541724930",
        "8096974373122",
        "8085738422530",
        "8099543384322",
        "8818192285954",
        "8097007632642",
        "9017746686210",
        "9015837032706",
        "8096980107522",
        "8088535466242",
        "8085643067650",
        "8078917042434",
        "8094522802434",
        "8079008989442",
        "8094641225986",
        "8582021710082",
        "7749314085122",
        "8096924303618",
        "7729976901890",
        "7729976705282",
        "8095625511170",
        "9131028939010",
        "8078945222914",
        "8078822932738",
        "8088261394690",
        "8885872656642",
        "8094550163714",
        "8078917992706",
        "8095407964418",
        "8818178752770",
        "8095401672962",
        "8095450104066",
        "8088224727298",
        "8078960296194",
        "8088232984834",
        "9131513315586",
        "9108597342466",
        "8885876982018",
        "8096958513410",
        "8818182750466",
        "8097044300034",
        "9025789329666",
        "9095101317378",
        "9112157815042",
        "8827279933698",
        "8827279769858",
        "8827279704322",
        "8094576509186",
        "8818268995842",
        "8088231313666",
        "8094532108546",
        "8094530339074",
        "8094524440834",
        "8094542102786",
        "8088225513730",
        "8088536023298",
        "8095617089794",
        "8094613176578",
        "8094689067266",
        "8094541775106",
        "8827286585602",
        "8827286454530",
        "8827286323458",
        "8827286094082",
        "8827285733634",
        "8095433654530",
        "8094670356738",
        "8088224203010",
        "8818283610370",
        "8078876999938",
        "8088235409666",
        "8078902329602",
        "8818184225026",
        "8099537125634",
        "8099537060098",
        "8099536666882",
        "8099534504194",
        "8818295800066",
        "8094717378818",
        "8085627207938",
        "8094545150210",
        "8098710814978",
        "8094517657858",
        "8078817165570",
        "8095416221954",
        "8096971030786",
        "8097054458114",
        "8097048756482",
        "8097040957698",
        "8097051934978",
        "8078939095298",
        "8818295832834",
        "8078941126914",
        "8094618648834",
        "8097027653890",
        "8078881718530",
        "8099565240578",
        "8099716563202",
        "8085507080450",
        "8826550944002",
        "8826550845698",
        "8826544619778",
        "8826544554242",
        "8078816313602",
        "8096985710850",
        "8095437783298",
        "8078960197890",
        "8071388725506",
        "8096934035714",
        "8818195792130",
        "8094546198786",
        "8097056456962",
        "8094649319682",
        "8094532829442",
        "8096981156098",
        "8094535909634",
        "8088547983618",
        "8098713731330",
        "8099766468866",
        "8096961724674",
        "8095598969090",
        "8097052262658",
        "8818294489346",
        "8095415107842",
        "8088541364482",
        "8094558945538",
        "8818298192130",
        "8096939737346",
        "8095587336450",
        "8099741106434",
        "8085714600194",
        "9042207604994",
        "8826599407874",
        "8826599276802",
        "9089972175106",
        "8095597920514",
        "8078880080130",
        "8818220335362",
        "8078918451458",
        "9117938909442",
        "8818180980994",
        "8078878343426",
        "8818221940994",
        "9042202657026",
        "8818286657794",
        "8095442895106",
        "8097009434882",
        "8094552588546",
        "9095101088002",
        "9095101022466",
        "8096950386946",
        "8085706408194",
        "8827270004994",
        "8094580441346",
        "8078942568706",
        "8096999244034",
        "8095393218818",
        "8823668048130",
        "8095563710722",
        "8818295996674",
        "8095491162370",
        "8085621244162",
        "8094694539522",
        "8094540071170",
        "8078820049154",
        "8094682251522",
        "8094689001730",
        "8094613373186",
        "8078877917442",
        "8088259428610",
        "8936573042946",
        "8979942080770",
        "8088233541890",
        "8818191532290",
        "8088511119618",
        "8094557700354",
        "8818183307522",
        "8078923333890",
        "8078938931458",
        "8826544914690",
        "8826544849154",
        "8826544750850",
        "8826544718082",
        "8095619612930",
        "8094614159618",
        "8094613668098",
        "8098718613762",
        "8096963920130",
        "8096963526914",
        "8096960413954",
        "8096943538434",
        "8096938328322",
        "8094526308610",
        "8818178720002",
        "8094650007810",
        "8094562550018",
        "8088505090306",
        "8097043218690",
        "8078893875458",
        "8096956711170",
        "8095598149890",
        "8094685856002",
        "8095406227714",
        "8095396397314",
        "8818299273474",
        "8097029292290",
        "9025789624578",
        "8088913379586",
        "8094528864514",
        "8099610984706",
        "8078917763330",
        "9050829553922",
        "8094604984578",
        "8097007141122",
        "8094524670210",
        "8097020674306",
        "8096945537282",
        "8818292195586",
        "8818181767426",
        "8818181669122",
        "8818181570818",
        "8818180587778",
        "8095608275202",
        "8095606898946",
        "8094683005186",
        "8088271094018",
        "8088505843970",
        "7765055635714",
        "8078894235906",
        "7728653009154",
        "8095420645634",
        "8094537908482",
        "8095579537666",
        "8094537744642",
        "8096929251586",
        "8096918831362",
        "8099795206402",
        "8099780296962",
        "8919913431298",
        "8096942227714",
        "8099811295490",
        "8099799400706",
        "8078823031042",
        "8094519722242",
        "8094674780418",
        "8088264507650",
        "8088533565698",
        "8818196283650",
        "7694291763458",
        "8935297155330",
        "9050829357314",
        "8096921321730",
        "8095450759426",
        "8818191368450",
        "8088259199234",
        "8094536204546",
        "7722515169538",
        "8078961541378",
        "8095596642562",
        "8827265941762",
        "8097042366722",
        "8885872001282",
        "8078894760194",
        "8094697128194",
        "8085722824962",
        "8078937096450",
        "8085734523138",
        "8094675730690",
        "8088231674114",
        "8095394431234",
        "8088254284034",
        "9025789722882",
        "8078895448322",
        "8078878802178",
        "8088257822978",
        "8088535662850",
        "8088531075330",
        "8085712077058",
        "8826545209602",
        "8826545176834",
        "8826545078530",
        "8826544980226",
        "8827285930242",
        "8885875179778",
        "8094796644610",
        "8088215814402",
        "8078938112258",
        "8078914093314",
        "8097019035906",
        "8097019003138",
        "8097018872066",
        "8097018413314",
        "8097017331970",
        "8097017102594",
        "8094526832898",
        "8078916780290",
        "8088235245826",
        "8078800486658",
        "8088272273666",
        "8099526803714",
        "9034211295490",
        "9034210902274",
        "8818294063362",
        "9034063282434",
        "8078942470402",
        "8097018806530",
        "9042204557570",
        "8078937325826",
        "8818231738626",
        "8097022542082",
        "6849809645758",
        "8094525784322",
        "6849818165438",
        "8094536007938",
        "8085702967554",
        "8097058881794",
        "8079002173698",
        "8078961508610",
        "8078961377538",
        "8088246780162",
        "8094614388994",
        "8818198511874",
        "8097001537794",
        "8818189762818",
        "8094569922818",
        "6862007664830",
        "8085614887170",
        "6834383782078",
        "8088210637058",
        "8095599362306",
        "8094717214978",
        "8094604755202",
        "8096922632450",
        "8094573461762",
        "8094552293634",
        "9106702106882",
        "8096900514050",
        "8085615313154",
        "8095622660354",
        "8078878933250",
        "8078919074050",
        "8085614493954",
        "6830152351934",
        "8088241864962",
        "8005627740418",
        "8005627609346",
        "8005627576578",
        "8005627052290",
        "8005626790146",
        "8078915567874",
        "8094681170178",
        "8088212603138",
        "7935504744706",
        "8078914224386",
        "8088224530690",
        "8094523490562",
        "8088542052610",
        "7757171818754",
        "8097020182786",
        "9089972011266",
        "9142626976002",
        "9025789591810",
        "8097064124674",
        "8078914027778",
        "8078913831170",
        "9114881589506",
        "8078921203970",
        "8099847864578",
        "8818191565058",
        "8078917337346",
        "8088233804034",
        "8818207326466",
        "8078923235586",
        "8078938767618",
        "8098721693954",
        "8818286330114",
        "8095425691906",
        "8078882636034",
        "8088533664002",
        "8095424315650",
        "8818214797570",
        "7749732237570",
        "8096938393858",
        "8094546919682",
        "8094546592002",
        "8094545740034",
        "8094541807874",
        "8094541316354",
        "8094538727682",
        "8094536663298",
        "8094522933506",
        "8097007370498",
        "8085639561474",
        "8096896745730",
        "8818295406850",
        "8818193760514",
        "8094643388674",
        "8885882126594",
        "9117925015810",
        "8085718565122",
        "8088543887618",
        "8096925876482",
        "8096991904002",
        "8818183635202",
        "8818182684930",
        "6661295341758",
        "8094546886914",
        "8085633859842",
        "9077161132290",
        "8088538775810",
        "8818292228354",
        "8078826602754",
        "8094571528450",
        "8817997021442",
        "8818290524418",
        "9025789755650",
        "8095431590146",
        "6786814640318",
        "8085634285826",
        "8078902198530",
        "8078902362370",
        "8079783035138",
        "8079783362818",
        "8818292490498",
        "8094548787458",
        "8071379386626",
        "8071378403586",
        "8085708079362",
        "8843953045762",
        "8843952947458",
        "8843952750850",
        "8843952685314",
        "8843952587010",
        "8843952554242",
        "8843949179138",
        "8094578213122",
        "8085733671170",
        "8078820114690",
        "8088213717250",
        "8095627051266",
        "9131513839874",
        "8096955433218",
        "8818185830658",
        "9017751175426",
        "8818184978690",
        "8096911393026",
        "8085699526914",
        "8079009775874",
        "8095463571714",
        "8885877178626",
        "9017739968770",
        "7720713715970",
        "8071379714306",
        "8071375847682",
        "8094540923138",
        "8094520312066",
        "8085615804674",
        "8099745693954",
        "8078880342274",
        "8078962032898",
        "8843953176834",
        "9017740656898",
        "8088533500162",
        "8094520443138",
        "8094518280450",
        "8095448727810",
        "6559203950782",
        "8953384698114",
        "8094518477058",
        "6996370620606",
        "8097056030978",
        "7730620498178",
        "8094669078786",
        "8629568209154",
        "8078913634562",
        "8095449252098",
        "8095424872706",
        "9131030249730",
        "9131030216962",
        "9131514134786",
        "8099818078466",
        "8094666064130",
        "8818263195906",
        "8095490834690",
        "8088223449346",
        "8818217681154",
        "8096898449666",
        "8095606112514",
        "8095599919362",
        "8095594512642",
        "8078878048514",
        "8818199101698",
        "8818260836610",
        "9121768177922",
        "9123060809986",
        "9042203443458",
        "8099711090946",
        "8818256773378",
        "8818180784386",
        "7711986778370",
        "8096956416258",
        "8924913467650",
        "8085726691586",
        "8096977649922",
        "8099710042370",
        "8085500723458",
        "8095430607106",
        "9042203115778",
        "8095469043970",
        "8099709190402",
        "8097042596098",
        "9025789526274",
        "8088271552770",
        "8088271192322",
        "8088270602498",
        "8035488268546",
        "8827276755202",
        "6821760270526",
        "8078878769410",
        "8088274370818",
        "8818266145026",
        "8827276853506",
        "8088541102338",
        "8078894727426",
        "8094703452418",
        "8094535155970",
        "8078902100226",
        "9106702401794",
        "8094558454018",
        "8097063207170",
        "8827270791426",
        "8827270529282",
        "9025801617666",
        "8827270627586",
        "8071394918658",
        "8094568284418",
        "8818192941314",
        "8095450628354",
        "8818219057410",
        "8094519787778",
        "8088234131714",
        "8094528504066",
        "8094524768514",
        "8094523031810",
        "8094604886274",
        "8085621702914",
        "8096988528898",
        "8094614946050",
        "8095493751042",
        "8096998719746",
        "9069286850818",
        "8085641953538",
        "8085732294914",
        "8095586779394",
        "8078883782914",
        "8095470616834",
        "8085737767170",
        "8096932724994",
        "8088218730754",
        "8088220270850",
        "8818179932418",
        "8097002455298",
        "8095410880770",
        "8094525292802",
        "9042205835522",
        "8876784058626",
        "7730016747778",
        "8919915888898",
        "8094546133250",
        "8088259264770",
        "8088256807170",
        "8088256413954",
        "8818179047682",
        "8099719250178",
        "8919914610946",
        "8085637202178",
        "8095454724354",
        "8818298650882",
        "8094695063810",
        "8099538075906",
        "9077167259906",
        "8078882668802",
        "9065542615298",
        "8818184945922",
        "8078884864258",
        "8095419236610",
        "6895048392894",
        "8094643781890",
        "8818185306370",
        "8818298093826",
        "8100476616962",
        "8071379124482",
        "8096997671170",
        "8095620923650",
        "8099633594626",
        "8099633496322",
        "8094535647490",
        "8088254382338",
        "8099768107266",
        "8924907995394",
        "8088224039170",
        "8094568481026",
        "8094786552066",
        "8094516773122",
        "6887008174270",
        "6886996967614",
        "8099633922306",
        "8099631890690",
        "8078897742082",
        "8088912986370",
        "8876782584066",
        "8818188288258",
        "8096931873026",
        "8096928268546",
        "8096903495938",
        "8096964739330",
        "8826548912386",
        "8826548879618",
        "8826548322562",
        "9062829424898",
        "8099765223682",
        "8088533238018",
        "9116638150914",
        "8094698930434",
        "8096953565442",
        "8824671174914",
        "8097055703298",
        "7720605909250",
        "8096911622402",
        "8818283380994",
        "8085629960450",
        "8094710366466",
        "8818228887810",
        "8953648021762",
        "8099765485826",
        "8094690902274",
        "8094721278210",
        "8088243077378",
        "8818257264898",
        "8095587074306",
        "8078817231106",
        "9017739182338",
        "8818199855362",
        "8094659412226",
        "8092884566274",
        "8099707027714",
        "8094524244226",
        "7730017829122",
        "8078944436482",
        "8097061699842",
        "8085738324226",
        "8078923366658",
        "8095488573698",
        "8095410651394",
        "8095413174530",
        "8885869805826",
        "8096895762690",
        "8827265581314",
        "8096936263938",
        "8096968540418",
        "8099628679426",
        "8078882799874",
        "8096890421506",
        "9025789559042",
        "8078877327618",
        "7738476757250",
        "6887008469182",
        "8826548551938",
        "8826548519170",
        "8078916976898",
        "8098724315394",
        "8098725101826",
        "8098724053250",
        "8085608005890",
        "8078913306882",
        "8097034076418",
        "8095398428930",
        "8098717630722",
        "8088232263938",
        "8079008661762",
        "8885875933442",
        "8085710438658",
        "8818195169538",
        "8818179277058",
        "8818245075202",
        "8095418155266",
        "8094808801538",
        "9070073839874",
        "8088266866946",
        "8088266735874",
        "8088267424002",
        "8085637431554",
        "8085640478978",
        "8094695457026",
        "9017740919042",
        "8094587355394",
        "9042206097666",
        "8095465734402",
        "8095438045442",
        "8094692376834",
        "8095393710338",
        "9019087552770",
        "8885875867906",
        "8078946533634",
        "8088276402434",
        "8094602166530",
        "8818187993346",
        "8088217157890",
        "8095595790594",
        "8088265326850",
        "8818185208066",
        "8818296881410",
        "7756230918402",
        "8818238914818",
        "8924907536642",
        "8088228921602",
        "7756230656258",
        "8100476158210",
        "8096945996034",
        "8818298388738",
        "7765098561794",
        "7765098529026",
        "7765098430722",
        "8078913667330",
        "6887007518910",
        "9074161680642",
        "9077167063298",
        "8099826237698",
        "8095478350082",
        "8096974602498",
        "6886995525822",
        "6886986711230",
        "8097019560194",
        "8094697259266",
        "8094691131650",
        "8094688805122",
        "8094561206530",
        "9077161427202",
        "8095563579650",
        "8085705621762",
        "8094514905346",
        "8095479038210",
        "8095413338370",
        "8099780002050",
        "8094570709250",
        "8818185732354",
        "9017752617218",
        "8098716844290",
        "8088257462530",
        "8095485100290",
        "8094614847746",
        "8099675078914",
        "8085738455298",
        "8096987152642",
        "8094580605186",
        "8826545307906",
        "8085726003458",
        "9108602683650",
        "9077162148098",
        "9077161951490",
        "8097053835522",
        "8818193432834",
        "7720458977538",
        "8094709481730",
        "8094525358338",
        "8085713125634",
        "8085720072450",
        "9095101186306",
        "9042203869442",
        "8094685757698",
        "8097039089922",
        "8088239571202",
        "8079007678722",
        "8875890704642",
        "8094515691778",
        "8818300551426",
        "6819942891710",
        "8094689493250",
        "8078879719682",
        "8096937181442",
        "9117924360450",
        "8085721645314",
        "8818177736962",
        "8075531911426",
        "7765098365186",
        "8095445713154",
        "8919915004162",
        "8099532407042",
        "8096967098626",
        "8096908935426",
        "8095438504194",
        "8094528372994",
        "8099858514178",
        "8818235310338",
        "8818298257666",
        "8096993968386",
        "8095400362242",
        "8085704540418",
        "7705300271362",
        "7705103925506",
        "7705103827202",
        "8095563022594",
        "8088243470594",
        "8096968442114",
        "8818211258626",
        "8973221789954",
        "8085712863490",
        "8818222301442",
        "7659286102274",
        "8097064288514",
        "8094564352258",
        "8094557405442",
        "9112157454594",
        "9112157225218",
        "9112157192450",
        "9112156799234",
        "8088256872706",
        "8078822703362",
        "8094538891522",
        "8922744094978",
        "8079009022210",
        "8088544182530",
        "6849817837758",
        "8098714648834",
        "7797518303490",
        "8095436505346",
        "8818196119810",
        "8078878671106",
        "8094560780546",
        "8085499052290",
        "8095605948674",
        "8875890573570",
        "8078995489026",
        "6827134845118",
        "8096959529218",
        "9077161787650",
        "9077161754882",
        "8818261786882",
        "8823947559170",
        "8094549770498",
        "8094604067074",
        "8088229773570",
        "8094673961218",
        "8088266834178",
        "8094543970562",
        "8095426347266",
        "8078938996994",
        "8078938964226",
        "8078800552194",
        "8085610234114",
        "8078881849602",
        "8095577866498",
        "6849818001598",
        "8088224923906",
        "8094572118274",
        "8096995574018",
        "8818295505154",
        "8094699913474",
        "8095571443970",
        "8078919041282",
        "7720699691266",
        "8818195759362",
        "8085730951426",
        "8078940537090",
        "8094520934658",
        "8078937391362",
        "8095483724034",
        "8094705058050",
        "9050832601346",
        "9050832175362",
        "9050831978754",
        "9232159801602",
        "9025789493506",
        "8094531387650",
        "8818292031746",
        "8094530076930",
        "8094537941250",
        "8098721726722",
        "7756229509378",
        "8099677110530",
        "8071393771778",
        "9062830113026",
        "8078913929474",
        "8088509481218",
        "6821760106686",
        "9023389761794",
        "8825999065346",
        "8094611308802",
        "8085738586370",
        "7721658056962",
        "9121768997122",
        "8078881259778",
        "8099557343490",
        "8099555082498",
        "8099731767554",
        "8094525063426",
        "9089970864386",
        "8096996294914",
        "8818257723650",
        "8095566233858",
        "8099673964802",
        "8097028047106",
        "8094529519874",
        "8094526144770",
        "7651801956610",
        "7651794518274",
        "7651789013250",
        "7651788488962",
        "8095405441282",
        "9124809376002",
        "8099718988034",
        "8818196087042",
        "8079004107010",
        "8818190418178",
        "9091292692738",
        "9128343372034",
        "9131028447490",
        "8088254644482",
        "8824704696578",
        "8088272896258",
        "8078880899330",
        "8097008812290",
        "8098721530114",
        "8078937358594",
        "8099777478914",
        "8088250351874",
        "8094550229250",
        "8095425265922",
        "8094545805570",
        "8096943505666",
        "8935165296898",
        "8097062289666",
        "8094520344834",
        "8096966312194",
        "8095395774722",
        "9080153571586",
        "9023390777602",
        "9023390646530",
        "9023390613762",
        "9023390548226",
        "9023390515458",
        "9023390482690",
        "9023390417154",
        "9023390286082",
        "9023390253314",
        "9023390155010",
        "9023390089474",
        "9023390056706",
        "9023389991170",
        "9023389958402",
        "9023389925634",
        "9023389892866",
        "9023389827330",
        "9023389565186",
        "9023389532418",
        "9023389499650",
        "9023390908674",
        "9023390843138",
        "9023390810370",
        "9023390449922",
        "9023390318850",
        "9023390122242",
        "9023389729026",
        "9023389663490",
        "9023389630722",
        "9023389434114",
        "8099558326530",
        "8099552493826",
        "8818244681986",
        "7756230000898",
        "9062829588738",
        "8088229642498",
        "8818224431362",
        "9108601929986",
        "9000956231938",
        "8094710071554",
        "8919916183810",
        "8818220695810",
        "7651810214146",
        "7651805790466",
        "8078877425922",
        "8818282004738",
        "8088224137474",
        "8088239833346",
        "8095414059266",
        "6712981061822",
        "9110446113026",
        "8088266211586",
        "8096989053186",
        "8085610103042",
        "8079806923010",
        "8094574641410",
        "8078894825730",
        "8095443878146",
        "8919911465218",
        "8088237932802",
        "9121769062658",
        "8088511381762",
        "8094532632834",
        "8078800748802",
        "8078915174658",
        "8099637002498",
        "8088540020994",
        "8078938898690",
        "8818237112578",
        "9089970372866",
        "8818196054274",
        "8885875736834",
        "9117939826946",
        "6886993854654",
        "8094643126530",
        "8826575192322",
        "8088269750530",
        "6830164672702",
        "7759268118786",
        "8088276435202",
        "8095480545538",
        "8843932270850",
        "8924911239426",
        "8098716909826",
        "8097026867458",
        "8818209259778",
        "8097046266114",
        "8071380566274",
        "8071377780994",
        "8071375683842",
        "8094528307458",
        "8094523162882",
        "8088257069314",
        "8095396790530",
        "8099717677314",
        "8099604037890",
        "8099598106882",
        "8088274862338",
        "7727841902850",
        "8088535597314",
        "8096979845378",
        "8078884438274",
        "8088237211906",
        "9017754255618",
        "9025787920642",
        "8096944816386",
        "7759267201282",
        "7759254388994",
        "8096946356482",
        "8088240783618",
        "8818195824898",
        "8094566154498",
        "8088239309058",
        "8818190647554",
        "8096965755138",
        "8096950518018",
        "7723416551682",
        "8088236392706",
        "8095482904834",
        "8088266473730",
        "8094688280834",
        "8099634020610",
        "8088267784450",
        "9017754222850",
        "8099694346498",
        "8094547640578",
        "8097044627714",
        "8818239045890",
        "8088539660546",
        "8818196021506",
        "6996804468926",
        "9131028873474",
        "8999681196290",
        "8094526177538",
        "8088240226562",
        "8818176884994",
        "8096909951234",
        "8085705883906",
        "8094602035458",
        "8094530535682",
        "8094525751554",
        "8096979714306",
        "8005573640450",
        "8818285707522",
        "8094573035778",
        "8818182848770",
        "8095428706562",
        "8095424741634",
        "8818214207746",
        "8818285084930",
        "8833457029378",
        "8924908257538",
        "7753031254274",
        "9131513413890",
        "8095408423170",
        "8088237965570",
        "8097035813122",
        "8099692314882",
        "8096921256194",
        "7651813261570",
        "7651808149762",
        "7651807985922",
        "7651797074178",
        "7651796451586",
        "7651789635842",
        "7651789144322",
        "8097004060930",
        "9023374622978",
        "8088266703106",
        "9042205442306",
        "9025789296898",
        "8095423693058",
        "8095586222338",
        "8088240521474",
        "8094525489410",
        "8096967033090",
        "8098717171970",
        "8035491643650",
        "8818181931266",
        "9117972267266",
        "8096934428930",
        "8096932266242",
        "8099706831106",
        "8046795522306",
        "7762385568002",
        "8071376142594",
        "6830159233214",
        "8088266440962",
        "8818298454274",
        "8078901674242",
        "8088266998018",
        "8099846390018",
        "8078913896706",
        "9110445916418",
        "8095438078210",
        "8095455674626",
        "8085701296386",
        "8096982335746",
        "8088233836802",
        "8095417565442",
        "8094575558914",
        "8818286067970",
        "8818205491458",
        "8826549174530",
        "8826549141762",
        "8826549043458",
        "8826549010690",
        "8110027211010",
        "6723223552190",
        "6887008796862",
        "9120841793794",
        "8818185765122",
        "8085710831874",
        "8078826733826",
        "8097009565954",
        "8095604408578",
        "8097027948802",
        "9042203377922",
        "8095419728130",
        "6886990938302",
        "6886987563198",
        "6886986547390",
        "6887005716670",
        "6887003947198",
        "6886993363134",
        "6886990184638",
        "6886988349630",
        "6886987137214",
        "6886985760958",
        "9077161918722",
        "9077161853186",
        "8856198119682",
        "8818298847490",
        "8096965296386",
        "8088209293570",
        "8098721923330",
        "8094610292994",
        "9077161394434",
        "8843937644802",
        "9023387828482",
        "8085718761730",
        "8876782780674",
        "8099568845058",
        "8099568681218",
        "8099565568258",
        "8826595213570",
        "9117921968386",
        "8078900199682",
        "8085721415938",
        "8088215585026",
        "7752603533570",
        "8046755709186",
        "8046755905794",
        "8046754889986",
        "8953385877762",
        "8078884503810",
        "8096988856578",
        "8094521819394",
        "8096924532994",
        "8094720164098",
        "7722445046018",
        "8099703881986",
        "8094537974018",
        "8085739471106",
        "7727836791042",
        "8098721399042",
        "7720395931906",
        "8907617599746",
        "8078894530818",
        "7730017894658",
        "8096962085122",
        "8035491447042",
        "7726323106050",
        "8094577197314",
        "8827273150722",
        "9077162049794",
        "9077162017026",
        "8095400722690",
        "8818222956802",
        "8098718155010",
        "9017739280642",
        "8078886961410",
        "6815671189694",
        "8818283675906",
        "8078886437122",
        "8078887092482",
        "8078886994178",
        "8078886928642",
        "8078886797570",
        "8078886174978",
        "8078885552386",
        "8085730590978",
        "9017739739394",
        "9120833110274",
        "8096930464002",
        "8094546166018",
        "8097021001986",
        "8097001996546",
        "8095431753986",
        "7793236705538",
        "9065543106818",
        "9131028742402",
        "8818264342786",
        "8096966607106",
        "8078878638338",
        "9077162475778",
        "9077162410242",
        "8094530633986",
        "8078897643778",
        "8085723250946",
        "7722363650306",
        "9095100891394",
        "8099648209154",
        "8095594676482",
        "8824724947202",
        "6997400191166",
        "9042202329346",
        "8078896693506",
        "9077161689346",
        "9077161591042",
        "8095565906178",
        "9017752715522",
        "8095616434434",
        "6718996283582",
        "9062831390978",
        "9094581518594",
        "6859926831294",
        "8076213321986",
        "8095461966082",
        "8085609578754",
        "8078877786370",
        "8885872525570",
        "8885869707522",
        "7756231573762",
        "8885876130050",
        "8099842556162",
        "8099842523394",
        "8097011892482",
        "8096998981890",
        "8085703885058",
        "8095468126466",
        "8818222825730",
        "8099751690498",
        "8094556160258",
        "6821218222270",
        "9118520574210",
        "8078895481090",
        "8818230034690",
        "9031763624194",
        "8095602802946",
        "8885877080322",
        "9077162213634",
        "9077162180866",
        "8818193400066",
        "8824687296770",
        "8088223711490",
        "8094517526786",
        "7720675868930",
        "9080153178370",
        "8818258542850",
        "8078879326466",
        "8885877211394",
        "7756231278850",
        "8088235278594",
        "9112156766466",
        "9112156340482",
        "8095622922498",
        "8818298224898",
        "8094560387330",
        "8827287306498",
        "8094642012418",
        "8094614651138",
        "8818298355970",
        "8830185701634",
        "8094516904194",
        "7765114650882",
        "8097059995906",
        "8935316422914",
        "8096985153794",
        "8094524997890",
        "8096903561474",
        "8095410192642",
        "9114882113794",
        "8088511742210",
        "8818292883714",
        "8826551730434",
        "8088229708034",
        "8818291933442",
        "8095402459394",
        "8088266899714",
        "8097046102274",
        "8094525260034",
        "8095420350722",
        "8095466553602",
        "8094534992130",
        "8094740414722",
        "8095438340354",
        "8088232165634",
        "8099715481858",
        "8096934985986",
        "8097006387458",
        "8096909394178",
        "8096979222786",
        "8078817820930",
        "8097047675138",
        "9077161558274",
        "8095421694210",
        "8097024082178",
        "8818270601474",
        "7711988384002",
        "8094586831106",
        "8094560944386",
        "8094515527938",
        "8096996688130",
        "9095102857474",
        "8096928891138",
        "8094548951298",
        "8094547149058",
        "8094546526466",
        "8094545019138",
        "8094544560386",
        "8094542168322",
        "8094540005634",
        "8094537122050",
        "8096896024834",
        "6883735011518",
        "9042203705602",
        "6886994280638",
        "8095429951746",
        "8097033912578",
        "8818297897218",
        "8088257790210",
        "9089970274562",
        "8099740778754",
        "9077161459970",
        "8818195071234",
        "8852218839298",
        "8852216545538",
        "8071377289474",
        "8085718860034",
        "8005578490114",
        "8099653746946",
        "8095477399810",
        "7719816626434",
        "8094527750402",
        "8096934297858",
        "8096932397314",
        "8096922730754",
        "8085494857986",
        "8085489418498",
        "8085491056898",
        "8085489058050",
        "8085501083906",
        "8085497774338",
        "8085487255810",
        "8085490467074",
        "8085503967490",
        "8085493973250",
        "8833398866178",
        "8097035026690",
        "8818296815874",
        "8818183373058",
        "6883727704254",
        "8095604211970",
        "8096966967554",
        "8095399182594",
        "8095397249282",
        "8095395152130",
        "8088531337474",
        "8094686773506",
        "8094613602562",
        "8088210571522",
        "8085710471426",
        "9065559490818",
        "8096892387586",
        "7720713584898",
        "8094521229570",
        "9077162606850",
        "9077162508546",
        "8071387742466",
        "9017754124546",
        "8099722821890",
        "8099648962818",
        "8099648372994",
        "8827267547394",
        "9108593049858",
        "8079004270850",
        "7765114716418",
        "8095613157634",
        "8085716664578",
        "8095439421698",
        "8094573527298",
        "8095399051522",
        "8085636972802",
        "8818226135298",
        "8099815653634",
        "8095411175682",
        "8085499216130",
        "8088268505346",
        "8843937743106",
        "9017741541634",
        "8078817427714",
        "8094515855618",
        "8818283806978",
        "8097004126466",
        "8088272339202",
        "8079001714946",
        "8088261296386",
        "8936571699458",
        "8088535499010",
        "8085636481282",
        "8095431426306",
        "8818195890434",
        "8078961869058",
        "8885868364034",
        "8818293801218",
        "8094534467842",
        "8078941257986",
        "6887012008126",
        "8818284265730",
        "8078886371586",
        "6886990086334",
        "8818207654146",
        "8095610208514",
        "8818183897346",
        "8875891130626",
        "8097031028994",
        "9065556902146",
        "8078878605570",
        "8099538403586",
        "8099535257858",
        "8099529163010",
        "8099519824130",
        "8094610161922",
        "8079008301314",
        "8088227938562",
        "8094558519554",
        "8827280818434",
        "8818177671426",
        "7659276697858",
        "8818183700738",
        "8085734064386",
        "8078880309506",
        "8875883692290",
        "8818244092162",
        "8818293866754",
        "8885877375234",
        "6886989693118",
        "9017741836546",
        "8078888927490",
        "8095600640258",
        "8094540366082",
        "8071389970690",
        "8015704293634",
        "8095589368066",
        "8095588876546",
        "8095581733122",
        "9023387173122",
        "8094515364098",
        "8099644014850",
        "8099643293954",
        "8099642474754",
        "8099642343682",
        "8099641721090",
        "8099641688322",
        "8099641229570",
        "8099639591170",
        "8099639427330",
        "8094519918850",
        "8094558912770",
        "8097055572226",
        "8818195104002",
        "8094536335618",
        "8843995906306",
        "8078876803330",
        "8910792589570",
        "8094527848706",
        "7738599244034",
        "8843953209602",
        "8085610496258",
        "8094549999874",
        "8094540202242",
        "8078915633410",
        "6819944399038",
        "8833398898946",
        "8097013072130",
        "8094663049474",
        "8085728657666",
        "8088211489026",
        "8079006826754",
        "8096901497090",
        "8079000699138",
        "8088547000578",
        "8088539693314",
        "8078880997634",
        "8088210768130",
        "8094519820546",
        "8099716104450",
        "8088224563458",
        "8078880637186",
        "8078940274946",
        "7765114519810",
        "8078816444674",
        "9124811047170",
        "9023387402498",
        "8100474192130",
        "8924908028162",
        "8094573134082",
        "6859922440382",
        "8095432868098",
        "9023390712066",
        "9023390679298",
        "8094679957762",
        "8098720612610",
        "8098719891714",
        "8098719957250",
        "8098718810370",
        "8098719301890",
        "8098719564034",
        "8098720153858",
        "8098721366274",
        "8098720186626",
        "8098720219394",
        "8097023557890",
        "8099675701506",
        "8095491653890",
        "8095422447874",
        "8085492629762",
        "8088225775874",
        "8078959771906",
        "9094579257602",
        "9042204492034",
        "8979933233410",
        "8097004945666",
        "8094526996738",
        "7759267037442",
        "8885872820482",
        "8094702600450",
        "8078899806466",
        "7623265255682",
        "8818237374722",
        "8818297929986",
        "8818187370754",
        "8818187337986",
        "8818187305218",
        "8818187272450",
        "8818187043074",
        "8818186977538",
        "8818186944770",
        "8818186912002",
        "8818186879234",
        "8818186813698",
        "8818186780930",
        "8818186715394",
        "8818186682626",
        "8818186617090",
        "8818186584322",
        "8088259625218",
        "8818226954498",
        "8088209981698",
        "8094782161154",
        "8088511906050",
        "9023387205890",
        "8818194252034",
        "8084032684290",
        "8084062863618",
        "8084055720194",
        "8084038713602",
        "8084018888962",
        "8084018757890",
        "8084049756418",
        "8084029309186",
        "8084067156226",
        "8084071448834",
        "8084053295362",
        "8084059750658",
        "8084047266050",
        "8094527062274",
        "8085725380866",
        "8085636710658",
        "8875883397378",
        "8094572708098",
        "9017740689666",
        "8924919431426",
        "8818194186498",
        "6887001325758",
        "8078884405506",
        "8078816051458",
        "8095602344194",
        "9017737969922",
        "8095432442114",
        "8078921171202",
        "8088248025346",
        "9131029528834",
        "9017741476098",
        "6887004504254",
        "8094722294018",
        "8094553178370",
        "9131028906242",
        "8099727900930",
        "6886994510014",
        "8827269775618",
        "8095403081986",
        "6883735339198",
        "8818215813378",
        "8818227675394",
        "7637867168002",
        "8078896398594",
        "8818218041602",
        "8095427068162",
        "8088234885378",
        "8085602795778",
        "8085522481410",
        "8078937260290",
        "6886995656894",
        "6886992216254",
        "6886991167678",
        "7644351889666",
        "8079007482114",
        "8096962216194",
        "8094569496834",
        "8088268931330",
        "8085709390082",
        "8924907110658",
        "8629549564162",
        "8097064321282",
        "8088537039106",
        "8094662590722",
        "8818294522114",
        "9025775567106",
        "9120836714754",
        "6821758927038",
        "8096924664066",
        "8824683266306",
        "8094534598914",
        "8826548257026",
        "8826548191490",
        "8826548093186",
        "8826547732738",
        "7765098627330",
        "8818198053122",
        "9042206130434",
        "8095462555906",
        "8885868265730",
        "8078884667650",
        "8071393214722",
        "7659274240258",
        "8096941736194",
        "9196409946370",
        "9196409913602",
        "8088226693378",
        "8818298028290",
        "9131030610178",
        "7765114618114",
        "8818180129026",
        "8818179834114",
        "8671932776706",
        "8088244486402",
        "8094546788610",
        "8099710402818",
        "8099495444738",
        "8078963310850",
        "8097028079874",
        "8078880211202",
        "8088546050306",
        "8094580375810",
        "8095394595074",
        "9117924589826",
        "7723266965762",
        "9042207408386",
        "8088239931650",
        "8885872918786",
        "8094520246530",
        "9017752453378",
        "8095420842242",
        "8095405080834",
        "8094605967618",
        "8099735175426",
        "8095428182274",
        "8085725184258",
        "9124809801986",
        "8078963343618",
        "8818286461186",
        "8078945190146",
        "8096945570050",
        "8095492473090",
        "8088533270786",
        "8097050493186",
        "9089970766082",
        "8094780817666",
        "9042205933826",
        "8085634679042",
        "9196409848066",
        "8078880178434",
        "8088268734722",
        "9062831325442",
        "8088219910402",
        "8088274206978",
        "7711985729794",
        "9050834927874",
        "8099722166530",
        "9094579355906",
        "8885871771906",
        "8097038106882",
        "9017752355074",
        "7730619187458",
        "8818298781954",
        "8097032110338",
        "8094629921026",
        "8094614880514",
        "9023389106434",
        "8818191794434",
        "8818296193282",
        "9196406178050",
        "7797590819074",
        "8818286133506",
        "7659281744130",
        "8818283086082",
        "8078963114242",
        "8095581372674",
        "8094639718658",
        "8094627266818",
        "8099621437698",
        "8088235311362",
        "8818231443714",
        "8818294849794",
        "8826599571714",
        "8088532222210",
        "9074289344770",
        "9023386878210",
        "9023386845442",
        "9017741181186",
        "8097059799298",
        "8094733304066",
        "8953385517314",
        "8095462260994",
        "9121767391490",
        "8092884271362",
        "7757170770178",
        "8085634547970",
        "8094560813314",
        "8084053033218",
        "8084058112258",
        "8084056375554",
        "9121768964354",
        "8095416582402",
        "9042207506690",
        "8094587093250",
        "9077162836226",
        "8818259394818",
        "8818243797250",
        "8078878114050",
        "8094574477570",
        "8869343035650",
        "8084039500034",
        "8084024361218",
        "8084020101378",
        "8084067320066",
        "8084020134146",
        "9025801715970",
        "9025790017794",
        "9128343699714",
        "8071394459906",
        "8094563401986",
        "6886992576702",
        "8096982565122",
        "6886987858110",
        "8100490445058",
        "8096992461058",
        "9123336519938",
        "8094527684866",
        "8078885028098",
        "8078884831490",
        "7637860319490",
        "9058692169986",
        "8078882603266",
        "8078945878274",
        "8085484568834",
        "8084055392514",
        "8084054311170",
        "8085459665154",
        "8084024852738",
        "8084021379330",
        "8085457305858",
        "8085484175618",
        "8085421162754",
        "8085476081922",
        "8084043497730",
        "8084043137282",
        "8085486567682",
        "8085486764290",
        "8084060111106",
        "8084050411778",
        "8084049920258",
        "8084035469570",
        "8085484437762",
        "8085416247554",
        "8085477261570",
        "8085476016386",
        "8085444657410",
        "8084030324994",
        "8085482766594",
        "8085469593858",
        "8084065059074",
        "8085410742530",
        "8085482537218",
        "8084018954498",
        "8084030652674",
        "8084027343106",
        "8085485682946",
        "8085405892866",
        "8084020560130",
        "8085484667138",
        "8085413593346",
        "8085477425410",
        "8084044906754",
        "8084040974594",
        "8084036485378",
        "8085482963202",
        "8085480079618",
        "8085478834434",
        "8084022362370",
        "8085448950018",
        "8084018594050",
        "8085484142850",
        "8085461762306",
        "8085411135746",
        "8084039467266",
        "8085481914626",
        "8084024295682",
        "8084022001922",
        "8085486928130",
        "8085408612610",
        "8085479981314",
        "8084052377858",
        "8085482045698",
        "8085418672386",
        "8085476835586",
        "8085476638978",
        "8085467005186",
        "8084026687746",
        "8085477032194",
        "8084023869698",
        "8085487059202",
        "8085477720322",
        "8085478310146",
        "8084034715906",
        "8085406089474",
        "8085436563714",
        "8085428535554",
        "8085483356418",
        "8085477163266",
        "8085477228802",
        "8085484273922",
        "8085444788482",
        "7623285276930",
        "8096954941698",
        "8084073316610",
        "8085479325954",
        "8085472411906",
        "8084048150786",
        "8084045431042",
        "8084039106818",
        "8084029636866",
        "8085479751938",
        "8084027736322",
        "8084071973122",
        "8085484830978",
        "8084051001602",
        "8084049690882",
        "8085452161282",
        "8084036714754",
        "8085482012930",
        "8085479391490",
        "8085480014082",
        "8085486797058",
        "8084020789506",
        "8085484536066",
        "8085481259266",
        "8084069613826",
        "8085481455874",
        "8084043727106",
        "8084026556674",
        "8085476278530",
        "8084071121154",
        "8085480177922",
        "8085457043714",
        "8084048380162",
        "8085485125890",
        "8085480243458",
        "8085477392642",
        "8085479457026",
        "8084044939522",
        "8085482569986",
        "8084030390530",
        "8084025082114",
        "8084069646594",
        "8084063224066",
        "8084061913346",
        "8085479227650",
        "8085482799362",
        "8084034814210",
        "8084020527362",
        "8084071645442",
        "8084063584514",
        "8084058013954",
        "8085486272770",
        "8084062798082",
        "8085484699906",
        "8085484306690",
        "8085482209538",
        "8085480112386",
        "8084071088386",
        "8085486371074",
        "8084041007362",
        "8085439119618",
        "8085484962050",
        "8085526053122",
        "8099621306626",
        "8094553997570",
        "6886992052414",
        "8088533860610",
        "8099552362754",
        "8629545304322",
        "8097028669698",
        "8097037779202",
        "8094688084226",
        "8078880833794",
        "8094545772802",
        "6887006634174",
        "8094523425026",
        "7726322450690",
        "8099517595906",
        "8099510485250",
        "8099505275138",
        "8099505242370",
        "7637897740546",
        "8078958493954",
        "6976179765438",
        "8098726772994",
        "8088535630082",
        "9023387926786",
        "8818205655298",
        "9023387861250",
        "8826548748546",
        "7623278133506",
        "8085733245186",
        "8094516019458",
        "8818180161794",
        "8385042907394",
        "8096961167618",
        "8094551179522",
        "8085716402434",
        "8095573901570",
        "8094528700674",
        "8099826663682",
        "8099825713410",
        "8099824435458",
        "8099824337154",
        "8099823714562",
        "8099823026434",
        "8099821060354",
        "8099820503298",
        "8099820372226",
        "8099818176770",
        "8085723644162",
        "8824698601730",
        "8826576699650",
        "8098743156994",
        "8096958775554",
        "9121767686402",
        "8078885093634",
        "8078885060866",
        "8078884897026",
        "8078884372738",
        "9089972240642",
        "7585084506370",
        "8078963147010",
        "8078808318210",
        "7727838429442",
        "8097007206658",
        "8096998588674",
        "8096992657666",
        "8094521295106",
        "8094542594306",
        "8818012291330",
        "8094573101314",
        "9120834093314",
        "8094644273410",
        "9074279252226",
        "8088913215746",
        "9074292228354",
        "7637859172610",
        "7651807297794",
        "8935339852034",
        "8875890344194",
        "8088211456258",
        "8094610850050",
        "8826558677250",
        "7651827810562",
        "8094560420098",
        "8095607324930",
        "8095580487938",
        "8095604113666",
        "7759268380930",
        "7759268249858",
        "7759267987714",
        "8085512421634",
        "8094570184962",
        "8085633368322",
        "8079004893442",
        "8099563274498",
        "9025788150018",
        "8818201821442",
        "8818297471234",
        "7797518008578",
        "8099565601026",
        "8097006059778",
        "9110446047490",
        "9131030348034",
        "9131030184194",
        "9131030151426",
        "9131030118658",
        "9131030085890",
        "8078948499714",
        "8078915764482",
        "8094578376962",
        "9131030053122",
        "9131030020354",
        "8078923432194",
        "9117937041666",
        "8096994132226",
        "8096974897410",
        "8095483887874",
        "7759267102978",
        "8085730623746",
        "8079008399618",
        "8094558224642",
        "8078913765634",
        "8818188714242",
        "6887012401342",
        "6887010238654",
        "8099828760834",
        "8099572744450",
        "8099828236546",
        "6886989889726",
        "8096984531202",
        "8818185470210",
        "7585085784322",
        "8973221101826",
        "8818289082626",
        "8088214896898",
        "9062829326594",
        "8094545674498",
        "9089970405634",
        "9131513086210",
        "8099717611778",
        "8099709681922",
        "8099718955266",
        "8099705127170",
        "8099714138370",
        "8099705487618",
        "8099717153026",
        "8099717185794",
        "8095401279746",
        "7637862547714",
        "8096954974466",
        "8096963428610",
        "8096942129410",
        "8088220827906",
        "6886990676158",
        "9042204721410",
        "8094523261186",
        "8098715238658",
        "8818293735682",
        "8094689165570",
        "7651797401858",
        "8094531059970",
        "8818291867906",
        "8085615280386",
        "8094525948162",
        "6827125670078",
        "8078817788162",
        "8085720793346",
        "8097002094850",
        "8094571561218",
        "8085720629506",
        "8078964162818",
        "7752601960706",
        "8875893162242",
        "7759268708610",
        "8095609487618",
        "7797590556930",
        "8820489388290",
        "8818194284802",
        "6895043412158",
        "8094686249218",
        "8095589630210",
        "9050837516546",
        "7730024743170",
        "8919916085506",
        "8094567399682",
        "8079009284354",
        "8094562058498",
        "9050838335746",
        "8085636219138",
        "8094665605378",
        "8818185601282",
        "8094540464386",
        "7651798909186",
        "8088503025922",
        "9043015532802",
        "7765109702914",
        "8885871411458",
        "8078964326658",
        "8818201035010",
        "9017752322306",
        "8088259756290",
        "8097002356994",
        "8096995442946",
        "8088546574594",
        "8099656794370",
        "8096965230850",
        "8099708797186",
        "8096965722370",
        "8096950649090",
        "8094631100674",
        "9017740886274",
        "8079007711490",
        "8095425364226",
        "8099747299586",
        "8999681097986",
        "8096988168450",
        "8629569749250",
        "8095594905858",
        "8099625140482",
        "9042204393730",
        "8097029783810",
        "8078886273282",
        "8078886207746",
        "8078885945602",
        "8085713813762",
        "8094686675202",
        "8876782977282",
        "8922694385922",
        "8826547241218",
        "8818214764802",
        "9117935829250",
        "8094605213954",
        "8099627041026",
        "8099625992450",
        "8099799433474",
        "8094516805890",
        "8099634708738",
        "8876783042818",
        "8817991385346",
        "8046787952898",
        "8046790279426",
        "8046785822978",
        "8046789755138",
        "8046788247810",
        "8098711077122",
        "8919911661826",
        "8924910878978",
        "9229975716098",
        "8085621309698",
        "9117921902850",
        "8097024213250",
        "9062829818114",
        "8110005846274",
        "9106702958850",
        "8094516216066",
        "7765109768450",
        "8095476154626",
        "8099577430274",
        "8099570712834",
        "8099575988482",
        "8099565666562",
        "8094690115842",
        "8078882504962",
        "8095566168322",
        "8095398854914",
        "8097033158914",
        "9023387664642",
        "8852223852802",
        "8094536433922",
        "8094543905026",
        "8078913732866",
        "8094548623618",
        "9043034046722",
        "8885873541378",
        "8919915856130",
        "9017740296450",
        "9017740263682",
        "9017740230914",
        "9017740198146",
        "9017740165378",
        "9017740132610",
        "9017740067074",
        "9017740034306",
        "8818192646402",
        "8094522048770",
        "7659285217538",
        "8973220970754",
        "8826547634434",
        "8096908673282",
        "9089970438402",
        "8088535073026",
        "8078884962562",
        "8085632483586",
        "8088208703746",
        "8094529913090",
        "8826548650242",
        "8096951042306",
        "8096945275138",
        "6826093543614",
        "8818182455554",
        "8099820732674",
        "8099819913474",
        "8095443222786",
        "8085720367362",
        "8096906674434",
        "8094530371842",
        "9034063544578",
        "9120759415042",
        "7730938839298",
        "8095586550018",
        "8096956219650",
        "8078914158850",
        "7576283873538",
        "8078886338818",
        "8078958297346",
        "8088913346818",
        "7749310152962",
        "8085720301826",
        "7753025913090",
        "8078882439426",
        "8085720957186",
        "8094524113154",
        "8085628059906",
        "8088223842562",
        "9078755524866",
        "8078959214850",
        "8094642667778",
        "8094530175234",
        "8094524637442",
        "8100476551426",
        "9095101382914",
        "8094525128962",
        "8827276099842",
        "8078945288450",
        "8088545198338",
        "8079007777026",
        "8078823162114",
        "8099651748098",
        "8099648241922",
        "8078948991234",
        "9017741607170",
        "8078878867714",
        "8085733835010",
        "8096997507330",
        "9091297181954",
        "8094602526978",
        "9023389401346",
        "8079071609090",
        "9074279842050",
        "7765114880258",
        "8085733900546",
        "7946839097602",
        "8095574589698",
        "9112155390210",
        "9112155291906",
        "8094571725058",
        "8826547470594",
        "8826547339522",
        "8818211946754",
        "8099838853378",
        "8088502829314",
        "8094549213442",
        "8973221921026",
        "8973221888258",
        "8094657577218",
        "8094612652290",
        "8094697521410",
        "8973221069058",
        "8099827810562",
        "9117921247490",
        "9017741705474",
        "8071395016962",
        "8096976306434",
        "8818191499522",
        "8891290484994",
        "8886717120770",
        "8099685073154",
        "8071394394370",
        "8818193301762",
        "8098715828482",
        "8818301501698",
        "8094687920386",
        "8096975126786",
        "6894996226238",
        "8078948729090",
        "9017740591362",
        "8078883488002",
        "8078882898178",
        "8085720760578",
        "7644353069314",
        "8973220413698",
        "8818298290434",
        "8095566725378",
        "8818189893890",
        "8095582748930",
        "9131514822914",
        "9131514724610",
        "8099825418498",
        "7721677816066",
        "7694053867778",
        "8085728002306",
        "8937014329602",
        "8099845112066",
        "8097014743298",
        "8085618000130",
        "8972802982146",
        "8094573920514",
        "8085618721026",
        "8096921387266",
        "8095423561986",
        "9074292326658",
        "8818283217154",
        "8088238096642",
        "8085736554754",
        "8818188779778",
        "9023387468034",
        "8099763093762",
        "8096983515394",
        "8977693212930",
        "8818224070914",
        "9121767457026",
        "8098726478082",
        "8094557438210",
        "8088251334914",
        "8099706339586",
        "8097037418754",
        "6844261138622",
        "6844261007550",
        "6844260810942",
        "6886993625278",
        "8096946979074",
        "7585086603522",
        "8099830563074",
        "9124811473154",
        "9124811342082",
        "9124811145474",
        "9124811014402",
        "9124810850562",
        "9124810817794",
        "9124810752258",
        "9124810653954",
        "9124810588418",
        "9124810522882",
        "9124810424578",
        "9124810326274",
        "9124810260738",
        "6849817706686",
        "6886985466046",
        "8078822834434",
        "9124811571458",
        "9124811538690",
        "9124811374850",
        "9124811276546",
        "9124811243778",
        "9124811211010",
        "9124811079938",
        "9124810981634",
        "9124810948866",
        "9124810785026",
        "9124810457346",
        "9124810391810",
        "8085632975106",
        "8078948466946",
        "8094516674818",
        "8088234852610",
        "8088233410818",
        "8088231510274",
        "8078949056770",
        "8099818471682",
        "9124809146626",
        "9124809113858",
        "9124809048322",
        "8099561013506",
        "8099565404418",
        "8099568943362",
        "8099568091394",
        "8099564978434",
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