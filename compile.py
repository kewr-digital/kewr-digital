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


# ─── CSS TREE SHAKER ──────────────────────────────────────────────────────────

def extract_used_classes(html_content):
    """Extract all CSS class names used in HTML files."""
    classes = set()
    for match in re.finditer(r'class=["\']([^"\']*)["\']', html_content):
        for cls in match.group(1).split():
            classes.add(cls.strip())
    return classes


def parse_css_blocks(css):
    """
    Parse CSS into a list of dicts:
      { 'type': 'rule'|'atrule'|'keyframe', 'raw': str, 'selectors': [str] }
    Handles nested @media blocks.
    """
    blocks = []
    i = 0
    n = len(css)
    depth = 0
    buf = ''
    in_string = False
    str_char = ''

    while i < n:
        ch = css[i]

        # Track string literals to avoid mis-counting braces
        if not in_string and ch in ('"', "'"):
            in_string = True
            str_char = ch
        elif in_string and ch == str_char and (i == 0 or css[i-1] != '\\'):
            in_string = False

        if in_string:
            buf += ch
            i += 1
            continue

        if ch == '{':
            depth += 1
            buf += ch
        elif ch == '}':
            depth -= 1
            buf += ch
            if depth == 0:
                raw = buf.strip()
                buf = ''
                if raw:
                    _classify_block(blocks, raw)
        else:
            buf += ch
        i += 1

    # Flush any remaining
    if buf.strip():
        _classify_block(blocks, buf.strip())

    return blocks


def _classify_block(blocks, raw):
    if raw.startswith('@keyframes') or raw.startswith('@-webkit-keyframes'):
        blocks.append({'type': 'keyframe', 'raw': raw, 'selectors': []})
    elif raw.startswith('@media') or raw.startswith('@supports') or raw.startswith('@layer'):
        # Nested block — parse its inner rules and remember the media wrapper
        brace = raw.index('{')
        at_header = raw[:brace].strip()
        inner = raw[brace+1:raw.rfind('}')].strip()
        inner_blocks = parse_css_blocks(inner)
        blocks.append({'type': 'atrule', 'raw': raw, 'header': at_header, 'inner': inner_blocks})
    else:
        # Plain rule(s)
        brace = raw.find('{')
        if brace == -1:
            return
        selector_part = raw[:brace].strip()
        selectors = [s.strip() for s in selector_part.split(',')]
        blocks.append({'type': 'rule', 'raw': raw, 'selectors': selectors})


def selector_uses_class(selector, used_classes):
    """Return True if selector references any class in used_classes."""
    found = re.findall(r'\.([-\w]+)', selector)
    return any(cls in used_classes for cls in found)


def is_base_rule(selectors):
    """Return True if this is a base/reset rule that should always be included."""
    base_patterns = [
        r'^[*]$',             # * (universal reset)
        r'^html$',
        r'^body$',
        r'^:root$',
        r'^[a-z][a-z0-9]*$', # plain element selectors like p, a, h1-h6, img, etc.
        r'^[a-z][a-z0-9]*(,[a-z][a-z0-9]*)+$',  # comma-grouped elements
        r'^\*,\s*::[a-z-]+$',  # *, ::before, ::after
        r'^\*::',
        r'^::',
    ]
    for sel in selectors:
        for pat in base_patterns:
            if re.match(pat, sel.strip(), re.IGNORECASE):
                return True
    return False


def treeshake_bulma(bulma_css, used_classes):
    """
    Parse bulma.min.css and return only the rules whose selectors
    match classes actually used in the HTML files, plus all base/reset rules.
    """
    blocks = parse_css_blocks(bulma_css)
    kept = []

    def process_blocks(block_list, used):
        out = []
        for block in block_list:
            if block['type'] == 'keyframe':
                # Always keep keyframes referenced by used animation classes
                out.append(block['raw'])
            elif block['type'] == 'atrule':
                # Recursively filter inner rules
                inner_kept = process_blocks(block['inner'], used)
                if inner_kept:
                    header = block['header']
                    inner_text = ' '.join(inner_kept)
                    out.append(f"{header} {{ {inner_text} }}")
            elif block['type'] == 'rule':
                sels = block['selectors']
                if is_base_rule(sels) or any(selector_uses_class(s, used) for s in sels):
                    out.append(block['raw'])
        return out

    kept = process_blocks(blocks, used_classes)
    return '\n'.join(kept)


# ─── FONT SUBSETTER ──────────────────────────────────────────────────────────

def subset_fonts(html_content, src_dir, dst_dir):
    """
    Subset woff2 font files to only the glyphs (Unicode codepoints) actually
    used in the HTML text. Requires fonttools + brotli.
    """
    try:
        from fontTools import subset as ftsubset
        from fontTools.ttLib import TTFont
    except ImportError:
        print("⚠️  fonttools not installed — copying fonts as-is (run: pip3 install fonttools brotli)")
        if os.path.exists(src_dir):
            shutil.copytree(src_dir, dst_dir)
        return

    if not os.path.exists(src_dir):
        return
    os.makedirs(dst_dir, exist_ok=True)

    # ── Extract every unique character from visible HTML text ──
    text = re.sub(r'<[^>]+>', '', html_content)          # strip tags
    text = re.sub(r'&[a-zA-Z0-9#]+;', ' ', text)        # strip entities
    # Always include ASCII printable + common punctuation as a safe baseline
    baseline = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'
                   '0123456789 .,!?-:;/"\'\'()[]{}@#$%&*+=<>_\n\t')
    used_chars = baseline | set(text)
    unicodes = sorted({ord(c) for c in used_chars if ord(c) > 31})
    unicode_str = ','.join(f'U+{cp:04X}' for cp in unicodes)

    print(f"🔤 Subsetting fonts — {len(unicodes)} unique glyphs used")

    for fname in os.listdir(src_dir):
        if not fname.endswith('.woff2'):
            continue
        src_path = os.path.join(src_dir, fname)
        dst_path = os.path.join(dst_dir, fname)
        src_size = os.path.getsize(src_path)

        try:
            options = ftsubset.Options()
            options.flavor = 'woff2'
            options.layout_features = ['*']   # keep all OpenType features
            options.name_IDs = ['*']
            font = TTFont(src_path)
            subsetter = ftsubset.Subsetter(options)
            subsetter.populate(unicodes=unicodes)
            subsetter.subset(font)
            font.save(dst_path)
            dst_size = os.path.getsize(dst_path)
            reduction = (1 - dst_size / src_size) * 100
            print(f"   {fname}: {src_size//1024}KB → {dst_size//1024}KB ({reduction:.0f}% smaller)")
        except Exception as e:
            print(f"   ⚠️  {fname}: subsetting failed ({e}), copying as-is")
            shutil.copy2(src_path, dst_path)


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
        icon_path = os.path.join('icons', f"{icon_name}.svg")

        if not os.path.exists(icon_path):
            print(f"📡 Fetching icon: {icon_name}...")
            try:
                url = f"https://raw.githubusercontent.com/lucide-icons/lucide/main/icons/{icon_name}.svg"
                with urllib.request.urlopen(url) as response:
                    svg_content = response.read().decode('utf-8')
                    with open(icon_path, 'w') as f:
                        f.write(svg_content)
                time.sleep(0.1)
            except Exception as e:
                print(f"⚠️ Error fetching icon '{icon_name}': {e}")
                return match.group(0)

        if os.path.exists(icon_path):
            with open(icon_path, 'r') as f:
                svg_content = f.read()
            inner_svg = "".join(re.findall(r'<(?:path|circle|line|polyline|polygon|rect|ellipse|text)[^>]*>', svg_content))
            classes = re.search(r'class="([^"]*)"', extra_attrs)
            extra_classes = classes.group(1) if classes else ''
            # Preserve inline style width/height from data attributes or style=""
            style_match = re.search(r'style="([^"]*)"', extra_attrs)
            style_attr = f' style="{style_match.group(1)}"' if style_match else ''
            return f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-{icon_name} {extra_classes}"{style_attr}>{inner_svg}</svg>'
        return match.group(0)

    content = re.sub(r'<i data-lucide="([^"]+)"([^>]*)></i>', replace_icon, content)
    # Remove tailwind/lucide scripts, replace with Bulma + compiled assets
    content = re.sub(r'<script src="[^"]*(?:lucide|tailwindcss|script\.js|languages\.js)[^"]*"></script>', '', content)
    content = re.sub(r'<script>\s*tailwind\.config\s*=\s*\{.*?\};?\s*</script>', '', content, flags=re.DOTALL)
    # Inject CSS links in head (bulma first, then style.css)
    content = re.sub(
        r'<link rel="stylesheet" href="css/bulma\.min\.css">\s*<link rel="stylesheet" href="css/style\.css">',
        '',
        content
    )
    if '</head>' in content:
        content = content.replace(
            '</head>',
            '    <link rel="stylesheet" href="css/bulma.min.css">\n    <link rel="stylesheet" href="css/style.css">\n</head>'
        )
    if '</body>' in content:
        content = content.replace(
            '</body>',
            '    <script src="js/languages.js"></script>\n    <script src="js/script.js"></script>\n</body>'
        )
    return content


# ─── MAIN COMPILER ────────────────────────────────────────────────────────────

def compile_project():
    dist_dir = 'dist'
    print(f"\n🚀 Starting optimized build process...")
    if os.path.exists(dist_dir):
        shutil.rmtree(dist_dir)
    os.makedirs(dist_dir)
    os.makedirs(os.path.join(dist_dir, 'css'))
    os.makedirs(os.path.join(dist_dir, 'js'))
    if os.path.exists('images'):
        shutil.copytree('images', os.path.join(dist_dir, 'images'))

    # ── Collect all HTML text (needed for both CSS + font tree-shaking) ──
    all_html_content = ''
    html_files = [f for f in os.listdir('.') if f.endswith('.html')]
    for hf in html_files:
        with open(hf, 'r') as f:
            all_html_content += f.read()
    used_classes = extract_used_classes(all_html_content)
    print(f"🔍 Found {len(used_classes)} unique CSS classes in HTML")

    # Size tracking
    stats = {}
    def save_file(path, content):
        with open(path, 'w') as f:
            f.write(content)
        ext = path.split('.')[-1].upper()
        stats[ext] = stats.get(ext, 0) + len(content.encode('utf-8'))

    # ── Subset fonts to used glyphs ──
    if os.path.exists('fonts'):
        subset_fonts(all_html_content, 'fonts', os.path.join(dist_dir, 'fonts'))
        # Tally subsetted font sizes into stats
        font_dist = os.path.join(dist_dir, 'fonts')
        if os.path.exists(font_dist):
            stats['WOFF2'] = sum(os.path.getsize(os.path.join(font_dist, f))
                                 for f in os.listdir(font_dist) if f.endswith('.woff2'))

    # ── Tree-shake Bulma ──
    bulma_src = os.path.join('css', 'bulma.min.css')
    if os.path.exists(bulma_src):
        print(f"🌿 Tree-shaking Bulma CSS...")
        with open(bulma_src, 'r') as f:
            bulma_css = f.read()
        original_size = len(bulma_css.encode('utf-8'))
        shaken = treeshake_bulma(bulma_css, used_classes)
        minified = minify_css(shaken)
        save_file(os.path.join(dist_dir, 'css', 'bulma.min.css'), minified)
        shaken_size = len(minified.encode('utf-8'))
        reduction = (1 - shaken_size / original_size) * 100
        print(f"   {original_size//1024}KB → {shaken_size//1024}KB  ({reduction:.0f}% reduction)")
    else:
        print("⚠️  bulma.min.css not found, skipping tree-shaking")

    # ── Process HTML ──
    for html_file in html_files:
        print(f"📦 Processing {html_file}...")
        with open(html_file, 'r') as f:
            content = f.read()
        content = inline_icons(content)
        save_file(os.path.join(dist_dir, html_file), minify_html(content))

    # ── Process style.css ──
    style_src = os.path.join('css', 'style.css')
    if os.path.exists(style_src):
        with open(style_src, 'r') as f:
            content = f.read()
        save_file(os.path.join(dist_dir, 'css', 'style.css'), minify_css(content))

    # ── Process JS ──
    if os.path.exists('js'):
        for jf in os.listdir('js'):
            # Skip the CDN libraries — no longer needed in dist
            if jf in ['lucide.min.js', 'tailwindcss.js']:
                continue
            src = os.path.join('js', jf)
            with open(src, 'r') as f:
                content = f.read()
            save_file(os.path.join(dist_dir, 'js', jf), minify_js(content))

    # ── Convert languages.json → languages.js ──
    if os.path.exists('languages.json'):
        with open('languages.json', 'r') as f:
            data = json.load(f)
        js_content = f"window.translations={json.dumps(data, separators=(',', ':'))};"
        save_file(os.path.join(dist_dir, 'js', 'languages.js'), js_content)

    print(f"\n✨ Build complete!")
    print("📊 Build Summary:")
    for ext, size in sorted(stats.items()):
        print(f"  - {ext}: {size/1024:.2f} KB")
    total = sum(stats.values())
    print(f"  ─────────────────")
    print(f"  Total: {total/1024:.2f} KB")


# ─── DEV SERVER ───────────────────────────────────────────────────────────────

def serve_dist(port=5173):
    dist_dir = 'dist'
    if not os.path.exists(dist_dir):
        print("❌ dist/ not found. Run compile first.")
        return
    os.chdir(dist_dir)
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", port), http.server.SimpleHTTPRequestHandler) as httpd:
            print(f"\n🌐 Preview server running at http://localhost:{port}")
            httpd.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kewr Digital build tool")
    parser.add_argument("--preview", action="store_true", help="Serve dist after building")
    parser.add_argument("--port", type=int, default=5173)
    args = parser.parse_args()
    compile_project()
    if args.preview:
        serve_dist(args.port)
