"""Command-line interface for ParqDB Knowledgebase."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from transformers import AutoTokenizer

from .content import markdown_chunks, render_documents, write_chunks, write_lookup

_MODEL = "Xenova/all-MiniLM-L6-v2"
_REVISION = "751bff37182d3f1213fa05d7196b954e230abad9"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="parqdb-kb")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="chunk Markdown into documents.parquet")
    prepare.add_argument("roots", nargs="+", type=Path)
    prepare.add_argument("--base-url", required=True)
    prepare.add_argument("--output", type=Path, default=Path(".parqdb-kb/documents.parquet"))
    prepare.add_argument("--chunk-tokens", type=int, default=180)
    prepare.add_argument("--overlap-tokens", type=int, default=24)
    build = commands.add_parser("build", help="build source data and a static IVF-LVQ8 index")
    build.add_argument("roots", nargs="+", type=Path)
    build.add_argument("--base-url", required=True)
    build.add_argument("--site-data", type=Path, default=Path("web/public/data"))
    build.add_argument("--work", type=Path, default=Path(".parqdb-kb"))
    build.add_argument("--chunk-tokens", type=int, default=180)
    build.add_argument("--overlap-tokens", type=int, default=24)
    build.add_argument("--nlist", type=int, required=True)
    build.add_argument("--threads", type=int, default=8)
    arguments = parser.parse_args(argv)
    if arguments.command in {"prepare", "build"}:
        tokenizer = AutoTokenizer.from_pretrained(_MODEL, revision=_REVISION)
        chunks = markdown_chunks(
            arguments.roots,
            tokenizer,
            base_url=arguments.base_url,
            chunk_tokens=arguments.chunk_tokens,
            overlap_tokens=arguments.overlap_tokens,
        )
        output = arguments.output if arguments.command == "prepare" else arguments.work / "documents.parquet"
        write_chunks(output, chunks)
        if arguments.command == "prepare":
            print(json.dumps({"output": str(output.resolve()), "chunks": len(chunks)}))
            return 0
        if arguments.nlist > len(chunks):
            parser.error(f"--nlist cannot exceed the {len(chunks)} generated chunks")
        from parqdb.publish import (  # pyright: ignore[reportMissingImports]
            build_index,
            publish,
        )

        built = build_index(
            source=output,
            source_key="chunk_id",
            work=arguments.work / "index-build",
            nlist=arguments.nlist,
            encoding="lvq8",
            metric="cosine",
            threads=arguments.threads,
            text_columns=("title", "section", "text"),
        )
        lookup = arguments.work / "lookup.parquet"
        write_lookup(lookup, chunks)
        render_documents(arguments.roots, arguments.site_data.parent)
        result = publish(
            index_manifest=built.manifest,
            source=lookup,
            source_key="chunk_id",
            destination=str(arguments.site_data),
            assets=built.model_assets,
        )
        print(
            json.dumps(
                {
                    "chunks": len(chunks),
                    "destination": result.destination,
                    "files": result.files,
                    "bytes": result.bytes,
                }
            )
        )
        return 0
    raise AssertionError("argparse accepted an unsupported command")


if __name__ == "__main__":
    raise SystemExit(main())
