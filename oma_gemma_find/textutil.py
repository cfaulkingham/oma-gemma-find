"""Text caps, EmbeddingGemma task prefixes, and chunking."""

DOCUMENT_PREFIX = "task: search result | text: "
QUERY_PREFIX = "task: search query | text: "
_MARKERS = ("<<passage>>", "<<end>>", "<<question>>")


def clean_text(value: str, limit: int) -> str:
    """Drop controls and prompt markers, then cap the length."""
    if not isinstance(value, str) or limit < 0:
        return ""
    text = value.replace("\x00", "")
    for marker in _MARKERS:
        text = text.replace(marker, "")
    kept = []
    for char in text:
        code = ord(char)
        if code < 32 and char not in "\n\t":
            continue
        if 0x7F <= code <= 0x9F or 0x202A <= code <= 0x202E or 0x2066 <= code <= 0x2069:
            continue
        kept.append(char)
    return "".join(kept).strip()[:limit]


def prefix_document(text: str) -> str:
    return DOCUMENT_PREFIX + clean_text(text, 4000)


def prefix_query(text: str) -> str:
    return QUERY_PREFIX + clean_text(text, 500)


def chunk_text(text: str, size: int = 1000, overlap: int = 150, limit: int = 24) -> list[str]:
    """Split text into capped overlapping pieces, preferring newlines."""
    if size < 1 or limit < 1:
        return []
    body = text.replace("\x00", "")
    chunks = []
    start = 0
    length = len(body)
    while start < length and len(chunks) < limit:
        end = min(length, start + size)
        if end < length:
            newline = body.rfind("\n", start + size // 2, end)
            if newline != -1:
                end = newline + 1
        piece = body[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return chunks
