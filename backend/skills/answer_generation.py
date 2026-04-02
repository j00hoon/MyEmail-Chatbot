from openai import OpenAI

from config import settings


class AnswerGenerationSkill:
    max_source_chars = 2500
    max_total_context_chars = 8000
    multi_email_source_chars = 550
    multi_email_total_context_chars = 16000

    def execute(self, question: str, sources: list[dict], answer_mode: str = "single_email"):
        if not sources:
            return "I could not find any indexed emails that look relevant yet. Try syncing Gmail first."

        primary_source = sources[0]

        if answer_mode == "multi_email" and self._is_sender_list_request(question):
            return self._format_sender_list_answer(question=question, sources=sources)

        if settings.openai_api_key:
            client = OpenAI(api_key=settings.openai_api_key)
            context_blocks = []
            total_context_chars = 0
            per_source_chars = (
                self.multi_email_source_chars
                if answer_mode == "multi_email"
                else self.max_source_chars
            )
            max_total_chars = (
                self.multi_email_total_context_chars
                if answer_mode == "multi_email"
                else self.max_total_context_chars
            )
            for index, source in enumerate(sources, start=1):
                content_source = (
                    source["snippet"]
                    if answer_mode == "multi_email" and source.get("snippet")
                    else source["document"]
                ) or source["document"] or source["snippet"] or ""
                trimmed_document = content_source[:per_source_chars]
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
                if total_context_chars + len(block) > max_total_chars:
                    break
                context_blocks.append(block)
                total_context_chars += len(block)

            joined_context = "\n\n".join(context_blocks)
            prompt = self._prompt_for_mode(question=question, joined_context=joined_context, answer_mode=answer_mode)
            response = client.responses.create(
                model=settings.openai_chat_model,
                input=prompt,
            )
            return response.output_text.strip()

        if answer_mode == "multi_email":
            return self._fallback_multi_email_answer(question=question, sources=sources)

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

    def _prompt_for_mode(self, question: str, joined_context: str, answer_mode: str):
        if answer_mode == "multi_email":
            return (
                "You are a personal Gmail assistant. Answer only from the provided email context. "
                "The user asked for multiple emails, so return a compact ranked list.\n\n"
                "Format exactly like this:\n"
                "Answer:\n"
                "Email 1\nFrom:\nDate:\nSubject:\nSummary:\nAttachment:\n"
                "Email 2\nFrom:\nDate:\nSubject:\nSummary:\nAttachment:\n"
                "Continue only for the matching emails you actually found.\n\n"
                "Rules:\n"
                "- 'Answer' should summarize what these emails represent overall.\n"
                "- Each email block must keep the exact labels shown above.\n"
                "- 'Attachment' must say either 'None' or list attachment names.\n"
                "- If multiple sources are provided, use them all in order unless you truly received fewer sources.\n"
                "- Do not add bullets or commentary outside this structure.\n\n"
                f"Question:\n{question}\n\n"
                f"Email Context:\n\n{joined_context}"
            )

        return (
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

    def _fallback_multi_email_answer(self, question: str, sources: list[dict]):
        lines = [
            f"Answer: I found {len(sources)} matching emails for your request.",
        ]
        for index, source in enumerate(sources, start=1):
            attachment_text = ", ".join(source["attachment_names"]) or "None"
            lines.extend(
                [
                    f"Email {index}",
                    f"From: {source['sender'] or 'Unknown'}",
                    f"Date: {source['sent_at'] or 'Unknown'}",
                    f"Subject: {source['subject']}",
                    f"Summary: {(source['snippet'] or source['document'] or 'No summary available.')[:220]}",
                    f"Attachment: {attachment_text}",
                ]
            )
        return "\n".join(lines)

    def _is_sender_list_request(self, question: str):
        lowered = question.lower()
        return (
            ("sender" in lowered or "who sent" in lowered or "from whom" in lowered)
            and any(term in lowered for term in ("latest", "recent", "newest", "last"))
        )

    def _format_sender_list_answer(self, question: str, sources: list[dict]):
        lines = [
            f"Answer: Here are the sender names for the latest {len(sources)} emails that matched your filter.",
        ]
        for index, source in enumerate(sources, start=1):
            attachment_text = ", ".join(source["attachment_names"]) or "None"
            lines.extend(
                [
                    f"Email {index}",
                    f"From: {source['sender'] or 'Unknown'}",
                    f"Date: {source['sent_at'] or 'Unknown'}",
                    f"Subject: {source['subject']}",
                    f"Summary: {(source['snippet'] or source['document'] or 'No summary available.')[:180]}",
                    f"Attachment: {attachment_text}",
                ]
            )
        return "\n".join(lines)
