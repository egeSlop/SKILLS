"""Strip comments from client-side source: CSS, JS/TS and Vue SFC blocks.

Usage: strip_comments.py FILE...
Keeps tool directives (@vite-ignore, __PURE__, eslint, @ts-*). Whole-line
comments go with their line; the blank line a removed block leaves collapses.
Rebuild afterwards and compare the minified output with the previous build.
"""
import re
import sys
import pathlib

KEEP = re.compile(r'^/[*/]\s*(@vite-ignore|[#@]__PURE__|eslint|@ts-|webpackChunkName|istanbul|prettier-ignore|@license|!)')

REGEX_PREV = set('(,=:[!&|?{};+-*%<>~^')
REGEX_KW = {'return', 'typeof', 'instanceof', 'in', 'of', 'new', 'delete', 'void', 'throw', 'case', 'do', 'else', 'yield', 'await'}


def strip_js(src: str) -> str:
    out = []
    i, n = 0, len(src)
    stack = []  # template literal nesting: brace depth at which `${` opened
    depth = 0
    last_sig = ''  # last significant token text

    def prev_allows_regex():
        if last_sig == '':
            return True
        if last_sig in REGEX_KW:
            return True
        return last_sig[-1] in REGEX_PREV

    while i < n:
        c = src[i]
        if c in '"\'':
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == '\\':
                    j += 1
                elif src[j] == '\n':
                    break
                j += 1
            out.append(src[i:j + 1])
            last_sig = 'str'
            i = j + 1
            continue
        if c == '`':
            j = i + 1
            while j < n:
                if src[j] == '\\':
                    j += 2
                    continue
                if src[j] == '`':
                    break
                if src[j] == '$' and j + 1 < n and src[j + 1] == '{':
                    break
                j += 1
            if j < n and src[j] == '$':
                out.append(src[i:j + 2])
                stack.append(depth)
                depth += 1
                last_sig = '{'
                i = j + 2
            else:
                out.append(src[i:j + 1])
                last_sig = 'str'
                i = j + 1
            continue
        if c == '}' and stack and depth - 1 == stack[-1]:
            depth -= 1
            stack.pop()
            # resume template literal
            j = i + 1
            while j < n:
                if src[j] == '\\':
                    j += 2
                    continue
                if src[j] == '`':
                    break
                if src[j] == '$' and j + 1 < n and src[j + 1] == '{':
                    break
                j += 1
            if j < n and src[j] == '$':
                out.append(src[i:j + 2])
                stack.append(depth)
                depth += 1
                last_sig = '{'
                i = j + 2
            else:
                out.append(src[i:j + 1])
                last_sig = 'str'
                i = j + 1
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            j = src.find('\n', i)
            j = n if j == -1 else j
            text = src[i:j]
            if KEEP.match(text):
                out.append(text)
            else:
                out.append('\x00LC')
            i = j
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            j = n if j == -1 else j + 2
            text = src[i:j]
            if KEEP.match(text):
                out.append(text)
            else:
                out.append('\x00BC')
            i = j
            continue
        if c == '/' and prev_allows_regex():
            j = i + 1
            in_class = False
            while j < n and src[j] != '\n':
                if src[j] == '\\':
                    j += 2
                    continue
                if src[j] == '[':
                    in_class = True
                elif src[j] == ']':
                    in_class = False
                elif src[j] == '/' and not in_class:
                    break
                j += 1
            j += 1
            while j < n and src[j].isalpha():
                j += 1
            out.append(src[i:j])
            last_sig = 'regex'
            i = j
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
        if not c.isspace():
            if c.isalnum() or c in '_$':
                j = i
                while j < n and (src[j].isalnum() or src[j] in '_$'):
                    j += 1
                word = src[i:j]
                out.append(word)
                last_sig = word if word in REGEX_KW else 'id'
                i = j
                continue
            last_sig = c
        out.append(c)
        i += 1
    return tidy(''.join(out))


def strip_css(src: str) -> str:
    out = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in '"\'':
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == '\\':
                    j += 1
                j += 1
            out.append(src[i:j + 1])
            i = j + 1
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            j = src.find('*/', i + 2)
            j = n if j == -1 else j + 2
            text = src[i:j]
            out.append(text if KEEP.match(text) else '\x00BC')
            i = j
            continue
        out.append(c)
        i += 1
    return tidy(''.join(out))


def strip_html(src: str) -> str:
    return tidy(re.sub(r'<!--.*?-->', '\x00BC', src, flags=re.S))


GAP = object()


def tidy(text: str) -> str:
    kept = []
    for line in text.split('\n'):
        if '\x00' in line:
            bare = line.replace('\x00LC', '').replace('\x00BC', '')
            if bare.strip() == '':
                if not kept or kept[-1] is not GAP:
                    kept.append(GAP)
                continue
            line = bare.rstrip()
        kept.append(line)

    def blank(x):
        return x is not GAP and x.strip() == ''

    out = []
    for k, line in enumerate(kept):
        if line is GAP:
            prev = out[-1] if out else None
            nxt = kept[k + 1] if k + 1 < len(kept) else None
            # the comment sat between two blanks, or opened a block, or
            # closed one: drop the blank it leaves behind
            if nxt is not None and blank(nxt) and (prev is None or blank(prev) or prev.rstrip().endswith(('{', '(', '[')) or re.match(r'\s*<(script|style|template)\b', prev)):
                kept[k + 1] = GAP
            elif prev is not None and blank(prev) and (nxt is None or (nxt is not GAP and nxt.strip().startswith(('}', ')', ']', '</')))):
                out.pop()
            continue
        out.append(line)
    return '\n'.join(out)


def strip_vue(src: str) -> str:
    parts = []
    pos = 0
    for m in re.finditer(r'(<script\b[^>]*>)(.*?)(</script>)|(<style\b[^>]*>)(.*?)(</style>)', src, re.S):
        parts.append(('html', src[pos:m.start()]))
        if m.group(1):
            parts.append(('raw', m.group(1)))
            parts.append(('js', m.group(2)))
            parts.append(('raw', m.group(3)))
        else:
            parts.append(('raw', m.group(4)))
            parts.append(('css', m.group(5)))
            parts.append(('raw', m.group(6)))
        pos = m.end()
    parts.append(('html', src[pos:]))
    out = []
    for kind, text in parts:
        if kind == 'html':
            out.append(re.sub(r'<!--.*?-->', '\x00BC', text, flags=re.S))
        elif kind == 'js':
            out.append(strip_js(text))
        elif kind == 'css':
            out.append(strip_css(text))
        else:
            out.append(text)
    return tidy(''.join(out))


for name in sys.argv[1:]:
    p = pathlib.Path(name)
    src = p.read_text()
    if p.suffix == '.css':
        new = strip_css(src)
    elif p.suffix in ('.js', '.ts', '.mjs'):
        new = strip_js(src)
    elif p.suffix == '.vue':
        new = strip_vue(src)
    else:
        continue
    if not new.endswith('\n'):
        new += '\n'
    if new != src:
        p.write_text(new)
