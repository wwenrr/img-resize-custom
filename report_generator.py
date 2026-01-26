def get_file_size_display(size_in_bytes):
    return f"{size_in_bytes / 1024:.2f} KB"

def generate_html_report(data, filename="report.html", product_id=None, shop_url=None):
    # Extract store name from shop_url
    store_name = ""
    admin_link = ""
    if shop_url and product_id:
        # shop_url format: "japan-toy-and-figure.myshopify.com"
        store_name = shop_url.replace(".myshopify.com", "")
        admin_link = f"https://admin.shopify.com/store/{store_name}/products/{product_id}?fromInventory=true"
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Image Optimization Report</title>
        <style>
            body {{ font-family: sans-serif; padding: 20px; background: #f4f4f4; }}
            h1 {{ text-align: center; }}
            .admin-link {{ text-align: center; margin: 20px 0; }}
            .admin-link a {{ 
                display: inline-block;
                padding: 10px 20px;
                background: #5c6ac4;
                color: white;
                text-decoration: none;
                border-radius: 4px;
                font-weight: bold;
            }}
            .admin-link a:hover {{ background: #4959bd; }}
            table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            th, td {{ padding: 15px; text-align: left; border-bottom: 1px solid #ddd; vertical-align: top; }}
            th {{ background: #333; color: white; }}
            .img-preview {{ max-width: 200px; height: auto; border: 1px solid #ddd; padding: 4px; border-radius: 4px; }}
            .stat-label {{ font-weight: bold; color: #666; font-size: 0.9em; }}
            .stat-val {{ font-family: monospace; }}
            .diff-good {{ color: green; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h1>Optimization Report</h1>
        {f'<div class="admin-link"><a href="{admin_link}" target="_blank">🔗 Open in Shopify Admin</a></div>' if admin_link else ''}
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Original</th>
                    <th>Optimized (WebP, Max 1500px, Q=75)</th>
                    <th>Savings</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for item in data:
        orig = item['orig']
        new = item['new']
        
        if not orig or not new:
            continue
            
        savings_bytes = orig['size'] - new['size']
        savings_percent = (savings_bytes / orig['size']) * 100
        
        html_content += f"""
                <tr>
                    <td>{item['id']}</td>
                    <td>
                        <a href="{orig['url']}" target="_blank">
                            <img src="{orig['url']}" class="img-preview">
                        </a><br>
                        <span class="stat-label">Size:</span> <span class="stat-val">{get_file_size_display(orig['size'])}</span><br>
                        <span class="stat-label">Res:</span> <span class="stat-val">{orig['width']}x{orig['height']}</span><br>
                        <span class="stat-label">Fmt:</span> <span class="stat-val">{orig['format']}</span><br>
                        <span class="stat-label">Ch:</span> <span class="stat-val">{orig.get('channels', 'N/A')}</span><br>
                        <span class="stat-label">Depth:</span> <span class="stat-val">{orig.get('bit_depth', 'N/A')}</span>
                    </td>
                    <td>
                        <a href="{new['path']}" target="_blank">
                            <img src="{new['path']}" class="img-preview">
                        </a><br>
                        <span class="stat-label">Size:</span> <span class="stat-val">{get_file_size_display(new['size'])}</span><br>
                        <span class="stat-label">Res:</span> <span class="stat-val">{new['width']}x{new['height']}</span><br>
                        <span class="stat-label">Fmt:</span> <span class="stat-val">{new.get('format', 'WEBP')}</span><br>
                        <span class="stat-label">Ch:</span> <span class="stat-val">{new.get('channels', 'N/A')}</span><br>
                        <span class="stat-label">Depth:</span> <span class="stat-val">{new.get('bit_depth', 'N/A')}</span>
                    </td>
                    <td>
                        <span class="diff-good">-{get_file_size_display(savings_bytes)}</span><br>
                        <span class="diff-good">(-{savings_percent:.1f}%)</span>
                    </td>
                </tr>
        """
        
    html_content += """
            </tbody>
        </table>
    </body>
    </html>
    """
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"\nReport generated: {filename}")

def generate_index_html():
    """Generate index.html that summarizes all report files"""
    import os
    import glob
    from datetime import datetime
    
    def time_ago(timestamp):
        """Convert timestamp to relative time like '5 phút trước'"""
        now = datetime.now()
        past = datetime.fromtimestamp(timestamp)
        diff = now - past
        
        seconds = diff.total_seconds()
        
        if seconds < 60:
            return "vừa xong"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} phút trước"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours} giờ trước"
        else:
            days = int(seconds / 86400)
            return f"{days} ngày trước"
    
    # Find all report files
    report_files = glob.glob("report-*.html")
    report_files.sort(key=os.path.getmtime, reverse=True)  # Sort by modification time
    
    if not report_files:
        print("No report files found.")
        return
    
    # Collect summary data
    summary_data = []
    total_images = 0
    
    for report_file in report_files:
        try:
            # Extract product ID from filename
            product_id = report_file.replace("report-", "").replace(".html", "")
            
            # Get file modification time
            mtime = os.path.getmtime(report_file)
            mtime_str = time_ago(mtime)
            mtime_full = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
            
            # Parse HTML to get stats (simple approach)
            with open(report_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Count images (count number of <tr> rows minus header)
            image_count = content.count('<tr>') - 1  # -1 for header row
            
            # Extract savings from diff-good spans
            import re
            savings_matches = re.findall(r'<span class="diff-good">-([0-9.]+)\s*KB</span>', content)
            percent_matches = re.findall(r'<span class="diff-good">\(-([0-9.]+)%\)</span>', content)
            
            if savings_matches:
                total_savings_kb = sum(float(s) for s in savings_matches)
                avg_percent = sum(float(p) for p in percent_matches) / len(percent_matches) if percent_matches else 0
                
                summary_data.append({
                    'product_id': product_id,
                    'report_file': report_file,
                    'image_count': image_count,
                    'total_savings_kb': total_savings_kb,
                    'avg_percent': avg_percent,
                    'mtime_str': mtime_str,
                    'mtime_full': mtime_full
                })
                
                total_images += image_count
        except Exception as e:
            print(f"Error processing {report_file}: {e}")
    
    # Generate index HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Image Optimization Report</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: #f5f5f5;
            padding: 40px 20px;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }}
        h1 {{
            color: #333;
            font-size: 1.8em;
            margin-bottom: 5px;
            border-bottom: 2px solid #eee;
            padding-bottom: 15px;
        }}
        .subtitle {{
            color: #777;
            margin-bottom: 30px;
            font-size: 0.9em;
            margin-top: 10px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: #fafafa;
            padding: 20px;
            border-radius: 6px;
            border: 1px solid #eee;
        }}
        .stat-value {{
            font-size: 1.8em;
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
        }}
        .stat-label {{
            color: #666;
            font-size: 0.8em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            font-size: 0.95em;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #eee;
        }}
        th {{
            background: #f8f9fa;
            color: #444;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.8em;
            letter-spacing: 0.5px;
        }}
        tr:hover {{
            background: #fbfbfb;
        }}
        .product-link {{
            color: #0066cc;
            text-decoration: none;
            font-weight: 500;
        }}
        .product-link:hover {{
            text-decoration: underline;
        }}
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            background: #e9ecef;
            color: #495057;
            border-radius: 4px;
            font-size: 0.85em;
            font-weight: 600;
        }}
        .savings {{
            color: #28a745;
            font-weight: 600;
        }}
        .percent {{
            color: #17a2b8;
            font-weight: 600;
        }}
        .time {{
            color: #666;
            font-size: 0.9em;
            white-space: nowrap;
        }}
        code {{
            background: #f1f3f5;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
            font-size: 0.9em;
            color: #c92a2a;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Image Optimization Report</h1>
        <p class="subtitle">Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Sorted by newest first</p>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{len(summary_data)}</div>
                <div class="stat-label">Products</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_images}</div>
                <div class="stat-label">Images</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{sum(d['total_savings_kb'] for d in summary_data):.0f} KB</div>
                <div class="stat-label">Total Saved</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{sum(d['avg_percent'] for d in summary_data) / len(summary_data) if summary_data else 0:.1f}%</div>
                <div class="stat-label">Avg Reduction</div>
            </div>
        </div>
        
        <table>
            <thead>
                <tr>
                    <th>Product ID</th>
                    <th>Images</th>
                    <th>Saved</th>
                    <th>Reduction</th>
                    <th>Last Modified</th>
                    <th>Action</th>
                </tr>
            </thead>
            <tbody>"""
    
    for data in summary_data:
        html += f"""
                <tr>
                    <td><code>{data['product_id']}</code></td>
                    <td><span class="badge">{data['image_count']}</span></td>
                    <td class="savings">-{data['total_savings_kb']:.2f} KB</td>
                    <td class="percent">-{data['avg_percent']:.1f}%</td>
                    <td class="time" title="{data['mtime_full']}">{data['mtime_str']}</td>
                    <td><a href="{data['report_file']}" class="product-link" target="_blank">View details →</a></td>
                </tr>"""
    
    html += """
            </tbody>
        </table>
    </div>
</body>
</html>"""
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"\n✨ Index generated: index.html (Total: {len(summary_data)} products, {total_images} images)")