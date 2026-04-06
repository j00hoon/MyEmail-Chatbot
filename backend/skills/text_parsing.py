import re
from html import unescape

from retrieval.email_cleaning import clean_email_body_for_embedding


class TextParsingSkill:
    max_body_chars = 12000
    _BLOCK_TAG_BREAKS = (
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "dl",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    )

    def execute(self, email):
        attachments = ", ".join(email.attachment_names) if email.attachment_names else "None"
        normalized_body = self._clean_body_text(email.body_text or "")
        cleaned_body = clean_email_body_for_embedding(normalized_body)
        cleaned_snippet = self._clean_snippet(email.snippet or "")
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

    def _clean_body_text(self, value: str):
        text = unescape(value)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"(?is)<style[^>]*>.*?</style>", "\n", text)
        text = re.sub(r"(?is)<script[^>]*>.*?</script>", "\n", text)
        text = re.sub(r"(?is)<blockquote\b[^>]*>.*?</blockquote>", "\n", text)
        text = re.sub(r"(?i)</?(%s)\b[^>]*>" % "|".join(self._BLOCK_TAG_BREAKS), "\n", text)
        text = re.sub(r"[\u200b-\u200f\ufeff]", " ", text)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n[ \t]+", "\n", text)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _clean_snippet(self, value: str):
        text = self._clean_body_text(value)
        text = re.sub(r"\s+", " ", text)
        return text.strip()
