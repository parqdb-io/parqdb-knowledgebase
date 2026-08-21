# ParqDB Knowledgebase

Turn a directory of documents into a static, serverless vector-search knowledge
base. ParqDB Knowledgebase chunks source documents, embeds every chunk with the
same pinned model used by the browser, builds an IVF-LVQ8 ParqDB index, and
produces a site that can be deployed to GitHub Pages.

```text
documents → token-aware chunks → MiniLM embeddings → ParqDB IVF-LVQ8
                                                        ↓
browser ← HTTP Range ← GitHub Pages, R2, or S3 ← Parquet source + index
```

No query server receives the question or searches the data.

## Quick start

Create a repository from this GitHub template, replace the Markdown under
`docs/`, choose an explicit `--nlist` in `.github/workflows/pages.yml`, and
push `main`. The included Action builds and deploys the complete GitHub Pages
site.

For a local data build:

```bash
python -m pip install -e .
parqdb-kb build docs \
  --base-url https://USER.github.io/REPOSITORY \
  --nlist 256
```

The command writes transient text and embedding inputs below `.parqdb-kb/`,
but publishes only the compact lookup relation, IVF-LVQ8 index, pinned browser
model, and rendered document pages. Vite writes the final site to `_site/`.

## Published rows

The source Parquet file contains one row per chunk:

| Column | Type | Purpose |
| --- | --- | --- |
| `chunk_id` | non-null `int64` | Dense index key and direct source lookup |
| `doc_id` | non-null `int64` | Groups chunks from the same source document |
| `title` | non-null `string` | Result title |
| `section` | non-null `string` | Section containing the chunk |
| `url` | non-null `string` | Result destination |
| `text` | build-only `string` | Embedded during the build; not published |

`chunk_id` is assigned deterministically from sorted document paths and source
order. Chunk boundaries are computed with the embedding model tokenizer, not
character counts. The published lookup table contains only `chunk_id`,
`doc_id`, `title`, `section`, and `url`; results link to the original document
instead of duplicating its text in object storage.

## Repository boundary

This repository owns document ingestion, chunking, embedding orchestration,
the search UI, and GitHub Actions deployment. The
[`parqdb`](https://github.com/parqdb-io/parqdb) repository owns the index
format, IVF-LVQ build, static publication, HTTP Range client, and WASM kernels.

## Status

Early development. The first release targets public GitHub Pages and public
S3-compatible storage, Markdown input, MiniLM, and IVF-LVQ8.
