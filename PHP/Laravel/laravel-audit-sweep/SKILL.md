---
name: laravel-audit-sweep
description: Audit a range of commits (or a whole Laravel codebase) against a fixed rulebook, fix what it finds, prove each fix, and write a report. Use when the user asks for an "audit sweep", "audit the new commits", "sweep main", or to check a Laravel/Filament/Inertia project against the house rules before a merge or deploy.
---

# Laravel audit sweep

A sweep is: pick a range, get a green baseline, scan every added line against
`RULES.md`, read the risky code by hand, fix, prove each fix by breaking it,
run everything, report. Rules live in `RULES.md` next to this file. Read it
before starting.

## 0. Ground rules

- **Work in a git worktree on a new branch** (`audit/sweep-MMDD`). Never touch
  the main checkout's working tree; someone else may have uncommitted work
  there. Never use bare `git stash`.
- **Code changes are allowed unless the user says "audit only".** If they say
  audit only, write findings to the report and change nothing.
- **Never write to a server.** No migrate, seed, cache clear, config cache,
  composer, npm, git or service restart on production unless the user
  authorises that exact action. Read-only SQL (`SELECT`, information schema).
- **Never open `.env` or credential files.** Report only the shape: which keys
  exist, which are read by nothing, which are read but unset. Redact anything
  that looks like a secret before it reaches a file.
- **Granular commits**, one finding per commit, message says what the code
  now does. No co-author trailer unless the user wants one. Don't push or
  merge without asking.
- **CI and deploy status are not the gate unless the user says so.** The local
  suite is.

## 1. Scope

```bash
git fetch origin
BASE=<last audited commit>          # ask, or find the previous sweep's report
git log --oneline $BASE..origin/main | wc -l
git diff --shortstat $BASE origin/main
git worktree add ../<repo>-audit -b audit/sweep-$(date +%m%d) origin/main
```

For a first sweep of a whole project, use the empty tree as the base:
`BASE=$(git hash-object -t tree /dev/null)`.

## 2. Baseline

Run the full suite **on the production database engine** before changing
anything, so you know which failures were already there.

- Postgres in docker: raise `max_locks_per_transaction` (1024) and
  `max_connections` (300) for parallel runs; `fsync=off` is fine for tests.
- Force `QUEUE_CONNECTION=sync` and `CACHE_STORE=array` unless a test needs
  otherwise. A redis queue with no worker silently drops queued writes.
- `php artisan test --parallel --processes=<cores>`.
- Also: `vendor/bin/pint --test`, `npm run build`.

Hash the build output (`public/build`, `bootstrap/ssr`) so later front-end
changes can be compared: `find public/build bootstrap/ssr -type f | sort | xargs sha256sum > b1.sum`.

## 3. Mechanical scan

```bash
python3 ~/.claude/skills/laravel-audit-sweep/scripts/sweep.py $BASE HEAD 40
```

It checks every **added** line against the greppable rules and prints
findings grouped by rule. Set `OWNER_NAMES="first|last|handle"` to include
the owner-name check, and `PHONE_CC=90` (or another country code) for the
phone check. Treat its output as leads: every hit is read in context before
it is fixed or dismissed.

## 4. Read by hand

The scan cannot find the expensive bugs. For every new or changed file in
these categories, read it:

1. **Authorization.** New Filament resources, pages, actions, relation
   managers; new routes and controllers; policies. Look for: a resource with
   no `canAccess`; a relationship `Select`/`CheckboxList` whose options are
   scoped but whose save is not re-checked; a `->disabled()` field that is
   still `->dehydrated()` (the browser can send any value); an action whose
   closure does not re-check what `->visible()` checked; a table
   `CreateAction` in a tenant panel (it does **not** attach the tenant, use
   `->using()`); anything scoped to "own" records that takes an id from input.
2. **Input and output.** Mutating routes without throttle; URLs from users or
   models that get fetched (SSRF) or put in `href` (`javascript:`); raw HTML
   output (`{!! !!}`, `v-html`) of anything a user typed; JSON-LD built by hand.
3. **Data.** New migrations (edited old ones, FKs without `onDelete`, `json`
   instead of `jsonb`, type changes on big tables); new models (mass
   assignment, missing audit logging for admin-editable ones, casts).
4. **Personal data.** New fixtures, seeders, factories, comments.

For each suspected bug: **write a failing test first** that performs the
attack or the broken flow through the real entry point (Livewire test,
HTTP request), then fix, then watch it pass.

## 5. Fix and prove

- Fix one finding per commit.
- **Prove every guard by breaking it**: revert the fix (or plant a bad
  value), watch the test fail, restore. A test that has never failed proves
  nothing. Delete any probe files afterwards.
- A fix that changes shared markup or CSS: rebuild, compare the build hashes
  with the baseline, and explain every difference (scope-id changes from
  editing a Vue file are expected; normalise `data-v-xxxxxxxx` before diffing).
  Render the affected page (SSR or browser) before and after.
- Client-side comment stripping: use `scripts/strip_comments.py`, then rebuild
  and confirm the minified output is identical apart from scope ids.

## 6. Verify

All of: full suite on the production engine, pint, build, and the guard
tests in `templates/` present and passing. If a guard test was missing from
the project, add it (adapt the template, prove it by breaking it).

## 7. Report

Write `temp/AUDIT-SWEEP-YYYY-MM-DD.md` (keep `temp/` gitignored):

- Scope (range, commit count, files, lines) and verification numbers.
- **Fixed**: table of commit, what was wrong in plain words, rule section.
- **Needs you**: anything that requires the owner (env vars on servers,
  content decisions, credentials).
- **Left as is, with the reason.**
- **Cleared on inspection**: leads that turned out fine, one line each, so
  the next sweep does not redo them.

If the project keeps its own rulebook (e.g. `temp/AUDIT_GUIDELINE.md`),
update it with any new rule the sweep taught, and record the new BASE.
Then ask the user whether to merge or push.

## Files in this skill

- `RULES.md`: the rulebook, sections 1 to 12.
- `scripts/sweep.py BASE [HEAD] [LIMIT]`: scans the lines added between two
  refs. Its output is leads to read, not verdicts.
- `scripts/strip_comments.py FILE...`: removes comments from CSS/JS/Vue
  while leaving strings, regexes and template literals alone.
- `templates/`: guard tests to copy into a project that lacks them. Adapt the
  namespaces, then prove each one by breaking what it guards.
  - `BaseResource.php` + `ResourceAccessFailsClosedTest.php`: every Filament
    resource in every panel fails closed.
  - `NoPersonalDataInSourceTest.php`: fixture emails and phones, national
    ID/IBAN/card numbers, the owner's name (set `OWNER`), and roles granted
    to a literal address.
  - `SuperAdminGrantTest.php`: needs `'super_admin_email' =>
    env('SUPER_ADMIN_EMAIL')` in `config/app.php` and a roles seeder that
    grants only that address.
