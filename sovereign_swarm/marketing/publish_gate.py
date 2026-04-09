"""Publish gate — human-in-the-loop approval for marketing campaign release.

This is deliberately a stub of the approval interface rather than a
live integration with social APIs. Sovereign's operating rule is
"never publish without explicit human approval" — this module
enforces that by routing every publish attempt through a file-based
approval handshake that a human must complete externally.

Flow
----
1. ``ensemble.run()`` calls ``PublishGate.request_approval(result)``
   at the end of a successful campaign run.
2. A ``PublishRequest`` dataclass is written to
   ``<output_dir>/publish_request.json`` alongside the campaign
   manifest. It captures the tenant, campaign_id, artifacts,
   intended platforms, and a random approval token.
3. The human reviews ``final.mp4`` + ``manifest.json`` + any stills,
   then either:
     a) Writes a ``<output_dir>/approved.token`` file containing the
        matching token (approve), or
     b) Writes a ``<output_dir>/rejected.txt`` file with a reason
        (reject).
4. A separate publish worker (NOT implemented here) polls
   ``publish_request.json`` files and executes the actual post when
   it sees an ``approved.token`` next to them.

This module owns steps 1-3. Step 4 is explicitly out of scope for
this session — it's the dangerous one and needs careful per-platform
implementation with credential handling and rate-limit awareness.

``check_approval()`` is the read side: given a PublishRequest,
return the current state ("pending" / "approved" / "rejected").
"""

from __future__ import annotations

import json
import logging
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishRequest:
    tenant: str
    campaign_id: str
    artifacts: dict[str, str]
    platforms: tuple[str, ...]
    approval_token: str
    requested_at: str
    owner: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant": self.tenant,
            "campaign_id": self.campaign_id,
            "artifacts": dict(self.artifacts),
            "platforms": list(self.platforms),
            "approval_token": self.approval_token,
            "requested_at": self.requested_at,
            "owner": self.owner,
            "notes": self.notes,
        }


@dataclass
class PublishApprovalState:
    state: str  # "pending" | "approved" | "rejected"
    approved_token: Optional[str] = None
    rejection_reason: Optional[str] = None
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class PublishGate:
    """File-based approval gate for marketing campaign publishing."""

    REQUEST_FILENAME = "publish_request.json"
    APPROVED_FILENAME = "approved.token"
    REJECTED_FILENAME = "rejected.txt"

    def request_approval(
        self,
        output_dir: Path,
        tenant: str,
        campaign_id: str,
        artifacts: dict[str, str],
        platforms: Iterable[str] = (),
        owner: str = "",
        notes: str = "",
    ) -> PublishRequest:
        """Write a publish_request.json into the campaign output directory.

        This does NOT block or poll for approval. It simply stages
        the request on disk. Call ``check_approval`` (possibly from
        a separate process / cron) to find out whether a human has
        approved or rejected it.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        # If a request already exists (replay of ensemble.run), preserve
        # the existing token so approvals aren't invalidated on re-run.
        existing_path = output_dir / self.REQUEST_FILENAME
        if existing_path.exists():
            try:
                prev = json.loads(existing_path.read_text())
                token = prev.get("approval_token") or secrets.token_urlsafe(32)
                requested_at = prev.get("requested_at") or datetime.now(
                    timezone.utc
                ).isoformat()
            except Exception:  # noqa: BLE001
                token = secrets.token_urlsafe(32)
                requested_at = datetime.now(timezone.utc).isoformat()
        else:
            token = secrets.token_urlsafe(32)
            requested_at = datetime.now(timezone.utc).isoformat()

        req = PublishRequest(
            tenant=tenant,
            campaign_id=campaign_id,
            artifacts=dict(artifacts),
            platforms=tuple(platforms),
            approval_token=token,
            requested_at=requested_at,
            owner=owner,
            notes=notes,
        )
        existing_path.write_text(json.dumps(req.to_dict(), indent=2))

        # Also write a human-readable approval instructions file
        instructions = output_dir / "APPROVAL_INSTRUCTIONS.md"
        instructions.write_text(
            "# Publishing approval\n\n"
            f"Campaign: **{req.tenant}** / **{req.campaign_id}**\n\n"
            f"Requested at: {req.requested_at}\n"
            f"Platforms: {', '.join(req.platforms) or '(unspecified)'}\n\n"
            "## Artifacts\n\n"
            + "\n".join(
                f"- **{name}**: `{path}`" for name, path in req.artifacts.items()
            )
            + "\n\n"
            "## To approve\n\n"
            "Write the approval token to `approved.token` in this directory:\n\n"
            f"```bash\necho '{req.approval_token}' > "
            f"'{output_dir / self.APPROVED_FILENAME}'\n```\n\n"
            "## To reject\n\n"
            "Write a reason to `rejected.txt` in this directory:\n\n"
            f"```bash\necho 'reason here' > "
            f"'{output_dir / self.REJECTED_FILENAME}'\n```\n"
        )
        return req

    def check_approval(
        self, output_dir: Path, request: PublishRequest
    ) -> PublishApprovalState:
        """Read approval state from disk. Does not block."""
        rejected_path = output_dir / self.REJECTED_FILENAME
        if rejected_path.exists():
            return PublishApprovalState(
                state="rejected",
                rejection_reason=rejected_path.read_text().strip() or "no reason provided",
            )
        approved_path = output_dir / self.APPROVED_FILENAME
        if approved_path.exists():
            token_on_disk = approved_path.read_text().strip()
            if token_on_disk == request.approval_token:
                return PublishApprovalState(
                    state="approved",
                    approved_token=token_on_disk,
                )
            # Mismatched token counts as rejection — probably a stale file
            return PublishApprovalState(
                state="rejected",
                rejection_reason=(
                    "approval token mismatch — "
                    f"disk has {token_on_disk!r}, request expected "
                    f"{request.approval_token!r}"
                ),
            )
        return PublishApprovalState(state="pending")
