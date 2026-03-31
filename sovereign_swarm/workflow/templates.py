"""Pre-built workflow templates for common automations."""

from __future__ import annotations

from sovereign_swarm.workflow.models import (
    ActionType,
    TriggerType,
    Workflow,
    WorkflowAction,
    WorkflowStep,
    WorkflowTrigger,
)


class WorkflowTemplates:
    """Factory for common workflow templates."""

    @staticmethod
    def daily_research_digest() -> Workflow:
        """Daily 7 AM: search knowledge base for new papers, summarize, email to Tim."""
        return Workflow(
            name="daily_research_digest",
            description="Search knowledge base for new papers, summarize, and email digest",
            trigger=WorkflowTrigger(
                type=TriggerType.SCHEDULE,
                config={"cron": "0 7 * * *"},
            ),
            steps=[
                WorkflowStep(
                    name="search_new_papers",
                    action=WorkflowAction(
                        type=ActionType.RUN_AGENT,
                        config={
                            "agent": "curation",
                            "task": "find new papers from last 24 hours",
                        },
                    ),
                    on_success="summarize_papers",
                ),
                WorkflowStep(
                    name="summarize_papers",
                    action=WorkflowAction(
                        type=ActionType.RUN_AGENT,
                        config={
                            "agent": "document_intel",
                            "task": "summarize the new research papers",
                        },
                    ),
                    on_success="email_digest",
                ),
                WorkflowStep(
                    name="email_digest",
                    action=WorkflowAction(
                        type=ActionType.SEND_MESSAGE,
                        config={
                            "channel": "email",
                            "recipient": "tim",
                            "subject": "Daily Research Digest",
                        },
                    ),
                ),
            ],
        )

    @staticmethod
    def trade_alert() -> Workflow:
        """Event-driven: on trade execution, log and notify if significant."""
        return Workflow(
            name="trade_alert",
            description="Log trade to episodic memory; notify if P&L is significant",
            trigger=WorkflowTrigger(
                type=TriggerType.EVENT,
                config={"event": "trade_executed"},
            ),
            steps=[
                WorkflowStep(
                    name="log_trade",
                    action=WorkflowAction(
                        type=ActionType.UPDATE_DATABASE,
                        config={
                            "table": "episodic_memory",
                            "operation": "insert_trade_event",
                        },
                    ),
                    on_success="check_significance",
                ),
                WorkflowStep(
                    name="check_significance",
                    action=WorkflowAction(
                        type=ActionType.RUN_AGENT,
                        config={
                            "agent": "personal_finance",
                            "task": "evaluate trade P&L significance",
                        },
                    ),
                    conditions={"always": True},
                    on_success="notify_slack",
                ),
                WorkflowStep(
                    name="notify_slack",
                    action=WorkflowAction(
                        type=ActionType.SEND_MESSAGE,
                        config={
                            "channel": "slack",
                            "message": "Significant trade executed -- check dashboard",
                        },
                    ),
                ),
            ],
        )

    @staticmethod
    def new_client_onboarding() -> Workflow:
        """Manual trigger: create tenant, provision DBs, send welcome, schedule intro."""
        return Workflow(
            name="new_client_onboarding",
            description="Full client onboarding: tenant creation, DB provisioning, welcome email, intro call",
            trigger=WorkflowTrigger(
                type=TriggerType.MANUAL,
                config={},
            ),
            steps=[
                WorkflowStep(
                    name="create_tenant",
                    action=WorkflowAction(
                        type=ActionType.API_CALL,
                        config={
                            "url": "/api/tenants",
                            "method": "POST",
                        },
                    ),
                    on_success="provision_databases",
                ),
                WorkflowStep(
                    name="provision_databases",
                    action=WorkflowAction(
                        type=ActionType.UPDATE_DATABASE,
                        config={
                            "operation": "provision_tenant_schema",
                        },
                    ),
                    on_success="send_welcome",
                ),
                WorkflowStep(
                    name="send_welcome",
                    action=WorkflowAction(
                        type=ActionType.SEND_MESSAGE,
                        config={
                            "channel": "email",
                            "template": "welcome_email",
                        },
                    ),
                    on_success="schedule_intro",
                ),
                WorkflowStep(
                    name="schedule_intro",
                    action=WorkflowAction(
                        type=ActionType.RUN_AGENT,
                        config={
                            "agent": "calendar",
                            "task": "schedule intro call with new client",
                        },
                    ),
                ),
            ],
        )

    @staticmethod
    def weekly_report() -> Workflow:
        """Weekly Friday: aggregate P&L, system health, KB growth, generate report."""
        return Workflow(
            name="weekly_report",
            description="Weekly aggregate: P&L, system health, knowledge base growth, final report",
            trigger=WorkflowTrigger(
                type=TriggerType.SCHEDULE,
                config={"cron": "0 17 * * 5"},  # Friday 5 PM
            ),
            steps=[
                WorkflowStep(
                    name="aggregate_pnl",
                    action=WorkflowAction(
                        type=ActionType.RUN_AGENT,
                        config={
                            "agent": "personal_finance",
                            "task": "generate weekly P&L summary",
                        },
                    ),
                    on_success="system_health",
                ),
                WorkflowStep(
                    name="system_health",
                    action=WorkflowAction(
                        type=ActionType.RUN_AGENT,
                        config={
                            "agent": "monitoring",
                            "task": "generate weekly system health summary",
                        },
                    ),
                    on_success="kb_growth",
                ),
                WorkflowStep(
                    name="kb_growth",
                    action=WorkflowAction(
                        type=ActionType.RUN_AGENT,
                        config={
                            "agent": "curation",
                            "task": "report on knowledge base growth this week",
                        },
                    ),
                    on_success="generate_report",
                ),
                WorkflowStep(
                    name="generate_report",
                    action=WorkflowAction(
                        type=ActionType.RUN_AGENT,
                        config={
                            "agent": "document_intel",
                            "task": "compile weekly report from all sections",
                        },
                    ),
                ),
            ],
        )

    @staticmethod
    def content_calendar() -> Workflow:
        """Weekly Monday: generate social content plan, create drafts, queue for approval."""
        return Workflow(
            name="content_calendar",
            description="Weekly content calendar: generate plan, draft posts, queue for approval",
            trigger=WorkflowTrigger(
                type=TriggerType.SCHEDULE,
                config={"cron": "0 9 * * 1"},  # Monday 9 AM
            ),
            steps=[
                WorkflowStep(
                    name="generate_plan",
                    action=WorkflowAction(
                        type=ActionType.RUN_AGENT,
                        config={
                            "agent": "content",
                            "task": "generate weekly social content plan based on current projects",
                        },
                    ),
                    on_success="create_drafts",
                ),
                WorkflowStep(
                    name="create_drafts",
                    action=WorkflowAction(
                        type=ActionType.RUN_AGENT,
                        config={
                            "agent": "content",
                            "task": "create draft posts from content plan",
                        },
                    ),
                    on_success="queue_approval",
                ),
                WorkflowStep(
                    name="queue_approval",
                    action=WorkflowAction(
                        type=ActionType.SEND_MESSAGE,
                        config={
                            "channel": "slack",
                            "message": "Weekly content drafts ready for review",
                        },
                    ),
                ),
            ],
        )

    @classmethod
    def list_templates(cls) -> list[dict[str, str]]:
        """Return metadata for all available templates."""
        return [
            {
                "name": "daily_research_digest",
                "description": "Daily search and summarize new research papers",
                "trigger": "schedule (daily 7 AM)",
            },
            {
                "name": "trade_alert",
                "description": "Log and notify on significant trade execution",
                "trigger": "event (trade_executed)",
            },
            {
                "name": "new_client_onboarding",
                "description": "Full client onboarding workflow",
                "trigger": "manual",
            },
            {
                "name": "weekly_report",
                "description": "Weekly P&L, health, and growth report",
                "trigger": "schedule (weekly Friday)",
            },
            {
                "name": "content_calendar",
                "description": "Weekly content planning and drafting",
                "trigger": "schedule (weekly Monday)",
            },
        ]

    @classmethod
    def get_template(cls, name: str) -> Workflow | None:
        """Retrieve a template workflow by name."""
        factory_map = {
            "daily_research_digest": cls.daily_research_digest,
            "trade_alert": cls.trade_alert,
            "new_client_onboarding": cls.new_client_onboarding,
            "weekly_report": cls.weekly_report,
            "content_calendar": cls.content_calendar,
        }
        factory = factory_map.get(name)
        return factory() if factory else None
