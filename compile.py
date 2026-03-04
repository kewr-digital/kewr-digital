import os
import re
import shutil
import json
import sys
import http.server
import socketserver
import argparse

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
        print(f"📦 Minifying {html_file}...")
        with open(html_file, 'r') as f:
            content = f.read()
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
            print(f"📦 Minifying js/{js_file}...")
            with open(os.path.join('js', js_file), 'r') as f:
                content = f.read()
            minified = minify_js(content)
            with open(os.path.join(dist_dir, 'js', js_file), 'w') as f:
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
