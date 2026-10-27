"""Scan the lines added between two git refs against the greppable rules in RULES.md.

Usage: sweep.py BASE [HEAD] [LIMIT]
  BASE   last audited commit (use the empty tree hash for a whole-project sweep)
  HEAD   defaults to HEAD
  LIMIT  rows printed per rule, default 6

Environment:
  APP_DIR      the Laravel app's folder in a monorepo (e.g. backend); found from `artisan` if unset
  OWNER_NAMES  regex alternation of names that must not appear, e.g. "jane|doe|jdoe"
  PHONE_CC     only check phone numbers with this country code (digits, e.g. 44); default any
  CLIENT_JS    comma-separated path prefixes whose JS/TS ships to the browser, added to the defaults
               (resources/js/, resources/ts/, public/, and any src/ folder)
  SERVER_JS    comma-separated path prefixes whose JS/TS runs on a server, even inside those
  TOKEN_FILES  regex for the stylesheets allowed to define :root tokens, default token|global|theme|variables
"""
import collections
import os
import re
import subprocess
import sys

base = sys.argv[1]
head = sys.argv[2] if len(sys.argv) > 2 else 'HEAD'
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 6
owner = os.environ.get('OWNER_NAMES', '').strip()
cc = os.environ.get('PHONE_CC', '').strip().lstrip('+')
token_files = re.compile(os.environ.get('TOKEN_FILES', r'token|global|theme|variables'), re.I)


def git(*args):
    return subprocess.run(['git', *args], capture_output=True, text=True, errors='ignore').stdout


def app_dir():
    configured = os.environ.get('APP_DIR', '').strip().strip('/')
    if configured:
        return configured + '/'
    found = [p for p in git('ls-tree', '-r', '--name-only', head).split('\n') if os.path.basename(p) == 'artisan']
    if not found:
        return ''
    shallowest = min(found, key=lambda p: p.count('/'))
    folder = os.path.dirname(shallowest)
    return folder + '/' if folder else ''


app = app_dir()


def in_app(path):
    """The path inside the Laravel app, or None for files outside it."""
    return path[len(app):] if path.startswith(app) else None


added = collections.defaultdict(list)
cur, lineno = None, 0
for raw in git('diff', '-U0', base, head).split('\n'):
    if raw.startswith('+++ '):
        cur = raw[6:] if raw.startswith('+++ b/') else None
        continue
    if raw.startswith('@@'):
        m = re.search(r'\+(\d+)', raw)
        lineno = int(m.group(1)) if m else 0
        continue
    if cur is None:
        continue
    if raw.startswith('+'):
        added[cur].append((lineno, raw[1:]))
        lineno += 1
    elif not raw.startswith('-'):
        lineno += 1

findings = collections.defaultdict(list)


def hit(rule, f, n, text):
    findings[rule].append(f'{f}:{n}  {text.strip()[:130]}')


FLOURISH = re.compile(r"earns its keep|is the point\b|not yet (exercised|tested|run|wired)|reads as one|exactly the (sort|kind)|the one that matters|first (sandbox|real) run", re.I)
CHANGELOG = re.compile(r"(//|\*|#|\{\{--)\s*.*\b(fixed|used to be|previously|moved from|edited by|changed from|was removed|refactored)\b", re.I)
SCREENCODE = re.compile(r"(//|/\*|\*|<!--|\{\{--).*\b[A-Z]{1,3}-?\d{2,4}[a-z]?\b")
PHONE = re.compile(r'(?<![\w.+])(?:\+\d{9,14}|0\d{9,11}|(?:\+\d{1,3}[ -]?)?(?:\(?\d{2,5}\)?[ -]){1,4}\d{2,5})(?![\w.])')
FICTIONAL_PHONE = re.compile(r'555[ -]?01\d\d$')
SAFE_MAIL = re.compile(r'@[\w.-]*(example\.(com|org|net)|\.test|\.invalid(\.[a-z0-9]+)?|localhost)$', re.I)
SKIP_ANYWHERE = ('/node_modules/', '/vendor/', '/dist/')
SKIP_IN_APP = ('vendor/', 'node_modules/', 'public/build', 'bootstrap/ssr', 'bootstrap/cache', 'storage/', 'public/js/filament/', 'public/css/filament/', 'public/vendor/')
def prefixes(name, defaults):
    return defaults + tuple(p.strip() for p in os.environ.get(name, '').split(',') if p.strip())


CLIENT_JS = prefixes('CLIENT_JS', ('resources/js/', 'resources/ts/', 'public/', 'src/'))
SERVER_JS = prefixes('SERVER_JS', ('tests/', 'bin/', 'scripts/', 'docker/', 'supabase/functions/'))
STYLES = ('.css', '.scss', '.sass', '.less')
SCRIPTS = ('.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx')
COMPONENTS = ('.vue', '.svelte')
JSX = ('.tsx', '.jsx')


def ships_to_browser(path, relative):
    """Browser code: components anywhere, scripts under a client folder, never generated files."""
    name = os.path.basename(path)
    if name.endswith(COMPONENTS):
        return True
    if not name.endswith(SCRIPTS) or re.search(r'\.(gen|generated|d)\.[cm]?[jt]sx?$|\.config\.[cm]?[jt]s$', name):
        return False
    paths = (path, relative or '')
    if any(p.startswith(SERVER_JS) for p in paths):
        return False
    return any(p.startswith(CLIENT_JS) for p in paths) or '/src/' in path


css_block = collections.defaultdict(bool)

for f, lines in added.items():
    relative = in_app(f)
    if any(s in '/' + f for s in SKIP_ANYWHERE):
        continue
    if relative is not None and relative.startswith(SKIP_IN_APP):
        continue
    if f.endswith(('.lock', '.min.js', '.min.css', '.svg', '.map')):
        continue
    blade = f.endswith('.blade.php')
    ext = os.path.splitext(f)[1]
    markup = blade or ext in COMPONENTS + JSX + ('.html',)
    client_script = ships_to_browser(f, relative)
    email_view = '/emails/' in f or '/mail/' in f
    config_like = (relative or '').startswith(('config/', 'lang/')) or f.endswith(('.md', '.json', '.yml', '.yaml'))
    for n, t in lines:
        s = t.strip()
        is_comment = s.startswith(('//', '/*', '*', '<!--', '{{--', '#', '{/*'))

        # 1. comments
        if '—' in t and (is_comment or client_script or ext in STYLES or markup) and not config_like:
            hit('1.em-dash', f, n, t)
        if is_comment and FLOURISH.search(t):
            hit('1.flourish-or-status', f, n, t)
        if is_comment and CHANGELOG.search(t):
            hit('1.changelog', f, n, t)
        if is_comment and SCREENCODE.search(t):
            hit('1.internal-code', f, n, t)
        if ext in STYLES:
            bare = re.sub(r"'[^']*'|\"[^\"]*\"", '', t)
            if s.startswith('/*') or (css_block[f] and not s.startswith(('*,', '*::', '* {', '*{'))) or ('/*' in bare and not s.startswith('/*')):
                hit('1.client-comment', f, n, t)
            if '/*' in bare and '*/' not in bare.split('/*', 1)[1]:
                css_block[f] = True
            if '*/' in bare:
                css_block[f] = False
        elif client_script and (is_comment or '{/*' in t):
            if not re.match(r'^\{?/[*/]\s*(@vite-ignore|[#@]__PURE__|eslint|@ts-|prettier-ignore)', s):
                hit('1.client-comment', f, n, t)
        if blade and ('<!--' in t or '{{--' in t):
            hit('1.client-comment', f, n, t)

        # 2. front end
        if markup and not email_view:
            m = re.search(r'(?<![:\w-])style="([^"]*)"', t)
            if m and any(d.strip() and not d.strip().startswith('--') for d in m.group(1).split(';')):
                hit('2.inline-style', f, n, t)
            m = re.search(r'(?::style|style:)="([^"]*)"', t)
            if m:
                keys = re.findall(r"(?:^|[{,])\s*('?[\w-]+'?)\s*:", m.group(1))
                if not keys or any(not k.strip("'").startswith('--') for k in keys):
                    hit('2.style-binding', f, n, t)
            m = re.search(r'style=\{\{([^}]*)\}\}', t)
            if m:
                keys = re.findall(r'(?:^|,)\s*["\']?([\w-]+)["\']?\s*:', m.group(1))
                if not keys or any(not k.startswith('--') for k in keys):
                    hit('2.inline-style', f, n, t)
            if re.search(r'<style\b', t) and ext not in COMPONENTS:
                hit('2.inline-style-block', f, n, t)
            if ext in COMPONENTS and re.search(r'^<style\b', s) and 'src=' not in s:
                hit('2.component-style-block', f, n, t)
            if re.search(r'<script\b(?![^>]*\b(src=|type="application/(ld\+)?json"))', t) and ext not in COMPONENTS + JSX:
                hit('2.inline-script-block', f, n, t)
            if re.search(r'\son[a-z]+="', t):
                hit('2.inline-event-handler', f, n, t)
        if '!important' in t and (ext in STYLES + COMPONENTS or blade):
            hit('2.important', f, n, t)
        if ext in STYLES and ':root' in t and not token_files.search(os.path.basename(f)):
            hit('2.root-outside-tokens', f, n, t)

        # 3. shared components
        if ext in COMPONENTS + JSX and re.search(r'class(Name)?="[^"]*crumb', t) and 'Breadcrumb' not in f:
            hit('3.hand-rolled-breadcrumb', f, n, t)

        # 4. database
        if (relative or '').startswith('database/migrations/'):
            if re.search(r'foreignId\(.*constrained\(', t) and not re.search(r'OnDelete|onDelete|cascade|restrict', t, re.I):
                hit('4.fk-without-ondelete', f, n, t)
            if re.search(r"->json\(", t):
                hit('4.json-not-jsonb (Postgres)', f, n, t)

        # 7. security
        if (relative or '').startswith('routes/') and re.search(r"Route::(post|put|patch|delete)\(", t) and 'throttle' not in t:
            hit('7.mutating-route-unthrottled?', f, n, t)
        if (blade and '{!!' in t) or (ext == '.vue' and 'v-html' in t) or (ext in JSX and 'dangerouslySetInnerHTML' in t) or (ext == '.svelte' and '{@html' in t):
            hit('7.raw-html-output', f, n, t)

        # 8. personal data
        if not config_like:
            for m in PHONE.finditer(t):
                phone = m.group(0).strip()
                digits = re.sub(r'\D', '', phone)
                if not 9 <= len(digits) <= 15 or not re.search(r'[ (-]|^[+0]', phone):
                    continue
                if cc and not (phone.startswith('+' + cc) or phone.startswith('0')):
                    continue
                if '0000' in digits[-8:] or FICTIONAL_PHONE.search(phone):
                    continue
                hit('8.real-looking-phone', f, n, t)
            for em in re.findall(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+', t):
                if not SAFE_MAIL.search(em.rstrip('.')):
                    hit('8.real-looking-email', f, n, t)
            if re.search(r"where\(\s*'email'\s*,\s*'[^']+@", t) and 'assignRole' in t:
                hit('8.role-by-literal-email', f, n, t)
        if owner and re.search(owner, t, re.I) and 'NoPersonalDataInSource' not in f:
            hit('8.owner-name', f, n, t)

for line in git('diff', '--name-status', base, head).split('\n'):
    parts = line.split('\t')
    if len(parts) == 2 and parts[0] == 'M' and (in_app(parts[1]) or '').startswith('database/migrations/'):
        findings['4.edited-existing-migration'].append(parts[1])

print(f'{len(added)} files with added lines, {base[:10]}..{head}, Laravel app in {app or "./"}')
for rule in sorted(findings):
    rows = findings[rule]
    print(f'\n=== {rule}: {len(rows)}')
    for r in rows[:limit]:
        print('   ' + r)
