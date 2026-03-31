"""SEO content scorer with readability analysis."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class SEOReport:
    """SEO analysis report for a piece of content."""

    overall_score: float = 0.0  # 0-100
    keyword_density: float = 0.0
    keyword_count: int = 0
    heading_score: float = 0.0
    meta_description_score: float = 0.0
    readability_grade: float = 0.0  # Flesch-Kincaid grade level
    readability_label: str = ""
    word_count: int = 0
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    internal_link_opportunities: list[str] = field(default_factory=list)


class SEOScorer:
    """Scores content for SEO quality.

    Evaluates keyword density, heading structure, meta description length,
    readability (Flesch-Kincaid approximation), and internal link opportunities.
    """

    def analyze(
        self,
        content: str,
        target_keywords: list[str] | None = None,
        meta_description: str = "",
    ) -> SEOReport:
        """Perform full SEO analysis on content."""
        report = SEOReport()
        target_keywords = target_keywords or []

        words = content.split()
        report.word_count = len(words)

        # Keyword analysis
        if target_keywords:
            kw_score = self._score_keywords(content, target_keywords, report)
        else:
            kw_score = 50.0  # neutral if no keywords specified

        # Heading structure
        heading_score = self._score_headings(content, report)

        # Meta description
        meta_score = self._score_meta_description(meta_description, report)

        # Readability
        readability_score = self._score_readability(content, report)

        # Word count check
        length_score = self._score_length(report)

        # Overall score (weighted average)
        report.overall_score = round(
            kw_score * 0.25
            + heading_score * 0.20
            + meta_score * 0.15
            + readability_score * 0.25
            + length_score * 0.15,
            1,
        )

        # Link opportunities
        report.internal_link_opportunities = self._find_link_opportunities(content)

        return report

    def _score_keywords(
        self,
        content: str,
        keywords: list[str],
        report: SEOReport,
    ) -> float:
        """Score keyword usage. Ideal density: 1-3%."""
        content_lower = content.lower()
        word_count = max(len(content.split()), 1)
        total_kw_count = 0

        for kw in keywords:
            count = content_lower.count(kw.lower())
            total_kw_count += count

        report.keyword_count = total_kw_count
        report.keyword_density = round((total_kw_count / word_count) * 100, 2)

        if report.keyword_density < 0.5:
            report.issues.append("Keyword density too low (< 0.5%)")
            report.suggestions.append("Add target keywords more naturally throughout the content")
            return 30.0
        elif report.keyword_density > 3.0:
            report.issues.append("Keyword density too high (> 3%) -- risk of keyword stuffing")
            report.suggestions.append("Reduce keyword repetition for more natural reading")
            return 40.0
        elif 1.0 <= report.keyword_density <= 2.5:
            return 100.0
        else:
            return 70.0

    def _score_headings(self, content: str, report: SEOReport) -> float:
        """Score heading structure (H1/H2/H3 hierarchy)."""
        h1_count = len(re.findall(r"^# [^#]", content, re.MULTILINE))
        h2_count = len(re.findall(r"^## [^#]", content, re.MULTILINE))
        h3_count = len(re.findall(r"^### [^#]", content, re.MULTILINE))

        score = 0.0

        if h1_count == 1:
            score += 40
        elif h1_count == 0:
            report.issues.append("Missing H1 heading")
            report.suggestions.append("Add a single H1 title at the top of your content")
        else:
            report.issues.append(f"Multiple H1 headings ({h1_count}) -- use only one")
            score += 20

        if h2_count >= 2:
            score += 40
        elif h2_count == 1:
            report.suggestions.append("Consider adding more H2 sections for better structure")
            score += 25
        else:
            report.issues.append("No H2 headings found")
            report.suggestions.append("Break content into sections with H2 headings")

        if h3_count >= 1:
            score += 20
        else:
            report.suggestions.append("Consider adding H3 subheadings for detailed sections")
            score += 10

        report.heading_score = score
        return score

    def _score_meta_description(self, meta: str, report: SEOReport) -> float:
        """Score meta description (ideal: 150-160 chars)."""
        if not meta:
            report.issues.append("No meta description provided")
            report.suggestions.append("Add a meta description of 150-160 characters")
            report.meta_description_score = 0
            return 0.0

        length = len(meta)
        if 150 <= length <= 160:
            report.meta_description_score = 100
            return 100.0
        elif 120 <= length <= 170:
            report.meta_description_score = 80
            return 80.0
        elif length < 120:
            report.issues.append(f"Meta description too short ({length} chars)")
            report.suggestions.append("Expand meta description to 150-160 characters")
            report.meta_description_score = 40
            return 40.0
        else:
            report.issues.append(f"Meta description too long ({length} chars)")
            report.suggestions.append("Trim meta description to 150-160 characters")
            report.meta_description_score = 50
            return 50.0

    def _score_readability(self, content: str, report: SEOReport) -> float:
        """Approximate Flesch-Kincaid grade level."""
        # Strip markdown formatting for analysis
        clean = re.sub(r"[#*_\[\]()]", "", content)
        sentences = re.split(r"[.!?]+", clean)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            report.readability_grade = 0
            report.readability_label = "N/A"
            return 50.0

        words = clean.split()
        word_count = len(words)
        sentence_count = len(sentences)

        # Approximate syllable count
        syllable_count = sum(self._count_syllables(w) for w in words)

        if word_count == 0 or sentence_count == 0:
            report.readability_grade = 0
            report.readability_label = "N/A"
            return 50.0

        # Flesch-Kincaid Grade Level
        grade = (
            0.39 * (word_count / sentence_count)
            + 11.8 * (syllable_count / word_count)
            - 15.59
        )
        grade = max(0, round(grade, 1))
        report.readability_grade = grade

        # Classify
        if grade <= 6:
            report.readability_label = "Easy"
            score = 100.0
        elif grade <= 8:
            report.readability_label = "Standard"
            score = 90.0
        elif grade <= 10:
            report.readability_label = "Moderate"
            score = 75.0
        elif grade <= 12:
            report.readability_label = "Difficult"
            report.suggestions.append("Consider simplifying sentence structure for broader audience")
            score = 55.0
        else:
            report.readability_label = "Very Difficult"
            report.issues.append("Content is very difficult to read (college+ level)")
            report.suggestions.append("Shorten sentences and use simpler vocabulary")
            score = 35.0

        return score

    def _score_length(self, report: SEOReport) -> float:
        """Score content length (ideal for blog: 1500-2500 words)."""
        wc = report.word_count
        if 1500 <= wc <= 2500:
            return 100.0
        elif 1000 <= wc < 1500:
            report.suggestions.append("Consider expanding content to 1500+ words for better SEO")
            return 75.0
        elif 2500 < wc <= 4000:
            return 85.0
        elif wc < 500:
            report.issues.append(f"Content too short ({wc} words)")
            report.suggestions.append("Aim for at least 1000 words for competitive SEO")
            return 30.0
        elif wc < 1000:
            report.suggestions.append("Content is on the shorter side for SEO")
            return 55.0
        else:
            return 70.0  # Very long is fine but diminishing returns

    @staticmethod
    def _count_syllables(word: str) -> int:
        """Approximate syllable count for English words."""
        word = word.lower().strip(".,!?;:'\"")
        if len(word) <= 2:
            return 1
        # Remove trailing silent 'e'
        if word.endswith("e"):
            word = word[:-1]
        # Count vowel groups
        count = len(re.findall(r"[aeiouy]+", word))
        return max(1, count)

    @staticmethod
    def _find_link_opportunities(content: str) -> list[str]:
        """Identify potential internal link anchor texts."""
        # Find noun phrases and repeated terms that could be link anchors
        words = content.lower().split()
        # Find 2-3 word phrases that appear multiple times
        bigrams: dict[str, int] = {}
        for i in range(len(words) - 1):
            pair = f"{words[i]} {words[i + 1]}"
            # Skip if contains markdown or punctuation
            if any(c in pair for c in "#*[]()_-"):
                continue
            bigrams[pair] = bigrams.get(pair, 0) + 1

        opportunities = [
            phrase
            for phrase, count in sorted(bigrams.items(), key=lambda x: -x[1])
            if count >= 2 and len(phrase) > 5
        ][:5]

        return opportunities

    def format_report_markdown(self, report: SEOReport) -> str:
        """Format SEO report as markdown."""
        lines = [
            "## SEO Analysis Report\n",
            f"**Overall Score:** {report.overall_score}/100\n",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Word Count | {report.word_count} |",
            f"| Keyword Density | {report.keyword_density}% |",
            f"| Keyword Occurrences | {report.keyword_count} |",
            f"| Heading Score | {report.heading_score}/100 |",
            f"| Meta Description | {report.meta_description_score}/100 |",
            f"| Readability | {report.readability_label} (Grade {report.readability_grade}) |",
            "",
        ]

        if report.issues:
            lines.append("### Issues\n")
            for issue in report.issues:
                lines.append(f"- {issue}")
            lines.append("")

        if report.suggestions:
            lines.append("### Suggestions\n")
            for suggestion in report.suggestions:
                lines.append(f"- {suggestion}")
            lines.append("")

        if report.internal_link_opportunities:
            lines.append("### Internal Link Opportunities\n")
            for phrase in report.internal_link_opportunities:
                lines.append(f"- \"{phrase}\"")
            lines.append("")

        return "\n".join(lines)
