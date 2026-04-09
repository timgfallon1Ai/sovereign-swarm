"""Claude-backed script generation for the marketing ensemble.

Takes a structured ``CampaignBrief`` + a ``TenantBrand`` and produces
the two text payloads the rest of the pipeline needs:

  - ``narration_text``  — spoken line the VibeVoice speaker will read
  - ``video_prompt``    — prompt handed to Wan 2.2 for motion video
  - ``still_prompts``   — prompts for FLUX still-image generation (0..N)
  - ``captions``        — optional word-level caption hints for Remotion

The generator calls ``AsyncAnthropic.messages.create`` with a strict
JSON-output contract. If anything in the round-trip fails (no API
key, timeout, parse failure, schema validation), the caller receives
a ``ScriptResult`` with ``status != "success"`` and a populated
``error`` field — nothing raises. Same fail-open posture as the
Claude shadow sleeve in ATS.

The Claude client is injected at construction time so tests can swap
in a stub and avoid live API calls.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from sovereign_swarm.marketing.brand import TenantBrand
from sovereign_swarm.marketing.brief import CampaignBrief

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are the scriptwriter for the Sovereign marketing
ensemble — a local-only AI production pipeline that produces short
marketing videos from a structured brief.

Your job on each call is to turn one CampaignBrief + one TenantBrand
into a complete production package that downstream stages can render
without any further clarification. You must:

1. Write a narration script that fits the requested duration at
   roughly 145-160 words per minute for VibeVoice TTS.
2. Write a motion-video prompt for Wan 2.2 TI2V-5B that captures
   the SUBJECT of the campaign with cinematic framing, tenant-
   appropriate palette, and an explicit style (cinematic, studio,
   macro, etc.).
3. Optionally write N still-image prompts for FLUX (0 to 6) that
   support the narrative — hero shots, product close-ups, context
   beats. Reference the tenant palette hex codes directly.
4. Optionally provide 3-6 caption beats (for Remotion lower thirds).

Strict output contract — return a SINGLE JSON OBJECT, no markdown
fences, no prose before or after:

{
  "narration_text":   str,
  "video_prompt":     str,
  "still_prompts":    [str, ...],   // 0 to 6 items; [] if none requested
  "captions":         [str, ...],   // 0 to 6 items; [] if none needed
  "rationale":        str,          // 1-2 sentences explaining your choices
  "warnings":         [str, ...]    // any brand / constraint conflicts
}

Rules you MUST follow:
- Stay in the tenant's brand voice (use the tone_keywords).
- Respect every constraint in the brief verbatim — if a constraint
  says "no medical claims", your output must not contain any.
- Never reference the call_to_action inside the narration unless it
  is explicitly a conversion or launch objective.
- The narration should OPEN with a promise (Winston's Rule) and
  CLOSE with either the CTA (if conversion/launch) or a callback
  slogan (if awareness/consideration).
- The video_prompt must be a single sentence, specific, <= 60 words,
  and include the tenant's palette anchor plus at least one lighting
  cue and one camera cue.
- If you detect a conflict between the brief and the brand (e.g.
  consumer hype copy requested for a B2B brand), emit a warning
  but still produce the best-possible output.
- Never refuse. Never ask clarifying questions. Produce the package.
"""


_USER_TEMPLATE = """## Tenant brand

Name: {display_name}
Tagline: {tagline}
One-liner: {one_liner}
Voice: {voice_name} (VibeVoice speaker preset)
Tone keywords: {tone_keywords}
Palette (primary first): {palette}
Negative prompt (for video/image): {negative_prompt}
Default target audience: {target_audience}
Domain: {domain}
Brand notes: {brand_notes}

## Campaign brief

{brief_block}

## Generation knobs

num_stills requested: {num_stills}
captions requested: {captions_requested}

Produce the JSON production package now.
"""


@dataclass
class ScriptResult:
    status: str  # "success" | "api_error" | "parse_error" | "disabled"
    narration_text: Optional[str] = None
    video_prompt: Optional[str] = None
    still_prompts: list[str] = field(default_factory=list)
    captions: list[str] = field(default_factory=list)
    rationale: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    duration_s: Optional[float] = None
    error: Optional[str] = None
    raw_response: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.status == "success"


class MarketingScriptGenerator:
    """Claude-backed script generator for CampaignBrief -> production package."""

    def __init__(
        self,
        client: Any = None,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> None:
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def generate(
        self,
        brief: CampaignBrief,
        brand: TenantBrand,
    ) -> ScriptResult:
        """Produce a full script package from a brief + tenant brand."""
        if self.client is None:
            return ScriptResult(
                status="disabled",
                model=self.model,
                error="script generator client is None (disabled mode)",
            )

        user_prompt = _USER_TEMPLATE.format(
            display_name=brand.display_name,
            tagline=brand.tagline,
            one_liner=brand.one_liner,
            voice_name=brand.voice_name,
            tone_keywords=", ".join(brand.tone_keywords),
            palette=", ".join(brand.palette),
            negative_prompt=brand.negative_prompt,
            target_audience=brand.target_audience,
            domain=brand.domain,
            brand_notes=brand.notes,
            brief_block=brief.brand_prompt_block(),
            num_stills=brief.num_stills,
            captions_requested="yes" if brief.enable_remotion else "no",
        )

        t0 = time.time()
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as exc:  # noqa: BLE001 — fail open
            return ScriptResult(
                status="api_error",
                model=self.model,
                duration_s=round(time.time() - t0, 3),
                error=f"{type(exc).__name__}: {exc}",
            )

        raw_text = _extract_text(response)
        result = ScriptResult(
            status="success",  # may be downgraded
            model=self.model,
            input_tokens=_extract_usage(response, "input_tokens"),
            output_tokens=_extract_usage(response, "output_tokens"),
            duration_s=round(time.time() - t0, 3),
            raw_response=raw_text,
        )

        parsed, parse_err = _parse_json_object(raw_text)
        if parse_err is not None:
            result.status = "parse_error"
            result.error = parse_err
            return result

        validation_err = _validate_payload(parsed)
        if validation_err is not None:
            result.status = "parse_error"
            result.error = validation_err
            return result

        result.narration_text = str(parsed["narration_text"]).strip()
        result.video_prompt = str(parsed["video_prompt"]).strip()
        result.still_prompts = [str(s) for s in parsed.get("still_prompts", [])]
        result.captions = [str(c) for c in parsed.get("captions", [])]
        result.rationale = parsed.get("rationale")
        result.warnings = [str(w) for w in parsed.get("warnings", [])]
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_text(response: Any) -> str:
    try:
        content = getattr(response, "content", None) or []
        for block in content:
            text = getattr(block, "text", None)
            if text:
                return str(text)
        return ""
    except Exception:  # noqa: BLE001
        return ""


def _extract_usage(response: Any, field_name: str) -> Optional[int]:
    try:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        val = getattr(usage, field_name, None)
        return int(val) if val is not None else None
    except Exception:  # noqa: BLE001
        return None


_FENCE_RX = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_json_object(raw_text: str) -> tuple[dict, Optional[str]]:
    if not raw_text:
        return {}, "empty response"
    txt = raw_text.strip()
    txt = _FENCE_RX.sub("", txt).strip()
    start = txt.find("{")
    end = txt.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}, "no JSON object found in response"
    try:
        parsed = json.loads(txt[start : end + 1])
    except json.JSONDecodeError as exc:
        return {}, f"json decode error: {exc}"
    if not isinstance(parsed, dict):
        return {}, f"parsed JSON is not an object: {type(parsed).__name__}"
    return parsed, None


def _validate_payload(data: dict) -> Optional[str]:
    required = ("narration_text", "video_prompt")
    missing = [k for k in required if not data.get(k)]
    if missing:
        return f"missing required fields: {missing}"
    if not isinstance(data.get("still_prompts", []), list):
        return "still_prompts must be a list"
    if not isinstance(data.get("captions", []), list):
        return "captions must be a list"
    if not isinstance(data.get("warnings", []), list):
        return "warnings must be a list"
    return None
