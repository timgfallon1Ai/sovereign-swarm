"""ModelLabAgent -- local model lab for the Sovereign AI swarm."""

from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)

logger = structlog.get_logger()


class ModelLabAgent(SwarmAgent):
    """Manages local models: registry, benchmarking, comparison, promotion."""

    def __init__(self, config: Any | None = None) -> None:
        self.config = config
        self._registry: Any | None = None
        self._benchmarker: Any | None = None
        self._manager: Any | None = None

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="model_lab",
            description=(
                "Local model lab agent -- manages model registry, runs benchmarks, "
                "compares models, handles download/quantize/promote lifecycle. "
                "Phase A: registry + benchmark framework. Phase B: real inference on Mac Studio."
            ),
            domains=["models", "benchmark", "quantization", "inference", "model_lab"],
            supported_intents=[
                "list_models",
                "benchmark",
                "compare_models",
                "download_model",
                "promote_model",
            ],
            capabilities=[
                "list_models",
                "benchmark",
                "compare_models",
                "download_model",
                "promote_model",
            ],
        )

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route model lab requests to the appropriate handler."""
        task = request.task.lower()

        try:
            if "benchmark" in task:
                result = await self._handle_benchmark(request)
            elif "compare" in task or "a/b" in task or "ab test" in task:
                result = await self._handle_compare(request)
            elif "download" in task:
                result = await self._handle_download(request)
            elif "promote" in task:
                result = await self._handle_promote(request)
            elif "rollback" in task:
                result = await self._handle_rollback(request)
            elif "register" in task:
                result = await self._handle_register(request)
            else:
                result = await self._handle_list(request)

            return SwarmAgentResponse(
                agent_name="model_lab",
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=0.85,
            )
        except Exception as e:
            logger.error("model_lab.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name="model_lab",
                status="error",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_list(self, request: SwarmAgentRequest) -> dict:
        registry = self._get_registry()
        active_only = request.parameters.get("active_only", False)
        models = registry.list_models(active_only=active_only)

        lines = [f"## Model Registry: {len(models)} models\n"]
        for m in models:
            status = "ACTIVE" if m.active else "inactive"
            quant = f" ({m.quantization})" if m.quantization else ""
            lines.append(
                f"- [{status}] **{m.name}**{quant} -- "
                f"{m.parameters_b}B params, ctx {m.context_length}"
            )

        if not models:
            lines.append("No models registered. Use 'register' or 'download' to add models.")

        # Show defaults
        manager = self._get_manager()
        defaults = manager.get_defaults()
        if defaults:
            lines.append("\n**Default assignments:**")
            for cap, model_name in defaults.items():
                lines.append(f"  - {cap}: {model_name}")

        return {"markdown": "\n".join(lines), "models": [m.model_dump() for m in models]}

    async def _handle_register(self, request: SwarmAgentRequest) -> dict:
        from sovereign_swarm.model_lab.models import ModelConfig

        config = ModelConfig(
            name=request.parameters.get("name", "unnamed"),
            path=request.parameters.get("path", ""),
            quantization=request.parameters.get("quantization", ""),
            context_length=request.parameters.get("context_length", 4096),
            parameters_b=request.parameters.get("parameters_b", 0.0),
            active=request.parameters.get("active", False),
            tags=request.parameters.get("tags", []),
        )

        registry = self._get_registry()
        registry.register(config)

        return {
            "markdown": f"## Model Registered: {config.name}\n"
            f"Path: {config.path}\n"
            f"Params: {config.parameters_b}B\n"
            f"Quantization: {config.quantization or 'none'}",
            "model": config.model_dump(),
        }

    async def _handle_benchmark(self, request: SwarmAgentRequest) -> dict:
        model_name = request.parameters.get("model", "")
        tasks = request.parameters.get("tasks", None)

        registry = self._get_registry()
        model = registry.get_model(model_name)

        if not model:
            # List available tasks if no model specified
            benchmarker = self._get_benchmarker()
            available = benchmarker.get_available_tasks()
            lines = ["## Available Benchmark Tasks\n"]
            for name, desc in available.items():
                lines.append(f"- **{name}**: {desc}")
            return {"markdown": "\n".join(lines), "tasks": available}

        benchmarker = self._get_benchmarker()
        suite = await benchmarker.benchmark_model(model, tasks=tasks)

        lines = [f"## Benchmark Results: {model.name}\n"]
        for r in suite.results:
            lines.append(
                f"- **{r.task}**: score={r.score:.1%}, "
                f"latency={r.latency_ms:.0f}ms, mem={r.memory_gb:.1f}GB"
            )

        avg_score = sum(r.score for r in suite.results) / len(suite.results) if suite.results else 0
        lines.append(f"\n**Average score**: {avg_score:.1%}")

        return {
            "markdown": "\n".join(lines),
            "suite": suite.model_dump(),
        }

    async def _handle_compare(self, request: SwarmAgentRequest) -> dict:
        model_a_name = request.parameters.get("model_a", "")
        model_b_name = request.parameters.get("model_b", "")

        registry = self._get_registry()
        model_a = registry.get_model(model_a_name)
        model_b = registry.get_model(model_b_name)

        if not model_a or not model_b:
            return {"markdown": "Both model_a and model_b must be registered models."}

        benchmarker = self._get_benchmarker()
        comparison = await benchmarker.compare_models(model_a, model_b)

        lines = [
            f"## Model Comparison: {comparison.model_a} vs {comparison.model_b}\n",
            f"**Overall winner**: {comparison.overall_winner}\n",
            "**By task:**",
        ]
        for task, winner in comparison.winner_by_task.items():
            lines.append(f"  - {task}: {winner}")

        return {
            "markdown": "\n".join(lines),
            "comparison": comparison.model_dump(),
        }

    async def _handle_download(self, request: SwarmAgentRequest) -> dict:
        repo_id = request.parameters.get("repo_id", "")
        quantization = request.parameters.get("quantization", "")
        name = request.parameters.get("name", "")

        if not repo_id:
            return {"markdown": "Provide a HuggingFace repo_id to download (e.g., 'meta-llama/Llama-3-8B')."}

        manager = self._get_manager()
        result = await manager.download_model(repo_id, quantization=quantization, name=name)

        return {
            "markdown": f"## Download: {repo_id}\n\n{result['message']}",
            "result": result,
        }

    async def _handle_promote(self, request: SwarmAgentRequest) -> dict:
        model_name = request.parameters.get("model", "")
        capability = request.parameters.get("capability", "")

        if not model_name or not capability:
            return {"markdown": "Provide 'model' and 'capability' to promote."}

        manager = self._get_manager()
        result = manager.promote(model_name, capability)

        prev = result.get("previous", "none")
        return {
            "markdown": f"## Model Promoted\n\n**{capability}**: {model_name} (was: {prev})",
            "result": result,
        }

    async def _handle_rollback(self, request: SwarmAgentRequest) -> dict:
        capability = request.parameters.get("capability", "")
        if not capability:
            return {"markdown": "Provide 'capability' to rollback."}

        manager = self._get_manager()
        result = manager.rollback(capability)

        if "error" in result:
            return {"markdown": f"Rollback failed: {result['error']}"}

        return {
            "markdown": f"## Rollback: {capability}\n\nRolled back to: {result['rolled_back_to']}",
            "result": result,
        }

    # ------------------------------------------------------------------
    # Lazy accessors
    # ------------------------------------------------------------------

    def _get_registry(self):
        if self._registry is None:
            from sovereign_swarm.model_lab.registry import ModelRegistry

            self._registry = ModelRegistry()
        return self._registry

    def _get_benchmarker(self):
        if self._benchmarker is None:
            from sovereign_swarm.model_lab.benchmarker import ModelBenchmarker

            self._benchmarker = ModelBenchmarker()
        return self._benchmarker

    def _get_manager(self):
        if self._manager is None:
            from sovereign_swarm.model_lab.manager import ModelManager

            self._manager = ModelManager(registry=self._get_registry())
        return self._manager
