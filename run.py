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
        "8099675275522",
        "8099797336322",
        "8099796943106",
        "8099796746498",
        "8099796353282",
        "8099796156674",
        "8099795960066",
        "8099795894530",
        "8099795763458",
        "8099794944258",
        "8099794518274",
        "8099794321666",
        "8099793993986",
        "8099793731842",
        "8099793699074",
        "8099793600770",
        "8099793240322",
        "8099792748802",
        "8099792617730",
        "8099792486658",
        "8099792421122",
        "8099792355586",
        "8099792126210",
        "8099792093442",
        "8099791831298",
        "8099791536386",
        "8099791143170",
        "8099790586114",
        "8099790389506",
        "8099790356738",
        "8099790029058",
        "8099789111554",
        "8099789046018",
        "8099789013250",
        "8099788751106",
        "8099788554498",
        "8099788488962",
        "8099787342082",
        "8099787243778",
        "8099787211010",
        "8099787047170",
        "8099786916098",
        "8099786752258",
        "8099786621186",
        "8099786326274",
        "8099786031362",
        "8099785769218",
        "8099784982786",
        "8099784950018",
        "8099784851714",
        "8099784720642",
        "8099784491266",
        "8099784098050",
        "8099783311618",
        "8099783049474",
        "8099782852866",
        "8099782689026",
        "8099782557954",
        "8099782197506",
        "8099782099202",
        "8099781607682",
        "8099781312770",
        "8099780755714",
        "8099780231426",
        "8099779772674",
        "8099779674370",
        "8099779543298",
        "8099779150082",
        "8099778429186",
        "8099778134274",
        "8099778003202",
        "8099777970434",
        "8099777577218",
        "8099777413378",
        "8099777347842",
        "8099777216770",
        "8099776921858",
        "8099776495874",
        "8099775873282",
        "8099775545602",
        "8099775414530",
        "8099775217922",
        "8099774857474",
        "8827270824194",
        "8085501149442",
        "9025801683202",
        "8099789144322",
        "8099783147778",
        "8818294915330",
        "8095426511106",
        "8095427723522",
        "7739814412546",
        "8097000161538",
        "8826575323394",
        "9025789821186",
        "8096996786434",
        "8876784517378",
        "9035897733378",
        "8094517854466",
        "9117938188546",
        "9117938090242",
        "9117937828098",
        "9117937729794",
        "9117937500418",
        "8078822736130",
        "8078822768898",
        "9017739411714",
        "8818301468930",
        "8094549475586",
        "8094548918530",
        "8094548459778",
        "8094547116290",
        "8094546755842",
        "8094546067714",
        "8094545379586",
        "8094543216898",
        "8094541512962",
        "8094541152514",
        "8094539809026",
        "8094538039554",
        "8094536892674",
        "8094536794370",
        "8099769909506",
        "8095423430914",
        "8818267717890",
        "8094519329026",
        "8099780788482",
        "8099788914946",
        "8099783803138",
        "8099602497794",
        "8818284757250",
        "8099711746306",
        "8885876162818",
        "9035896488194",
        "8099656663298",
        "6824303231166",
        "8099660726530",
        "8099656892674",
        "8094520574210",
        "8818258084098",
        "8097001111810",
        "9017739378946",
        "8095488835842",
        "9035898683650",
        "8099655123202",
        "8088530944258",
        "6862016708798",
        "8095579799810",
        "8078916288770",
        "8885874721026",
        "8095429558530",
        "9114881720578",
        "8078917107970",
        "8094523719938",
        "8099679404290",
        "8095409602818",
        "8818201428226",
        "7756233081090",
        "8824694046978",
        "8824693686530",
        "8818295537922",
        "8094521164034",
        "8078937063682",
        "8099767746818",
        "8094740644098",
        "8097007272194",
        "8088531665154",
        "6886996738238",
        "8094643355906",
        "8885872460034",
        "8097044398338",
        "8099702178050",
        "8099565994242",
        "8099537649922",
        "8099528179970",
        "8088239374594",
        "8824704794882",
        "8094529126658",
        "8098716483842",
        "8094520115458",
        "8824680710402",
        "8095435849986",
        "8078916354306",
        "8094520148226",
        "8099492823298",
        "8078917271810",
        "8094521393410",
        "8818296553730",
        "8095419040002",
        "8818187862274",
        "8095617941762",
        "8818188189954",
        "8099707224322",
        "8085719515394",
        "8085719449858",
        "8095421202690",
        "8085719810306",
        "9120841826562",
        "6862016118974",
        "8099784818946",
        "8088506532098",
        "8818260967682",
        "8096992264450",
        "8088502862082",
        "9121767620866",
        "8943431352578",
        "8818294128898",
        "8076212961538",
        "8099541844226",
        "9074279383298",
        "8824705024258",
        "8824704925954",
        "8094519623938",
        "8099702735106",
        "8818294325506",
        "8088506859778",
        "8095425528066",
        "8097010811138",
        "8099774955778",
        "8088888115458",
        "8088545231106",
        "9074279121154",
        "9025789100290",
        "9017740427522",
        "9017740394754",
        "8818177212674",
        "8095425069314",
        "8818295374082",
        "8096979091714",
        "8095405244674",
        "8818177540354",
        "8818171871490",
        "8094652498178",
        "8818282660098",
        "8818048958722",
        "8099686646018",
        "8826574995714",
        "8818181308674",
        "8935298990338",
        "8818294292738",
        "8094529945858",
        "8818288918786",
        "8818205262082",
        "7720439349506",
        "8854568567042",
        "8854567649538",
        "8078823817474",
        "8078920483074",
        "8094680580354",
        "8099521429762",
        "8078884798722",
        "8924911075586",
        "8078913208578",
        "8095396593922",
        "8094685069570",
        "8099474440450",
        "8099654926594",
        "8095432737026",
        "8919914316034",
        "8099798253826",
        "8094727307522",
        "9017739510018",
        "6862021689534",
        "8095407374594",
        "8078939128066",
        "8098731098370",
        "8095407833346",
        "8095429591298",
        "9089970471170",
        "8094522671362",
        "8095392694530",
        "8094536171778",
        "8095457870082",
        "8078940406018",
        "7690444013826",
        "9065548710146",
        "8088252285186",
        "8088251564290",
        "8099790848258",
        "8095426019586",
        "8100490412290",
        "8099772629250",
        "8095489753346",
        "8099701588226",
        "6894997864638",
        "6862030602430",
        "8094529290498",
        "8094735532290",
        "8824696242434",
        "8099784556802",
        "9089971814658",
        "8078825685250",
        "8097048166658",
        "8094522147074",
        "8094516412674",
        "8099481092354",
        "8099468017922",
        "8818190680322",
        "8818295472386",
        "8818185076994",
        "8818189369602",
        "8818284396802",
        "8629548744962",
        "9074289246466",
        "8099506848002",
        "8099502063874",
        "8099492167938",
        "6886991331518",
        "8818185863426",
        "8094700339458",
        "7746112487682",
        "8094686609666",
        "8098721464578",
        "8824694833410",
        "8095450005762",
        "8873629974786",
        "6723762979006",
        "8099770466562",
        "8099766042882",
        "8818217877762",
        "8094521852162",
        "9117921378562",
        "9117921411330",
        "8095405637890",
        "6895047311550",
        "9074289213698",
        "8818281709826",
        "9074288886018",
        "8751388524802",
        "8826592690434",
        "8818193662210",
        "8824707023106",
        "8078925332738",
        "8924916613378",
        "8824723865858",
        "9089971912962",
        "8078897578242",
        "8953386139906",
        "8885868134658",
        "8094531453186",
        "8095433523458",
        "8095416025346",
        "8095618793730",
        "8818171085058",
        "7711989465346",
        "8096984105218",
        "8818180194562",
        "8088535761154",
        "9112153817346",
        "9112153784578",
        "9112153391362",
        "9112153325826",
        "8078899118338",
        "8751383019778",
        "9239732945154",
        "8818188255490",
        "8094530404610",
        "9095100956930",
        "8088215879938",
        "9043016548610",
        "9117938647298",
        "9117938483458",
        "8078919139586",
        "8818195038466",
        "9025789034754",
        "9000953544962",
        "8085706113282",
        "8996700553474",
        "8824689033474",
        "8099790717186",
        "8094680285442",
        "8078917468418",
        "8085708439810",
        "8094684938498",
        "8085569896706",
        "8085518745858",
        "8885870887170",
        "9065560408322",
        "9065559556354",
        "8094564712706",
        "8085529100546",
        "8085512552706",
        "8088213750018",
        "8094791368962",
        "8754017861890",
        "8753962483970",
        "8818171543810",
        "8818179178754",
        "8078826340610",
        "8109984973058",
        "9050834829570",
        "9270556197122",
        "8099637428482",
        "8099636084994",
        "8935161135362",
        "8097030537474",
        "6827127406782",
        "8099795599618",
        "8099794223362",
        "8099792290050",
        "8099789603074",
        "8097017528578",
        "8095459246338",
        "8885872951554",
        "8094536073474",
        "8078937719042",
        "8095462654210",
        "8818292818178",
        "8078819131650",
        "8818295308546",
        "8096946192642",
        "8099557638402",
        "8078961705218",
        "8818241470722",
        "8818182947074",
        "8818285314306",
        "8818172625154",
        "7694074118402",
        "8099733405954",
        "8818294096130",
        "8078919860482",
        "8085710176514",
        "8078938734850",
        "8818183962882",
        "8095581798658",
        "9050834632962",
        "8099798057218",
        "8919912022274",
        "8079009218818",
        "8818295439618",
        "8827285405954",
        "8095482085634",
        "9095101120770",
        "8818284495106",
        "6661295014078",
        "8818260443394",
        "8095391482114",
        "8098716254466",
        "9089972044034",
        "8094529487106",
        "8818286199042",
        "8099766796546",
        "8843932598530",
        "8078937489666",
        "9089971847426",
        "8094709907714",
        "9034211098882",
        "8099599384834",
        "8818210996482",
        "8094707482882",
        "8094687985922",
        "8818221580546",
        "8078923399426",
        "8094527160578",
        "8885875147010",
        "8094523588866",
        "9089971880194",
        "8094613209346",
        "9023386583298",
        "9042205671682",
        "8818230100226",
        "8094526341378",
        "8078917435650",
        "8094526275842",
        "7727836987650",
        "8095601688834",
        "8085628911874",
        "8818181341442",
        "9017740787970",
        "9017740722434",
        "8095622365442",
        "8095429198082",
        "8095466193154",
        "8924911960322",
        "7756279382274",
        "9117923836162",
        "9117923770626",
        "8078880375042",
        "8078880145666",
        "8088250122498",
        "8095619383554",
        "8824696930562",
        "8824696799490",
        "8824696635650",
        "8824696537346",
        "8078937030914",
        "9023386648834",
        "8088215060738",
        "6661294031038",
        "8094689296642",
        "8078881423618",
        "8094700994818",
        "8099505471746",
        "8818294030594",
        "8088507908354",
        "8078917501186",
        "8095460491522",
        "8818190582018",
        "8095624233218",
        "8095615353090",
        "8095576326402",
        "8818179703042",
        "8085573763330",
        "8085557838082",
        "8818186289410",
        "7738604093698",
        "8088253563138",
        "8818232295682",
        "8085625372930",
        "8827269939458",
        "8078963409154",
        "8099787833602",
        "8094683201794",
        "9089971781890",
        "8078817689858",
        "8085594636546",
        "8085601485058",
        "8085595095298",
        "8085517730050",
        "8085592965378",
        "8085521727746",
        "8085518188802",
        "8085510619394",
        "8085596668162",
        "8085517369602",
        "8085539750146",
        "8085515206914",
        "9025789067522",
        "8097034174722",
        "8095459574018",
        "8095393480962",
        "8094719770882",
        "8088545034498",
        "8818182619394",
        "8094528733442",
        "8818060230914",
        "8078879129858",
        "8097010843906",
        "8088258511106",
        "8088256512258",
        "8818293965058",
        "8088534712578",
        "8094558814466",
        "9042203476226",
        "8078900134146",
        "8818301174018",
        "8818259984642",
        "8094651187458",
        "8818179571970",
        "8078822899970",
        "8818295177474",
        "8818191663362",
        "8818013110530",
        "8818281283842",
        "8095423365378",
        "8078919237890",
        "9017740493058",
        "8096913555714",
        "9123046916354",
        "8095572001026",
        "9023386484994",
        "9023386681602",
        "8094524735746",
        "9089972207874",
        "8095449055490",
        "8085699789058",
        "8818239504642",
        "8818215158018",
        "8094566023426",
        "8094526800130",
        "8085701558530",
        "8823668506882",
        "8818062754050",
        "8097031979266",
        "8818184651010",
        "8094548164866",
        "8879210529026",
        "8979941982466",
        "7738603897090",
        "7738601996546",
        "8094524932354",
        "8085732983042",
        "8088233738498",
        "8088217190658",
        "8903374471426",
        "8095608078594",
        "8824342380802",
        "6819943612606",
        "9108596556034",
        "8078940111106",
        "8078876737794",
        "8818222596354",
        "8085719023874",
        "8085719089410",
        "8085718532354",
        "8818281185538",
        "8095391383810",
        "8094536040706",
        "8818285183234",
        "8085609677058",
        "8085609644290",
        "8085609480450",
        "8085609349378",
        "8085609283842",
        "8085609218306",
        "8085609054466",
        "8085609021698",
        "8085608890626",
        "8085608857858",
        "8085608694018",
        "8085608628482",
        "8085608530178",
        "8085608497410",
        "8085608268034",
        "8085607710978",
        "8085607645442",
        "8085607317762",
        "8085607055618",
        "8085606924546",
        "8085606629634",
        "8085606596866",
        "8085606138114",
        "9095101284610",
        "8088541888770",
        "8875885592834",
        "7746115240194",
        "8088879104258",
        "8818282037506",
        "8098727919874",
        "8818181177602",
        "6723702587582",
        "8818210078978",
        "8094538367234",
        "8818174165250",
        "8835950051586",
        "8094528602370",
        "8094526439682",
        "8094524145922",
        "8094522474754",
        "8095435686146",
        "8094688346370",
        "9110374613250",
        "8095431262466",
        "8094644240642",
        "8078938833154",
        "8095434146050",
        "8818301600002",
        "9108596818178",
        "8085631467778",
        "8818239734018",
        "8088913248514",
        "8095428083970",
        "7738602520834",
        "9089970503938",
        "8088228167938",
        "9017740361986",
        "8827282751746",
        "8078876442882",
        "9034211000578",
        "8818057052418",
        "8818056757506",
        "8818034147586",
        "8818032247042",
        "8078804320514",
        "8818299404546",
        "9077161165058",
        "8078881554690",
        "8088237801730",
        "7738604224770",
        "8818228396290",
        "9023385796866",
        "8818217058562",
        "8885876916482",
        "8078938702082",
        "8078938571010",
        "8094689820930",
        "8078876705026",
        "8826599506178",
        "9025788510466",
        "8071392329986",
        "9017739247874",
        "8085483323650",
        "8099946463490",
        "8094728126722",
        "7738603208962",
        "8088248975618",
        "8099865231618",
        "8095399411970",
        "8098740011266",
        "8818298061058",
        "8097030635778",
        "9023386550530",
        "8094683365634",
        "8833399488770",
        "8088222138626",
        "8078916944130",
        "8088274600194",
        "8094536237314",
        "8088226431234",
        "8823667622146",
        "8097000718594",
        "8094549934338",
        "8092884500738",
        "8094562353410",
        "8085715583234",
        "9025789460738",
        "8096989217026",
        "8097032536322",
        "8094568218882",
        "8094515101954",
        "8094641553666",
        "8088229347586",
        "9128343929090",
        "8098730836226",
        "8094808572162",
        "8099751559426",
        "8818262409474",
        "8818032574722",
        "8094533779714",
        "8078915895554",
        "8088233476354",
        "9025789427970",
        "8088529830146",
        "8078961344770",
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