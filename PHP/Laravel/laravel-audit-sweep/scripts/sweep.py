"""Scan the lines added between two git refs against the greppable rules in RULES.md.

Usage: sweep.py BASE [HEAD] [LIMIT]
  BASE   last audited commit (use the empty tree hash for a whole-project sweep)
  HEAD   defaults to HEAD
  LIMIT  rows printed per rule, default 6

Environment:
  OWNER_NAMES  regex alternation of names that must not appear, e.g. "jane|doe|jdoe"
  PHONE_CC     country calling code for the phone check, default 90
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
cc = os.environ.get('PHONE_CC', '90')


def git(*args):
    return subprocess.run(['git', *args], capture_output=True, text=True, errors='ignore').stdout


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
PHONE = re.compile(r'(?<![\d.])(?:\+' + cc + r'|0)?[\s.-]?\(?[2-9]\d{2}\)?[\s.-]?\d{3}[\s.-]?\d{2}[\s.-]?\d{2}(?![\d.])')
SAFE_MAIL = re.compile(r'@[\w.-]*(example\.(com|org|net)|\.test|\.invalid(\.[a-z0-9]+)?|localhost)$', re.I)
SKIP = ('vendor/', 'node_modules/', 'public/build', 'bootstrap/ssr', 'bootstrap/cache', 'storage/', 'public/js/filament/', 'public/css/filament/', 'public/vendor/')
# server-side TypeScript (Supabase / Deno edge functions) follows the server comment rule, not the client one
SERVER_TS = ('supabase/functions/',)
CLIENT = ('.css', '.scss', '.js', '.ts', '.vue', '.html')

css_block = collections.defaultdict(bool)

for f, lines in added.items():
    if f.startswith(SKIP) or f.endswith(('.lock', '.min.js', '.min.css', '.svg', '.map')):
        continue
    blade = f.endswith('.blade.php')
    ext = os.path.splitext(f)[1]
    email_view = '/emails/' in f or '/mail/' in f
    config_like = f.startswith(('config/', 'lang/')) or f.endswith(('.md', '.json', '.yml', '.yaml'))
    for n, t in lines:
        s = t.strip()
        is_comment = s.startswith(('//', '/*', '*', '<!--', '{{--', '#'))

        # 1. comments
        if '—' in t and (is_comment or ext in CLIENT or blade) and not config_like:
            hit('1.em-dash', f, n, t)
        if is_comment and FLOURISH.search(t):
            hit('1.flourish-or-status', f, n, t)
        if is_comment and CHANGELOG.search(t):
            hit('1.changelog', f, n, t)
        if is_comment and SCREENCODE.search(t):
            hit('1.internal-code', f, n, t)
        if ext in ('.css', '.scss'):
            bare = re.sub(r"'[^']*'|\"[^\"]*\"", '', t)
            if s.startswith('/*') or (css_block[f] and not s.startswith(('*,', '*::', '* {', '*{'))) or ('/*' in bare and not s.startswith('/*')):
                hit('1.client-comment', f, n, t)
            if '/*' in bare and '*/' not in bare.split('/*', 1)[1]:
                css_block[f] = True
            if '*/' in bare:
                css_block[f] = False
        elif ext in ('.js', '.ts', '.vue') and is_comment and not f.startswith(('tests/',) + SERVER_TS):
            if not re.match(r'^/[*/]\s*(@vite-ignore|[#@]__PURE__|eslint|@ts-)', s):
                hit('1.client-comment', f, n, t)
        if blade and ('<!--' in t or '{{--' in t):
            hit('1.client-comment', f, n, t)

        # 2. front end
        if (blade or ext in ('.vue', '.html')) and not email_view:
            m = re.search(r'(?<![:\w-])style="([^"]*)"', t)
            if m and any(d.strip() and not d.strip().startswith('--') for d in m.group(1).split(';')):
                hit('2.inline-style', f, n, t)
            m = re.search(r':style="([^"]*)"', t)
            if m:
                keys = re.findall(r"(?:^|[{,])\s*('?[\w-]+'?)\s*:", m.group(1))
                if not keys or any(not k.strip("'").startswith('--') for k in keys):
                    hit('2.style-binding', f, n, t)
            if re.search(r'<style\b', t) and ext != '.vue':
                hit('2.inline-style-block', f, n, t)
            if ext == '.vue' and re.search(r'^<style\b', s) and 'src=' not in s:
                hit('2.vue-style-block', f, n, t)
            if re.search(r'<script\b(?![^>]*\b(src=|type="application/(ld\+)?json"))', t) and ext != '.vue':
                hit('2.inline-script-block', f, n, t)
            if re.search(r'\son[a-z]+="', t):
                hit('2.inline-event-handler', f, n, t)
        if '!important' in t and (ext in ('.css', '.scss', '.vue') or blade):
            hit('2.important', f, n, t)
        if ext in ('.css', '.scss') and ':root' in t and 'token' not in f:
            hit('2.root-outside-tokens', f, n, t)

        # 3. shared components
        if ext == '.vue' and re.search(r'class="[^"]*crumb', t) and 'Breadcrumb' not in f:
            hit('3.hand-rolled-breadcrumb', f, n, t)

        # 4. database
        if f.startswith('database/migrations/'):
            if re.search(r'foreignId\(.*constrained\(', t) and not re.search(r'OnDelete|onDelete|cascade|restrict', t, re.I):
                hit('4.fk-without-ondelete', f, n, t)
            if re.search(r"->json\(", t):
                hit('4.json-not-jsonb', f, n, t)

        # 7. security
        if f.startswith('routes/') and re.search(r"Route::(post|put|patch|delete)\(", t) and 'throttle' not in t:
            hit('7.mutating-route-unthrottled?', f, n, t)
        if (blade and '{!!' in t) or (ext == '.vue' and 'v-html' in t):
            hit('7.raw-html-output', f, n, t)

        # 8. personal data
        if not config_like:
            m = PHONE.search(t)
            if m and re.search(r'[\s+(-]|^0', m.group(0)):
                digits = re.sub(r'\D', '', m.group(0))[-10:]
                if digits[3:8] != '00000':
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
    if len(parts) == 2 and parts[0] == 'M' and parts[1].startswith('database/migrations/'):
        findings['4.edited-existing-migration'].append(parts[1])

print(f'{len(added)} files with added lines, {base[:10]}..{head}')
for rule in sorted(findings):
    rows = findings[rule]
    print(f'\n=== {rule}: {len(rows)}')
    for r in rows[:limit]:
        print('   ' + r)
