"""sovereign_brand_mcp — tenant brand lookups as an MCP server.

Read-only MCP server that exposes the cross-tenant brand registry
(``sovereign_swarm.marketing.brand``) to external MCP clients such
as Accio Work, Claude Desktop, or Cursor. Lets those clients stay
on-brand when drafting RFQs, writing sourcing copy, or producing
supplier outreach without ever pulling the full brand module into
the client's own process space.

Exposed tools
-------------
- ``list_tenants``          — return every known tenant brand key + display name.
- ``get_brand``             — return the full TenantBrand for one key.
- ``get_negative_prompt``   — return just the negative prompt for a tenant.
- ``get_voice_preset``      — return the VibeVoice speaker preset.
- ``get_palette``           — return the palette hex codes as a list.

Run with:
    python -m sovereign_swarm.mcp_servers.brand_server
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from sovereign_swarm.marketing.brand import TENANTS, TenantBrand, get_brand

mcp = FastMCP(
    "sovereign-brand",
    instructions=(
        "Tenant brand registry for the Sovereign AI ecosystem. Call "
        "these tools to stay on-brand when generating copy, RFQs, or "
        "supplier outreach for ATX Mats, Green Bear Brand, or Green "
        "Light Innovations. Every response is read-only and carries "
        "no customer-zero trace data."
    ),
)


def _brand_to_dict(brand: TenantBrand) -> dict[str, Any]:
    """Serialize a TenantBrand into a JSON-safe dict for MCP responses."""
    return {
        "key": brand.key,
        "display_name": brand.display_name,
        "tagline": brand.tagline,
        "one_liner": brand.one_liner,
        "target_audience": brand.target_audience,
        "tone_keywords": list(brand.tone_keywords),
        "palette": list(brand.palette),
        "voice_name": brand.voice_name,
        "negative_prompt": brand.negative_prompt,
        "default_duration_seconds": brand.default_duration_seconds,
        "default_resolution": list(brand.default_resolution),
        "default_aspect_ratio": brand.default_aspect_ratio,
        "cta_template": brand.cta_template,
        "domain": brand.domain,
        "notes": brand.notes,
    }


@mcp.tool()
async def list_tenants() -> dict[str, Any]:
    """List every tenant brand registered in the Sovereign ecosystem.

    Returns a dict with ``tenants`` (mapping of key -> display name) and
    ``count``. Use this first to discover which tenants exist before
    calling ``get_brand``.
    """
    return {
        "tenants": {key: brand.display_name for key, brand in TENANTS.items()},
        "count": len(TENANTS),
    }


@mcp.tool()
async def get_brand_profile(tenant: str) -> dict[str, Any]:
    """Return the full brand profile for one tenant.

    Args:
        tenant: Tenant key from ``list_tenants`` (e.g. ``atx_mats``).

    Returns the full TenantBrand as a dict, or an error dict with a
    list of known tenant keys when the requested tenant is unknown.
    """
    try:
        brand = get_brand(tenant)
    except KeyError as exc:
        return {
            "error": str(exc),
            "known_tenants": sorted(TENANTS.keys()),
        }
    return _brand_to_dict(brand)


@mcp.tool()
async def get_negative_prompt(tenant: str) -> dict[str, Any]:
    """Return just the tenant's negative prompt string.

    Useful for image/video generation clients that want to inject the
    tenant's negative prompt into a FLUX / Wan 2.2 / Sora call without
    pulling the full brand profile.
    """
    try:
        brand = get_brand(tenant)
    except KeyError as exc:
        return {"error": str(exc), "known_tenants": sorted(TENANTS.keys())}
    return {
        "tenant": brand.key,
        "negative_prompt": brand.negative_prompt,
    }


@mcp.tool()
async def get_voice_preset(tenant: str) -> dict[str, Any]:
    """Return the VibeVoice speaker preset name for the tenant.

    The preset names match the en-*.pt files shipped in VibeVoice's
    ``demo/voices/streaming_model/`` directory (Carter, Davis, Emma,
    Frank, Grace, Mike).
    """
    try:
        brand = get_brand(tenant)
    except KeyError as exc:
        return {"error": str(exc), "known_tenants": sorted(TENANTS.keys())}
    return {
        "tenant": brand.key,
        "voice_name": brand.voice_name,
    }


@mcp.tool()
async def get_palette(tenant: str) -> dict[str, Any]:
    """Return the tenant's palette as a list of hex color strings.

    Primary color is first. Use directly as CSS variables or embed in
    Wan 2.2 / FLUX prompts (``"palette colors #1a2332 and #c9a961"``).
    """
    try:
        brand = get_brand(tenant)
    except KeyError as exc:
        return {"error": str(exc), "known_tenants": sorted(TENANTS.keys())}
    return {
        "tenant": brand.key,
        "palette": list(brand.palette),
        "primary": brand.palette[0] if brand.palette else None,
    }


def main() -> None:
    """Entry point for ``python -m sovereign_swarm.mcp_servers.brand_server``."""
    mcp.run()


if __name__ == "__main__":
    main()
