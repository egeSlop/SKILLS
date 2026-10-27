# Rules

What every commit is checked against. Each rule says what to do; the reason
follows where it is not obvious. `[scan]` marks rules `scripts/sweep.py`
checks; `[guard]` marks rules a test in `templates/` enforces; the rest are
read by hand.

---

## 1. Comments

Write a comment only when the code cannot say it.

- **No changelog comments** `[scan]`. Not `// fixed X`, `// used to be`,
  `// moved from`, `// no longer`. Git holds history; a comment about what
  used to be there is stale the moment it is written.
- **No design-rationale essays.** If a pattern is shared, share the code.
- **No status or confidence narration** `[scan]`. "Not yet tested against a
  real account", "the first sandbox run will prove this". Maturity belongs in
  the tracker or PR, which are dated and get closed.
- **No literary flourish** `[scan]`. "earns its keep", "is the point",
  "reads as one", "exactly the sort of". If it would fit in an essay, cut it.
- **No comments in client-side files** `[scan]`: CSS, JS and TS (JSX and TSX
  included), Vue, Svelte, Blade, HTML, email templates. Anyone can read what
  the browser receives: comments leak internals and feature names, explanatory
  ones mark the code as machine-written and invite probing, and prose between
  rules hides the rules. Tool directives (`@vite-ignore`, `__PURE__`,
  `eslint-*`, `@ts-*`) stay.
- **Server-side PHP may carry a short comment where it earns the line**: a
  trap that cost real time, a guard whose absence would be silent, why a value
  is what it is. One to three lines.
- **No em dashes in code or comments** `[scan]`. Use a comma, colon, or new
  sentence. The glyph as a data value (an empty cell) is fine.
- **No internal codes in comments** (ticket numbers, screen codes like
  `T04`). The file name says which page it is.
- **No personal data in comments** (see §8).

## 2. Front-end: CSS and JS

- **CSS lives in `.css` files and JS in `.js` files. Nothing inline.**
  - No `<style>` blocks and no `<script>` blocks in Blade or HTML. Load a
    file through Vite (`@vite(...)`) instead.
  - No `style="..."` attributes `[scan]`. A genuinely computed value (a bar's
    width) is passed as a CSS custom property
    (`style="--w: {{ $pct }}%"`, `:style="{ '--w': pct + '%' }"`,
    `style={{ "--w": `${pct}%` }}`), and the rule that uses it lives in the
    stylesheet.
  - No inline event handlers (`onclick="..."`) `[scan]`. Bind in the JS file
    (Alpine, Vue and Svelte directives and React props are not inline scripts).
  - Single-file components (Vue, Svelte) keep their script block, but their
    styles go in a `.css` file rather than a `<style>` block `[scan]`. React
    components import a `.css` file; no CSS-in-JS.
  - Data a script needs from the server goes in a `data-*` attribute or a
    `<script type="application/json">` payload, not in generated JS.
  - Why: inline code cannot be cached, linted or minified with the rest, and
    it forces `unsafe-inline` into the Content Security Policy.
  - Exception: email templates, whose clients drop external CSS.
- **Shared furniture lives in `components/`.** Anything more than one page
  renders (card, badge, breadcrumb) has one stylesheet.
- **Cascade layers, not import order, decide precedence.** Declare the order
  once (e.g. `tokens < base < components < pages < widgets`). Prefix your layer
  names; Tailwind reserves `theme`, `base`, `components`, `utilities`.
- **A `:root` token is global** `[scan]`. Define every token, and every
  responsive step of it, in one tokens file per bundle.
- **No `!important`** `[scan]` unless beating an inline style or a `*`
  selector.
- **Shorthand padding on a container resets its gutter.** Use long-hand
  `padding-block` on anything that is also a width wrapper.
- **Delete classes no template renders**, but remember `:class` bindings a
  static scan cannot read. Delete whole clusters, match with word boundaries.

## 3. Shared components

- **Two pages rendering the same thing from the same data shape is one
  component** `[scan: breadcrumbs]`. Breadcrumbs, cards, pagination, empty
  states.
- The component owns appearance; the page passes a class for position only
  (margin/padding). Variants go through a prop or a slot, not a copy.
- Mark state with attributes (`aria-current="page"`, `aria-expanded`) and
  style the attribute. A class for it drifts.
- Server-side, the data shape is the same everywhere (e.g. crumbs are always
  `{name, url}`), so JSON-LD and the component read the same array.

## 4. Database

- **Never edit a migration that has run anywhere** `[scan]`. Add a new one.
- **Every foreign key states `onDelete`** `[scan]`: cascade or null,
  chosen on purpose.
- **Postgres: JSON columns are `jsonb`**. Never compare jsonb values by
  `json_encode` hash or `assertSame` on an associative array: Postgres
  reorders keys. Sort maps recursively, leave lists alone.
- **Changing a column's type rewrites the table under a lock.** Check the
  table's size in production before it deploys.
- **Locale-aware sorting** for user-facing text (a collation, not a bare
  `ORDER BY`) when the language needs it (Turkish, for example).
- **Read the migrations, not the production schema**, when sweeping schema:
  undeployed tables exist only in the migrations.

## 5. Authorization (Filament, Livewire, controllers)

- **Resources fail closed.** Every resource extends a base whose `canAccess()`
  returns `false`, and still declares its own rule `[guard]`. Filament's
  default is allow.
- **Ask permissions, not role names.**
- **Relationship `Select`/`CheckboxList` do not re-check submitted ids.**
  Re-filter in `saveRelationshipsUsing` against the same scope the options
  used. Plain `Select` with `options()`: add `->in(...)` with the same keys.
- **A disabled field is still submitted.** `->disabled()->dehydrated()` saves
  whatever the browser sends. Pin the value in `dehydrateStateUsing` for
  users who may not change it, or `->dehydrated(false)`.
- **A table `CreateAction` does not attach the panel tenant.** Create through
  the tenant relation with `->using()`.
- **An action's closure re-checks what `->visible()` checked.** Visibility is
  UI; the closure is the guard.
- **Null-owner paths.** `$model->user_id === auth()->id()` is true when both
  are null. Compare explicitly.
- **Hidden things are 404, not 403**, when the existence itself is private
  (drafts, other tenants' records).
- **Tenant isolation**: every query in a tenant panel is scoped to the
  tenant, including option lists, relation managers and exports.

## 6. Translations

- **Base-language parity**: the fallback language has every key the others
  have, file by file `[guard]`. A key missing from the fallback renders as its
  raw name.
- Every key the front end calls exists in the catalogue.
- A key is only dead if nothing builds it dynamically (interpolated names,
  namespaced `__('file.key')`, Blade literals).

## 7. Security

- **Mutating routes are throttled** `[scan]`. Add a relaxed group-level limit
  on authenticated API groups as a backstop. Use a **named** limiter
  (`RateLimiter::for`) for it: plain `throttle:N,1` limits share one counter
  per user across every route, so nesting two counts each request twice.
- **URLs a user or a model chooses are validated**: scheme allow-list, no
  credentials, and for anything fetched, every resolved IP is public (SSRF).
  Anything put in an `href` rejects `javascript:` and `data:`.
- **Raw HTML output** (`{!! !!}`, `v-html`, `dangerouslySetInnerHTML`,
  `{@html}`) only of sanitised content `[scan]`.
- **No public source maps.** They publish every comment and the original
  source; upload them to the error tracker and delete them before deploy.
- **JSON-LD / inline JSON escapes `</script>`.**
- **CSP**: ship report-only first, then enforce. Section 2 is what makes it
  enforceable.
- **Secrets never reach a report or a log.** Shape only.

## 8. Personal data in source

Tests, seeders, factories, comments and copy are all source: cloned onto
every laptop and outside any retention rule.

- **Fixture emails** use `example.com`/`.org`/`.net`, `.test`, or `.invalid`
  (optionally `.invalid.<random>`) `[scan][guard]`. Never the company's own
  domain (it receives mail) or a registered one (`spam.com`, `x.com`).
- **Fixture phones** have a run of zeros in the subscriber part
  (`+CC NNN 0000 NN`), or use a range the country reserves for fiction
  (`555-01xx` in North America) `[scan][guard]`. A real-looking number is
  indistinguishable from someone's.
- **No national ID, IBAN or card number**, real or invented `[guard]`. An
  invented one that passes the checksum is somebody's.
- **No real person's name** in fixtures, comments or config, including the
  owner's `[scan][guard]`. Generic placeholders (`Test User`) only.
- **No real company as demo data** (a named hospital, a brand that has not
  agreed).
- **No role granted to a literal email** `[guard]`. Seeders that run on
  deploy read the address from an env var and grant nobody when it is unset.

## 9. Performance

- No query in a loop on a read path; eager-load, preload media, memoise
  per-request checks. A write path may loop.
- Counts and facets computed once per page, on the server.

## 10. Models and logging

- **Every admin-editable model is audit-logged** (e.g. spatie activitylog)
  with an explicit attribute list. Member-owned and system-written rows are
  exempt; say why in the class docblock.
- Admin actions that are not model saves (retry, refund, export) log an
  activity entry.
- Two models with the same lifecycle share a trait; a god class is split into
  concerns and its method list diffed before and after.

## 11. Verification

- **Tests run on the production database engine.** SQLite has no jsonb, no
  ICU collation, and case-insensitive LIKE.
- **A guard is proven by breaking what it guards.**
- **Front-end changes are measured**: rebuild, diff the bundles, render the
  page (SSR or browser) before and after, at the breakpoints the change
  touches.
- **SSR renders from wherever the SSR process was started.** A worktree
  served with the main checkout's SSR process shows the main checkout's
  markup.
- **Make a WIP commit before reverting to capture a baseline.** A checkout
  over uncommitted work destroys it.
- **After a merge, rebuild before running tests that read the build.**

## 12. Deploy

- Know whether deploy waits for CI. If it does not, the local suite is the
  gate: suite, pint, build.
- Size any table a type-changing migration rewrites.
- Dependency audit blocks on advisories, reports abandonment.
- After deploy: confirm the release, the migration rows, the public pages in
  each region or market, and that failed jobs have not grown.
- An audit never writes production data.
