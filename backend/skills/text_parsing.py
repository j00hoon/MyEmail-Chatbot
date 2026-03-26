import re
from html import unescape


class TextParsingSkill:
    max_body_chars = 12000

    def execute(self, email):
        attachments = ", ".join(email.attachment_names) if email.attachment_names else "None"
        cleaned_body = self._clean_text(email.body_text or "")
        cleaned_snippet = self._clean_text(email.snippet or "")
        parts = [
            f"Subject: {email.subject or 'No Subject'}",
            f"From: {email.sender or 'Unknown Sender'}",
            f"To: {email.recipients or 'Unknown Recipients'}",
            f"Sent At: {email.sent_at or 'Unknown Date'}",
            f"Attachments: {attachments}",
            f"Snippet: {cleaned_snippet}",
            f"Body: {cleaned_body[:self.max_body_chars]}",
        ]
        return "\n".join(parts).strip()

    def _clean_text(self, value: str):
        text = unescape(value)
        text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
        text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
        text = re.sub(r"[\u200b-\u200f\ufeff]", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
