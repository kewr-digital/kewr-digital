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

class TailwindGenerator:
    def __init__(self):
        self.preflight = """
            *, ::before, ::after { box-sizing: border-box; border-width: 0; border-style: solid; border-color: #e5e7eb; }
            html { line-height: 1.5; -webkit-text-size-adjust: 100%; font-family: ui-sans-serif, system-ui, sans-serif; }
            body { margin: 0; line-height: inherit; }
            h1, h2, h3, h4, h5, h6 { font-size: inherit; font-weight: inherit; margin: 0; }
            a { color: inherit; text-decoration: inherit; }
            button, input, textarea { font-family: inherit; font-size: 100%; margin: 0; padding: 0; }
            ol, ul { list-style: none; margin: 0; padding: 0; }
            img, svg { display: block; vertical-align: middle; max-width: 100%; height: auto; }
            .hidden { display: none; }
        """
        self.colors = {
            "white": "255,255,255", "black": "0,0,0", "transparent": "transparent",
            "gray-50": "249,250,251", "gray-100": "243,244,246", "gray-200": "229,231,235", "gray-300": "209,213,223",
            "gray-400": "156,163,175", "gray-500": "107,114,128", "gray-600": "75,85,99", "gray-700": "55,65,81",
            "gray-800": "31,41,55", "gray-900": "17,24,39"
        }
        self.breakpoints = {"sm":"640px", "md":"768px", "lg":"1024px", "xl":"1280px", "2xl":"1536px"}

    def get_val(self, v):
        if v.startswith("[") and v.endswith("]"): return v[1:-1].replace("_", " ")
        if v == "full": return "100%"
        if v == "auto": return "auto"
        if v == "px": return "1px"
        if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
            val = float(v)
            return f"{val*0.25}rem" if val != 0 else "0px"
        return v

    def get_color(self, cv):
        alpha = "1"
        if "/" in cv: cv, op = cv.split("/"); alpha = str(float(op)/100) if "." in op else str(int(op)/100)
        if cv.startswith("[") and cv.endswith("]"): 
            c = cv[1:-1]
            return f"rgba({c}, {alpha})" if "," in c else c
        rgb = self.colors.get(cv, "0,0,0")
        return f"rgba({rgb}, {alpha})" if rgb != "transparent" else "transparent"

    def generate_rule(self, cls):
        orig, variants = cls, cls.split(":")
        c = variants[-1]
        is_neg = c.startswith("-")
        if is_neg: c = c[1:]
        
        body = ""
        # Spacing: p-, m-
        m = re.match(r"^([pm])([xytrbl])?-(.+)$", c)
        if m:
            t, ax, v = m.group(1), m.group(2), self.get_val(m.group(3))
            if is_neg: v = f"-{v}"
            p = "padding" if t == "p" else "margin"
            sm = {"t":"top","r":"right","b":"bottom","l":"left"}
            if not ax: body = f"{p}: {v};"
            elif ax == "x": body = f"{p}-left: {v}; {p}-right: {v};"
            elif ax == "y": body = f"{p}-top: {v}; {p}-bottom: {v};"
            else: body = f"{p}-{sm[ax]}: {v};"

        # Sizing/Pos: w-, h-, top-, etc.
        m = re.match(r"^(w|h|max-w|min-h|top|bottom|left|right|inset)-(.+)$", c)
        if m:
            t, raw_v = m.group(1), m.group(2)
            if "/" in raw_v and not raw_v.startswith("["):
                n,d = raw_v.split("/"); v = f"{(float(n)/float(d))*100}%"
            else: v = self.get_val(raw_v)
            if is_neg: v = f"-{v}"
            p = {"w":"width", "h":"height", "max-w":"max-width", "min-h":"min-height", "top":"top", "bottom":"bottom", "left":"left", "right":"right", "inset":"inset"}[t]
            body = f"{p}: {v};"

        # Colors & Gradients
        m = re.match(r"^(bg|text|border|from|via|to)-(.+)$", c)
        if m:
            t, cv = m.group(1), m.group(2)
            if t == "bg" and "gradient-to-" in cv:
                dirs = {"r":"to right", "l":"to left", "t":"to top", "b":"to bottom", "br":"to bottom right"}
                d = dirs.get(cv.split("-")[-1], "to bottom")
                body = f"background-image: linear-gradient({d}, var(--tw-gradient-stops, transparent, transparent));"
            else:
                color = self.get_color(cv)
                if t == "bg": body = f"background-color: {color};"
                elif t == "text": body = f"color: {color};"
                elif t == "border": body = f"border-color: {color}; border-width: 1px;"
                elif t == "from": body = f"--tw-gradient-from: {color}; --tw-gradient-to: rgba(0,0,0,0); --tw-gradient-stops: var(--tw-gradient-from), var(--tw-gradient-to);"
                elif t == "to": body = f"--tw-gradient-to: {color};"

        # Layout
        lmap = {"flex":"display: flex;", "grid":"display: grid;", "block":"display: block;", "hidden":"display: none;", "relative":"position: relative;", "absolute":"position: absolute;", "fixed":"position: fixed;", "sticky":"position: sticky;", "inset-0":"inset: 0;", "flex-col":"flex-direction: column;", "sr-only":"position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border-width: 0;"}
        if c in lmap: body = lmap[c]
        elif c.startswith("z-"): body = f"z-index: {c.replace('z-', '').replace('[','').replace(']','')};"
        elif c.startswith("grid-cols-"): body = f"grid-template-columns: repeat({self.get_val(c.replace('grid-cols-', ''))}, minmax(0, 1fr));"
        elif c.startswith("items-"): body = f"align-items: {c.replace('items-', 'flex-') if 'start' in c or 'end' in c else c.replace('items-', '')};"
        elif c.startswith("justify-"): body = f"justify-content: {c.replace('justify-', 'flex-') if 'start' in c or 'end' in c else c.replace('justify-', '')};"

        # Transformations & Animations
        if c == "animate-pulse": body = "animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }"
        elif c.startswith("scale-"): body = f"transform: scale({float(c.split('-')[-1])/100});"
        elif c.startswith("translate-x-"):
            v = c.split("-")[-1]
            if "/" in v: n,d = v.split("/"); v = f"{(float(n)/float(d))*100}%"
            else: v = self.get_val(v)
            if is_neg: v = f"-{v}"
            body = f"transform: translateX({v});"

        # Typography
        if c.startswith("text-") and not body:
            smap = {"xs":"0.75rem", "sm":"0.875rem", "base":"1rem", "lg":"1.125rem", "xl":"1.25rem", "2xl":"1.5rem", "3xl":"1.875rem", "4xl":"2.25rem", "5xl":"3rem"}
            v = smap.get(c.replace("text-", ""), "")
            if v: body = f"font-size: {v};"
            else:
                color = self.get_color(c.replace("text-", ""))
                if color != "rgba(0,0,0,1)" or c == "text-black": body = f"color: {color};"
        elif c.startswith("font-"): body = f"font-weight: {c.replace('font-', '')};"
        elif c == "text-center": body = "text-align: center;"
        elif c == "underline": body = "text-decoration-line: underline;"

        # Effects
        if c.startswith("rounded"):
            rmap = {"full":"9999px", "lg":"0.5rem", "xl":"0.75rem", "2xl":"1rem", "3xl":"1.5rem", "md":"0.375rem"}
            body = f"border-radius: {rmap.get(c.replace('rounded-', '').replace('rounded', ''), '0.25rem')};"
        elif c.startswith("shadow"): body = "box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px -2px rgba(0,0,0,0.05);"
        elif "blur" in c: body = f"backdrop-filter: blur({self.get_val(c.split('-')[-1] if '-' in c else '[8px]')}); -webkit-backdrop-filter: blur({self.get_val(c.split('-')[-1] if '-' in c else '[8px]')});"
        elif c.startswith("opacity-"): body = f"opacity: {float(c.split('-')[-1])/100};"

        if not body: return ""
        sel = "." + orig.replace(':', '\\:').replace('/', '\\/').replace('[','\\[').replace(']','\\]').replace('.','\\.').replace('#','\\#').replace('!','\\!')
        if "hover" in variants: sel += ":hover"
        for v in variants:
            if "group-hover" in v: sel = f".group:hover {sel}"
        rule = f"{sel} {{ {body} }}"
        for bp in self.breakpoints:
            if bp in variants: rule = f"@media (min-width: {self.breakpoints[bp]}) {{ {rule} }}"
        return rule

    def build(self, class_list):
        css = [self.preflight]
        for c in sorted(list(set(class_list))):
            r = self.generate_rule(c)
            if r: css.append(r)
        return "\n".join(css)

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

    content = re.sub(r'<i data-lucide="([^"]+)"([^>]*)></i>', replace_icon, content)
    # Cleanup Tailwind & Lucide
    content = re.sub(r'<script src="[^"]*(?:lucide|tailwindcss)[^"]*"></script>', '', content)
    content = re.sub(r'<script>\s*tailwind\.config\s*=\s*\{.*?\};?\s*</script>', '', content, flags=re.DOTALL)
    # Link optimized CSS
    if '</head>' in content:
        content = content.replace('</head>', '    <link rel="stylesheet" href="css/tailwind-built.css">\n</head>')
    return content

def compile_project():
    dist_dir = 'dist'
    print(f"\n🚀 Starting optimized build process...")
    if os.path.exists(dist_dir): shutil.rmtree(dist_dir)
    os.makedirs(dist_dir); os.makedirs(os.path.join(dist_dir, 'css')); os.makedirs(os.path.join(dist_dir, 'js'))
    if os.path.exists('images'): shutil.copytree('images', os.path.join(dist_dir, 'images'))

    # Class detection
    used_classes = set()
    source_files = [f for f in os.listdir('.') if f.endswith('.html')] + ['js/script.js']
    for sf in source_files:
        if os.path.exists(sf):
            with open(sf, 'r') as f:
                content = f.read()
                matches = re.findall(r'class="([^"]+)"', content)
                for m in matches:
                    for cls in m.split(): used_classes.add(cls)

    # Generate Tailwind CSS
    generator = TailwindGenerator()
    tailwind_css = generator.build(used_classes)
    with open(os.path.join(dist_dir, 'css/tailwind-built.css'), 'w') as f:
        f.write(minify_css(tailwind_css))
    print(f"✨ Generated optimized Tailwind CSS ({len(used_classes)} classes)")

    # Process HTML
    for html_file in [f for f in os.listdir('.') if f.endswith('.html')]:
        print(f"📦 Processing {html_file}...")
        with open(html_file, 'r') as f: content = f.read()
        content = inline_icons(content)
        with open(os.path.join(dist_dir, html_file), 'w') as f: f.write(minify_html(content))

    # Process CSS/JS/JSON
    if os.path.exists('css'):
        for cf in os.listdir('css'):
            if cf.endswith('.css'):
                with open(os.path.join('css', cf), 'r') as f: content = f.read()
                with open(os.path.join(dist_dir, 'css', cf), 'w') as f: f.write(minify_css(content))

    if os.path.exists('js'):
        for jf in os.listdir('js'):
            if jf in ['lucide.min.js', 'tailwindcss.js']: continue
            with open(os.path.join('js', jf), 'r') as f: content = f.read()
            if jf == 'script.js': content = re.sub(r'\/\/ Initialize Lucide icons.*lucide\.createIcons\(\);\s*\}', '', content, flags=re.DOTALL)
            with open(os.path.join(dist_dir, 'js', jf), 'w') as f: f.write(minify_js(content))

    if os.path.exists('languages.json'):
        with open('languages.json', 'r') as f: data = json.load(f)
        with open(os.path.join(dist_dir, 'languages.json'), 'w') as f: json.dump(data, f, separators=(',', ':'))

    print(f"\n✨ Build complete! (~800KB assets removed/optimized)")

def serve_dist(port=5173):
    dist_dir = 'dist'
    if not os.path.exists(dist_dir): return
    os.chdir(dist_dir)
    socketserver.TCPServer.allow_reuse_address = True
    try:
        with socketserver.TCPServer(("", port), http.server.SimpleHTTPRequestHandler) as httpd:
            print(f"\n🌐 Preview server running at http://localhost:{port}"); httpd.serve_forever()
    except KeyboardInterrupt: sys.exit(0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--port", type=int, default=5173)
    args = parser.parse_args(); compile_project()
    if args.preview: serve_dist(args.port)
