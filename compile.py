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

def split_selectors_safe(selector_group):
    """Split selectors by comma while respecting parentheses (for :not, etc)."""
    selectors = []
    current = []
    depth = 0
    for char in selector_group:
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        
        if char == ',' and depth == 0:
            selectors.append(''.join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        selectors.append(''.join(current).strip())
    return selectors


def tree_shake_css(css_content, used_classes, extra_context_css=""):
    """
    Recursive CSS tree-shaker that handles media queries, container queries, 
    and strictly prunes unused classes while preserving base styles.
    """
    # 1. Whitelist common classes used in JS or required for Bulma structure
    js_classes = {
        'is-active', 'is-open', 'is-open-nav', 'is-hidden', 'is-block', 
        'navbar-burger', 'navbar-menu', 'is-active-page', 'modal-close',
        'is-loading', 'is-vcentered', 'is-centered', 'is-multiline',
        'is-mobile', 'is-tablet', 'is-desktop', 'is-gapless',
        'is-flex', 'is-flex-direction-column', 'is-justify-content-center',
        'is-align-items-center', 'is-size-7', 'has-text-grey-light', 'is-hidden-mobile',
        'is-fixed-top', 'is-clipped', 'is-overlay', 'is-fullwidth', 'is-hidden-tablet',
        'is-relative', 'is-overflow-hidden', 'is-flex-wrap-wrap', 'is-flex-grow-1',
        'is-align-items-start', 'is-justify-content-end', 'is-flex-direction-row',
        'is-variable', 'is-gap-1', 'is-gap-2', 'is-gap-3', 'is-gap-4', 'is-gap-5', 
        'is-gap-6', 'is-gap-7', 'is-gap-8', 'is-1', 'is-2', 'is-3', 'is-4', 'is-5', 
        'is-6', 'is-7', 'is-8', 'is-9', 'is-10', 'is-11', 'is-12'
    }
    used_classes = used_classes | js_classes

    # 2. Extract blocks, including nested braces (for @media, @container)
    blocks = re.findall(r'([^{}]+)\{((?:[^{}]+|\{(?:[^{}]+|\{[^{}]*\})*\})+)\}', css_content)
    
    shaken_css = []
    # Base selectors to always preserve
    keep_selectors = {'html', 'body', 'a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
                     'p', 'li', 'span', 'label', 'input', 'button', 'textarea', 
                     '*', '::after', '::before', ':root', 'img', 'svg', 'main', 
                     'section', 'footer', 'nav', 'hr', 'div', 'ul', 'ol', 'dl', 
                     'dt', 'dd', 'table', 'tbody', 'thead', 'tr', 'td', 'th', 'i', 'b', 'strong'}

    for selector_group, rules in blocks:
        selector_group = selector_group.strip()
        
        # Recursive handle for media/container queries
        if selector_group.startswith(('@media', '@container')):
            inner_content = tree_shake_css(rules, used_classes, extra_context_css)
            if inner_content.strip():
                shaken_css.append(f"{selector_group}{{{inner_content}}}")
            continue

        # Keep other @rules (@keyframes, @font-face, etc)
        if selector_group.startswith('@'):
            shaken_css.append(f"{selector_group}{{{rules}}}")
            continue

        selectors = split_selectors_safe(selector_group)
        kept_selectors = []
        
        for selector in selectors:
            # 1. Keep if it's a known base selector
            base_parts = re.split(r'[\s>+~:]+', selector)
            if any(p.lower() in keep_selectors for p in base_parts if p):
                kept_selectors.append(selector)
                continue

            # 2. Find all classes in selector (e.g. .navbar-item)
            classes_in_selector = re.findall(r'\.([a-zA-Z0-9\-_]+)', selector)
            
            if classes_in_selector:
                # Keep if AT LEAST ONE class is used in HTML/JS
                if any(cls in used_classes for cls in classes_in_selector):
                    kept_selectors.append(selector)
            else:
                # 3. If no classes (attribute selectors, IDs, etc), keep it to be safe
                kept_selectors.append(selector)
        
        if kept_selectors:
            shaken_css.append(f"{', '.join(kept_selectors)}{{{rules}}}")

    output_css = "\n".join(shaken_css)
    
    # 3. Aggressive CSS variable pruning (Only for :root and only if flat)
    def prune_vars(match):
        selector = match.group(1).strip()
        # Ensure we don't accidentally match multi-level nested stuff here
        rules = match.group(2).strip()
        if '{' in rules: return match.group(0) # Skip nested for pruning here
        
        if selector != ':root': return match.group(0) # Only prune in :root

        # [FIX] Look for variables in BOTH the current Bulma block AND the extra context (style.css)
        used_vars = set(re.findall(r'var\((--[a-zA-Z0-9\-_]+)\)', output_css + extra_context_css))
        parts = rules.split(';')
        kept_parts = []
        for p in parts:
            p = p.strip()
            if not p: continue
            v_match = re.match(r'(--[a-zA-Z0-9\-_]+)\s*:', p)
            if v_match:
                var_name = v_match.group(1)
                if var_name in used_vars or "bulma" not in var_name:
                    kept_parts.append(p)
            else:
                kept_parts.append(p)
        return f"{selector}{{{';'.join(kept_parts)}}}"

    final_css = output_css
    # (Disabled variable pruning as it's too aggressive for complex themes)
    # final_css = re.sub(r'([^{}\n]+)\{([^{}]+)\}', prune_vars, output_css)
            
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
    # Remove comments
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    # Be conservative: don't collapse all spaces between tags (breaks inline-block)
    # Just collapse multiple spaces/newlines to a single space
    content = re.sub(r'\s{2,}', ' ', content)
    return content.strip()


def minify_css(content):
    # Remove comments
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
    # Remove whitespace around structural characters
    content = re.sub(r'\s*([{};:,])\s*', r'\1', content)
    # Collapse multiple spaces
    content = re.sub(r'\s{2,}', ' ', content)
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
        # group(1) = attributes before data-lucide
        # group(2) = icon name
        # group(3) = attributes after data-lucide
        prefix_attrs = match.group(1)
        icon_name = match.group(2)
        suffix_attrs = match.group(3)
        extra_attrs = f"{prefix_attrs} {suffix_attrs}".strip()
        
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
            # Only target the first <svg tag to avoid stripping attributes from internal elements like <rect>
            def strip_svg_attrs(svg_match):
                tag_content = svg_match.group(1)
                tag_content = re.sub(r'(?<!-)width="[^"]*"', '', tag_content)
                tag_content = re.sub(r'(?<!-)height="[^"]*"', '', tag_content)
                return f"<svg{tag_content}"

            svg = re.sub(r'<svg([^>]*)', strip_svg_attrs, svg, count=1)
            svg = svg.replace('  ', ' ').replace(' >', '>') # Cleanup
            
            # Inject extra attributes into the <svg> tag
            if extra_attrs.strip():
                # Filter out data-lucide from being injected twice
                clean_attrs = re.sub(r'data-lucide="[^"]*"', '', extra_attrs).strip()
                if clean_attrs:
                    # Robust injection: find the first <svg and insert attributes
                    svg = re.sub(r'(<svg\b[^>]*)', r'\1 ' + clean_attrs, svg, count=1)
            return svg

    return re.sub(r'<i\s+([^>]*)data-lucide="([^"]*)"([^>]*)></i>', replace_icon, content)


# ─── MAIN BUILDER ─────────────────────────────────────────────────────────────

def compile_project():
    dist_dir = 'dist'
    # ── CLEAN DIST ──
    if os.path.exists(dist_dir):
        print(f"🧹 Cleaning {dist_dir}...")
        for root, dirs, files in os.walk(dist_dir):
            for f in files: os.unlink(os.path.join(root, f))
            for d in dirs: shutil.rmtree(os.path.join(root, d))
    else:
        os.makedirs(dist_dir)

    stats = {'HTML': 0, 'CSS': 0, 'JS': 0, 'IMAGE': 0}
    
    print("\n🚀 Starting optimized production build...")

    # Load all HTML files to find used classes
    pages = ['index.html', 'about.html', 'services.html']
    all_html_content = ""
    for page in pages:
        if os.path.exists(page):
            with open(page, 'r') as f:
                all_html_content += f.read()
    
    used_classes = extract_used_classes(all_html_content)
    print(f"🔍 Found {len(used_classes)} unique CSS classes in HTML")

    # ── Optimize images ──
    process_images('images', os.path.join(dist_dir, 'images'), stats)

    # ── Process CSS ──
    os.makedirs(os.path.join(dist_dir, 'css'), exist_ok=True)
    
    # 1. Process Bulma (Tree-shaken)
    if os.path.exists('css/bulma.css'):
        with open('css/bulma.css', 'r') as f:
            print("🌿 Tree-shaking Bulma CSS...")
            # Load style_css if it exists to preserve variables used there
            style_css = ""
            if os.path.exists('css/style.css'):
                with open('css/style.css', 'r') as f_style:
                    style_css = f_style.read()
            
            shaken_bulma = tree_shake_css(f.read(), used_classes, style_css)
            bulma_min = minify_css(shaken_bulma)
            with open(os.path.join(dist_dir, 'css', 'bulma.css'), 'w') as out:
                out.write(bulma_min)
            stats['CSS'] += len(bulma_min.encode('utf-8'))

    # 2. Process Custom style.css
    if os.path.exists('css/style.css'):
        with open('css/style.css', 'r') as f:
            print("🎨 Minifying custom styles...")
            style_min = minify_css(f.read())
            with open(os.path.join(dist_dir, 'css', 'style.css'), 'w') as out:
                out.write(style_min)
            stats['CSS'] += len(style_min.encode('utf-8'))

    print(f"✅ CSS files optimized: {stats['CSS']//1024}KB total")

    # ── Process HTML files ──
    for page in pages:
        if not os.path.exists(page): continue
        print(f"📦 Processing {page}...")
        with open(page, 'r') as f:
            content = f.read()
            
        # 1. Inline Icons (SVG)
        content = inline_icons(content)
        
        # 2. Update Asset Links
        # Replace bulma.css or bulma.min.css with dist path
        content = re.sub(r'<link rel="stylesheet" href="css/bulma(?:\.min)?\.css">', 
                         '<link rel="stylesheet" href="css/bulma.css">', content)
        # Update style.css link
        content = re.sub(r'<link rel="stylesheet" href="css/style\.css">', 
                         '<link rel="stylesheet" href="css/style.css">', content)
        
        content = re.sub(r'images/([^ ,]+)\.(png|jpg|jpeg)', r'images/\1.webp', content)
        
        # 4. Remove redundant/missing script references
        content = re.sub(r'<script src="js/lucide.min.js"></script>', '', content)
        content = re.sub(r'<script src="js/languages.js"></script>', '', content)

        # 5. Minify HTML
        content = minify_html(content)
        with open(os.path.join(dist_dir, page), 'w') as f:
            f.write(content)
        stats['HTML'] += len(content.encode('utf-8'))

    # ── Process JS (With minification) ──
    js_src = 'js'
    js_dst = os.path.join(dist_dir, 'js')
    os.makedirs(js_dst, exist_ok=True)
    if os.path.exists(js_src):
        for fname in os.listdir(js_src):
            if fname in ['tailwindcss.js', 'lucide.min.js']: continue
            if fname.endswith('.js'):
                with open(os.path.join(js_src, fname), 'r') as f:
                    js_content = minify_js(f.read())
                with open(os.path.join(js_dst, fname), 'w') as f:
                    f.write(js_content)
                stats['JS'] += len(js_content.encode('utf-8'))

    # Copy languages.json
    if os.path.exists('languages.json'):
        shutil.copy2('languages.json', os.path.join(dist_dir, 'languages.json'))

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
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n🛑 Server stopped.")
                httpd.shutdown()
