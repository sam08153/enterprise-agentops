def chunk_text(text, chunk_size=800, overlap=100):
    chunks = []

    start = 0

    while start < len(text):
        end = start + chunk_size

        chunks.append(text[start:end])

        start += chunk_size - overlap

    return chunks


def chunk_document(document: dict, chunk_size: int = 800, overlap: int = 100) -> list[dict]:
    source = document.get("source", "")
    content = document.get("content", "")

    chunks = chunk_text(content, chunk_size=chunk_size, overlap=overlap)
    document_id = document.get("document_id") or source

    return [
        {
            "document_id": document_id,
            "source": source,
            "chunk_index": i,
            "content": chunk,
        }
        for i, chunk in enumerate(chunks)
        if chunk.strip()
    ]
