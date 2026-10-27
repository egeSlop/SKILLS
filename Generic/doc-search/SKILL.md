---
name: doc-search
description: Search any project's documentation by meaning with a local embedding model (EmbeddingGemma 2 on llama.cpp, in Docker or Podman, natively with Metal on macOS). Indexes Markdown and text docs and, on request, the code's doc comments (PHPDoc, rustdoc, C# XML docs, JSDoc/TSDoc, Javadoc, Go, Python docstrings). Use when starting a task, to find every part of the docs, specs and ADRs the task touches, and whenever you need to know where something is described or decided.
---

# Doc search

Ranks a project's documentation against a question by meaning, so it finds sections written in other words than yours: a spec that says "customer" where you would say "user", or one feature described in several places. Everything runs locally; nothing leaves the machine.

`<skill>` below is this skill's directory. Run the script from inside the project; it finds the root through git.

## Workflow

1. **Find the docs.** Read the project's agent instructions (`AGENTS.md`, `CLAUDE.md`) and its README, then list what documentation exists: `docs/`, specs, ADRs, any Markdown or text file. When a document has a table of contents, read it first and pick the sections the task touches.
2. **Thin or no docs: use the code's doc comments.** `--code` indexes doc comments with the declaration each one documents: PHPDoc, JSDoc and TSDoc, Javadoc and KDoc, rustdoc (`///`, `//!`), C# XML docs (`///`), Go doc comments and Python docstrings. This needs no doc generator or toolchain. If the project already generates Markdown docs (typedoc-plugin-markdown, cargo-readme and the like), include that output folder too.
3. **Embed first.**
   ```sh
   <skill>/scripts/search index                    # every Markdown and text file in the project
   <skill>/scripts/search index docs src --code    # only these paths, doc comments included
   ```
   A progress bar shows the embedding. Every section is cached, so later runs embed only what changed. The paths and `--code` given to `index` become the scope of later searches.
4. **Search** with two or three phrasings, in the project's words and in yours:
   ```sh
   <skill>/scripts/search "how a user resets a forgotten password"
   <skill>/scripts/search "password reset" --in docs/auth --top 12
   ```
   A search first embeds any section that changed since the last run.
5. **Read every hit** you have not read yet, at the line range it prints. A hit is a pointer, not an answer.

## Reading the results

```
0.812  docs/architecture/auth.md:42-61
       Authentication › Sessions › Expiry
       Sessions expire after 30 minutes without activity, and refresh tokens rotate on every use...
```

Score (cosine similarity), file and line range, the section's headings or the documented declaration, then the first words. Compare scores within one search, not across searches.

## Commands

| Command | Does |
|---|---|
| `search index [PATH...] [--code]` | Embed the docs under the paths (default: the whole project) and set them as the scope |
| `search "QUERY" [--top N] [--in PATH]` | Rank the scope against the query; `--in` keeps one folder |
| `search status` | Project, scope, backend and whether the server runs, with where its log is |
| `search stop` | Stop the embedding server, which otherwise stays up between searches |

## How it runs

- It needs Docker or Podman. The search itself runs in a pinned `oven/bun` image with the project mounted read-only.
- llama.cpp runs in a container with CUDA (NVIDIA), ROCm (AMD, x86-64) or Vulkan (`/dev/dri`) when the host has that GPU, and on the CPU otherwise. On macOS, containers cannot reach the GPU, so the official llama.cpp build runs natively with Metal.
- The first run downloads the model (176 MB) and, on macOS, llama.cpp (16 MB) into `~/.cache/doc-search`, each checked against a pinned SHA-256. The container images are pinned by digest. Each project's index lives in the same cache, never in the project.
- `DOC_SEARCH_BACKEND=native|cpu|cuda|rocm|vulkan` forces a backend, `DOC_SEARCH_ENGINE=docker|podman` an engine, `DOC_SEARCH_PORT` the native server's port (8091). A GPU container that fails to start falls back to the CPU.
- Stuck on "Waiting for llama.cpp": `search status` names the log.
- To have it in every project, copy this directory to `~/.claude/skills/doc-search`.
