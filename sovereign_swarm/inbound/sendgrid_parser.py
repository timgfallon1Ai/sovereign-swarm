"""Parse SendGrid Inbound Parse webhook payloads.

SendGrid posts multipart/form-data with fields:
- `from` — raw RFC-2822 from header (e.g., "John Doe <john@example.com>")
- `to` — raw to header
- `subject` — email subject
- `text` — plain text body
- `html` — HTML body (optional)
- `envelope` — JSON: `{"to":[...], "from":"..."}`
- `headers` — raw headers string (includes Message-ID, In-Reply-To, References)
- `attachments` — count; files as `attachment1`, `attachment2`, ...

We extract the bits we need and normalize into InboundEmail.
"""

from __future__ import annotations

import email
import re
from dataclasses import dataclass, field
from email.utils import parseaddr
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class InboundEmail:
    """Normalized inbound email record."""
    from_email: str
    from_name: str
    to_emails: list[str]
    subject: str
    text_body: str
    html_body: str = ""
    message_id: str = ""          # unique ID from the email's Message-ID header
    in_reply_to: str = ""         # Message-ID of the email this replies to
    references: list[str] = field(default_factory=list)
    raw_headers: str = ""
    attachments_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _parse_from(from_raw: str) -> tuple[str, str]:
    """Parse 'Name <email@host>' → ('Name', 'email@host').

    Uses stdlib email.utils.parseaddr which handles RFC-2822 from headers
    correctly, including bare addresses, quoted names, and angle-bracketed
    forms.
    """
    if not from_raw:
        return "", ""
    name, email_addr = parseaddr(from_raw.strip())
    name = (name or "").strip().strip('"')
    email_addr = (email_addr or "").strip().lower()
    if not email_addr:
        # Last-resort: find any email-shaped substring
        match = _EMAIL_RE.search(from_raw)
        email_addr = match.group(0).lower() if match else ""
    return name, email_addr


def _parse_to(to_raw: str) -> list[str]:
    """Extract all email addresses from a to/cc header."""
    if not to_raw:
        return []
    return [m.group(0).lower() for m in _EMAIL_RE.finditer(to_raw)]


def _extract_header(headers: str, name: str) -> str:
    """Extract a single header value from a raw headers string."""
    if not headers:
        return ""
    try:
        msg = email.message_from_string(headers)
        val = msg.get(name) or ""
        return val.strip()
    except Exception:
        # Fallback: regex
        pat = re.compile(rf"^{re.escape(name)}:\s*(.+?)$", re.IGNORECASE | re.MULTILINE)
        match = pat.search(headers)
        return match.group(1).strip() if match else ""


def _parse_references(refs_raw: str) -> list[str]:
    """References header: space-separated Message-IDs."""
    if not refs_raw:
        return []
    return [m.strip() for m in refs_raw.split() if m.strip()]


def parse_sendgrid_webhook(payload: dict[str, Any]) -> InboundEmail:
    """Convert a SendGrid Inbound Parse payload dict → InboundEmail."""
    from_raw = payload.get("from", "")
    to_raw = payload.get("to", "")
    subject = (payload.get("subject") or "").strip()
    text_body = (payload.get("text") or "").strip()
    html_body = payload.get("html") or ""
    raw_headers = payload.get("headers") or ""

    from_name, from_email_addr = _parse_from(from_raw)
    to_emails = _parse_to(to_raw)

    # Thread tracking
    message_id = _extract_header(raw_headers, "Message-ID")
    in_reply_to = _extract_header(raw_headers, "In-Reply-To")
    references = _parse_references(_extract_header(raw_headers, "References"))

    # SendGrid also provides `envelope` field as JSON
    envelope = payload.get("envelope") or "{}"
    if isinstance(envelope, str):
        import json
        try:
            envelope_dict = json.loads(envelope)
        except (json.JSONDecodeError, TypeError):
            envelope_dict = {}
    else:
        envelope_dict = envelope

    attachments = int(payload.get("attachments", 0) or 0)

    inbound = InboundEmail(
        from_email=from_email_addr,
        from_name=from_name,
        to_emails=to_emails,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
        message_id=message_id,
        in_reply_to=in_reply_to,
        references=references,
        raw_headers=raw_headers,
        attachments_count=attachments,
        metadata={"envelope": envelope_dict},
    )

    logger.info(
        "inbound.parsed",
        from_email=inbound.from_email,
        subject=inbound.subject[:80],
        has_reply_to=bool(in_reply_to),
    )
    return inbound
