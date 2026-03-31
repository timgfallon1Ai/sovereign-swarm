"""Social media content generator with platform-specific formatting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from sovereign_swarm.content.models import ContentBrief, ContentDraft, ContentType

logger = structlog.get_logger()

# Platform character/formatting constraints
PLATFORM_LIMITS = {
    "twitter": {"max_chars": 280, "name": "Twitter/X"},
    "x": {"max_chars": 280, "name": "Twitter/X"},
    "instagram": {"max_chars": 2200, "name": "Instagram"},
    "linkedin": {"max_chars": 3000, "name": "LinkedIn"},
    "facebook": {"max_chars": 63206, "name": "Facebook"},
}


@dataclass
class SocialPost:
    """A platform-formatted social media post."""

    platform: str
    text: str
    hashtags: list[str] = field(default_factory=list)
    char_count: int = 0
    within_limit: bool = True


class SocialGenerator:
    """Generates platform-specific social media content.

    Supports Twitter/X, Instagram, LinkedIn, and Facebook with
    appropriate formatting and hashtag suggestions.
    """

    def __init__(self, anthropic_client: Any | None = None) -> None:
        self._client = anthropic_client

    async def generate(
        self,
        brief: ContentBrief,
        platforms: list[str] | None = None,
    ) -> list[SocialPost]:
        """Generate social posts for specified platforms."""
        target_platforms = platforms or ["twitter", "instagram", "linkedin"]
        posts: list[SocialPost] = []

        for platform in target_platforms:
            post = await self._generate_for_platform(brief, platform.lower())
            posts.append(post)

        return posts

    async def _generate_for_platform(
        self, brief: ContentBrief, platform: str
    ) -> SocialPost:
        """Generate a post for a specific platform."""
        if self._client:
            return await self._generate_with_claude(brief, platform)
        return self._generate_template(brief, platform)

    async def _generate_with_claude(
        self, brief: ContentBrief, platform: str
    ) -> SocialPost:
        """Generate using Claude API."""
        limits = PLATFORM_LIMITS.get(platform, PLATFORM_LIMITS["facebook"])
        prompt = (
            f"Write a {limits['name']} post about: {brief.topic}\n"
            f"Audience: {brief.audience}\n"
            f"Tone: {brief.tone}\n"
            f"Max characters: {limits['max_chars']}\n"
        )
        if brief.keywords:
            prompt += f"Include keywords: {', '.join(brief.keywords)}\n"
        prompt += (
            "\nProvide ONLY the post text. "
            "Do not include hashtags in the main text. "
            "After the post, on a new line write 'HASHTAGS:' followed by "
            "5-8 relevant hashtags separated by spaces."
        )

        try:
            response = await self._client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text
            text, hashtags = self._parse_response(raw)
            char_count = len(text)

            return SocialPost(
                platform=platform,
                text=text[:limits["max_chars"]],
                hashtags=hashtags,
                char_count=min(char_count, limits["max_chars"]),
                within_limit=char_count <= limits["max_chars"],
            )
        except Exception as e:
            logger.warning("social.claude_fallback", platform=platform, error=str(e))
            return self._generate_template(brief, platform)

    def _generate_template(self, brief: ContentBrief, platform: str) -> SocialPost:
        """Template-based fallback."""
        limits = PLATFORM_LIMITS.get(platform, PLATFORM_LIMITS["facebook"])
        hashtags = self._suggest_hashtags(brief)

        if platform in ("twitter", "x"):
            text = self._format_twitter(brief)
        elif platform == "instagram":
            text = self._format_instagram(brief)
        elif platform == "linkedin":
            text = self._format_linkedin(brief)
        else:
            text = self._format_facebook(brief)

        char_count = len(text)
        return SocialPost(
            platform=platform,
            text=text[:limits["max_chars"]],
            hashtags=hashtags,
            char_count=min(char_count, limits["max_chars"]),
            within_limit=char_count <= limits["max_chars"],
        )

    def _format_twitter(self, brief: ContentBrief) -> str:
        """Format for Twitter/X 280-char limit."""
        hashtags = self._suggest_hashtags(brief)[:3]
        tag_str = " ".join(f"#{h}" for h in hashtags)
        max_text = 280 - len(tag_str) - 2
        text = f"{brief.topic[:max_text]}"
        return f"{text}\n\n{tag_str}"

    def _format_instagram(self, brief: ContentBrief) -> str:
        """Format for Instagram caption."""
        return (
            f"{brief.topic}\n\n"
            f"Here's what you need to know:\n\n"
            f"Key insight about {brief.topic.lower()} that "
            f"{brief.audience} audiences will find valuable.\n\n"
            f"Save this post for later.\n"
            f"Share with someone who needs this."
        )

    def _format_linkedin(self, brief: ContentBrief) -> str:
        """Format for LinkedIn article post."""
        return (
            f"I've been thinking about {brief.topic.lower()} lately.\n\n"
            f"Here's what I've learned:\n\n"
            f"1. [Key insight #1]\n"
            f"2. [Key insight #2]\n"
            f"3. [Key insight #3]\n\n"
            f"The bottom line: {brief.topic} matters for "
            f"{brief.audience} because [reason].\n\n"
            f"What's your take? I'd love to hear your thoughts.\n\n"
            f"#Agree?"
        )

    def _format_facebook(self, brief: ContentBrief) -> str:
        """Format for Facebook post."""
        return (
            f"{brief.topic}\n\n"
            f"We wanted to share something important with our community.\n\n"
            f"[Expand on {brief.topic.lower()} with a personal angle "
            f"for {brief.audience} audiences]\n\n"
            f"What do you think? Drop a comment below."
        )

    @staticmethod
    def _suggest_hashtags(brief: ContentBrief) -> list[str]:
        """Suggest hashtags based on topic and keywords."""
        hashtags: list[str] = []
        # From keywords
        for kw in brief.keywords[:5]:
            tag = kw.replace(" ", "").replace("-", "")
            hashtags.append(tag)
        # From topic words
        for word in brief.topic.split()[:3]:
            clean = word.strip(".,!?").replace(" ", "")
            if len(clean) > 2 and clean.lower() not in [h.lower() for h in hashtags]:
                hashtags.append(clean)
        return hashtags[:8]

    @staticmethod
    def _parse_response(raw: str) -> tuple[str, list[str]]:
        """Parse Claude response into text and hashtags."""
        if "HASHTAGS:" in raw:
            parts = raw.split("HASHTAGS:", 1)
            text = parts[0].strip()
            hashtag_str = parts[1].strip()
            hashtags = [
                h.lstrip("#").strip()
                for h in hashtag_str.split()
                if h.startswith("#") or len(h) > 1
            ]
            return text, hashtags
        return raw.strip(), []
