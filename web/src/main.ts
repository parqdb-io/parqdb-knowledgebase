import { env, pipeline } from '@huggingface/transformers'
import { parquetMetadataAsync, parquetReadObjects } from 'hyparquet'
import { compressors } from 'hyparquet-compressors'

import { ParqDB } from '@parqdb/index'
import { HttpRangeBuffer } from '@parqdb/http'

import './style.css'

interface SourceManifest {
  rows: number
  'row-group-rows': number
  object: { path: string; size: number }
}

interface ResultRow {
  chunk_id: number
  doc_id: number
  title: string
  section: string
  url: string
  _distance: number
}

const dataRoot = new URL('./data/', location.href)
const status = document.querySelector<HTMLDivElement>('#status')!
const button = document.querySelector<HTMLButtonElement>('#search')!
const query = document.querySelector<HTMLInputElement>('#query')!
const results = document.querySelector<HTMLElement>('#results')!

env.allowRemoteModels = true
env.allowLocalModels = false
env.remoteHost = new URL('models/', dataRoot).href
env.remotePathTemplate = '{model}/'

const ready = Promise.all([
  pipeline('feature-extraction', 'all-MiniLM-L6-v2', { model_file_name: 'model_quantized' }),
  fetch(new URL('source-manifest.json', dataRoot)).then(async response => {
    if (!response.ok) throw new Error(`source manifest: HTTP ${response.status}`)
    return response.json() as Promise<SourceManifest>
  }),
  fetch(new URL('./parqdb_browser_kernels.wasm', location.href)).then(response => response.arrayBuffer()),
]).then(async ([embedder, source, wasm]) => {
  const index = await ParqDB.open(new URL('index/manifest.json', dataRoot), { wasm })
  const file = new HttpRangeBuffer(new URL(source.object.path, dataRoot), source.object.size, {})
  const metadata = await parquetMetadataAsync(file)
  button.disabled = false
  status.textContent = `${source.rows.toLocaleString()} CHUNKS · READY`
  return { embedder, source, index, file, metadata }
})

ready.catch(error => {
  status.textContent = `BOOT FAILED · ${error instanceof Error ? error.message : String(error)}`
})

document.querySelector<HTMLFormElement>('#search-form')!.addEventListener('submit', async event => {
  event.preventDefault()
  const text = query.value.trim()
  if (!text) return
  button.disabled = true
  status.textContent = 'EMBEDDING + SEARCHING IN THIS TAB…'
  try {
    const runtime = await ready
    const output = await runtime.embedder(text, { pooling: 'mean', normalize: true })
    const hits = await runtime.index.search(Float32Array.from(output.data), {
      nprobe: Math.min(64, runtime.index.manifest.index.nlist),
      k: 10,
      maxConcurrentReads: 16,
    })
    const rows = await lookup(runtime, hits.map(hit => Number(hit.chunk_id)))
    const distances = new Map(hits.map(hit => [Number(hit.chunk_id), Number(hit._distance)]))
    render(rows.map(row => ({ ...row, _distance: distances.get(row.chunk_id) ?? 0 })))
    status.textContent = `${rows.length} RESULTS · QUERY COMPLETE`
  } catch (error) {
    status.textContent = `QUERY FAILED · ${error instanceof Error ? error.message : String(error)}`
  } finally {
    button.disabled = false
  }
})

async function lookup(
  runtime: Awaited<typeof ready>,
  ids: number[],
): Promise<Omit<ResultRow, '_distance'>[]> {
  const wanted = new Set(ids)
  const groups = [...new Set(ids.map(id => Math.floor(id / runtime.source['row-group-rows'])))]
  const starts: number[] = []
  let row = 0
  for (const group of runtime.metadata.row_groups) {
    starts.push(row)
    row += Number(group.num_rows)
  }
  const found = new Map<number, Omit<ResultRow, '_distance'>>()
  await Promise.all(groups.map(async group => {
    const rows = await parquetReadObjects({
      file: runtime.file,
      metadata: runtime.metadata,
      compressors,
      columns: ['chunk_id', 'doc_id', 'title', 'section', 'url'],
      rowStart: starts[group],
      rowEnd: starts[group] + Number(runtime.metadata.row_groups[group]!.num_rows),
    })
    for (const value of rows) {
      const id = Number(value.chunk_id)
      if (wanted.has(id)) found.set(id, value as unknown as Omit<ResultRow, '_distance'>)
    }
  }))
  return ids.flatMap(id => found.has(id) ? [found.get(id)!] : [])
}

function render(rows: ResultRow[]): void {
  results.replaceChildren(...rows.map((row, rank) => {
    const article = document.createElement('article')
    const link = document.createElement('a')
    link.href = row.url
    link.textContent = row.title
    const meta = document.createElement('p')
    meta.textContent = `${String(rank + 1).padStart(2, '0')} · ${row.section} · distance ${row._distance.toFixed(4)}`
    article.append(link, meta)
    return article
  }))
}
