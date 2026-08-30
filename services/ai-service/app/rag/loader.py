from pathlib import Path


def load_documents(directory):
    documents = []

    for path in Path(directory).rglob("*.md"):
        content = path.read_text(encoding="utf-8", errors="ignore")

        documents.append(
            {
                "source": str(path),
                "content": content,
            }
        )

    return documents
