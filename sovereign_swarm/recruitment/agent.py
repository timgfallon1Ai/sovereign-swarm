"""RecruitmentAgent -- HR and hiring operations for the swarm (GBB-focused)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog

from sovereign_swarm.recruitment.models import (
    Candidate,
    CandidateStage,
    InterviewSchedule,
    InterviewType,
    JobPosting,
)
from sovereign_swarm.protocol.swarm_agent import (
    SwarmAgent,
    SwarmAgentCard,
    SwarmAgentRequest,
    SwarmAgentResponse,
)

logger = structlog.get_logger()


class RecruitmentAgent(SwarmAgent):
    """Recruitment and HR agent.

    Creates job postings, screens resumes, schedules interviews,
    manages candidate pipelines, and generates onboarding checklists.
    Tailored for GBB roles (BJJ instructor, front desk, marketing, trainer).
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._job_builder = None
        self._screener = None
        self._onboarding = None
        # In-memory stores for demo/Phase A
        self._postings: list[JobPosting] = []
        self._candidates: list[Candidate] = []

    @property
    def card(self) -> SwarmAgentCard:
        return SwarmAgentCard(
            name="RecruitmentAgent",
            description=(
                "Recruitment and HR agent -- job postings, resume screening, "
                "interview scheduling, candidate pipeline, and onboarding "
                "checklists. Tailored for GBB roles."
            ),
            version="0.1.0",
            domains=["hr", "recruitment", "hiring", "onboarding"],
            supported_intents=[
                "create_posting",
                "screen_resumes",
                "schedule_interview",
                "onboarding_checklist",
                "candidate_pipeline",
            ],
            capabilities=[
                "create_posting",
                "screen_resumes",
                "schedule_interview",
                "onboarding_checklist",
                "candidate_pipeline",
            ],
        )

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(self, request: SwarmAgentRequest) -> SwarmAgentResponse:
        """Route an HR task to the appropriate handler."""
        task = request.task.lower()
        params = request.parameters or request.context or {}

        try:
            if any(kw in task for kw in ("job", "posting", "create post")):
                result = await self._handle_create_posting(params)
            elif any(kw in task for kw in ("screen", "resume", "rank candidate")):
                result = await self._handle_screen_resumes(params)
            elif any(kw in task for kw in ("interview", "schedule")):
                result = await self._handle_schedule_interview(params)
            elif any(kw in task for kw in ("onboard", "checklist", "new hire")):
                result = await self._handle_onboarding(params)
            elif any(kw in task for kw in ("pipeline", "candidate", "status")):
                result = await self._handle_pipeline(params)
            elif "template" in task:
                result = await self._handle_list_templates()
            else:
                result = await self._handle_pipeline(params)

            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="success",
                output=result.get("markdown", str(result)),
                data=result,
                confidence=result.get("confidence", 0.75),
            )
        except Exception as e:
            logger.error("recruitment.execute_failed", error=str(e))
            return SwarmAgentResponse(
                agent_name=self.card.name,
                status="error",
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_create_posting(self, params: dict) -> dict:
        """Create a job posting from template or custom parameters."""
        builder = self._get_job_builder()
        template = params.get("template", "")

        if template:
            posting = builder.build_from_template(
                template,
                location=params.get("location", ""),
                salary_range=params.get("salary_range", ""),
                department=params.get("department", ""),
            )
        else:
            posting = builder.build_custom(
                title=params.get("title", "Open Position"),
                description=params.get("description", ""),
                requirements=params.get("requirements", []),
                nice_to_haves=params.get("nice_to_haves", []),
                benefits=params.get("benefits", []),
                location=params.get("location", ""),
                salary_range=params.get("salary_range", ""),
                department=params.get("department", ""),
            )

        self._postings.append(posting)
        md = builder.format_posting_markdown(posting)

        return {"markdown": md, "posting_id": posting.id, "confidence": 0.8}

    async def _handle_screen_resumes(self, params: dict) -> dict:
        """Screen candidates against a job posting."""
        screener = self._get_screener()

        # Build candidates from params or use stored
        candidate_data = params.get("candidates", [])
        candidates = []
        for cd in candidate_data:
            candidates.append(
                Candidate(
                    name=cd.get("name", "Unknown"),
                    email=cd.get("email", ""),
                    resume_summary=cd.get("resume_summary", cd.get("resume", "")),
                )
            )

        if not candidates:
            candidates = self._candidates

        if not candidates:
            return {
                "markdown": "## Resume Screening\n\nNo candidates to screen.",
                "confidence": 0.5,
            }

        # Find job posting
        posting_id = params.get("posting_id", "")
        posting = None
        if posting_id:
            posting = next((p for p in self._postings if p.id == posting_id), None)
        if not posting and self._postings:
            posting = self._postings[-1]
        if not posting:
            posting = JobPosting(
                title=params.get("role", "General"),
                description=params.get("description", ""),
                requirements=params.get("requirements", []),
            )

        results = screener.screen(candidates, posting)
        md = screener.format_results_markdown(results, posting)

        return {
            "markdown": md,
            "candidates_screened": len(results),
            "top_candidates": [
                r.candidate_name for r in results if r.recommendation == "advance"
            ],
            "confidence": 0.7,
        }

    async def _handle_schedule_interview(self, params: dict) -> dict:
        """Generate an interview schedule entry."""
        schedule = InterviewSchedule(
            candidate_id=params.get("candidate_id", ""),
            candidate_name=params.get("candidate_name", ""),
            interview_datetime=datetime.fromisoformat(
                params.get("datetime", datetime.now().isoformat())
            ),
            interviewer=params.get("interviewer", ""),
            interview_type=InterviewType(params.get("type", "video")),
            location=params.get("location", ""),
            notes=params.get("notes", ""),
            duration_minutes=params.get("duration", 60),
        )

        md = (
            f"## Interview Scheduled\n\n"
            f"**Candidate:** {schedule.candidate_name}\n"
            f"**Date/Time:** {schedule.interview_datetime.strftime('%Y-%m-%d %H:%M')}\n"
            f"**Interviewer:** {schedule.interviewer}\n"
            f"**Type:** {schedule.interview_type.value.replace('_', ' ').title()}\n"
            f"**Duration:** {schedule.duration_minutes} minutes\n"
        )
        if schedule.location:
            md += f"**Location:** {schedule.location}\n"
        if schedule.notes:
            md += f"**Notes:** {schedule.notes}\n"

        return {"markdown": md, "confidence": 0.8}

    async def _handle_onboarding(self, params: dict) -> dict:
        """Generate an onboarding checklist."""
        manager = self._get_onboarding()
        employee = params.get("employee_name", params.get("name", "New Hire"))
        role = params.get("role", "general")
        start_str = params.get("start_date")
        start_date = datetime.fromisoformat(start_str) if start_str else None

        checklist = manager.generate_checklist(employee, role, start_date)
        md = manager.format_checklist_markdown(checklist)

        return {
            "markdown": md,
            "total_items": len(checklist.items),
            "confidence": 0.8,
        }

    async def _handle_pipeline(self, params: dict) -> dict:
        """Show candidate pipeline summary."""
        if not self._candidates:
            md = (
                "## Candidate Pipeline\n\n"
                "No candidates in pipeline. Use 'screen resumes' to add candidates."
            )
            return {"markdown": md, "confidence": 0.6}

        # Group by stage
        stages: dict[str, list[str]] = {}
        for c in self._candidates:
            stage_name = c.stage.value.replace("_", " ").title()
            stages.setdefault(stage_name, []).append(c.name)

        md = f"## Candidate Pipeline ({len(self._candidates)} total)\n\n"
        md += "| Stage | Candidates | Count |\n"
        md += "|-------|-----------|-------|\n"
        for stage, names in stages.items():
            md += f"| {stage} | {', '.join(names)} | {len(names)} |\n"

        return {"markdown": md, "total": len(self._candidates), "confidence": 0.7}

    async def _handle_list_templates(self) -> dict:
        """List available job posting templates."""
        builder = self._get_job_builder()
        templates = builder.get_available_templates()

        md = "## Available Job Posting Templates\n\n"
        for t in templates:
            md += f"- `{t}` -- {t.replace('_', ' ').title()}\n"
        md += "\nUse `create posting` with `template: <name>` to generate.\n"

        return {"markdown": md, "templates": templates, "confidence": 0.9}

    # ------------------------------------------------------------------
    # Lazy init
    # ------------------------------------------------------------------

    def _get_job_builder(self):
        if self._job_builder is None:
            from sovereign_swarm.recruitment.job_builder import JobBuilder

            self._job_builder = JobBuilder()
        return self._job_builder

    def _get_screener(self):
        if self._screener is None:
            from sovereign_swarm.recruitment.screening import ResumeScreener

            self._screener = ResumeScreener()
        return self._screener

    def _get_onboarding(self):
        if self._onboarding is None:
            from sovereign_swarm.recruitment.onboarding import OnboardingManager

            self._onboarding = OnboardingManager()
        return self._onboarding
