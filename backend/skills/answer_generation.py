from openai import OpenAI

from config import settings


class AnswerGenerationSkill:
    max_source_chars = 2500
    max_total_context_chars = 8000

    def execute(self, question: str, sources: list[dict]):
        if not sources:
            return "I could not find any indexed emails that look relevant yet. Try syncing Gmail first."

        if settings.openai_api_key:
            client = OpenAI(api_key=settings.openai_api_key)
            context_blocks = []
            total_context_chars = 0
            for index, source in enumerate(sources, start=1):
                trimmed_document = (source["document"] or "")[: self.max_source_chars]
                block = "\n".join(
                    [
                        f"Source {index}",
                        f"Subject: {source['subject']}",
                        f"From: {source['sender'] or 'Unknown'}",
                        f"Sent At: {source['sent_at'] or 'Unknown'}",
                        f"Attachments: {', '.join(source['attachment_names']) or 'None'}",
                        f"Content: {trimmed_document}",
                    ]
                )
                if total_context_chars + len(block) > self.max_total_context_chars:
                    break
                context_blocks.append(block)
                total_context_chars += len(block)

            joined_context = "\n\n".join(context_blocks)
            prompt = (
                "You are a personal Gmail assistant. Answer only from the provided email context. "
                "When the user is looking for emails about a company, topic, sender, or keyword, explicitly name the matching emails first. "
                "If relevant, summarize the subject, sender, and why each email matches. "
                "If the answer is uncertain, say so clearly.\n\n"
                f"Question:\n{question}\n\n"
                f"Email Context:\n\n{joined_context}"
            )
            response = client.responses.create(
                model=settings.openai_chat_model,
                input=prompt,
            )
            return response.output_text.strip()

        summary_lines = [
            "OpenAI API key is not configured, so this is a local retrieval-only summary.",
            f"Question: {question}",
            "",
            "Most relevant emails:",
        ]
        for source in sources:
            summary_lines.append(
                f"- {source['subject']} | from {source['sender'] or 'Unknown'} | {source['snippet'] or 'No snippet'}"
            )
        return "\n".join(summary_lines)
