#!/usr/bin/env python3

# ESTA - Minimal Static Site Generator.
# Usage: python esta.py build

import argparse
import json
import os
import posixpath
import re
import shutil
import sys
from configparser import ConfigParser, Error as ConfigError
from datetime import datetime
from html.parser import HTMLParser

# --------------------------------------------------------------------------
# Paths (relative to the directory containing esta.py)
# --------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(ROOT, "config.ini")
SOURCE = os.path.join(ROOT, "source")
CSS_DIR = os.path.join(SOURCE, "css")
JS_DIR = os.path.join(SOURCE, "js")
LANG_DIR = os.path.join(SOURCE, "lang")
TEMPLATES_DIR = os.path.join(SOURCE, "templates")
PAGES_DIR = os.path.join(SOURCE, "pages")
ASSETS_DIR = os.path.join(SOURCE, "assets")
BUILD = os.path.join(ROOT, "build")
STAMP_FORMAT = "%Y%m%d%H%M%S"


class EstaError(Exception):
    """A problem that stops the build (or the current page)."""


WARNINGS = []


def warn(message):
    WARNINGS.append(message)
    print(f"  warning: {message}", file=sys.stderr)


# --------------------------------------------------------------------------
# File helpers
# --------------------------------------------------------------------------
def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise EstaError(f"File not found: {os.path.relpath(path, ROOT)}")
    except PermissionError:
        raise EstaError(f"No permission to read: {os.path.relpath(path, ROOT)}")
    except UnicodeDecodeError:
        raise EstaError(f"File is not valid UTF-8: {os.path.relpath(path, ROOT)}")
    except OSError as e:
        raise EstaError(f"Could not read {os.path.relpath(path, ROOT)}: {e}")


def write_file(path, content):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except PermissionError:
        raise EstaError(f"No permission to write: {os.path.relpath(path, ROOT)}")
    except OSError as e:
        raise EstaError(f"Could not write {os.path.relpath(path, ROOT)}: {e}")


def rel(target, page_path):
    """Relative URL from the folder of `page_path` to `target`."""
    start = os.path.dirname(page_path)
    return os.path.relpath(target, start).replace(os.sep, "/")


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
def load_config():
    parser = ConfigParser(
        allow_no_value=True,
        delimiters=("=",),
        comment_prefixes=("#", ";"),
        inline_comment_prefixes=None,
    )
    parser.optionxform = str  # keep file names case-sensitive
    try:
        parser.read_string(read_file(CONFIG_FILE))
    except ConfigError as e:
        raise EstaError(f"Invalid config.ini: {e}")

    config = {}
    for section in ("lang", "css", "js"):
        if not parser.has_section(section):
            raise EstaError(f"config.ini is missing the [{section}] section.")
        config[section] = list(parser.options(section))
    if not config["lang"]:
        raise EstaError("config.ini: the [lang] section is empty.")
    
    config["paths"] = {}
    for key in ("source", "css", "js", "lang", "templates", 
                "pages", "assets", "build"):
        if not parser.has_option("paths", key):
            raise EstaError(f"config.ini: [paths] section is missing '{key}'.")
        # Make paths absolute relative to ROOT
        path_value = parser.get("paths", key)
        config["paths"][key] = os.path.join(ROOT, path_value)
    
    return config


# --------------------------------------------------------------------------
# Basic syntax checks (warnings only)
# --------------------------------------------------------------------------
_CSS_NOISE = re.compile(r'/\*.*?\*/|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'', re.S)
_JS_NOISE = re.compile(
    r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`(?:\\.|[^`\\])*`',
    re.S,
)


def check_balanced(text, js):
    """Return a problem description if brackets are unbalanced, else None."""
    noise = _JS_NOISE if js else _CSS_NOISE
    cleaned = noise.sub(lambda m: "\n" * m.group().count("\n"), text)
    closers = {")": "(", "]": "[", "}": "{"}
    stack, line = [], 1
    for ch in cleaned:
        if ch == "\n":
            line += 1
        elif ch in "([{":
            stack.append((ch, line))
        elif ch in closers:
            if not stack or stack[-1][0] != closers[ch]:
                return f"unexpected '{ch}' on line {line}"
            stack.pop()
    if stack:
        return f"unclosed '{stack[-1][0]}' opened on line {stack[-1][1]}"
    return None


class _HtmlChecker(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
            "meta", "param", "source", "track", "wbr"}
    OPTIONAL_END = {"p", "li", "dt", "dd", "tr", "td", "th", "thead", "tbody",
                    "tfoot", "option"}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.problems = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID and tag not in self.OPTIONAL_END:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        pass  # self-closing tags

    def handle_endtag(self, tag):
        if tag in self.VOID or tag in self.OPTIONAL_END:
            return
        line = self.getpos()[0]
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
        elif any(t == tag for t, _ in self.stack):
            while self.stack[-1][0] != tag:
                t, l = self.stack.pop()
                self.problems.append(f"<{t}> opened on line {l} is never closed")
            self.stack.pop()
        else:
            self.problems.append(f"unexpected </{tag}> on line {line}")


def check_html(text):
    checker = _HtmlChecker()
    try:
        checker.feed(text)
        checker.close()
    except Exception as e:
        return [f"could not parse: {e}"]
    return checker.problems + [
        f"<{t}> opened on line {l} is never closed" for t, l in checker.stack
    ]


# --------------------------------------------------------------------------
# CSS / JS bundles
# --------------------------------------------------------------------------
def compile_bundle(names, src_dir, ext, out_path, js):
    parts = []
    for name in names:
        path = os.path.join(src_dir, f"{name}.{ext}")
        content = read_file(path)
        problem = check_balanced(content, js)
        if problem:
            warn(f"{name}.{ext}: {problem}")
        parts.append(content)
    write_file(out_path, "\n".join(parts))


# --------------------------------------------------------------------------
# Page rendering
# --------------------------------------------------------------------------
TEMPLATE_RE = re.compile(
    r"<esta-template\b([^>]*?)(?:/>|>\s*</esta-template\s*>)", re.I | re.S
)
ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')
T_RE = re.compile(r"\{\{\s*t:\s*([\"'])(.+?)\1\s*\}\}")
ASSET_RE = re.compile(r"\{\{\s*asset:\s*([\"'])(.+?)\1\s*\}\}")
CSS_TAG_RE = re.compile(r"<esta-css\s*/?>(?:\s*</esta-css>)?", re.I)
JS_TAG_RE = re.compile(r"<esta-js\s*/?>(?:\s*</esta-js>)?", re.I)


def expand_templates(page, templates, label):
    def replace(match):
        attrs = {k: a or b for k, a, b in ATTR_RE.findall(match.group(1))}
        name = attrs.get("template")
        if not name:
            raise EstaError(f"{label}: <esta-template> without a 'template' attribute.")
        if name not in templates:
            raise EstaError(f"{label}: template '{name}' not found in source/templates.")
        out = templates[name]
        # Attributes: {{ SAMPLE }} is replaced by the value of the `SAMPLE` attribute
        for attr, value in attrs.items():
            pattern = r"\{\{\s*" + re.escape(attr) + r"\s*\}\}"
            out = re.sub(pattern, lambda _: value, out)
        return out

    for _ in range(10): # nested templates
        expanded = TEMPLATE_RE.sub(replace, page)
        if expanded == page:
            break
        page = expanded
    if TEMPLATE_RE.search(page):
        warn(f"{label}: templates are nested too deeply (or recursive).")
    return page


def lookup(data, key):
    """Find a translation by flat key or dotted path ('nav.home')."""
    if key in data:
        return data[key]
    node = data
    for part in key.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node


def render_page(src, out, lang, data, templates, css_file, js_file, asset_map):
    label = os.path.relpath(src, ROOT)
    page = read_file(src)

    page = expand_templates(page, templates, label)

    def translate(match):
        value = lookup(data, match.group(2))
        if value is None or isinstance(value, (dict, list)):
            warn(f"{label}: missing translation '{match.group(2)}' for '{lang}'.")
            return match.group(0)
        return str(value)

    page = T_RE.sub(translate, page)

    page = CSS_TAG_RE.sub(
        lambda _: f'<link rel="stylesheet" href="{rel(css_file, out)}">', page
    )
    page = JS_TAG_RE.sub(
        lambda _: f'<script src="{rel(js_file, out)}"></script>', page
    )

    def asset(match):
        key = posixpath.normpath(match.group(2).lstrip("/"))
        built = asset_map.get(key)
        if built is None:
            warn(f"{label}: asset '{key}' not found in assets/.")
            built = key
        return rel(os.path.join(BUILD, "assets", built), out)

    page = ASSET_RE.sub(asset, page)

    for problem in check_html(page):
        warn(f"{label} ({lang}): {problem}")

    write_file(out, page)


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
def clear_build():
    try:
        os.makedirs(BUILD, exist_ok=True)
        for entry in os.listdir(BUILD):
            if entry == "assets":
                continue
            path = os.path.join(BUILD, entry)
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
    except PermissionError:
        raise EstaError("No permission to clear the 'build' directory.")
    except OSError as e:
        raise EstaError(f"Could not clear the 'build' directory: {e}")


def load_language(lang):
    path = os.path.join(LANG_DIR, f"{lang}.json")
    try:
        data = json.loads(read_file(path))
    except json.JSONDecodeError as e:
        raise EstaError(f"Invalid JSON in source/lang/{lang}.json: {e}")
    if not isinstance(data, dict):
        raise EstaError(f"source/lang/{lang}.json must contain a JSON object.")
    return data


def load_templates():
    templates = {}
    if not os.path.isdir(TEMPLATES_DIR):
        return templates
    for filename in sorted(os.listdir(TEMPLATES_DIR)):
        path = os.path.join(TEMPLATES_DIR, filename)
        if os.path.isfile(path):
            content = read_file(path)
            templates[filename] = content # "SAMPLE.html"
            templates.setdefault(os.path.splitext(filename)[0], content) # "SAMPLE"
    return templates


def find_copies(directory, stem, ext):
    """Existing timestamped copies of an asset: [(datetime, filename), ...]."""
    pattern = re.compile(re.escape(stem) + r"-(\d{14})" + re.escape(ext))
    copies = []
    if not os.path.isdir(directory):
        return copies
    for name in os.listdir(directory):
        match = pattern.fullmatch(name)
        if match:
            try:
                copies.append((datetime.strptime(match.group(1), STAMP_FORMAT), name))
            except ValueError:
                pass
    return copies


def sync_assets():
    """
    Copy assets/ into build/assets/ as 'name-YYYYMMDDHHMMSS.ext'.

    - missing in build/assets        -> add
    - original newer than the copy   -> replace
    - original not newer than copy   -> do nothing

    The timestamp in the file name is the original's modification time.
    Returns a dict: original relative path -> relative path of the built copy.
    """
    mapping = {}
    if not os.path.isdir(ASSETS_DIR):
        return mapping
    dest_root = os.path.join(BUILD, "assets")
    added = updated = unchanged = 0

    for dirpath, dirnames, files in os.walk(ASSETS_DIR):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        rel_dir = os.path.relpath(dirpath, ASSETS_DIR)
        dest_dir = os.path.normpath(os.path.join(dest_root, rel_dir))
        for filename in sorted(files):
            if filename.startswith("."):
                continue  # skip hidden files such as .DS_Store
            src = os.path.join(dirpath, filename)
            key = os.path.normpath(os.path.join(rel_dir, filename)).replace(os.sep, "/")
            stem, ext = os.path.splitext(filename)
            try:
                original = datetime.fromtimestamp(os.path.getmtime(src)).replace(microsecond=0)
                existing = find_copies(dest_dir, stem, ext)

                if existing and max(existing)[0] >= original:
                    newest = max(existing)[1]
                    unchanged += 1
                else:
                    newest = f"{stem}-{original.strftime(STAMP_FORMAT)}{ext}"
                    os.makedirs(dest_dir, exist_ok=True)
                    shutil.copy2(src, os.path.join(dest_dir, newest))
                    for _, old in existing:  # remove outdated copies
                        os.remove(os.path.join(dest_dir, old))
                    if existing:
                        updated += 1
                    else:
                        added += 1
            except PermissionError:
                raise EstaError(f"No permission to copy asset: assets/{key}")
            except OSError as e:
                raise EstaError(f"Could not copy asset assets/{key}: {e}")

            mapping[key] = posixpath.normpath(
                posixpath.join(posixpath.dirname(key), newest)
            )

    print(f"  assets: {added} added, {updated} updated, {unchanged} unchanged")
    return mapping


def build():
    global SOURCE, CSS_DIR, JS_DIR, LANG_DIR, TEMPLATES_DIR, PAGES_DIR, ASSETS_DIR, BUILD

    config = load_config()

    # Set global paths from config
    SOURCE = config["paths"]["source"]
    CSS_DIR = config["paths"]["css"]
    JS_DIR = config["paths"]["js"]
    LANG_DIR = config["paths"]["lang"]
    TEMPLATES_DIR = config["paths"]["templates"]
    PAGES_DIR = config["paths"]["pages"]
    ASSETS_DIR = config["paths"]["assets"]
    BUILD = config["paths"]["build"]

    stamp = datetime.now().strftime("%Y%m%d%H%M%S")

    if not os.path.isdir(PAGES_DIR):
        raise EstaError("Directory not found: source/pages")

    print("Clearing build/ ...")
    clear_build()

    print("Compiling CSS and JS ...")
    css_file = os.path.join(BUILD, "css", f"styles-{stamp}.css")
    js_file = os.path.join(BUILD, "js", f"script-{stamp}.js")
    compile_bundle(config["css"], CSS_DIR, "css", css_file, js=False)
    compile_bundle(config["js"], JS_DIR, "js", js_file, js=True)

    print("Syncing assets ...")
    asset_map = sync_assets()

    templates = load_templates()
    errors = []

    for lang in config["lang"]:
        print(f"Building '{lang}' ...")
        data = load_language(lang)
        for dirpath, _, files in os.walk(PAGES_DIR):
            for filename in sorted(files):
                if not filename.lower().endswith(".html"):
                    continue
                src = os.path.join(dirpath, filename)
                out = os.path.join(BUILD, lang, os.path.relpath(src, PAGES_DIR))
                try:
                    render_page(src, out, lang, data, templates, css_file, js_file, asset_map)
                except EstaError as e:
                    errors.append(str(e))
                    print(f"  error: {e}", file=sys.stderr)

    # Root index.html (redirect to default language)
    index_src = os.path.join(SOURCE, "index.html")
    if os.path.isfile(index_src):
        try:
            shutil.copy2(index_src, os.path.join(BUILD, "index.html"))
        except OSError as e:
            raise EstaError(f"Could not copy source/index.html: {e}")

    if errors:
        raise EstaError(f"Build finished with {len(errors)} error(s).")
    suffix = f" with {len(WARNINGS)} warning(s)" if WARNINGS else ""
    print(f"Done{suffix}.")


def main():
    parser = argparse.ArgumentParser(description="ESTA - static site generator")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build", help="build the site into the 'build' directory")
    args = parser.parse_args()

    try:
        if args.command == "build":
            build()
    except EstaError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
