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
import subprocess

# ─── AUTO-VENV SWITCHER ──────────────────────────────────────────────────────
# If not already in the venv, try to re-execute using .venv/bin/python
if sys.prefix == sys.base_prefix:
    venv_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv")
    venv_exe = os.path.join(venv_dir, "bin", "python")
    if os.name == 'nt': venv_exe = venv_exe.replace("bin/python", "Scripts/python.exe")
    
    if not os.path.exists(venv_exe):
        print("🛠️  Setting up virtual environment (.venv)...")
        subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
        print("📦 Installing dependencies (Pillow, fonttools, brotli)...")
        subprocess.run([venv_exe, "-m", "pip", "install", "Pillow", "fonttools", "brotli"], check=True)
        print("✅ Environment ready!")

    os.execv(venv_exe, [venv_exe] + sys.argv)


# ─── CSS TREE SHAKER ──────────────────────────────────────────────────────────

def extract_used_classes(html_content):
    """Extract all CSS class names used in HTML files."""
    classes = set()
    for match in re.finditer(r'class=["\']([^"\']*)["\']', html_content):
        for cls in match.group(1).split():
            classes.add(cls.strip())
    return classes

def tree_shake_css(css_content, used_classes):
    """
    Recursive CSS tree-shaker that handles media queries and strictly 
    prunes unused classes while preserving base styles.
    """
    # Add common classes used in JS to used_classes
    js_classes = {'is-active', 'is-open', 'is-open-nav', 'is-hidden', 'navbar-burger', 'navbar-menu'}
    used_classes = used_classes | js_classes

    # 1. Extract blocks, including nested braces (for @media)
    blocks = re.findall(r'([^{}]+)\{((?:[^{}]+|\{[^{}]*\})+)\}', css_content)
    
    shaken_css = []
    # Base selectors to always preserve
    keep_selectors = {'html', 'body', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
                     'p', 'li', 'span', 'label', 'input', 'button', 'textarea', 
                     '*', '::after', '::before', ':root', 'img', 'svg', 'main', 'section', 'footer', 'nav'}

    for selector_group, rules in blocks:
        selector_group = selector_group.strip()
        
        # Recursive handle for media queries
        if selector_group.startswith('@media'):
            inner_content = tree_shake_css(rules, used_classes)
            if inner_content.strip():
                shaken_css.append(f"{selector_group}{{{inner_content}}}")
            continue

        # Keep other @rules
        if selector_group.startswith('@'):
            shaken_css.append(f"{selector_group}{{{rules}}}")
            continue

        selectors = [s.strip() for s in selector_group.split(',')]
        kept_selectors = []
        
        for selector in selectors:
            # Find all classes in selector (e.g. .navbar-item)
            classes_in_selector = re.findall(r'\.([a-zA-Z0-9\-_]+)', selector)
            
            if classes_in_selector:
                # Keep if AT LEAST ONE class is used in HTML/JS
                if any(cls in used_classes for cls in classes_in_selector):
                    kept_selectors.append(selector)
            else:
                # If no classes, check if it targets base elements
                base_parts = re.split(r'[\s>+~:]+', selector)
                if any(p.lower() in keep_selectors for p in base_parts if p):
                    kept_selectors.append(selector)
        
        if kept_selectors:
            # For :root, we filter the rules (variables) inside
            if selector_group == ':root':
                # This will be handled in the variable pruning pass
                shaken_css.append(f":root{{{rules}}}")
            else:
                shaken_css.append(f"{', '.join(kept_selectors)}{{{rules}}}")

    output_css = "\n".join(shaken_css)
    
    # 2. Aggressive CSS variable pruning
    # First, find ALL used variables in the entire resulting CSS
    used_vars = set(re.findall(r'var\((--[a-zA-Z0-9\-_]+)\)', output_css))
    
    def prune_vars(match):
        selector = match.group(1).strip()
        rules = match.group(2).strip()
        
        # Split rules by ; to find individual variables
        parts = rules.split(';')
        kept_parts = []
        for p in parts:
            p = p.strip()
            if not p: continue
            
            v_match = re.match(r'(--[a-zA-Z0-9\-_]+)\s*:', p)
            if v_match:
                var_name = v_match.group(1)
                # Keep if used or not a bulma variable
                if var_name in used_vars or "bulma" not in var_name:
                    kept_parts.append(p)
            else:
                kept_parts.append(p)
        return f"{selector}{{{';'.join(kept_parts)}}}"

    # Apply pruning to all blocks (especially :root)
    final_css = re.sub(r'([^{}]+)\{([^{}]+)\}', prune_vars, output_css)
            
    return final_css


def process_images(src_dir, dst_dir, stats):
    """
    Handles general conversion and specific 1x/2x logo generation.
    """
    from PIL import Image
    
    if os.path.exists(dst_dir):
        shutil.rmtree(dst_dir)
    os.makedirs(dst_dir, exist_ok=True)

    print(f"🖼️  Optimizing image assets (WebP conversion)...")

    logo_name = "kewrlogo.png"
    logo_src = os.path.join(src_dir, logo_name)
    
    # Process all images
    for fname in os.listdir(src_dir):
        src_path = os.path.join(src_dir, fname)
        if not os.path.isfile(src_path): continue
        
        lower_name = fname.lower()
        base_name = os.path.splitext(fname)[0]
        
        # 1. Handle special logo generation (1x, 2x)
        if fname == logo_name:
            img = Image.open(src_path)
            base_w, base_h = 128, 32
            # 1x
            logo_1x = img.resize((base_w, base_h), Image.Resampling.LANCZOS)
            logo_1x.save(os.path.join(dst_dir, "kewrlogo-1x.webp"), "WEBP", quality=90)
            # 2x
            logo_2x = img.resize((base_w * 2, base_h * 2), Image.Resampling.LANCZOS)
            logo_2x.save(os.path.join(dst_dir, "kewrlogo-2x.webp"), "WEBP", quality=90)
            # Original to webp as fallback
            img.save(os.path.join(dst_dir, f"{base_name}.webp"), "WEBP", quality=90)
            print(f"   Generated 1x/2x WebP logos from {logo_name}")
            continue

        # 2. General conversion for other png/jpg/jpeg
        if lower_name.endswith(('.png', '.jpg', '.jpeg')):
            try:
                img = Image.open(src_path)
                # Use lossless for transparency-critical PNGs, lossy for others
                method = "WEBP"
                is_lossless = lower_name.endswith('.png')
                img.save(os.path.join(dst_dir, f"{base_name}.webp"), method, lossless=is_lossless, quality=80)
            except Exception as e:
                print(f"   ⚠️ Failed to convert {fname}: {e}")
                shutil.copy2(src_path, os.path.join(dst_dir, fname))
        else:
            # Copy other assets (gifs, svgs, etc) as is
            shutil.copy2(src_path, os.path.join(dst_dir, fname))

    # Tally image sizes
    stats['IMAGE'] = sum(os.path.getsize(os.path.join(dst_dir, f)) 
                         for f in os.listdir(dst_dir) if os.path.isfile(os.path.join(dst_dir, f)))


# ─── MINIFIERS ────────────────────────────────────────────────────────────────

def minify_html(content):
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    content = re.sub(r'>\s+<', '><', content)
    content = re.sub(r'\s{2,}', ' ', content)
    return content.strip()


def minify_css(content):
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    content = re.sub(r'\s*([{};:,])\s*', r'\1', content)
    content = re.sub(r'\s+', ' ', content)
    return content.strip()


def minify_js(content):
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    content = re.sub(r'(?<!:)\/\/.*', '', content)
    lines = [l.strip() for l in content.split('\n') if l.strip()]
    content = ' '.join(lines)
    content = re.sub(r'\s*([={}\(\)\[\]\+\-\*\/,;:])\s*', r'\1', content)
    content = re.sub(r'\s{2,}', ' ', content)
    return content.strip()


# ─── ICON INLINER ─────────────────────────────────────────────────────────────

def inline_icons(content):
    os.makedirs('icons', exist_ok=True)

    def replace_icon(match):
        icon_name = match.group(1)
        extra_attrs = match.group(2)
        
        local_path = os.path.join('icons', f"{icon_name}.svg")
        
        # Auto-fetch if missing
        if not os.path.exists(local_path):
            try:
                url = f"https://raw.githubusercontent.com/lucide-icons/lucide/main/icons/{icon_name}.svg"
                with urllib.request.urlopen(url) as response:
                    svg_data = response.read().decode('utf-8')
                    with open(local_path, 'w') as f:
                        f.write(svg_data)
            except Exception as e:
                print(f"⚠️ Failed to fetch icon {icon_name}: {e}")
                return match.group(0)

        with open(local_path, 'r') as f:
            svg = f.read()
            # Remove Lucide's default width/height and add our attributes
            svg = re.sub(r'width="[^"]*"', '', svg)
            svg = re.sub(r'height="[^"]*"', '', svg)
            
            # Inject extra attributes into the <svg> tag
            if extra_attrs.strip():
                svg = svg.replace('<svg ', f'<svg {extra_attrs.strip()} ')
            return svg

    return re.sub(r'<i\s+data-lucide="([^"]*)"([^>]*)></i>', replace_icon, content)


# ─── MAIN BUILDER ─────────────────────────────────────────────────────────────

def compile_project():
    dist_dir = 'dist'
    if not os.path.exists(dist_dir):
        os.makedirs(dist_dir)

    stats = {'HTML': 0, 'CSS': 0, 'JS': 0, 'IMAGE': 0}
    
    print("\n🚀 Starting optimized build process...")

    # Load all HTML files to find used classes for tree-shaking
    pages = ['index.html', 'about.html', 'services.html']
    all_html_content = ""
    for page in pages:
        if os.path.exists(page):
            with open(page, 'r') as f:
                all_html_content += f.read()
    
    used_classes = extract_used_classes(all_html_content)
    print(f"🔍 Found {len(used_classes)} unique CSS classes in HTML")

    # ── Optimize images (WebP conversion + cleanup) ──
    process_images('images', os.path.join(dist_dir, 'images'), stats)

    # ── Bundle and Minify CSS ──
    css_bundle = ""
    
    # 1. Standard Bulma (Tree-shaken)
    if os.path.exists('css/bulma.min.css'):
        with open('css/bulma.min.css', 'r') as f:
            bulma_css = f.read()
            css_bundle += tree_shake_css(bulma_css, used_classes)
            
    # 2. Custom style.css (Direct minification)
    if os.path.exists('css/style.css'):
        with open('css/style.css', 'r') as f:
            css_bundle += minify_css(f.read())

    # Write Bundle
    os.makedirs(os.path.join(dist_dir, 'css'), exist_ok=True)
    with open(os.path.join(dist_dir, 'css', 'main.min.css'), 'w') as f:
        f.write(css_bundle)
    stats['CSS'] = len(css_bundle.encode('utf-8'))
    print(f"🌿 Tree-shaking Bulma CSS...\n   CSS Bundle: {stats['CSS']//1024}KB (Bulma tree-shaken + style.css)")

    # ── Process HTML files ──
    for page in pages:
        if not os.path.exists(page): continue
        print(f"📦 Processing {page}...")
        with open(page, 'r') as f:
            content = f.read()
            
        # 1. Inline Icons (SVG)
        content = inline_icons(content)
        
        # 2. Update Asset Links
        # Replace bulma and style sheets with the new bundle
        content = re.sub(r'<link rel="stylesheet" href="css/bulma.min.css">', '', content)
        content = re.sub(r'<link rel="stylesheet" href="css/style.css">', 
                         '<link rel="stylesheet" href="css/main.min.css">', content)
        
        # 3. Swap Image Extensions to WebP
        # Handles <img src="..."> and any other attributes like srcset
        content = re.sub(r'src="images/([^"]+)\.(png|jpg|jpeg)"', r'src="images/\1.webp"', content)
        content = re.sub(r'srcset="images/([^"]+)\.(png|jpg|jpeg)"', r'srcset="images/\1.webp"', content)
        # Handle complex srcset (e.g. logo 1x, 2x)
        content = re.sub(r'images/([^ ,]+)\.(png|jpg|jpeg)', r'images/\1.webp', content)

        # 4. Minify
        minified = minify_html(content)
        with open(os.path.join(dist_dir, page), 'w') as f:
            f.write(minified)
        stats['HTML'] += len(minified.encode('utf-8'))

    # ── Process JS ──
    if os.path.exists('js/script.js'):
        with open('js/script.js', 'r') as f:
            js_min = minify_js(f.read())
        
        os.makedirs(os.path.join(dist_dir, 'js'), exist_ok=True)
        with open(os.path.join(dist_dir, 'js', 'script.js'), 'w') as f:
            f.write(js_min)
        stats['JS'] = len(js_min.encode('utf-8'))

    # ── Summary ──
    total = sum(stats.values())
    print(f"\n✨ Build complete!")
    print(f"📊 Build Summary:")
    for k, v in stats.items():
        print(f"  - {k}: {v/1024:.2f} KB")
    print(f"  ─────────────────")
    print(f"  Total: {total/1024:.2f} KB\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compiler for KEWR Digital")
    parser.add_argument("--preview", action="store_true", help="Start preview server after build")
    args = parser.parse_args()

    compile_project()

    if args.preview:
        PORT = 5173
        DIRECTORY = "dist"

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=DIRECTORY, **kwargs)

        print(f"📡 Preview server: http://localhost:{PORT}")
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n🛑 Server stopped.")
                httpd.shutdown()
