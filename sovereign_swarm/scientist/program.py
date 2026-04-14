"""Markdown-driven experiment orchestration (program.md pattern).

Ported from Karpathy's autoresearch concept: instead of writing Python
to define experiments, write a ``program.md`` Markdown file that serves
as the "research organization code." The ScientistAgent reads the
program.md, interprets sections as experiment specs, and drives the
research cycle accordingly.

This decouples experiment DESIGN (human-readable Markdown) from
experiment EXECUTION (Python in the runner). Tim or any agent can
author a program.md, and the scientist module executes it.

program.md format
-----------------
```markdown
# Research Program: <title>

## Question
<The core research question>

## Hypotheses
- H1: <statement> | rationale: <why>
- H2: <statement> | rationale: <why>

## Experiments
### E1: <name>
- type: data_analysis | computation | literature_review | api_query
- hypothesis: H1
- method: <step-by-step methodology>
- sources: <comma-separated data sources>
- parameters:
  - key1: value1
  - key2: value2

## Success Criteria
- <criterion 1>
- <criterion 2>

## Iteration Rules
- max_iterations: 3
- stop_when: all_resolved | any_supported | budget_exceeded
```
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import structlog

from sovereign_swarm.scientist.models import (
    Experiment,
    ExperimentType,
    Hypothesis,
)

logger = structlog.get_logger()


@dataclass
class ProgramSpec:
    """Parsed representation of a program.md file."""

    title: str
    question: str
    hypotheses: list[Hypothesis]
    experiments: list[Experiment]
    success_criteria: list[str] = field(default_factory=list)
    max_iterations: int = 3
    stop_when: str = "all_resolved"
    raw_markdown: str = ""
    source_path: Optional[str] = None


def parse_program_md(content: str, source_path: Optional[str] = None) -> ProgramSpec:
    """Parse a program.md file into a ProgramSpec.

    Tolerant parser — extracts what it can, skips what it can't.
    """
    title = ""
    question = ""
    hypotheses: list[Hypothesis] = []
    experiments: list[Experiment] = []
    success_criteria: list[str] = []
    max_iterations = 3
    stop_when = "all_resolved"

    # Extract title from first H1
    title_match = re.search(r"^#\s+(?:Research Program:\s*)?(.+)$", content, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()

    # Extract question section
    question_match = re.search(
        r"^##\s+Question\s*\n(.*?)(?=^##|\Z)",
        content, re.MULTILINE | re.DOTALL,
    )
    if question_match:
        question = question_match.group(1).strip()

    # Extract hypotheses
    hyp_match = re.search(
        r"^##\s+Hypotheses\s*\n(.*?)(?=^##|\Z)",
        content, re.MULTILINE | re.DOTALL,
    )
    if hyp_match:
        hyp_block = hyp_match.group(1)
        for line in hyp_block.strip().split("\n"):
            line = line.strip()
            if not line or not line.startswith("-"):
                continue
            line = line.lstrip("- ").strip()
            # Parse "H1: statement | rationale: why"
            h_match = re.match(r"H\d+:\s*(.+?)(?:\|\s*rationale:\s*(.+))?$", line)
            if h_match:
                hypotheses.append(Hypothesis(
                    statement=h_match.group(1).strip(),
                    rationale=(h_match.group(2) or "").strip() or "From program.md",
                ))
            else:
                # Bare hypothesis without H# prefix
                hypotheses.append(Hypothesis(
                    statement=line,
                    rationale="From program.md",
                ))

    # Extract experiments (H3 blocks under ## Experiments)
    exp_section = re.search(
        r"^##\s+Experiments\s*\n(.*?)(?=^##(?!#)|\Z)",
        content, re.MULTILINE | re.DOTALL,
    )
    if exp_section:
        exp_blocks = re.split(r"^###\s+", exp_section.group(1), flags=re.MULTILINE)
        for block in exp_blocks:
            block = block.strip()
            if not block:
                continue
            exp = _parse_experiment_block(block, hypotheses)
            if exp:
                experiments.append(exp)

    # Extract success criteria
    crit_match = re.search(
        r"^##\s+Success Criteria\s*\n(.*?)(?=^##|\Z)",
        content, re.MULTILINE | re.DOTALL,
    )
    if crit_match:
        for line in crit_match.group(1).strip().split("\n"):
            line = line.strip().lstrip("- ").strip()
            if line:
                success_criteria.append(line)

    # Extract iteration rules
    iter_match = re.search(
        r"^##\s+Iteration Rules\s*\n(.*?)(?=^##|\Z)",
        content, re.MULTILINE | re.DOTALL,
    )
    if iter_match:
        iter_block = iter_match.group(1)
        mi = re.search(r"max_iterations:\s*(\d+)", iter_block)
        if mi:
            max_iterations = int(mi.group(1))
        sw = re.search(r"stop_when:\s*(\w+)", iter_block)
        if sw:
            stop_when = sw.group(1)

    spec = ProgramSpec(
        title=title or "Untitled Research Program",
        question=question or "No question specified",
        hypotheses=hypotheses,
        experiments=experiments,
        success_criteria=success_criteria,
        max_iterations=max_iterations,
        stop_when=stop_when,
        raw_markdown=content,
        source_path=source_path,
    )

    logger.info(
        "program.parsed",
        title=spec.title,
        hypotheses=len(spec.hypotheses),
        experiments=len(spec.experiments),
    )
    return spec


def load_program(path: str | Path) -> ProgramSpec:
    """Load and parse a program.md file from disk."""
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Program file not found: {p}")
    content = p.read_text()
    return parse_program_md(content, source_path=str(p))


def _parse_experiment_block(
    block: str, hypotheses: list[Hypothesis]
) -> Optional[Experiment]:
    """Parse a single experiment block (text after ### header)."""
    lines = block.split("\n")
    name = lines[0].strip().rstrip(":")

    # Remove E# prefix if present
    name = re.sub(r"^E\d+:\s*", "", name)

    exp_type_str = ""
    hypothesis_ref = ""
    method = ""
    sources: list[str] = []
    parameters: dict[str, Any] = {}
    in_params = False

    for line in lines[1:]:
        stripped = line.strip().lstrip("- ").strip()
        if not stripped:
            in_params = False
            continue

        if stripped.startswith("type:"):
            exp_type_str = stripped.split(":", 1)[1].strip()
            in_params = False
        elif stripped.startswith("hypothesis:"):
            hypothesis_ref = stripped.split(":", 1)[1].strip()
            in_params = False
        elif stripped.startswith("method:"):
            method = stripped.split(":", 1)[1].strip()
            in_params = False
        elif stripped.startswith("sources:"):
            raw = stripped.split(":", 1)[1].strip()
            sources = [s.strip() for s in raw.split(",") if s.strip()]
            in_params = False
        elif stripped.startswith("parameters:"):
            in_params = True
        elif in_params and ":" in stripped:
            k, v = stripped.split(":", 1)
            parameters[k.strip()] = v.strip()

    # Resolve experiment type
    type_map = {
        "data_analysis": ExperimentType.DATA_ANALYSIS,
        "computation": ExperimentType.COMPUTATION,
        "literature_review": ExperimentType.LITERATURE_REVIEW,
        "api_query": ExperimentType.API_QUERY,
        "comparison": ExperimentType.COMPARISON,
    }
    exp_type = type_map.get(exp_type_str, ExperimentType.DATA_ANALYSIS)

    # Resolve hypothesis ID
    hypothesis_id = ""
    h_idx_match = re.match(r"H(\d+)", hypothesis_ref)
    if h_idx_match:
        idx = int(h_idx_match.group(1)) - 1
        if 0 <= idx < len(hypotheses):
            hypothesis_id = hypotheses[idx].id

    if not name:
        return None

    return Experiment(
        hypothesis_id=hypothesis_id,
        experiment_type=exp_type,
        description=name,
        methodology=method,
        data_sources=sources,
        parameters=parameters,
    )
