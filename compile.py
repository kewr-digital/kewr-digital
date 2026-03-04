import os
import re
import shutil
import json
import sys
import http.server
import socketserver
import argparse
import urllib.request
import time

def minify_html(content):
    # Remove HTML comments
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    # Collapse whitespace (but be careful with <pre>, <script>, <style>)
    # For simplicity, we just collapse multiple spaces/newlines outside of tags
    content = re.sub(r'>\s+<', '><', content)
    content = re.sub(r'\s{2,}', ' ', content)
    return content.strip()

def minify_css(content):
    # Remove comments
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    # Remove whitespace around delimiters
    content = re.sub(r'\s*([\{\};:,])\s*', r'\1', content)
    # Remove extra spaces/newlines
    content = re.sub(r'\s+', ' ', content)
    return content.strip()

def minify_js(content):
    # Remove multi-line comments
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    # Remove single-line comments (careful with URLs)
    content = re.sub(r'(?<!:)\/\/.*', '', content)
    
    # Aggressive whitespace removal for obfuscation-like effect
    # Split into lines to remove them and join with no space where possible
    lines = content.split('\n')
    minified_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            minified_lines.append(stripped)
    
    # Rejoin and remove spaces around operators
    content = ' '.join(minified_lines)
    content = re.sub(r'\s*([=\{\}\(\)\[\]\+\-\*\/,;:])\s*', r'\1', content)
    # Remove any doubling spaces from the join above
    content = re.sub(r'\s{2,}', ' ', content)
    return content.strip()

def inline_icons(content):
    # Ensure icons directory exists
    os.makedirs('icons', exist_ok=True)
    
    # Find all <i data-lucide="icon-name" ...></i>
    def replace_icon(match):
        icon_name = match.group(1)
        extra_attrs = match.group(2)
        
        icon_path = os.path.join('icons', f"{icon_name}.svg")
            
        if not os.path.exists(icon_path):
            print(f"📡 Fetching missing icon: {icon_name}...")
            try:
                url = f"https://raw.githubusercontent.com/lucide-icons/lucide/main/icons/{icon_name}.svg"
                with urllib.request.urlopen(url) as response:
                    svg_content = response.read().decode('utf-8')
                    with open(icon_path, 'w') as f:
                        f.write(svg_content)
                time.sleep(0.1) # Small delay to be polite to GitHub
            except Exception as e:
                print(f"⚠️ Error fetching icon '{icon_name}': {e}")
                return match.group(0) # Return original on failure

        if os.path.exists(icon_path):
            with open(icon_path, 'r') as f:
                svg_content = f.read()
            
            # Combine all child elements (paths, circles, etc.)
            inner_svg = "".join(re.findall(r'<(?:path|circle|line|polyline|polygon|rect|ellipse|text)[^>]*>', svg_content))
            
            # Extract classes from <i> and merge with default lucide classes
            classes = re.search(r'class="([^"]*)"', extra_attrs)
            extra_classes = classes.group(1) if classes else ""
            
            # Build new SVG tag
            return f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-{icon_name} {extra_classes}">{inner_svg}</svg>'
        return match.group(0)

    # Replace <i> tags
    content = re.sub(r'<i data-lucide="([^"]+)"([^>]*)></i>', replace_icon, content)
    
    # Remove Lucide script tag (handling both local and CDN paths)
    content = re.sub(r'<script src="[^"]*lucide(?:\.min)?\.js"></script>', '', content)
    return content

def compile_project():
    dist_dir = 'dist'
    src_dir = '.'
    
    print(f"\n🚀 Starting build process...")
    
    # Clean/Create dist folder
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
    os.makedirs(dist_dir)

    # Assets and subfolders
    folders_to_copy = ['images']
    for folder in folders_to_copy:
        if os.path.exists(folder):
            shutil.copytree(folder, os.path.join(dist_dir, folder))
            print(f"✅ Copied {folder}/")

    # Single files (minified or copied)
    files = os.listdir(src_dir)
    
    # Process HTML files
    html_files = [f for f in files if f.endswith('.html')]
    for html_file in html_files:
        print(f"📦 Processing and Minifying {html_file}...")
        with open(html_file, 'r') as f:
            content = f.read()
        
        # Inline Lucide icons
        content = inline_icons(content)
        
        minified = minify_html(content)
        with open(os.path.join(dist_dir, html_file), 'w') as f:
            f.write(minified)

    # Process CSS
    os.makedirs(os.path.join(dist_dir, 'css'), exist_ok=True)
    if os.path.exists('css'):
        for css_file in [f for f in os.listdir('css') if f.endswith('.css')]:
            print(f"📦 Minifying css/{css_file}...")
            with open(os.path.join('css', css_file), 'r') as f:
                content = f.read()
            minified = minify_css(content)
            with open(os.path.join(dist_dir, 'css', css_file), 'w') as f:
                f.write(minified)

    # Process JS
    os.makedirs(os.path.join(dist_dir, 'js'), exist_ok=True)
    if os.path.exists('js'):
        for js_file in [f for f in os.listdir('js') if f.endswith('.js')]:
            # Skip lucide.min.js (it's tree-shaken now)
            if js_file == 'lucide.min.js':
                print(f"✂️ Skipping {js_file} (tree-shaken)...")
                continue
                
            # Skip minification for already minified libraries or large ones
            if js_file.endswith('.min.js') or js_file == 'tailwindcss.js':
                print(f"⏩ Copying js/{js_file} (skipping minification)...")
                shutil.copy(os.path.join('js', js_file), os.path.join(dist_dir, 'js', js_file))
            else:
                print(f"📦 Minifying js/{js_file}...")
                with open(os.path.join('js', js_file), 'r') as f:
                    content = f.read()
                
                # Remove Lucide initialization from script.js
                if js_file == 'script.js':
                    content = re.sub(r'\/\/ Initialize Lucide icons.*lucide\.createIcons\(\);\s*\}', '', content, flags=re.DOTALL)
                
                minified = minify_js(content)
                with open(os.path.join(dist_dir, js_file), 'w') as f: # Fixed path (js/js_file)
                    f.write(minified)

    # Process JSON (languages.json)
    if os.path.exists('languages.json'):
        print("📦 Minifying languages.json...")
        with open('languages.json', 'r') as f:
            data = json.load(f)
        with open(os.path.join(dist_dir, 'languages.json'), 'w') as f:
            json.dump(data, f, separators=(',', ':'))

    print("\n✨ Build complete! Output in dist/")

def serve_dist(port=5173):
    dist_dir = 'dist'
    if not os.path.exists(dist_dir):
        print(f"Error: {dist_dir} directory not found. Run build first.")
        return

    os.chdir(dist_dir)
    Handler = http.server.SimpleHTTPRequestHandler
    
    # Allow port reuse
    socketserver.TCPServer.allow_reuse_address = True
    
    try:
        with socketserver.TCPServer(("", port), Handler) as httpd:
            print(f"\n🌐 Preview server running at http://localhost:{port}")
            print("Press Ctrl+C to stop.")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Server stopped.")
        sys.exit(0)
    except Exception as e:
        print(f"Error starting server: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Python Static Website Compiler")
    parser.add_argument("--preview", action="store_true", help="Start a preview server after build")
    parser.add_argument("--port", type=int, default=5173, help="Port for preview server (default: 5173)")
    
    args = parser.parse_args()
    
    compile_project()
    
    if args.preview:
        serve_dist(args.port)
