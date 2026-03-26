class TextChunkingSkill:
    chunk_size = 1200
    overlap = 180

    def execute(self, text: str):
        normalized = (text or "").strip()
        if not normalized:
            return []

        chunks = []
        start = 0
        text_length = len(normalized)

        while start < text_length:
            end = min(text_length, start + self.chunk_size)
            chunk = normalized[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= text_length:
                break
            start = max(end - self.overlap, start + 1)

        return chunks
