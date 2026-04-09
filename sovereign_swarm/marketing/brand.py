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
        display_name="Green Bear Brand",
        tagline="Family-owned. AI-assisted. Built to last.",
        one_liner=(
            "Green Bear Brand is Tim Fallon's parent holding for the "
            "Sovereign ecosystem — an AI-first family-owned operator "
            "of manufacturing and e-commerce businesses."
        ),
        target_audience=(
            "enterprise partners, family-office LPs, and prospective "
            "customers evaluating GBB as a long-term vendor who won't "
            "disappear in a funding crunch."
        ),
        tone_keywords=(
            "principled",
            "long-horizon",
            "family-owned",
            "AI-native",
            "understated",
        ),
        palette=("#0f3b2e", "#d4a850", "#f7f3e9", "#2a5e4c"),  # deep forest, gold, cream, moss
        voice_name="Frank",  # en-Frank_man — steady, measured
        negative_prompt=(
            "corporate stock imagery, hype, forced smiles, flashy "
            "transitions, bright saturated colors, cartoon, watermark"
        ),
        default_duration_seconds=45,
        default_resolution=(1280, 704),
        default_aspect_ratio="16:9",
        cta_template="Learn more at {domain}",
        domain="greenbear.ai",
        notes=(
            "Parent-brand voice: focus on longevity, principle, and "
            "AI-assisted craftsmanship across the family portfolio. "
            "Avoid product-specific claims; GBB is a holding brand."
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
