"""Per-tenant brand profiles for the Sovereign marketing ensemble.

A ``TenantBrand`` is the minimum set of parameters every downstream
provider (VibeVoice TTS, Wan2.2 video, FLUX imagery, Claude copy)
needs to produce on-brand assets for a given company. It is NOT a
full brand guide — the full guide lives in the tenant's own repo or
brand kit. This is the runtime slice the ensemble reads each time a
campaign request arrives.

Design notes
------------
- Everything on ``TenantBrand`` is a stable string or tuple so the
  whole dataclass is JSON-serializable and hashable.
- ``negative_prompt`` is a comma-separated string so it drops straight
  into image/video generator prompts without extra formatting.
- ``voice_name`` must match one of the VibeVoice speaker presets
  bundled at ``~/Documents/GitHub/VibeVoice/demo/voices/streaming_model/``
  (en-Carter_man, en-Davis_man, en-Emma_woman, en-Frank_man,
  en-Grace_woman, en-Mike_man, plus the non-English ones).
- ``palette`` is a tuple of hex strings — the FLUX / Wan2.2 prompt
  can embed these verbatim and the Remotion composer can consume
  them directly as CSS variables.
- ``tone_keywords`` is a small handful of adjectives that Claude can
  slot into the copywriting prompt to keep voice consistent across
  blog, video script, and social copy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class TenantBrand:
    key: str
    display_name: str
    tagline: str
    one_liner: str
    target_audience: str
    tone_keywords: tuple[str, ...]
    palette: tuple[str, ...]  # hex colors, primary first
    voice_name: str  # VibeVoice speaker preset
    negative_prompt: str  # comma-separated negative prompt for image/video
    default_duration_seconds: int = 30
    default_resolution: tuple[int, int] = (1280, 704)
    default_aspect_ratio: str = "16:9"
    cta_template: str = "Learn more at {domain}"
    domain: str = ""
    notes: str = ""


TENANTS: Mapping[str, TenantBrand] = {
    "sovereign": TenantBrand(
        key="sovereign",
        display_name="Sovereign",
        tagline="Your data. Your intelligence. Your sovereignty.",
        one_liner=(
            "Sovereign is a private AI operating system that runs every "
            "automatable function of your business — sales, marketing, "
            "inventory, accounting, staffing — through a single voice or "
            "text interface, without ever touching your data."
        ),
        target_audience=(
            "small business owners doing $2-20M annual revenue who are "
            "paying $2-5K/month for fragmented tools that don't talk to "
            "each other and want a unified, private AI operating system."
        ),
        tone_keywords=(
            "sovereign",
            "private",
            "operator-grade",
            "battle-tested",
            "founder-built",
        ),
        palette=("#0b0f14", "#d4a94a", "#faf8f5", "#1c2028"),  # near-black, gold, warm white, dark charcoal
        voice_name="Carter",  # en-Carter_man — confident, founder energy
        negative_prompt=(
            "corporate stock imagery, fake smiles, generic SaaS dashboard "
            "screenshots, bright saturated colors, cartoon, watermark, "
            "text, logo overlay, cheap, gimmicky, hype"
        ),
        default_duration_seconds=120,
        default_resolution=(1280, 704),
        default_aspect_ratio="16:9",
        cta_template="Start your diagnostic pilot at {domain}",
        domain="svrnmind.ai",
        notes=(
            "Master brand voice: founder-operator authority, not corporate "
            "marketing. Speak as someone who built this to run his own "
            "businesses, not as a SaaS vendor. Emphasize privacy as "
            "architecture, not policy. Emphasize customer-zero credibility. "
            "Never use hype language. Never promise AI magic. Position as "
            "operator-grade infrastructure, not a tool or an app."
        ),
    ),
    "atx_mats": TenantBrand(
        key="atx_mats",
        display_name="ATX Mats",
        tagline="Flooring that outlasts the warranty.",
        one_liner=(
            "Commercial and OEM flooring manufacturer shipping from "
            "Austin and Shanghai, specializing in ultra-durable mats "
            "for warehouses, gyms, showrooms, and industrial spaces."
        ),
        target_audience=(
            "facility managers, commercial builders, gym owners, and "
            "OEM buyers evaluating flooring at $3-$15/sqft that needs "
            "to survive a decade of abuse."
        ),
        tone_keywords=(
            "practical",
            "durable",
            "no-nonsense",
            "engineered",
            "warranty-backed",
        ),
        palette=("#1a2332", "#c9a961", "#f4f1ea", "#3a4556"),  # dark navy, brass, cream, slate
        voice_name="Davis",  # en-Davis_man — authoritative but warm
        negative_prompt=(
            "blurry, low quality, cartoon, stock-photo feel, clip art, "
            "watermark, text, logo, fake, oversaturated, glossy"
        ),
        default_duration_seconds=30,
        default_resolution=(1280, 704),
        default_aspect_ratio="16:9",
        cta_template="See the full warranty at {domain}",
        domain="atxmats.com",
        notes=(
            "Commercial tone — B2B buyers, not consumers. Avoid hype "
            "language. Emphasize load ratings, slip coefficients, "
            "fireproofing specs, and the OEM manufacturing pipeline "
            "from Austin to Shanghai."
        ),
    ),
    "gbb": TenantBrand(
        key="gbb",
        display_name="Gracie Barra Buda",
        tagline="Jiu-Jitsu for Everyone.",
        one_liner=(
            "Gracie Barra Buda is a family-friendly Brazilian "
            "Jiu-Jitsu academy in Buda, Texas, offering kids and "
            "adult programs with world-class instruction."
        ),
        target_audience=(
            "families in Buda/Kyle/South Austin looking for martial "
            "arts training, parents enrolling kids ages 4-15, adults "
            "seeking fitness and self-defense, and competitors "
            "training for tournaments."
        ),
        tone_keywords=(
            "welcoming",
            "community",
            "family-friendly",
            "discipline",
            "growth",
        ),
        palette=("#1E40AF", "#DC2626", "#FFFFFF", "#1E3A8A"),  # GB blue, GB red, white, dark blue
        voice_name="Frank",  # en-Frank_man — steady, measured
        negative_prompt=(
            "violence, blood, aggressive fighting, corporate stock "
            "imagery, flashy transitions, cartoon, watermark"
        ),
        default_duration_seconds=30,
        default_resolution=(1280, 704),
        default_aspect_ratio="16:9",
        cta_template="Start your free trial at {domain}",
        domain="gbbuda.com",
        notes=(
            "Gracie Barra is a global BJJ franchise. Buda location "
            "is owned by Professor Tim Fallon. Emphasize community, "
            "family training together, belt progression, and the GB "
            "methodology. Use real GB brand colors (blue/red/white)."
        ),
    ),
    "gli": TenantBrand(
        key="gli",
        display_name="Green Light Innovations",
        tagline="LED grow lights engineered by growers.",
        one_liner=(
            "Green Light Innovations is a specialty e-commerce company "
            "selling high-performance LED grow lights to commercial "
            "and enthusiast indoor cultivators, backed by in-house "
            "patent scanning and customer-support agent clusters."
        ),
        target_audience=(
            "commercial cultivators, hobbyist growers, and dispensary "
            "operators upgrading from HPS to full-spectrum LEDs."
        ),
        tone_keywords=(
            "technical",
            "grower-to-grower",
            "data-driven",
            "enthusiast",
            "approachable",
        ),
        palette=("#0d5c2e", "#a8d82c", "#0b1a0f", "#f5f6f1"),  # green, lime, near-black, bone
        voice_name="Emma",  # en-Emma_woman — bright, knowledgeable
        negative_prompt=(
            "marijuana leaf cliche, flashy neon, fake dollar signs, "
            "stock smile, watermark, logo, low quality"
        ),
        default_duration_seconds=30,
        default_resolution=(1280, 704),
        default_aspect_ratio="16:9",
        cta_template="Shop the full lineup at {domain}",
        domain="growgli.com",
        notes=(
            "Grower-to-grower voice: PAR numbers, spectrum curves, "
            "canopy coverage, warranty specifics. Avoid legal-gray "
            "copy. Emphasize engineering provenance and the in-house "
            "CS portal."
        ),
    ),
}


def get_brand(key: str) -> TenantBrand:
    """Look up a tenant brand by key. Raises KeyError with a helpful message."""
    try:
        return TENANTS[key]
    except KeyError as exc:
        known = ", ".join(sorted(TENANTS.keys()))
        raise KeyError(
            f"Unknown marketing tenant '{key}'. Known tenants: {known}"
        ) from exc
