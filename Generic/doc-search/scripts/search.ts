// Run through ./search, which starts llama.cpp, mounts the project at /work and the cache at /cache.
import { createHash } from "node:crypto"
import { extname } from "node:path"

type Chunk = {
  file: string
  start: number
  end: number
  title: string
  text: string
}
type Heading = { level: number; text: string }

const model = "embeddinggemma-2-UD-Q4_K_XL"
const indexPath = "/cache/index.json"
const prose = new Set([".md", ".mdx", ".markdown", ".rst", ".adoc", ".txt"])
const code = new Set([
  ".php",
  ".rs",
  ".cs",
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".mjs",
  ".java",
  ".kt",
  ".swift",
  ".go",
  ".py",
])
const windowChars = 1800
const batchSize = 16

function headingOf(line: string): Heading | null {
  const markdown = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line)
  if (markdown) return { level: markdown[1].length, text: markdown[2] }
  const bold = /^\*\*([^*].*?)\*\*:?\s*$/.exec(line.trim())
  return bold ? { level: 7, text: bold[1] } : null
}

function isContentsList(lines: string[]): boolean {
  const items = lines.filter((l) => l.trim())
  const links = items.filter((l) =>
    /^\s*[-*+]\s+\[[^\]]+\]\([^)]+\)\s*$/.test(l)
  )
  return links.length >= 5 && links.length / items.length > 0.7
}

function proseChunks(file: string, source: string): Chunk[] {
  const lines = source.split("\n")
  const out: Chunk[] = []
  const trail: Heading[] = []
  let sectionStart = 0
  let fenced = false

  const flush = (end: number) => {
    const section = lines.slice(sectionStart, end)
    if (isContentsList(section)) return
    const title =
      trail
        .slice(-3)
        .map((h) => h.text)
        .join(" › ") || file
    let start = sectionStart
    let body: string[] = []
    const emit = (last: number) => {
      const text = body.join("\n").trim()
      if (text.length >= 40) {
        out.push({ file, start: start + 1, end: last + 1, title, text })
      }
      body = []
      start = last + 1
    }
    for (let i = sectionStart; i < end; i++) {
      if (i > sectionStart || !headingOf(lines[i])) body.push(lines[i])
      if (body.join("\n").length >= windowChars) emit(i)
    }
    if (body.length) emit(end - 1)
  }

  lines.forEach((line, i) => {
    if (line.trimStart().startsWith("```")) fenced = !fenced
    const heading = fenced ? null : headingOf(line)
    if (!heading) return
    flush(i)
    while (trail.length && trail.at(-1)!.level >= heading.level) trail.pop()
    trail.push(heading)
    sectionStart = i
  })
  flush(lines.length)
  return out
}

const owner =
  /^\s*(?:export\s+)?(?:(?:pub(?:\([^)]*\))?|public|internal|abstract|final|sealed|static|partial|readonly|default)\s+)*(?:class|interface|trait|enum|struct|impl|mod|namespace|record|object)\s+([A-Za-z_]\w*)/
const annotation = /^\s*(?:#\[|\[[A-Z]|@[A-Za-z])/
const goDeclaration = /^(?:func|type|var|const|package)\b/

function cleanDoc(lines: string[]): string {
  return lines
    .map((l) =>
      l
        .replace(/^\s*\/\*\*?/, "")
        .replace(/\*\/\s*$/, "")
        .replace(/^\s*\/\/[/!]?\s?/, "")
        .replace(/^\s*\*\s?/, "")
    )
    .join("\n")
    .replace(/<param name="([^"]+)">/g, "$1: ")
    .replace(/<see cref="([^"]+)"\s*\/>/g, "$1")
    .replace(/<\/?[a-z]+[^>]*>/g, "")
    .trim()
}

// Doc comments (PHPDoc, JSDoc/TSDoc, Javadoc, rustdoc, C# XML docs, Go doc comments,
// Python docstrings), each with the declaration it documents.
function codeChunks(file: string, source: string): Chunk[] {
  const lines = source.split("\n")
  const ext = extname(file)
  const out: Chunk[] = []
  let currentOwner = ""

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    let docStart = i
    let docEnd = -1
    let declarationLine = -1

    if (/^\s*\/\*\*(?!\/)/.test(line)) {
      docEnd = i
      while (docEnd < lines.length - 1 && !lines[docEnd].includes("*/"))
        docEnd++
    } else if (ext !== ".go" && /^\s*\/\/[/!](?!\s*<reference)/.test(line)) {
      docEnd = i
      while (/^\s*\/\/[/!]/.test(lines[docEnd + 1] ?? "")) docEnd++
    } else if (ext === ".go" && /^\/\/ /.test(line)) {
      docEnd = i
      while (/^\/\//.test(lines[docEnd + 1] ?? "")) docEnd++
      if (!goDeclaration.test(lines[docEnd + 1] ?? "")) {
        i = docEnd
        continue
      }
    } else if (ext === ".py" && /^\s*(?:async\s+)?(?:def|class)\s/.test(line)) {
      let open = i + 1
      while (open < lines.length && !lines[open].trim()) open++
      const quote = /^\s*[rRuU]?("""|''')/.exec(lines[open] ?? "")?.[1]
      if (quote) {
        docStart = open
        docEnd = open
        const rest = lines[open].trim().slice(quote.length + 1)
        if (!rest.includes(quote)) {
          docEnd++
          while (docEnd < lines.length && !lines[docEnd].includes(quote))
            docEnd++
        }
        declarationLine = i
      }
    }

    const ownerMatch = owner.exec(line)
    if (ownerMatch && docEnd < 0) currentOwner = ownerMatch[1]
    if (docEnd < 0) continue

    if (declarationLine < 0) {
      declarationLine = docEnd + 1
      while (
        declarationLine < lines.length &&
        (!lines[declarationLine].trim() ||
          annotation.test(lines[declarationLine]))
      ) {
        declarationLine++
      }
    }
    const declaration = (lines[declarationLine] ?? "").trim().slice(0, 160)
    const text = cleanDoc(
      lines
        .slice(docStart, docEnd + 1)
        .map((l) => l.replace(/^\s*[rRuU]?("""|''')|("""|''')\s*$/g, ""))
    )
    const declaredOwner = owner.exec(declaration)?.[1]
    if (text.length >= 30) {
      const title = declaredOwner
        ? declaration
        : [currentOwner, declaration].filter(Boolean).join(" › ")
      out.push({
        file,
        start: Math.min(docStart, declarationLine) + 1,
        end: Math.max(docEnd, declarationLine) + 1,
        title: title || file,
        text: `${text}\n${declaration}`,
      })
    }
    if (declaredOwner) currentOwner = declaredOwner
    i = Math.max(i, docEnd)
  }
  return out
}

function documentInput(c: Chunk): string {
  return `title: ${c.title} | text: ${c.text}`.slice(0, 6000)
}

function keyOf(input: string): string {
  return createHash("sha256").update(`${model}\n${input}`).digest("hex")
}

function encode(vector: number[]): string {
  return Buffer.from(new Float32Array(vector).buffer).toString("base64")
}

function decode(stored: string): Float32Array {
  return new Float32Array(new Uint8Array(Buffer.from(stored, "base64")).buffer)
}

function cosine(a: Float32Array, b: Float32Array): number {
  let dot = 0
  let na = 0
  let nb = 0
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i]
    na += a[i] * a[i]
    nb += b[i] * b[i]
  }
  return dot / (Math.sqrt(na * nb) || 1)
}

function progress(label: string, total: number) {
  const started = Date.now()
  const tty = process.stderr.isTTY
  let shown = -1
  return (done: number) => {
    const share = total ? done / total : 1
    if (!tty) {
      const step = Math.floor(share * 10)
      if (step > shown) console.error(`${label}: ${done}/${total}`)
      shown = step
      return
    }
    const width = 30
    const filled = Math.round(share * width)
    const seconds = (Date.now() - started) / 1000
    const left = done ? Math.ceil((seconds / done) * (total - done)) : 0
    const bar = "█".repeat(filled) + "░".repeat(width - filled)
    const eta = done < total && done ? `, ${left}s left` : ""
    process.stderr.write(
      `\r${label} ${bar} ${Math.round(share * 100)}% (${done}/${total}${eta})  `
    )
    if (done === total) process.stderr.write("\n")
  }
}

async function waitForServer(url: string) {
  const deadline = Date.now() + 180_000
  let told = false
  while (Date.now() < deadline) {
    const ok = await fetch(`${url}/health`)
      .then((r) => r.ok)
      .catch(() => false)
    if (ok) return
    if (!told) console.error("Waiting for llama.cpp to load the model...")
    told = true
    await Bun.sleep(500)
  }
  throw new Error(
    `No embedding server at ${url}. Check ${process.env.SEARCH_LOG ?? "its log"}.`
  )
}

async function embed(url: string, inputs: string[]): Promise<number[][]> {
  const response = await fetch(`${url}/v1/embeddings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model, input: inputs, encoding_format: "float" }),
  })
  if (!response.ok) {
    throw new Error(
      `Embedding failed: ${response.status} ${await response.text()}`
    )
  }
  const body = (await response.json()) as {
    data: { index: number; embedding: number[] }[]
  }
  return body.data.sort((a, b) => a.index - b.index).map((d) => d.embedding)
}

async function readChunks(withCode: boolean): Promise<Chunk[]> {
  const listed = (await Bun.file("/cache/files.txt").text()).split("\n")
  const chunks: Chunk[] = []
  for (const file of listed.filter(Boolean).sort()) {
    const ext = extname(file).toLowerCase()
    const isProse = prose.has(ext)
    if (!isProse && !(withCode && code.has(ext))) continue
    const source = await Bun.file(file)
      .text()
      .catch(() => "")
    chunks.push(
      ...(isProse ? proseChunks(file, source) : codeChunks(file, source))
    )
  }
  return chunks
}

async function loadIndex(): Promise<Map<string, string>> {
  const file = Bun.file(indexPath)
  if (!(await file.exists())) return new Map()
  const stored = (await file.json()) as { entries: Record<string, string> }
  return new Map(Object.entries(stored.entries))
}

async function update(url: string, chunks: Chunk[], keys: string[]) {
  const index = await loadIndex()
  const missing = chunks.filter((_, i) => !index.has(keys[i]))
  if (missing.length) {
    await waitForServer(url)
    const tick = progress("Embedding", missing.length)
    tick(0)
    for (let i = 0; i < missing.length; i += batchSize) {
      const inputs = missing.slice(i, i + batchSize).map(documentInput)
      const vectors = await embed(url, inputs)
      inputs.forEach((input, j) => index.set(keyOf(input), encode(vectors[j])))
      tick(Math.min(i + batchSize, missing.length))
    }
  }
  if (missing.length || index.size !== new Set(keys).size) {
    const entries = Object.fromEntries(keys.map((k) => [k, index.get(k)!]))
    await Bun.write(indexPath, JSON.stringify({ model, entries }))
  }
  return { index, embedded: missing.length }
}

function parseQuery(argv: string[]) {
  const words: string[] = []
  let top = 8
  let prefix = ""
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--top") top = Number(argv[++i]) || top
    else if (argv[i] === "--in") prefix = (argv[++i] ?? "").replace(/^\.\//, "")
    else words.push(argv[i])
  }
  return { query: words.join(" ").trim(), top, prefix }
}

async function main() {
  const [mode, codeFlag, ...rest] = process.argv.slice(2)
  const url = process.env.SEARCH_URL!
  const started = Date.now()
  const chunks = await readChunks(codeFlag === "--code=true")
  if (!chunks.length) {
    console.error(
      "Nothing to index: no Markdown or text docs in scope. Run `search index --code` to index doc comments."
    )
    process.exit(1)
  }
  const keys = chunks.map((c) => keyOf(documentInput(c)))
  const { index, embedded } = await update(url, chunks, keys)

  if (mode === "index") {
    const files = new Set(chunks.map((c) => c.file)).size
    const seconds = Math.round((Date.now() - started) / 1000)
    console.log(
      `Indexed ${chunks.length} sections from ${files} files (${embedded} embedded now) in ${seconds}s.`
    )
    return
  }

  const { query, top, prefix } = parseQuery(rest)
  if (!query) {
    console.error('Usage: search "QUERY" [--top 8] [--in PATH]')
    process.exit(1)
  }
  await waitForServer(url)
  const [queryVector] = await embed(url, [
    `task: search result | query: ${query}`,
  ])
  const q = new Float32Array(queryVector)
  const ranked = chunks
    .map((c, i) => ({ c, score: cosine(q, decode(index.get(keys[i])!)) }))
    .filter(({ c }) => c.file.startsWith(prefix))
    .sort((a, b) => b.score - a.score)
    .slice(0, top)

  for (const { c, score } of ranked) {
    console.log(`${score.toFixed(3)}  ${c.file}:${c.start}-${c.end}`)
    console.log(`       ${c.title}`)
    console.log(`       ${c.text.replace(/\s+/g, " ").slice(0, 160)}\n`)
  }
}

await main()
