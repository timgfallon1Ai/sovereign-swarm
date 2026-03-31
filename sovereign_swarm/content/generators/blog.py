"""Blog post generator with SEO structure."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.content.models import ContentBrief, ContentDraft, ContentType

logger = structlog.get_logger()


class BlogGenerator:
    """Generates blog post drafts with SEO structure.

    Uses Claude API if available, falls back to template-based generation.
    Produces H1/H2/H3 hierarchy, meta description, and internal link suggestions.
    """

    def __init__(self, anthropic_client: Any | None = None) -> None:
        self._client = anthropic_client

    async def generate(self, brief: ContentBrief) -> ContentDraft:
        """Generate a blog post from a content brief."""
        if self._client:
            return await self._generate_with_claude(brief)
        return self._generate_template(brief)

    async def _generate_with_claude(self, brief: ContentBrief) -> ContentDraft:
        """Generate using Claude API."""
        prompt = self._build_prompt(brief)
        try:
            response = await self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            body = response.content[0].text
            title = self._extract_title(body) or brief.topic
            word_count = len(body.split())

            return ContentDraft(
                title=title,
                body=body,
                content_type=ContentType.BLOG_POST,
                word_count=word_count,
                metadata={
                    "keywords": brief.keywords,
                    "audience": brief.audience,
                    "tone": brief.tone,
                    "generated_by": "claude",
                },
            )
        except Exception as e:
            logger.warning("blog.claude_fallback", error=str(e))
            return self._generate_template(brief)

    def _generate_template(self, brief: ContentBrief) -> ContentDraft:
        """Template-based fallback when Claude API is unavailable."""
        keywords_str = ", ".join(brief.keywords) if brief.keywords else brief.topic
        meta_desc = (
            f"Learn about {brief.topic}. "
            f"This guide covers everything you need to know about {keywords_str}."
        )

        body_parts = [
            f"# {brief.topic}\n",
            f"*Meta description: {meta_desc}*\n",
            f"## Introduction\n",
            f"This article explores {brief.topic} for {brief.audience} audiences. "
            f"Written in a {brief.tone} tone.\n",
        ]

        # Generate sections from keywords
        if brief.keywords:
            for i, kw in enumerate(brief.keywords[:5], 1):
                body_parts.append(f"## {kw.title()}\n")
                body_parts.append(
                    f"[Content about {kw} — expand with research and examples]\n"
                )
                if i <= 2:
                    body_parts.append(f"### Key Takeaways on {kw.title()}\n")
                    body_parts.append(
                        f"- Point 1 about {kw}\n- Point 2 about {kw}\n"
                        f"- Point 3 about {kw}\n"
                    )
        else:
            body_parts.append("## Overview\n")
            body_parts.append(f"[Expand on {brief.topic} with key details]\n")
            body_parts.append("## Deep Dive\n")
            body_parts.append("[Detailed analysis and supporting evidence]\n")

        body_parts.append("## Conclusion\n")
        body_parts.append(
            f"[Summarize key points about {brief.topic} and provide next steps]\n"
        )
        body_parts.append("\n---\n*Internal link suggestions:*\n")
        body_parts.append(f"- Related: [topic 1]\n- Related: [topic 2]\n")

        body = "\n".join(body_parts)
        word_count = len(body.split())

        return ContentDraft(
            title=brief.topic,
            body=body,
            content_type=ContentType.BLOG_POST,
            word_count=word_count,
            metadata={
                "keywords": brief.keywords,
                "audience": brief.audience,
                "tone": brief.tone,
                "meta_description": meta_desc,
                "generated_by": "template",
            },
        )

    def _build_prompt(self, brief: ContentBrief) -> str:
        """Build the Claude prompt for blog generation."""
        keywords_section = ""
        if brief.keywords:
            keywords_section = (
                f"\nTarget keywords: {', '.join(brief.keywords)}\n"
                "Naturally incorporate these keywords throughout the post."
            )

        return (
            f"Write a blog post about: {brief.topic}\n\n"
            f"Target audience: {brief.audience}\n"
            f"Tone: {brief.tone}\n"
            f"Target length: ~{brief.length} words\n"
            f"{keywords_section}\n\n"
            "Requirements:\n"
            "- Use proper heading hierarchy (# H1, ## H2, ### H3)\n"
            "- Start with a compelling H1 title\n"
            "- Include a meta description (italicized at top)\n"
            "- Use scannable formatting (lists, bold key terms)\n"
            "- End with a conclusion and call-to-action\n"
            "- Suggest 2-3 internal link opportunities at the bottom\n"
        )

    @staticmethod
    def _extract_title(body: str) -> str:
        """Extract H1 title from generated markdown."""
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                return stripped[2:].strip()
        return ""
