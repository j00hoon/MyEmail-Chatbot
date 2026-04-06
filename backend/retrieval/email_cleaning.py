from __future__ import annotations

import re


SIGNATURE_MARKERS = (
    "best,",
    "best regards",
    "best regards,",
    "regards",
    "regards,",
    "kind regards",
    "kind regards,",
    "kindly,",
    "thanks,",
    "thanks and regards,",
    "thank you,",
    "sincerely",
    "warm regards",
    "warm regards,",
)

FOOTER_PATTERNS = (
    r"sent from my iphone",
    r"sent from my ipad",
    r"sent from my samsung",
    r"get outlook for ios",
    r"this email and any attachments",
    r"this message may contain confidential",
    r"please consider the environment before printing",
    r"confidentiality notice",
)

REPLY_CHAIN_PATTERNS = (
    r"^>.*$",
    r"^on .+ wrote:$",
    r"^on .+sent:$",
    r"^from:\s.+$",
    r"^sent:\s.+$",
    r"^to:\s.+$",
    r"^cc:\s.+$",
    r"^subject:\s.+$",
    r"^-{2,}\s*original message\s*-{2,}$",
    r"^_{2,}$",
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
    cleaned = _strip_leading_quote_markers(cleaned)
    cleaned = _strip_reply_chain(cleaned)
    cleaned = _strip_signatures(cleaned)
    cleaned = _strip_footers(cleaned)
    cleaned = _strip_disclaimer_blocks(cleaned)
    cleaned = _normalize_whitespace(cleaned)
    return cleaned.strip()


def _strip_leading_quote_markers(text: str) -> str:
    cleaned_lines = []
    for line in text.split("\n"):
        cleaned_lines.append(re.sub(r"^\s*>+\s?", "", line))
    return "\n".join(cleaned_lines)


def _normalize_whitespace(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    compact_lines: list[str] = []
    previous_blank = False

    for line in lines:
        if not line:
            if not previous_blank:
                compact_lines.append("")
            previous_blank = True
            continue

        compact_lines.append(line)
        previous_blank = False

    cleaned = "\n".join(compact_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def _strip_reply_chain(text: str) -> str:
    lines = text.split("\n")
    kept_lines: list[str] = []
    reply_patterns = [re.compile(pattern, flags=re.IGNORECASE) for pattern in REPLY_CHAIN_PATTERNS]
    consecutive_header_lines = 0

    for line in lines:
        normalized = line.strip()
        if any(pattern.match(normalized) for pattern in reply_patterns):
            break

        if re.match(r"^(from|sent|to|cc|subject):\s.+$", normalized, flags=re.IGNORECASE):
            consecutive_header_lines += 1
            if consecutive_header_lines >= 2:
                break
        elif normalized:
            consecutive_header_lines = 0

        kept_lines.append(line)

    return "\n".join(kept_lines)


def _strip_signatures(text: str) -> str:
    lines = text.split("\n")

    for index, line in enumerate(lines):
        normalized = line.strip().lower()
        normalized = re.sub(r"[.!:,;\-]+$", "", normalized)
        if normalized == "--":
            return "\n".join(lines[:index])
        if normalized in SIGNATURE_MARKERS and index >= max(len(lines) // 3, 2):
            return "\n".join(lines[:index])

    return text


def _strip_footers(text: str) -> str:
    cleaned = text
    for pattern in FOOTER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned


def _strip_disclaimer_blocks(text: str) -> str:
    lines = text.split("\n")
    for index, line in enumerate(lines):
        normalized = line.strip().lower()
        if not normalized:
            continue
        if any(
            marker in normalized
            for marker in (
                "this email and any attachments",
                "this message may contain confidential",
                "confidentiality notice",
            )
        ):
            return "\n".join(lines[:index])
    return text
