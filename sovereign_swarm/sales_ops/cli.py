"""CLI for sales_ops — minimal Typer interface for the pilot.

Usage:
    python -m sovereign_swarm.sales_ops.cli prospect --tenant atx_mats --titles "facility manager,VP ops" --limit 20
    python -m sovereign_swarm.sales_ops.cli enroll --contact-id 1 --sequence atx_distributor
    python -m sovereign_swarm.sales_ops.cli tick
    python -m sovereign_swarm.sales_ops.cli queue
    python -m sovereign_swarm.sales_ops.cli approve 1
    python -m sovereign_swarm.sales_ops.cli approve-all-safe
    python -m sovereign_swarm.sales_ops.cli pipeline --tenant atx_mats
    python -m sovereign_swarm.sales_ops.cli reply --contact-id 1
"""

from __future__ import annotations

import asyncio
import sys

try:
    import typer
except ImportError:
    typer = None  # type: ignore

from sovereign_swarm.sales_ops.agent import SalesOpsAgent
from sovereign_swarm.protocol.swarm_agent import SwarmAgentRequest


def _run(agent: SalesOpsAgent, task: str, params: dict) -> None:
    """Run a task and print the markdown output."""
    async def _go():
        req = SwarmAgentRequest(task=task, parameters=params)
        resp = await agent.execute(req)
        if resp.status == "error":
            print(f"ERROR: {resp.error}", file=sys.stderr)
            sys.exit(1)
        print(resp.output or "(no output)")
    asyncio.run(_go())


if typer is not None:
    app = typer.Typer(help="sales_ops CLI — prospect, enroll, queue, approve, pipeline.")

    @app.command()
    def prospect(
        tenant: str = typer.Option("atx_mats", help="Tenant key"),
        titles: str = typer.Option(
            "facility manager,operations manager",
            help="Comma-separated person titles",
        ),
        keywords: str = typer.Option("", help="Free-text keywords"),
        locations: str = typer.Option("", help="Comma-separated locations"),
        industries: str = typer.Option("", help="Comma-separated industries"),
        limit: int = typer.Option(10, help="Max contacts"),
    ):
        """Apollo.io prospect search → upsert contacts."""
        agent = SalesOpsAgent()
        params = {
            "tenant": tenant,
            "titles": [t.strip() for t in titles.split(",") if t.strip()],
            "keywords": keywords,
            "limit": limit,
        }
        if locations:
            params["locations"] = [s.strip() for s in locations.split(",") if s.strip()]
        if industries:
            params["industries"] = [s.strip() for s in industries.split(",") if s.strip()]
        _run(agent, "prospect", params)

    @app.command()
    def enroll(
        contact_id: int = typer.Option(..., help="Contact ID"),
        tenant: str = typer.Option("atx_mats"),
        sequence: str = typer.Option("atx_distributor"),
    ):
        """Enroll a contact in a sequence."""
        agent = SalesOpsAgent()
        _run(agent, "enroll", {
            "contact_id": contact_id,
            "tenant": tenant,
            "sequence": sequence,
        })

    @app.command()
    def tick(tenant: str = typer.Option(None)):
        """Run a sequencer tick — stage next due messages."""
        agent = SalesOpsAgent()
        _run(agent, "tick", {"tenant": tenant} if tenant else {})

    @app.command()
    def queue(tenant: str = typer.Option(None)):
        """List all messages pending approval."""
        agent = SalesOpsAgent()
        _run(agent, "queue", {"tenant": tenant} if tenant else {})

    @app.command()
    def approve(message_id: int):
        """Approve + send a specific message."""
        agent = SalesOpsAgent()
        _run(agent, "approve", {"message_id": message_id})

    @app.command("approve-all-safe")
    def approve_all_safe(tenant: str = typer.Option(None)):
        """Auto-approve all low-risk staged messages (non-pricing, non-SMS)."""
        agent = SalesOpsAgent()
        _run(agent, "approve safe", {"tenant": tenant} if tenant else {})

    @app.command()
    def skip(message_id: int, reason: str = typer.Option("")):
        """Skip a message."""
        agent = SalesOpsAgent()
        _run(agent, "skip", {"message_id": message_id, "reason": reason})

    @app.command()
    def pipeline(tenant: str = typer.Option("atx_mats")):
        """Show pipeline summary for a tenant."""
        agent = SalesOpsAgent()
        _run(agent, "pipeline", {"tenant": tenant})

    @app.command()
    def reply(
        contact_id: int = typer.Option(..., help="Contact who replied"),
        reason: str = typer.Option("reply_received"),
    ):
        """Pause a contact's enrollments (reply received — hand to human)."""
        agent = SalesOpsAgent()
        _run(agent, "record_reply", {"contact_id": contact_id, "reason": reason})

    def main():
        app()
else:
    def main():
        print("Install typer: pip install typer", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
