"""Document comparison using difflib."""

from __future__ import annotations

import difflib
from typing import Any

import structlog

from sovereign_swarm.document_intel.models import DocumentComparison

logger = structlog.get_logger()


class DocumentComparator:
    """Diff two documents and compute similarity."""

    def compare(
        self, text_a: str, text_b: str, label_a: str = "doc_a", label_b: str = "doc_b"
    ) -> DocumentComparison:
        """Compare two document texts and return structured diff."""
        lines_a = text_a.splitlines()
        lines_b = text_b.splitlines()

        differ = difflib.unified_diff(
            lines_a, lines_b, fromfile=label_a, tofile=label_b, lineterm=""
        )

        additions: list[str] = []
        deletions: list[str] = []
        modifications: list[dict[str, str]] = []

        diff_lines = list(differ)
        i = 0
        while i < len(diff_lines):
            line = diff_lines[i]
            if line.startswith("+ ") and not line.startswith("+++"):
                additions.append(line[2:])
            elif line.startswith("- ") and not line.startswith("---"):
                # Check if the next line is an addition (modification pair)
                if (
                    i + 1 < len(diff_lines)
                    and diff_lines[i + 1].startswith("+ ")
                    and not diff_lines[i + 1].startswith("+++")
                ):
                    modifications.append(
                        {"before": line[2:], "after": diff_lines[i + 1][2:]}
                    )
                    i += 1  # skip the addition line
                else:
                    deletions.append(line[2:])
            i += 1

        # Similarity via SequenceMatcher
        similarity = difflib.SequenceMatcher(None, text_a, text_b).ratio()

        return DocumentComparison(
            doc_a=label_a,
            doc_b=label_b,
            additions=additions,
            deletions=deletions,
            modifications=modifications,
            similarity_score=round(similarity, 4),
        )

    def quick_similarity(self, text_a: str, text_b: str) -> float:
        """Return a 0-1 similarity score between two texts."""
        return round(difflib.SequenceMatcher(None, text_a, text_b).ratio(), 4)
