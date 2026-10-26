#!/usr/bin/env python3

# Esta - Minimal Static Site Generator.

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

__version__ = "0.1"

# --------------------------------------------------------------------------
# Paths (relative to the directory containing esta.py)
# --------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_NAME = "config.ini"
SOURCE = os.path.join(os.getcwd(), "source")
CSS_DIR = os.path.join(SOURCE, "css")
JS_DIR = os.path.join(SOURCE, "js")
LANG_DIR = os.path.join(SOURCE, "lang")
TEMPLATES_DIR = os.path.join(SOURCE, "templates")
PAGES_DIR = os.path.join(SOURCE, "pages")
ASSETS_DIR = os.path.join(SOURCE, "assets")
BUILD = os.path.join(os.getcwd(), "build")
SAMPLE_DIR = os.path.join(ROOT, "sample")
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
def display_path(path):
    """Path as shown in messages: relative to the current directory."""
    try:
        return os.path.relpath(path)
    except ValueError:  # e.g. a different drive on Windows
        return path


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        raise EstaError(f"File not found: {display_path(path)}")
    except PermissionError:
        raise EstaError(f"No permission to read: {display_path(path)}")
    except UnicodeDecodeError:
        raise EstaError(f"File is not valid UTF-8: {display_path(path)}")
    except OSError as e:
        raise EstaError(f"Could not read {display_path(path)}: {e}")


def write_file(path, content):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
    except PermissionError:
        raise EstaError(f"No permission to write: {display_path(path)}")
    except OSError as e:
        raise EstaError(f"Could not write {display_path(path)}: {e}")


def rel(target, page_path):
    """Relative URL from the folder of `page_path` to `target`."""
    start = os.path.dirname(page_path)
    return os.path.relpath(target, start).replace(os.sep, "/")


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------
def load_config(config_file=None):
    config_file = os.path.abspath(config_file or CONFIG_NAME)
    config_dir = os.path.dirname(config_file)
    config_name = os.path.basename(config_file)
    parser = ConfigParser(
        allow_no_value=True,
        delimiters=("=",),
        comment_prefixes=("#", ";"),
        inline_comment_prefixes=None,
    )
    parser.optionxform = str  # keep file names case-sensitive
    try:
        parser.read_string(read_file(config_file))
    except ConfigError as e:
        raise EstaError(f"Invalid {config_name}: {e}")

    config = {}

    # [general] base_url (optional): a single trailing '/' is discarded
    base_url = ""
    if parser.has_option("general", "base_url"):
        base_url = (parser.get("general", "base_url") or "").strip()
        if base_url.endswith("/"):
            base_url = base_url[:-1]
    config["base_url"] = base_url

    for section in ("lang", "css", "js"):
        if not parser.has_section(section):
            raise EstaError(f"{config_name} is missing the [{section}] section.")
        config[section] = list(parser.options(section))
    if not config["lang"]:
        raise EstaError(f"{config_name}: the [lang] section is empty.")
    
    config["paths"] = {}
    for key in ("source", "css", "js", "lang", "templates", 
                "pages", "assets", "build"):
        if not parser.has_option("paths", key):
            raise EstaError(f"{config_name}: [paths] section is missing '{key}'.")
        # Paths are relative to the directory containing the config file
        path_value = parser.get("paths", key)
        config["paths"][key] = os.path.normpath(os.path.join(config_dir, path_value))
    
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


# ---- CSS minifier --------------------------------------------------------
_CSS_TOKEN_RE = re.compile(
    r"""
    (?P<comment>/\*.*?\*/)
  | (?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')
  | url\(\s*(?P<url>(?![\s'"])[^)]*?)\s*\)
  | (?P<space>\s+)
  | (?P<other>.)
    """,
    re.S | re.I | re.X,
)


def minify_css(src):
    """Strip comments and unnecessary whitespace (strings and url() are kept)."""
    out, space = [], False
    for m in _CSS_TOKEN_RE.finditer(src):
        kind = m.lastgroup
        if kind in ("comment", "space"):
            space = True
            continue
        if kind == "url":
            tok = f"url({m.group('url')})"
        else:
            tok = m.group()
        if out and space and out[-1][-1] not in "{};,>(:" and tok[0] not in "{};,>)":
            out.append(" ")
        space = False
        if tok == "}" and out and out[-1] == ";":
            out.pop()  # the last ';' in a block is redundant
        out.append(tok)
    return "".join(out)


# ---- JS minifier ---------------------------------------------------------
_JS_WORD_RE = re.compile(r"[\w$\\\u0080-\uffff]+")
_JS_REGEX_AFTER = {
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
    "throw", "case", "do", "else", "yield", "await",
}


def _js_word_char(c):
    return c.isalnum() or c in "_$\\" or ord(c) > 127


def _skip_js_string(s, i):
    quote, n, j = s[i], len(s), i + 1
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
        elif c == quote:
            return j + 1
        elif c == "\n":
            return j  # unterminated: stop at the end of the line
        else:
            j += 1
    return n


def _skip_js_template(s, i):
    n, j = len(s), i + 1
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
        elif c == "`":
            return j + 1
        elif c == "$" and s.startswith("${", j):
            j = _skip_js_braces(s, j + 2)
        else:
            j += 1
    return n


def _skip_js_braces(s, i):
    """Skip to just after the '}' closing a '${' (i is just after the '${')."""
    n, depth = len(s), 1
    while i < n:
        c = s[i]
        if c in "'\"":
            i = _skip_js_string(s, i)
        elif c == "`":
            i = _skip_js_template(s, i)
        elif s.startswith("/*", i):
            end = s.find("*/", i + 2)
            i = n if end == -1 else end + 2
        elif s.startswith("//", i):
            end = s.find("\n", i)
            i = n if end == -1 else end
        elif c == "{":
            depth += 1
            i += 1
        elif c == "}":
            depth -= 1
            i += 1
            if depth == 0:
                return i
        else:
            i += 1
    return n


def _skip_js_regex(s, i):
    """End index of a regex literal starting at s[i] == '/', or None."""
    n, j, in_class = len(s), i + 1, False
    while j < n:
        c = s[j]
        if c == "\n":
            return None
        if c == "\\":
            j += 2
            continue
        if in_class:
            if c == "]":
                in_class = False
        elif c == "[":
            in_class = True
        elif c == "/":
            return j + 1
        j += 1
    return None


def _js_gap(prev, nxt, newline):
    """Separator needed between two tokens that had whitespace between them."""
    a, b = prev[-1], nxt[0]
    if newline:
        if a in "{([,;" or b in "})],;":
            return ""
        return "\n"
    if ((_js_word_char(a) and _js_word_char(b))
            or (a == b and a in "+-/")
            or (a.isdigit() and b == ".")):
        return " "
    return ""


def minify_js(src):
    """Strip comments and unnecessary whitespace (strings/regex/templates kept)."""
    out, n, i = [], len(src), 0
    last, last_kind = "", None
    space = newline = False
    while i < n:
        c = src[i]
        if c.isspace():
            j = i
            while j < n and src[j].isspace():
                j += 1
            if re.search(r"[\n\r\u2028\u2029]", src[i:j]):
                newline = True
            space, i = True, j
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            space, i = True, (n if j == -1 else j)
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            end = n if j == -1 else j + 2
            if "\n" in src[i:end]:
                newline = True
            space, i = True, end
            continue

        end = None
        kind = "punct"
        if c in "'\"":
            end, kind = _skip_js_string(src, i), "str"
        elif c == "`":
            end, kind = _skip_js_template(src, i), "str"
        elif c == "/":
            regex_ok = (last_kind is None
                        or (last_kind == "punct" and last not in ")]")
                        or (last_kind == "word" and last in _JS_REGEX_AFTER))
            if regex_ok:
                end = _skip_js_regex(src, i)
                if end:
                    kind = "str"
        if end is None:
            m = _JS_WORD_RE.match(src, i)
            if m:
                end, kind = m.end(), "word"
            else:
                end, kind = i + 1, "punct"

        tok = src[i:end]
        if out and space:
            out.append(_js_gap(last, tok, newline))
        out.append(tok)
        last, last_kind = tok, kind
        space = newline = False
        i = end
    return "".join(out)


# ---- Bundles -------------------------------------------------------------
def resolve_bundle_assets(text, label, out_path, asset_map, js, base_url):
    """
    Replace {{ asset: 'route' }} inside a CSS/JS file.

    - CSS: URL relative to the bundle (this is how url() is resolved).
    - JS:  absolute URL ('<base_url>/assets/...'), because a relative path
           in a script is resolved against the page, not the script. Without a
           base_url it is root-relative ('/assets/...').
    """
    def asset(match):
        key = posixpath.normpath(match.group(2).lstrip("/"))
        built = asset_map.get(key)
        if built is None:
            warn(f"{label}: asset '{key}' not found in assets/.")
            built = key
        if js:
            return f"{base_url}/assets/{built}"
        return rel(os.path.join(BUILD, "assets", built), out_path)

    return ASSET_RE.sub(asset, text)


def compile_bundle(names, src_dir, ext, out_path, js, asset_map=None, base_url=""):
    parts = []
    for name in names:
        path = os.path.join(src_dir, f"{name}.{ext}")
        label = f"{name}.{ext}"
        content = read_file(path)
        content = resolve_bundle_assets(content, label, out_path,
                                        asset_map or {}, js, base_url)
        problem = check_balanced(content, js)
        if problem:
            warn(f"{label}: {problem}")
        parts.append(minify_js(content) if js else minify_css(content))
    write_file(out_path, "\n".join(parts))


# --------------------------------------------------------------------------
# Page rendering
# --------------------------------------------------------------------------
# Matches an opening/self-closing/closing <esta-template ...> tag. Quoted
# attribute values may contain '>'. group(1) = "/" for closing tags,
# group(2) = the raw attribute text (ends with "/" for self-closing tags).
TEMPLATE_TAG_RE = re.compile(
    r"<(/?)esta-template(?=[\s/>])((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>", re.I
)
CONTENT_RE = re.compile(r"<esta-content\s*/?>(?:\s*</esta-content\s*>)?", re.I)
MAX_TEMPLATE_DEPTH = 10
ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')')
T_RE = re.compile(r"\{\{\s*t:\s*([\"'])(.+?)\1\s*\}\}")
ASSET_RE = re.compile(r"\{\{\s*asset:\s*([\"'])(.+?)\1\s*\}\}")
LANG_RE = re.compile(r"\{\{\s*lang\s*\}\}")
LANGS_RE = re.compile(r"\{\{\s*langs\s*\}\}")
PAGE_RE = re.compile(
    r"\{\{\s*page:\s*([\"'])(.*?)\1"
    r"(?:\s*,?\s*lang:\s*([\"'])(.+?)\3)?\s*\}\}"
)
CSS_TAG_RE = re.compile(r"<esta-css\s*/?>(?:\s*</esta-css>)?", re.I)
JS_TAG_RE = re.compile(r"<esta-js\s*/?>(?:\s*</esta-js>)?", re.I)


def expand_templates(page, templates, label, depth=0):
    """
    Expand <esta-template template="name" ...> tags.

    - Attributes fill `{{ attr }}` placeholders inside the template.
    - Anything between the opening and closing tag is projected into the
      template wherever it contains <esta-content>.
    - Templates may use other templates, and tags may be nested.
    """
    if depth > MAX_TEMPLATE_DEPTH:
        warn(f"{label}: templates are nested too deeply (or recursive).")
        return page

    out = []
    pos = 0
    while True:
        # Find the next opening tag (skip stray closing tags)
        match = TEMPLATE_TAG_RE.search(page, pos)
        while match and match.group(1):
            match = TEMPLATE_TAG_RE.search(page, match.end())
        if not match:
            out.append(page[pos:])
            break
        out.append(page[pos:match.start()])

        if match.group(2).rstrip().endswith("/"):  # <esta-template ... />
            inner, end = "", match.end()
        else:  # find the matching </esta-template>, counting nested ones
            level, scan = 1, match.end()
            while level:
                tag = TEMPLATE_TAG_RE.search(page, scan)
                if not tag:
                    raise EstaError(f"{label}: <esta-template> is never closed.")
                if tag.group(1):
                    level -= 1
                elif not tag.group(2).rstrip().endswith("/"):
                    level += 1
                scan = tag.end()
            inner, end = page[match.end():tag.start()], tag.end()

        attrs = {k: a or b for k, a, b in ATTR_RE.findall(match.group(2))}
        name = attrs.get("template")
        if not name:
            raise EstaError(f"{label}: <esta-template> without a 'template' attribute.")
        if name not in templates:
            raise EstaError(f"{label}: template '{name}' not found in {display_path(TEMPLATES_DIR)}.")
        body = templates[name]

        # Attributes: {{ SAMPLE }} is replaced by the value of the `SAMPLE` attribute
        for attr, value in attrs.items():
            pattern = r"\{\{\s*" + re.escape(attr) + r"\s*\}\}"
            body = re.sub(pattern, lambda _: value, body)

        # Content projection: <esta-content> receives the tag's inner content
        projected = expand_templates(inner, templates, label, depth)
        if CONTENT_RE.search(body):
            body = CONTENT_RE.sub(lambda _: projected, body)
        elif projected.strip():
            warn(f"{label}: template '{name}' has no <esta-content>; "
                 f"the content inside the tag is ignored.")

        # The template itself may use other templates
        out.append(expand_templates(body, templates, label, depth + 1))
        pos = end
    return "".join(out)


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


def render_page(src, out, lang, data, templates, css_file, js_file, asset_map,
                base_url="", languages=()):
    label = display_path(src)
    page = read_file(src)

    page = expand_templates(page, templates, label)

    def translate(match):
        value = lookup(data, match.group(2))
        if value is None or isinstance(value, (dict, list)):
            warn(f"{label}: missing translation '{match.group(2)}' for '{lang}'.")
            return match.group(0)
        return str(value)

    page = T_RE.sub(translate, page)

    page = LANG_RE.sub(lambda _: lang, page)
    page = LANGS_RE.sub(lambda _: json.dumps(list(languages)), page)

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

    def page_link(match):
        url = match.group(2).strip().lstrip("/")
        target_lang = match.group(4).strip() if match.group(4) else lang
        if languages and target_lang not in languages:
            warn(f"{label}: language '{target_lang}' in '{match.group(0)}' "
                 f"is not listed in the config.")
        if not url:  # {{ page: '' }} -> the base url
            if match.group(4):
                return f"{base_url}/{target_lang}/"
            return base_url
        # Check the page exists (ignoring any #fragment or ?query)
        path_part = re.split(r"[?#]", url, maxsplit=1)[0]
        key = posixpath.normpath(path_part) if path_part else "."
        candidate = os.path.join(PAGES_DIR, *key.split("/"))
        if not (os.path.isfile(candidate)
                or os.path.isfile(os.path.join(candidate, "index.html"))):
            warn(f"{label}: linked page '{url}' not found in pages/.")
        return f"{base_url}/{target_lang}/{url}"

    page = PAGE_RE.sub(page_link, page)

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
        raise EstaError(f"Invalid JSON in {display_path(path)}: {e}")
    if not isinstance(data, dict):
        raise EstaError(f"{display_path(path)} must contain a JSON object.")
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


def build(config_file=None):
    global SOURCE, CSS_DIR, JS_DIR, LANG_DIR, TEMPLATES_DIR, PAGES_DIR, ASSETS_DIR, BUILD

    config = load_config(config_file)
    base_url = config["base_url"]

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
        raise EstaError(f"Directory not found: {display_path(PAGES_DIR)}")

    print("Clearing build/ ...")
    clear_build()

    print("Syncing assets ...")
    asset_map = sync_assets()

    print("Bundling CSS and JS ...")
    css_file = os.path.join(BUILD, "css", f"styles-{stamp}.css")
    js_file = os.path.join(BUILD, "js", f"script-{stamp}.js")
    compile_bundle(config["css"], CSS_DIR, "css", css_file, False, asset_map, base_url)
    compile_bundle(config["js"], JS_DIR, "js", js_file, True, asset_map, base_url)

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
                    render_page(src, out, lang, data, templates, css_file, js_file,
                                asset_map, base_url, config["lang"])
                except EstaError as e:
                    errors.append(str(e))
                    print(f"  error: {e}", file=sys.stderr)

    # Source index.html with the first lang from config
    index_src = os.path.join(SOURCE, "index.html")
    if os.path.isfile(index_src):
        default_lang = config["lang"][0]
        print("Building 'index.html' ...")
        try:
            render_page(index_src, os.path.join(BUILD, "index.html"),
                        default_lang, load_language(default_lang), templates,
                        css_file, js_file, asset_map, base_url, config["lang"])
        except EstaError as e:
            errors.append(str(e))
            print(f"  error: {e}", file=sys.stderr)

    if errors:
        raise EstaError(f"Build finished with {len(errors)} error(s).")
    suffix = f" with {len(WARNINGS)} warning(s)" if WARNINGS else ""
    print(f"Done{suffix}.")


def new_project(directory=None):
    target = os.path.abspath(directory or os.getcwd())

    if not os.path.isdir(SAMPLE_DIR):
        raise EstaError(f"Sample folder not found: {SAMPLE_DIR}")
    if os.path.exists(target) and not os.path.isdir(target):
        raise EstaError(f"Not a directory: {target}")

    # List everything to copy
    dirs, files = [], []
    for dirpath, dirnames, filenames in os.walk(SAMPLE_DIR):
        rel_dir = os.path.relpath(dirpath, SAMPLE_DIR)
        for name in dirnames:
            dirs.append(os.path.normpath(os.path.join(rel_dir, name)))
        for name in filenames:
            files.append(os.path.normpath(os.path.join(rel_dir, name)))

    # Detect conflicts
    conflicts = [f for f in files if os.path.exists(os.path.join(target, f))]
    if conflicts:
        shown = ", ".join(conflicts[:5]) + (", ..." if len(conflicts) > 5 else "")
        raise EstaError(
            f"Could not create the project: {len(conflicts)} file(s) already exist in "
            f"{target} ({shown})."
        )

    try:
        os.makedirs(target, exist_ok=True)
        for d in dirs:
            os.makedirs(os.path.join(target, d), exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(SAMPLE_DIR, f), os.path.join(target, f))
    except PermissionError:
        raise EstaError(f"No permission to write in: {target}")
    except OSError as e:
        raise EstaError(f"Could not create the project in {target}: {e}")

    print(f"New project created in {target}")


def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="esta.py",
        description="Esta - Minimal Static Site Generator",
        add_help=False,
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"esta {__version__}",
        help="Show the installed version and exit.",
    )
    parser.add_argument(
        "-h", "--help", action="help", help="Show this help message and exit."
    )
    sub = parser.add_subparsers(dest="command", metavar="command", required=True)

    new_parser = sub.add_parser(
        "new", help="Create a new project."
    )
    new_parser.add_argument(
        "directory", nargs="?", default=None, metavar="DIR",
        help="Directory for the new project; created if missing "
             "(default: current directory).",
    )

    build_parser = sub.add_parser(
        "build", help="Build the site into the 'build' directory."
    )
    build_parser.add_argument(
        "-c", "--config", metavar="PATH", default=None,
        help="Path to the config file, relative to the current directory "
             "(default: config.ini in the current directory).",
    )

    help_parser = sub.add_parser(
        "help", help="Show help about the program or about a command."
    )
    help_parser.add_argument(
        "topic", nargs="?", default=None, metavar="command",
        help="Command to show help for.",
    )
    return parser, sub.choices


def main():
    parser, commands = build_arg_parser()
    args = parser.parse_args()

    try:
        if args.command == "new":
            new_project(args.directory)
        elif args.command == "build":
            config_file = os.path.abspath(args.config) if args.config else None
            build(config_file)
        elif args.command == "help":
            if args.topic is None:
                parser.print_help()
            elif args.topic in commands:
                commands[args.topic].print_help()
            else:
                raise EstaError(f"Unknown command: {args.topic}")
    except EstaError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
