"""Deterministic Markdown ingestion and tokenizer-aware chunking."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Protocol

import pyarrow as pa
import pyarrow.parquet as pq
from markdown_it import MarkdownIt

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class Tokenizer(Protocol):
    def encode(self, text: str, *, add_special_tokens: bool) -> list[int]: ...

    def decode(self, tokens: list[int], *, skip_special_tokens: bool) -> str: ...


@dataclass(frozen=True)
class Chunk:
    chunk_id: int
    doc_id: int
    title: str
    section: str
    url: str
    text: str


def markdown_chunks(
    roots: Iterable[Path],
    tokenizer: Tokenizer,
    *,
    base_url: str,
    chunk_tokens: int = 180,
    overlap_tokens: int = 24,
) -> list[Chunk]:
    """Read Markdown files in canonical path order and produce dense chunk IDs."""
    if chunk_tokens <= 0 or overlap_tokens < 0 or overlap_tokens >= chunk_tokens:
        raise ValueError("chunk token limits must satisfy 0 <= overlap < chunk")
    files = sorted(
        {path.resolve() for root in roots for path in root.resolve().rglob("*.md")}
    )
    chunks: list[Chunk] = []
    for doc_id, path in enumerate(files):
        sections = _sections(path.read_text(encoding="utf-8"), path.stem)
        title = sections[0][0]
        relative = _relative_to_any(path, roots)
        url = f"{base_url.rstrip('/')}/{relative.with_suffix('.html').as_posix()}"
        for section, body in sections:
            tokens = tokenizer.encode(body, add_special_tokens=False)
            start = 0
            while start < len(tokens):
                end = min(len(tokens), start + chunk_tokens)
                text = tokenizer.decode(tokens[start:end], skip_special_tokens=True).strip()
                if text:
                    chunks.append(Chunk(len(chunks), doc_id, title, section, url, text))
                if end == len(tokens):
                    break
                start = end - overlap_tokens
    return chunks


def write_chunks(path: Path, chunks: list[Chunk], *, row_group_rows: int = 128) -> None:
    _write_rows(path, chunks, include_text=True, row_group_rows=row_group_rows)


def write_lookup(path: Path, chunks: list[Chunk], *, row_group_rows: int = 128) -> None:
    """Write the compact browser lookup table without duplicating source text."""
    _write_rows(path, chunks, include_text=False, row_group_rows=row_group_rows)


def render_documents(roots: Iterable[Path], output: Path) -> None:
    """Render the original Markdown as link targets outside the Parquet lookup."""
    renderer = MarkdownIt("commonmark", {"html": False, "linkify": True})
    for root in roots:
        root = root.resolve()
        for source in sorted(root.rglob("*.md")):
            relative = source.relative_to(root).with_suffix(".html")
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            title = source.stem.replace("-", " ").replace("_", " ").title()
            body = renderer.render(source.read_text(encoding="utf-8"))
            destination.write_text(
                "<!doctype html><html><head><meta charset=\"utf-8\">"
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                f"<title>{escape(title)}</title>"
                "<style>body{max-width:760px;margin:48px auto;padding:0 20px;"
                "background:#070907;color:#d7ddd7;font:16px/1.7 system-ui}"
                "a{color:#7bff9e}code,pre{background:#101510}pre{padding:16px;overflow:auto}"
                "</style></head><body>"
                f"{body}</body></html>",
                encoding="utf-8",
            )


def _write_rows(
    path: Path,
    chunks: list[Chunk],
    *,
    include_text: bool,
    row_group_rows: int,
) -> None:
    if not chunks:
        raise ValueError("no document chunks were produced")
    fields = [
        pa.field("chunk_id", pa.int64(), nullable=False),
        pa.field("doc_id", pa.int64(), nullable=False),
        pa.field("title", pa.string(), nullable=False),
        pa.field("section", pa.string(), nullable=False),
        pa.field("url", pa.string(), nullable=False),
    ]
    if include_text:
        fields.append(pa.field("text", pa.string(), nullable=False))
    schema = pa.schema(fields)
    table = pa.Table.from_pylist(
        [
            {
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "title": chunk.title,
                "section": chunk.section,
                "url": chunk.url,
                **({"text": chunk.text} if include_text else {}),
            }
            for chunk in chunks
        ],
        schema=schema,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table,
        path,
        compression="zstd",
        compression_level=6,
        row_group_size=row_group_rows,
        write_page_index=True,
    )


def _sections(markdown: str, fallback_title: str) -> list[tuple[str, str]]:
    title = fallback_title.replace("-", " ").replace("_", " ").strip().title()
    heading = title
    lines: list[str] = []
    sections: list[tuple[str, str]] = []
    for line in markdown.splitlines():
        match = _HEADING.match(line)
        if match is None:
            lines.append(line)
            continue
        body = "\n".join(lines).strip()
        if body:
            sections.append((heading, body))
        heading = match.group(2).strip()
        if len(match.group(1)) == 1 and title == fallback_title.replace("-", " ").replace("_", " ").strip().title():
            title = heading
        lines = []
    body = "\n".join(lines).strip()
    if body:
        sections.append((heading, body))
    if not sections:
        sections.append((title, markdown.strip()))
    return [(title, sections[0][1]), *[(name, body) for name, body in sections[1:]]]


def _relative_to_any(path: Path, roots: Iterable[Path]) -> Path:
    for root in roots:
        try:
            return path.relative_to(root.resolve())
        except ValueError:
            continue
    raise ValueError(f"document is outside configured roots: {path}")
