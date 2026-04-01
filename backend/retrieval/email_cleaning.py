from __future__ import annotations

import re


SIGNATURE_MARKERS = (
    "best regards",
    "regards",
    "kind regards",
    "thanks,",
    "thank you,",
    "sincerely",
    "warm regards",
)

FOOTER_PATTERNS = (
    r"sent from my iphone",
    r"sent from my ipad",
    r"sent from my samsung",
    r"get outlook for ios",
    r"this email and any attachments",
)

REPLY_CHAIN_PATTERNS = (
    r"^on .+ wrote:$",
    r"^from:\s.+$",
    r"^sent:\s.+$",
    r"^to:\s.+$",
    r"^subject:\s.+$",
    r"^-{2,}\s*original message\s*-{2,}$",
)


def clean_email_body_for_embedding(body_text: str) -> str:
    """
    Remove common email noise before embedding:
    - signatures
    - mobile footers
    - legal footers
    - quoted reply chains
    """
    if not body_text:
        return ""

    cleaned = body_text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _strip_reply_chain(cleaned)
    cleaned = _strip_signatures(cleaned)
    cleaned = _strip_footers(cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _strip_reply_chain(text: str) -> str:
    lines = text.split("\n")
    kept_lines: list[str] = []
    reply_patterns = [re.compile(pattern, flags=re.IGNORECASE) for pattern in REPLY_CHAIN_PATTERNS]

    for line in lines:
        normalized = line.strip()
        if any(pattern.match(normalized) for pattern in reply_patterns):
            break
        kept_lines.append(line)

    return "\n".join(kept_lines)


def _strip_signatures(text: str) -> str:
    lowered = text.lower()
    cut_positions = []

    for marker in SIGNATURE_MARKERS:
        index = lowered.find(f"\n{marker}")
        if index != -1:
            cut_positions.append(index)

    if not cut_positions:
        return text

    return text[: min(cut_positions)]


def _strip_footers(text: str) -> str:
    cleaned = text
    for pattern in FOOTER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned
