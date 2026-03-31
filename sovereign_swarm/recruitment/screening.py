"""Resume screening and candidate scoring."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

from sovereign_swarm.recruitment.models import Candidate, CandidateStage, JobPosting

logger = structlog.get_logger()


@dataclass
class ScreeningResult:
    """Result of screening a candidate against a job posting."""

    candidate_name: str
    overall_score: float = 0.0  # 0-100
    requirement_matches: list[str] = field(default_factory=list)
    requirement_misses: list[str] = field(default_factory=list)
    nice_to_have_matches: list[str] = field(default_factory=list)
    experience_years: float = 0.0
    keywords_found: list[str] = field(default_factory=list)
    recommendation: str = ""  # "advance", "maybe", "pass"


class ResumeScreener:
    """Scores candidates against job requirements.

    Uses keyword matching and experience years extraction to produce
    a ranked candidate list.
    """

    def screen(
        self,
        candidates: list[Candidate],
        posting: JobPosting,
    ) -> list[ScreeningResult]:
        """Screen all candidates against a job posting. Returns ranked list."""
        results: list[ScreeningResult] = []
        for candidate in candidates:
            result = self._screen_single(candidate, posting)
            results.append(result)

        # Sort by score descending
        results.sort(key=lambda r: r.overall_score, reverse=True)
        return results

    def _screen_single(
        self, candidate: Candidate, posting: JobPosting
    ) -> ScreeningResult:
        """Screen a single candidate."""
        result = ScreeningResult(candidate_name=candidate.name)
        resume = (candidate.resume_summary or "").lower()

        # Check requirements
        req_score = 0.0
        for req in posting.requirements:
            keywords = self._extract_keywords(req)
            if any(kw in resume for kw in keywords):
                result.requirement_matches.append(req)
                req_score += 1
            else:
                result.requirement_misses.append(req)

        total_reqs = max(len(posting.requirements), 1)
        req_pct = (req_score / total_reqs) * 60  # 60% weight for requirements

        # Check nice-to-haves
        nth_score = 0.0
        for nth in posting.nice_to_haves:
            keywords = self._extract_keywords(nth)
            if any(kw in resume for kw in keywords):
                result.nice_to_have_matches.append(nth)
                nth_score += 1

        total_nth = max(len(posting.nice_to_haves), 1)
        nth_pct = (nth_score / total_nth) * 20  # 20% weight

        # Extract experience years
        result.experience_years = self._extract_years(resume)
        exp_pct = min(result.experience_years * 5, 20)  # 20% weight, cap at 4+ years

        # Keyword density
        all_keywords = self._extract_keywords(posting.description)
        for kw in all_keywords:
            if kw in resume:
                result.keywords_found.append(kw)

        result.overall_score = round(min(req_pct + nth_pct + exp_pct, 100), 1)

        # Recommendation
        if result.overall_score >= 70:
            result.recommendation = "advance"
        elif result.overall_score >= 45:
            result.recommendation = "maybe"
        else:
            result.recommendation = "pass"

        return result

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract meaningful keywords from a requirement or description."""
        # Remove common words
        stopwords = {
            "a", "an", "the", "and", "or", "of", "in", "to", "for",
            "with", "is", "are", "be", "at", "on", "by", "from",
            "this", "that", "will", "can", "may", "must", "should",
            "have", "has", "had", "do", "does", "did", "not", "no",
            "all", "any", "our", "we", "you", "your", "their",
            "ability", "experience", "skills", "strong", "minimum",
            "preferred", "required", "knowledge", "including",
        }
        words = re.findall(r"\b[a-z]{3,}\b", text.lower())
        return [w for w in words if w not in stopwords]

    @staticmethod
    def _extract_years(text: str) -> float:
        """Extract years of experience from resume text."""
        patterns = [
            r"(\d+)\+?\s*years?\s*(?:of\s*)?experience",
            r"(\d+)\+?\s*years?\s*(?:in|of|working)",
            r"experience:\s*(\d+)\+?\s*years?",
        ]
        max_years = 0.0
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for m in matches:
                try:
                    years = float(m)
                    max_years = max(max_years, years)
                except ValueError:
                    pass
        return max_years

    def format_results_markdown(
        self, results: list[ScreeningResult], posting: JobPosting
    ) -> str:
        """Format screening results as markdown."""
        lines = [
            f"## Candidate Screening: {posting.title}\n",
            f"**{len(results)} candidates screened**\n",
            "| Rank | Candidate | Score | Experience | Recommendation |",
            "|------|-----------|-------|------------|----------------|",
        ]
        for i, r in enumerate(results, 1):
            exp = f"{r.experience_years:.0f} yrs" if r.experience_years else "N/A"
            lines.append(
                f"| {i} | {r.candidate_name} | {r.overall_score}/100 "
                f"| {exp} | {r.recommendation.upper()} |"
            )

        lines.append("")

        # Detail for top candidates
        top = [r for r in results if r.recommendation == "advance"]
        if top:
            lines.append("### Top Candidates\n")
            for r in top:
                lines.append(f"**{r.candidate_name}** (Score: {r.overall_score})")
                if r.requirement_matches:
                    lines.append(f"- Matches: {', '.join(r.requirement_matches[:3])}")
                if r.requirement_misses:
                    lines.append(f"- Gaps: {', '.join(r.requirement_misses[:3])}")
                lines.append("")

        return "\n".join(lines)
