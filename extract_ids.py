#!/usr/bin/env python3
"""
Extract product IDs from Shopify admin links
Paste console output, script will extract all product IDs
"""

import re
import sys

def extract_ids(text):
    """Extract product IDs from Shopify admin URLs"""
    pattern = r'products/(\d+)'
    ids = re.findall(pattern, text)
    
    # Remove duplicates, preserve order
    seen = set()
    unique = []
    for id in ids:
        if id not in seen:
            seen.add(id)
            unique.append(id)
    
    return unique

# Read from stdin
print("Paste console output, then press Ctrl+D:")
text = sys.stdin.read()

ids = extract_ids(text)

print(f"\n✓ Extracted {len(ids)} unique product IDs\n")
print("=" * 60)
print("Copy this to run.py:")
print("=" * 60)
print("\nPRODUCT_IDS = [")
for id in ids:
    print(f'    "{id}",')
print("]")
print("\nMODE = \"product_ids\"")
print("=" * 60)

# Save to file
with open("product_ids.txt", "w") as f:
    f.write("PRODUCT_IDS = [\n")
    for id in ids:
        f.write(f'    "{id}",\n')
    f.write("]\n\nMODE = \"product_ids\"\n")

print(f"\n✓ Saved to: product_ids.txt")
