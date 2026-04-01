from openai import OpenAI

from config import settings


class AnswerGenerationSkill:
    max_source_chars = 2500
    max_total_context_chars = 8000

    def execute(self, question: str, sources: list[dict]):
        if not sources:
            return "I could not find any indexed emails that look relevant yet. Try syncing Gmail first."

        primary_source = sources[0]

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
                "Choose the single best matching email for the user's question and format the answer exactly with these labels in this order:\n"
                "Answer:\nFrom:\nDate:\nSubject:\nSummary:\nAttachment:\n\n"
                "Rules:\n"
                "- 'Answer' must be a direct 1-2 sentence answer to the user's question.\n"
                "- 'From', 'Date', and 'Subject' must come from the selected email.\n"
                "- 'Summary' must be a short plain-English summary of that selected email.\n"
                "- 'Attachment' must say either 'None' or list the attachment names.\n"
                "- If the answer is uncertain, say so clearly in 'Answer'.\n"
                "- Do not add extra headings, bullets, or commentary outside those six labels.\n\n"
                f"Question:\n{question}\n\n"
                f"Email Context:\n\n{joined_context}"
            )
            response = client.responses.create(
                model=settings.openai_chat_model,
                input=prompt,
            )
            return response.output_text.strip()

        attachment_text = ", ".join(primary_source["attachment_names"]) or "None"
        summary_lines = [
            "Answer: I found a matching email in your indexed mailbox.",
            f"From: {primary_source['sender'] or 'Unknown'}",
            f"Date: {primary_source['sent_at'] or 'Unknown'}",
            f"Subject: {primary_source['subject']}",
            f"Summary: {(primary_source['snippet'] or primary_source['document'] or 'No summary available.')[:280]}",
            f"Attachment: {attachment_text}",
        ]
        return "\n".join(summary_lines)
