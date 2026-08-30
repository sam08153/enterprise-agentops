import hashlib


class DeterministicHashEmbedding:
    def __init__(self, dim: int = 1536):
        self.dim = dim

    def embed_text(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self.dim

        floats: list[float] = []
        counter = 0

        while len(floats) < self.dim:
            digest = hashlib.sha256(f"{counter}:{text}".encode("utf-8")).digest()
            for b in digest:
                floats.append((b / 255.0) * 2.0 - 1.0)
                if len(floats) >= self.dim:
                    break
            counter += 1

        return floats

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(t) for t in texts]


def get_default_embedding_model() -> DeterministicHashEmbedding:
    return DeterministicHashEmbedding(dim=1536)
