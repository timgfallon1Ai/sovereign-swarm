"""Simple template engine for outbound message templates."""

from __future__ import annotations

from sovereign_swarm.communication.models import Channel, MessageTemplate


class TemplateEngine:
    """Render message templates with variable substitution."""

    def __init__(self) -> None:
        self._templates: dict[str, MessageTemplate] = {}
        self._load_defaults()

    def render(self, template_name: str, variables: dict[str, str]) -> tuple[str, str]:
        """Render a template, return (subject, body)."""
        template = self._templates.get(template_name)
        if not template:
            raise ValueError(f"Template '{template_name}' not found")
        subject = template.subject_template
        body = template.body_template
        for key, value in variables.items():
            placeholder = "{{" + key + "}}"
            subject = subject.replace(placeholder, str(value))
            body = body.replace(placeholder, str(value))
        return subject, body

    def register(self, template: MessageTemplate) -> None:
        """Register a custom template."""
        self._templates[template.name] = template

    def list_templates(self) -> list[str]:
        """Return names of all registered templates."""
        return list(self._templates.keys())

    def get_template(self, name: str) -> MessageTemplate | None:
        return self._templates.get(name)

    def _load_defaults(self) -> None:
        """Load default message templates."""
        defaults = [
            MessageTemplate(
                name="welcome_client",
                channel=Channel.EMAIL,
                subject_template="Welcome, {{client_name}}!",
                body_template=(
                    "Hi {{client_name}},\n\n"
                    "Welcome aboard! I'm excited to start working together.\n\n"
                    "Here's a quick summary of what we discussed:\n"
                    "{{summary}}\n\n"
                    "Next steps: {{next_steps}}\n\n"
                    "Best,\nTim"
                ),
                variables=["client_name", "summary", "next_steps"],
            ),
            MessageTemplate(
                name="meeting_reminder",
                channel=Channel.EMAIL,
                subject_template="Reminder: {{meeting_title}} on {{date}}",
                body_template=(
                    "Hi {{recipient_name}},\n\n"
                    "Just a friendly reminder about our upcoming meeting:\n\n"
                    "  Title: {{meeting_title}}\n"
                    "  Date: {{date}}\n"
                    "  Time: {{time}}\n"
                    "  Location: {{location}}\n\n"
                    "{{agenda}}\n\n"
                    "See you there!\nTim"
                ),
                variables=["recipient_name", "meeting_title", "date", "time", "location", "agenda"],
            ),
            MessageTemplate(
                name="trade_alert",
                channel=Channel.SLACK,
                subject_template="Trade Alert: {{symbol}} {{action}}",
                body_template=(
                    "**Trade Executed**\n"
                    "Symbol: {{symbol}}\n"
                    "Action: {{action}}\n"
                    "Quantity: {{quantity}}\n"
                    "Price: {{price}}\n"
                    "Account: {{account}}\n"
                    "Notes: {{notes}}"
                ),
                variables=["symbol", "action", "quantity", "price", "account", "notes"],
            ),
            MessageTemplate(
                name="weekly_report",
                channel=Channel.EMAIL,
                subject_template="Weekly Report: {{week_of}}",
                body_template=(
                    "Hi {{recipient_name}},\n\n"
                    "Here's the weekly summary for {{week_of}}:\n\n"
                    "## Highlights\n{{highlights}}\n\n"
                    "## Metrics\n{{metrics}}\n\n"
                    "## Next Week\n{{next_week}}\n\n"
                    "Best,\nTim"
                ),
                variables=["recipient_name", "week_of", "highlights", "metrics", "next_week"],
            ),
            MessageTemplate(
                name="error_notification",
                channel=Channel.SLACK,
                subject_template="Error: {{service_name}}",
                body_template=(
                    "**System Alert**\n"
                    "Service: {{service_name}}\n"
                    "Error: {{error_message}}\n"
                    "Severity: {{severity}}\n"
                    "Timestamp: {{timestamp}}\n"
                    "Action Required: {{action_required}}"
                ),
                variables=["service_name", "error_message", "severity", "timestamp", "action_required"],
            ),
            MessageTemplate(
                name="gbb_class_reminder",
                channel=Channel.SMS,
                subject_template="GBB Class Reminder",
                body_template=(
                    "Hey! Reminder: GBB class at {{time}} today ({{date}}). "
                    "Topic: {{topic}}. Don't forget to bring {{materials}}."
                ),
                variables=["time", "date", "topic", "materials"],
            ),
        ]
        for t in defaults:
            self._templates[t.name] = t
