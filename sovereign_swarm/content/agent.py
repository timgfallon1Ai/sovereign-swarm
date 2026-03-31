"""ContentAgent -- content creation and SEO optimization for the swarm."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import structlog

from sovereign_swarm.content.models import (
    CalendarEntry,
    ContentBrief,
    ContentCalendar,
    ContentDraft,
    ContentType,
)
from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)

logger = structlog.get_logger()


class ContentAgent(SwarmAgent):
    """Content creation agent.

    Generates blog posts, social media content, email sequences,
    product descriptions, and content calendars with SEO analysis.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._blog_gen = None
        self._social_gen = None
        self._email_gen = None
        self._seo_scorer = None
        self._anthropic = None

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="ContentAgent",
            description=(
                "Content creation agent -- generates blog posts, social media "
                "content, email sequences, product descriptions, and content "
                "calendars with SEO optimization."
            ),
            version="0.1.0",
            domains=["content", "marketing", "seo", "blog", "social", "email"],
            supported_intents=[
                "blog_post",
                "social_content",
                "email_sequence",
                "product_description",
                "content_calendar",
                "seo_review",
            ],
            capabilities=[
                "blog_post",
                "social_content",
                "email_sequence",
                "product_description",
                "content_calendar",
                "seo_review",
            ],
        )

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route a content task to the appropriate handler."""
        task = request.task.lower()
        params = request.parameters or request.context or {}

        try:
            if any(kw in task for kw in ("blog", "article", "post")):
                if "seo" in task or "review" in task or "score" in task:
                    result = await self._handle_seo_review(params)
                else:
                    result = await self._handle_blog(params)
            elif any(kw in task for kw in ("social", "twitter", "instagram", "linkedin", "facebook")):
                result = await self._handle_social(params)
            elif any(kw in task for kw in ("email", "sequence", "campaign")):
                result = await self._handle_email_sequence(params)
            elif any(kw in task for kw in ("product", "description")):
                result = await self._handle_product_description(params)
            elif any(kw in task for kw in ("calendar", "schedule", "plan")):
                result = await self._handle_content_calendar(params)
            elif "seo" in task:
                result = await self._handle_seo_review(params)
            else:
                result = await self._handle_blog(params)

            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=result.get("confidence", 0.75),
            )
        except Exception as e:
            logger.error("content.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="error",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_blog(self, params: dict) -> dict:
        """Generate a blog post."""
        brief = self._build_brief(params, ContentType.BLOG_POST)
        gen = self._get_blog_generator()
        draft = await gen.generate(brief)

        # Auto-run SEO analysis
        scorer = self._get_seo_scorer()
        meta = draft.metadata.get("meta_description", "")
        seo = scorer.analyze(draft.body, brief.keywords, meta)
        draft.seo_score = seo.overall_score
        draft.readability_score = seo.readability_grade

        md = f"## Blog Draft: {draft.title}\n\n"
        md += draft.body
        md += f"\n\n---\n**SEO Score:** {seo.overall_score}/100 | "
        md += f"**Readability:** {seo.readability_label} (Grade {seo.readability_grade}) | "
        md += f"**Words:** {draft.word_count}\n"

        return {"markdown": md, "draft": draft.model_dump(), "confidence": 0.75}

    async def _handle_social(self, params: dict) -> dict:
        """Generate social media posts."""
        brief = self._build_brief(params, ContentType.SOCIAL_POST)
        platforms = params.get("platforms", ["twitter", "instagram", "linkedin"])
        gen = self._get_social_generator()
        posts = await gen.generate(brief, platforms)

        md = f"## Social Media Posts: {brief.topic}\n\n"
        for post in posts:
            status = "OK" if post.within_limit else "OVER LIMIT"
            md += f"### {post.platform.title()} ({post.char_count} chars -- {status})\n\n"
            md += f"{post.text}\n\n"
            if post.hashtags:
                md += f"**Hashtags:** {' '.join('#' + h for h in post.hashtags)}\n\n"
            md += "---\n\n"

        return {
            "markdown": md,
            "posts": [
                {
                    "platform": p.platform,
                    "text": p.text,
                    "hashtags": p.hashtags,
                    "char_count": p.char_count,
                    "within_limit": p.within_limit,
                }
                for p in posts
            ],
            "confidence": 0.7,
        }

    async def _handle_email_sequence(self, params: dict) -> dict:
        """Generate an email sequence."""
        gen = self._get_email_generator()
        seq_type = params.get("sequence_type", "welcome")
        brand = params.get("brand", "Our Company")
        audience = params.get("audience", "customers")
        goal = params.get("goal", "")
        num_emails = params.get("num_emails")

        sequence = await gen.generate(seq_type, brand, audience, goal, num_emails)
        md = gen.format_sequence_markdown(sequence)

        return {"markdown": md, "sequence_name": sequence.name, "confidence": 0.7}

    async def _handle_product_description(self, params: dict) -> dict:
        """Generate a product description."""
        brief = self._build_brief(params, ContentType.PRODUCT_DESCRIPTION)
        product_name = params.get("product_name", brief.topic)
        features = params.get("features", [])

        features_str = ""
        if features:
            features_str = "\n".join(f"- {f}" for f in features)

        md = f"## Product Description: {product_name}\n\n"
        md += f"### Headline\n{brief.topic}\n\n"
        md += f"### Description\n"
        md += (
            f"{product_name} is designed for {brief.audience}. "
            f"[Expand with key value propositions and benefits.]\n\n"
        )
        if features_str:
            md += f"### Features\n{features_str}\n\n"
        md += "### Call to Action\n[Buy Now / Learn More / Get Started]\n"

        return {"markdown": md, "product_name": product_name, "confidence": 0.65}

    async def _handle_content_calendar(self, params: dict) -> dict:
        """Generate a content calendar."""
        weeks = params.get("weeks", 4)
        channels = params.get("channels", ["blog", "twitter", "linkedin"])
        topic_themes = params.get("themes", ["industry trends", "how-to guides", "case studies"])

        entries: list[CalendarEntry] = []
        start = datetime.now()

        for week in range(weeks):
            for i, channel in enumerate(channels):
                entry_date = start + timedelta(weeks=week, days=i)
                theme = topic_themes[week % len(topic_themes)]
                ct = ContentType.BLOG_POST if channel == "blog" else ContentType.SOCIAL_POST
                entries.append(
                    CalendarEntry(
                        date=entry_date,
                        title=f"{theme.title()} -- {channel.title()} Post",
                        content_type=ct,
                        channel=channel,
                        status="planned",
                    )
                )

        calendar = ContentCalendar(
            name=f"{weeks}-Week Content Calendar",
            entries=entries,
            start_date=start,
            end_date=start + timedelta(weeks=weeks),
        )

        md = f"## {calendar.name}\n\n"
        md += "| Date | Channel | Title | Type | Status |\n"
        md += "|------|---------|-------|------|--------|\n"
        for entry in calendar.entries:
            md += (
                f"| {entry.date.strftime('%Y-%m-%d')} "
                f"| {entry.channel} "
                f"| {entry.title} "
                f"| {entry.content_type.value} "
                f"| {entry.status} |\n"
            )

        md += f"\n*{len(entries)} entries across {weeks} weeks*\n"
        return {"markdown": md, "entry_count": len(entries), "confidence": 0.7}

    async def _handle_seo_review(self, params: dict) -> dict:
        """Run SEO analysis on provided content."""
        content = params.get("content", "")
        keywords = params.get("keywords", [])
        meta = params.get("meta_description", "")

        if not content:
            return {
                "markdown": "## SEO Review\n\nNo content provided for analysis.",
                "confidence": 0.5,
            }

        scorer = self._get_seo_scorer()
        report = scorer.analyze(content, keywords, meta)
        md = scorer.format_report_markdown(report)

        return {"markdown": md, "seo_score": report.overall_score, "confidence": 0.8}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_brief(self, params: dict, content_type: ContentType) -> ContentBrief:
        """Build a ContentBrief from request parameters."""
        return ContentBrief(
            topic=params.get("topic", params.get("subject", "Untitled")),
            audience=params.get("audience", "general"),
            tone=params.get("tone", "professional"),
            keywords=params.get("keywords", []),
            length=params.get("length", 1000),
            channel=params.get("channel", "blog"),
            content_type=content_type,
            additional_notes=params.get("notes", ""),
        )

    # ------------------------------------------------------------------
    # Lazy init
    # ------------------------------------------------------------------

    def _get_anthropic(self):
        if self._anthropic is None:
            try:
                import anthropic

                self._anthropic = anthropic.AsyncAnthropic()
            except Exception:
                self._anthropic = None
        return self._anthropic

    def _get_blog_generator(self):
        if self._blog_gen is None:
            from sovereign_swarm.content.generators.blog import BlogGenerator

            self._blog_gen = BlogGenerator(anthropic_client=self._get_anthropic())
        return self._blog_gen

    def _get_social_generator(self):
        if self._social_gen is None:
            from sovereign_swarm.content.generators.social import SocialGenerator

            self._social_gen = SocialGenerator(anthropic_client=self._get_anthropic())
        return self._social_gen

    def _get_email_generator(self):
        if self._email_gen is None:
            from sovereign_swarm.content.generators.email import (
                EmailSequenceGenerator,
            )

            self._email_gen = EmailSequenceGenerator(anthropic_client=self._get_anthropic())
        return self._email_gen

    def _get_seo_scorer(self):
        if self._seo_scorer is None:
            from sovereign_swarm.content.seo_scorer import SEOScorer

            self._seo_scorer = SEOScorer()
        return self._seo_scorer
