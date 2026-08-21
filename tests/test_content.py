from pathlib import Path

import pyarrow.parquet as pq

from parqdb_knowledgebase.content import (
    markdown_chunks,
    render_documents,
    write_chunks,
    write_lookup,
)


class WordTokenizer:
    def encode(self, text: str, *, add_special_tokens: bool) -> list[int]:
        del add_special_tokens
        self.words = text.split()
        return list(range(len(self.words)))

    def decode(self, tokens: list[int], *, skip_special_tokens: bool) -> str:
        del skip_special_tokens
        return " ".join(self.words[token] for token in tokens)


def test_markdown_chunks_are_dense_and_preserve_document_identity(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "b.md").write_text("# Beta\none two three four five", encoding="utf-8")
    (docs / "a.md").write_text("# Alpha\none two\n## Details\nthree four", encoding="utf-8")

    chunks = markdown_chunks(
        [docs], WordTokenizer(), base_url="https://example.com", chunk_tokens=3, overlap_tokens=1
    )

    assert [chunk.chunk_id for chunk in chunks] == list(range(len(chunks)))
    assert chunks[0].doc_id == 0
    assert chunks[-1].doc_id == 1
    assert chunks[0].title == "Alpha"
    assert chunks[0].url == "https://example.com/a.html"

    output = tmp_path / "documents.parquet"
    write_chunks(output, chunks, row_group_rows=2)
    table = pq.read_table(output)
    assert table.schema.field("chunk_id").nullable is False
    assert table.num_rows == len(chunks)

    lookup = tmp_path / "lookup.parquet"
    write_lookup(lookup, chunks, row_group_rows=2)
    assert pq.read_schema(lookup).names == [
        "chunk_id",
        "doc_id",
        "title",
        "section",
        "url",
    ]

    rendered = tmp_path / "site"
    render_documents([docs], rendered)
    assert "<h1>Alpha</h1>" in (rendered / "a.html").read_text(encoding="utf-8")
