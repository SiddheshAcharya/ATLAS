"""Section-aware chunking.

`RecursiveCharacterTextSplitter` (the one good piece of LangChain we use, ADR-002),
1000 chars / 150 overlap from `config/scoring.yaml`. A chunk never spans two sections.
Abstracts are never chunked. Every chunk keeps `char_start`/`char_end` into the doc's
normalized `full_text` so a quote can be mapped back to the exact source span.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from langchain_text_splitters import RecursiveCharacterTextSplitter

from atlas.contracts import Chunk, ParsedDoc

_SCORING = Path("config/scoring.yaml")


@lru_cache
def _chunk_cfg() -> tuple[int, int]:
    cfg = yaml.safe_load(_SCORING.read_text(encoding="utf-8")).get("chunking", {})
    return int(cfg.get("size", 1000)), int(cfg.get("overlap", 150))


def chunk_doc(doc: ParsedDoc) -> list[Chunk]:
    size, overlap = _chunk_cfg()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size, chunk_overlap=overlap, add_start_index=True
    )
    chunks: list[Chunk] = []
    idx = 0
    for sec in doc.sections:
        if sec.name == "abstract" or len(sec.text) <= size:
            pieces = [(sec.text, 0)]
        else:
            pieces = [
                (d.page_content, int(d.metadata["start_index"]))
                for d in splitter.create_documents([sec.text])
            ]
        for text, local_start in pieces:
            start = sec.char_start + local_start
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.paper_id}::{idx}",
                    paper_id=doc.paper_id,
                    section=sec.name,
                    chunk_index=idx,
                    text=text,
                    char_start=start,
                    char_end=start + len(text),
                )
            )
            idx += 1
    return chunks
