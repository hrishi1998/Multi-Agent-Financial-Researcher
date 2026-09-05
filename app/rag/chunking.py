import re
from typing import List
from uuid import uuid4

from app.rag.schemas import DocumentChunk, DocumentMetadata

_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")


def _is_table_line(line: str) -> bool:
    if _TABLE_ROW.match(line):
        return True
    return line.count("\t") >= 2


def _split_table_on_rows(block: str, max_chars: int) -> List[str]:
    rows = block.splitlines(keepends=True)
    pieces: List[str] = []
    current = ""
    for row in rows:
        if current and len(current) + len(row) > max_chars:
            pieces.append(current)
            current = row
        else:
            current += row
    if current.strip():
        pieces.append(current)
    return pieces


def chunk_document(
    text: str,
    metadata: DocumentMetadata,
    max_chars: int = 1200,
) -> List[DocumentChunk]:
    """Split text while keeping markdown/TSV financial tables on row boundaries."""
    blocks: List[str] = []
    buffer: List[str] = []
    in_table = False

    for line in text.splitlines(keepends=True):
        table_line = _is_table_line(line)
        if table_line:
            if not in_table and buffer:
                blocks.append("".join(buffer))
                buffer = []
            in_table = True
            buffer.append(line)
            continue
        if in_table:
            blocks.append("".join(buffer))
            buffer = [line]
            in_table = False
            continue
        buffer.append(line)
        joined = "".join(buffer)
        if line.strip() == "" and len(joined) >= max_chars:
            blocks.append(joined)
            buffer = []
    if buffer:
        blocks.append("".join(buffer))

    segments: List[str] = []
    current = ""
    for block in blocks:
        table_block = any(_is_table_line(line) for line in block.splitlines())
        if table_block and len(block) > max_chars:
            if current.strip():
                segments.append(current)
                current = ""
            segments.extend(_split_table_on_rows(block, max_chars))
            continue
        if current and len(current) + len(block) > max_chars:
            segments.append(current)
            current = block
        else:
            current += block
    if current.strip():
        segments.append(current)

    return [
        DocumentChunk(chunk_id=str(uuid4()), content=segment.strip(), metadata=metadata)
        for segment in segments
        if segment.strip()
    ]
