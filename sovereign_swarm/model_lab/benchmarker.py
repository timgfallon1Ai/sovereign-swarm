"""Model benchmarking against Tim's use-case-specific tasks."""

from __future__ import annotations

import time
from typing import Any

import structlog

from sovereign_swarm.model_lab.models import (
    BenchmarkResult,
    BenchmarkSuite,
    ModelComparison,
    ModelConfig,
)

logger = structlog.get_logger()

# Benchmark task definitions with reference prompts and expected quality criteria
_BENCHMARK_TASKS: dict[str, dict[str, Any]] = {
    "trading_analysis": {
        "description": "Analyze a trading setup and provide entry/exit/risk assessment",
        "prompt": (
            "Analyze the following trading setup: AAPL is trading at $185, "
            "forming a cup-and-handle pattern on the daily chart. RSI is 58, "
            "MACD is crossing bullish. Volume has been declining in the handle. "
            "The 50-day MA is at $178. Provide entry, stop-loss, and target."
        ),
        "reference_keywords": [
            "entry", "stop", "target", "risk", "reward", "volume", "breakout"
        ],
        "max_score_keywords": 7,
    },
    "code_generation": {
        "description": "Generate Python code for data analysis",
        "prompt": (
            "Write a Python function that takes a pandas DataFrame of daily stock prices "
            "(columns: date, open, high, low, close, volume) and returns a DataFrame "
            "with added columns for 20-day SMA, 50-day SMA, RSI(14), and a signal "
            "column that is 1 when the 20-day SMA crosses above the 50-day SMA."
        ),
        "reference_keywords": [
            "def", "pandas", "rolling", "mean", "rsi", "signal", "crossover"
        ],
        "max_score_keywords": 7,
    },
    "research_summary": {
        "description": "Summarize an academic paper",
        "prompt": (
            "Summarize the key findings, methodology, and implications of a "
            "research paper titled 'Attention Is All You Need' that introduces "
            "the Transformer architecture. Focus on practical implications for "
            "NLP and computer vision."
        ),
        "reference_keywords": [
            "attention", "transformer", "self-attention", "encoder", "decoder",
            "parallel", "sequence"
        ],
        "max_score_keywords": 7,
    },
    "design_feedback": {
        "description": "Critique a UI design",
        "prompt": (
            "Review a dashboard UI that has: a dark sidebar with 12 navigation items, "
            "a main content area with 6 cards showing KPIs, a line chart below the cards, "
            "and a data table at the bottom. The color scheme is dark blue and white. "
            "Font is Inter. Provide specific actionable feedback."
        ),
        "reference_keywords": [
            "hierarchy", "spacing", "contrast", "typography", "layout", "responsive"
        ],
        "max_score_keywords": 6,
    },
    "conversation": {
        "description": "Natural dialogue quality",
        "prompt": (
            "A user asks: 'I'm feeling overwhelmed with my project deadlines. "
            "I have three major deliverables due this week and I haven't started on two of them. "
            "What should I do?' Respond naturally and helpfully."
        ),
        "reference_keywords": [
            "prioritize", "break down", "deadline", "focus", "plan"
        ],
        "max_score_keywords": 5,
    },
}


class ModelBenchmarker:
    """Runs standardized benchmarks against Tim's use cases."""

    def __init__(self, model_api: Any | None = None) -> None:
        self._model_api = model_api
        self._results: list[BenchmarkResult] = []

    def get_available_tasks(self) -> dict[str, str]:
        """Return available benchmark tasks and their descriptions."""
        return {name: task["description"] for name, task in _BENCHMARK_TASKS.items()}

    async def benchmark_model(
        self,
        model: ModelConfig,
        tasks: list[str] | None = None,
    ) -> BenchmarkSuite:
        """Run benchmark suite against a model.

        Phase A: uses keyword matching for scoring (no actual inference).
        Phase B: runs actual inference through model API and scores output quality.
        """
        tasks = tasks or list(_BENCHMARK_TASKS.keys())
        results: list[BenchmarkResult] = []

        for task_name in tasks:
            task_def = _BENCHMARK_TASKS.get(task_name)
            if not task_def:
                continue

            result = await self._run_single_benchmark(model, task_name, task_def)
            results.append(result)
            self._results.append(result)

        # Determine best overall score
        suite = BenchmarkSuite(
            name=f"benchmark_{model.name}",
            tasks=tasks,
            results=results,
            best_model=model.name,
        )

        logger.info(
            "benchmarker.suite_complete",
            model=model.name,
            tasks=len(results),
            avg_score=sum(r.score for r in results) / len(results) if results else 0,
        )
        return suite

    async def compare_models(
        self,
        model_a: ModelConfig,
        model_b: ModelConfig,
        tasks: list[str] | None = None,
    ) -> ModelComparison:
        """A/B test: run same tasks through two models and compare."""
        tasks = tasks or list(_BENCHMARK_TASKS.keys())

        suite_a = await self.benchmark_model(model_a, tasks)
        suite_b = await self.benchmark_model(model_b, tasks)

        winner_by_task: dict[str, str] = {}
        a_wins = 0
        b_wins = 0

        for task_name in tasks:
            score_a = next(
                (r.score for r in suite_a.results if r.task == task_name), 0.0
            )
            score_b = next(
                (r.score for r in suite_b.results if r.task == task_name), 0.0
            )

            if score_a > score_b:
                winner_by_task[task_name] = model_a.name
                a_wins += 1
            elif score_b > score_a:
                winner_by_task[task_name] = model_b.name
                b_wins += 1
            else:
                winner_by_task[task_name] = "tie"

        overall = model_a.name if a_wins > b_wins else model_b.name if b_wins > a_wins else "tie"

        return ModelComparison(
            model_a=model_a.name,
            model_b=model_b.name,
            tasks=tasks,
            winner_by_task=winner_by_task,
            overall_winner=overall,
        )

    async def _run_single_benchmark(
        self,
        model: ModelConfig,
        task_name: str,
        task_def: dict[str, Any],
    ) -> BenchmarkResult:
        """Run a single benchmark task.

        Phase A: stub scoring based on model metadata.
        Phase B: actual inference + quality scoring.
        """
        start = time.monotonic()

        if self._model_api:
            # Phase B: actual inference
            response = await self._model_api.generate(
                model=model.name, prompt=task_def["prompt"]
            )
            output_text = response.get("text", "")
            score = self._score_output(output_text, task_def)
            tokens_per_second = response.get("tokens_per_second", 0.0)
            memory_gb = response.get("memory_gb", 0.0)
        else:
            # Phase A: estimate scores from model config
            score = self._estimate_score(model, task_name)
            tokens_per_second = 0.0
            memory_gb = model.parameters_b * 0.6  # rough estimate

        latency_ms = (time.monotonic() - start) * 1000

        return BenchmarkResult(
            model_name=model.name,
            task=task_name,
            score=round(score, 3),
            tokens_per_second=tokens_per_second,
            memory_gb=memory_gb,
            latency_ms=round(latency_ms, 1),
        )

    @staticmethod
    def _score_output(output: str, task_def: dict[str, Any]) -> float:
        """Score model output based on reference keyword presence."""
        if not output:
            return 0.0

        keywords = task_def.get("reference_keywords", [])
        max_score = task_def.get("max_score_keywords", len(keywords))
        output_lower = output.lower()

        matched = sum(1 for kw in keywords if kw.lower() in output_lower)
        return matched / max_score if max_score else 0.0

    @staticmethod
    def _estimate_score(model: ModelConfig, task_name: str) -> float:
        """Estimate a benchmark score from model metadata (Phase A heuristic)."""
        # Larger models generally score higher; this is a rough heuristic
        base = min(0.9, 0.3 + model.parameters_b * 0.02)

        # Quantization penalty
        if "4bit" in model.quantization.lower():
            base *= 0.85
        elif "8bit" in model.quantization.lower():
            base *= 0.92

        # Task-specific adjustments
        if task_name == "code_generation" and model.parameters_b < 7:
            base *= 0.7  # small models struggle with code

        return round(min(1.0, base), 3)

    def get_all_results(self) -> list[BenchmarkResult]:
        """Return all stored benchmark results."""
        return self._results
