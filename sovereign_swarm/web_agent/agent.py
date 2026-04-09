"""WebAgent — swarm-protocol wrapper around the UI-TARS VLM backend.

Exposes GUI/web visual understanding as a SwarmAgent so it can be dispatched
by the swarm runtime alongside ScientistAgent, SynesthesiaAgent, etc.

Supported intents:
  - describe : general image/screenshot description
  - locate   : ground an element description to (x, y) pixel coordinates
  - answer   : free-form visual Q&A

Request format (SwarmAgentRequest.parameters):
  image       : str path to image (required)
  intent      : "describe" | "locate" | "answer" (default: "describe")
  element     : str (required for intent="locate")
  question    : str (required for intent="answer")
  max_tokens  : int (optional)
"""
from __future__ import annotations

from typing import Any

import structlog

from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)
from sovereign_swarm.web_agent.backend import DEFAULT_MODEL, UITarsBackend, VLMResponse

logger = structlog.get_logger()


class WebAgent(SwarmAgent):
    """Visual understanding / web-UI agent backed by UI-TARS-1.5-7B-4bit MLX."""

    def __init__(
        self,
        model_path: str = DEFAULT_MODEL,
        backend: UITarsBackend | None = None,
        config: Any | None = None,
    ) -> None:
        self.config = config
        self.backend = backend or UITarsBackend(model_path=model_path)

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="web_agent",
            description=(
                "Visual understanding and GUI grounding agent -- describes "
                "screenshots, grounds natural-language element references to "
                "pixel coordinates, answers visual questions. Backed by "
                "UI-TARS-1.5-7B-4bit running on MLX."
            ),
            domains=["web", "gui", "vision", "screenshot", "browser"],
            supported_intents=[
                "describe",
                "describe_image",
                "locate",
                "locate_element",
                "ground",
                "answer",
                "visual_qa",
                "extract_text",
                "read_ui",
            ],
            capabilities=[
                "image_description",
                "gui_grounding",
                "visual_question_answering",
                "coordinate_extraction",
            ],
        )

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        params = request.parameters or {}
        image = params.get("image")
        if not image:
            return SwarmAgentResponse(
                agent_name="web_agent",
                status="error",
                error="missing required parameter: image (path to image file)",
            )

        intent = (params.get("intent") or self._infer_intent(request.task)).lower()
        max_tokens = int(params.get("max_tokens") or 128)

        try:
            if intent in {"locate", "locate_element", "ground"}:
                element = params.get("element") or request.task
                if not element:
                    return SwarmAgentResponse(
                        agent_name="web_agent",
                        status="error",
                        error="intent=locate requires 'element' parameter or task text",
                    )
                resp = self.backend.locate(image, element, max_tokens=max_tokens)
            elif intent in {"answer", "visual_qa"}:
                question = params.get("question") or request.task
                if not question:
                    return SwarmAgentResponse(
                        agent_name="web_agent",
                        status="error",
                        error="intent=answer requires 'question' parameter or task text",
                    )
                resp = self.backend.answer(image, question, max_tokens=max_tokens)
            else:
                resp = self.backend.describe(image, max_tokens=max_tokens)
        except Exception as exc:  # noqa: BLE001
            logger.exception("web_agent.execute_failed", intent=intent, image=image)
            return SwarmAgentResponse(
                agent_name="web_agent",
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )

        return self._response_from_vlm(resp, intent)

    @staticmethod
    def _infer_intent(task: str) -> str:
        t = (task or "").lower()
        if any(kw in t for kw in ("where", "locate", "click", "coordinate", "find the", "point to")):
            return "locate"
        if any(kw in t for kw in ("?", "what", "how", "which", "who", "why")):
            return "answer"
        return "describe"

    @staticmethod
    def _response_from_vlm(resp: VLMResponse, intent: str) -> SwarmAgentResponse:
        data = {
            "text": resp.text,
            "model": resp.model,
            "time_s": resp.time_s,
            "n_tokens": resp.n_tokens,
            "tok_s": resp.tok_s,
            "intent": intent,
        }
        if resp.coordinates is not None:
            data["coordinates"] = {"x": resp.coordinates[0], "y": resp.coordinates[1]}
        # Confidence is a rough proxy — grounding with explicit coords is the
        # strongest signal, descriptions are middling, empty outputs are low.
        if resp.coordinates is not None:
            confidence = 0.9
        elif resp.text.strip():
            confidence = 0.7
        else:
            confidence = 0.0
        return SwarmAgentResponse(
            agent_name="web_agent",
            status="success",
            output=resp.text.strip(),
            data=data,
            confidence=confidence,
            tokens_used=resp.n_tokens,
        )
