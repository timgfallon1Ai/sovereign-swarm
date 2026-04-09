"""CLI entry point for sovereign-swarm."""

from __future__ import annotations

import argparse
import asyncio
import sys

from sovereign_swarm import __version__


def _print_header() -> None:
    print(f"sovereign-swarm v{__version__}")
    print()


async def _cmd_status(args: argparse.Namespace) -> None:
    """Show active graphs, agent count, patch count."""
    from sovereign_swarm.audit.store import AuditStore
    from sovereign_swarm.config import get_settings

    settings = get_settings()
    _print_header()

    print(f"Data dir:   {settings.data_dir}")
    print(f"Fast model: {settings.fast_model}")
    print(f"Slow model: {settings.slow_model}")
    print()

    store = AuditStore(db_path=settings.data_dir / "swarm_audit.db")
    try:
        await store.initialize()
        recent = await store.query(limit=10)
        print(f"Recent audit entries: {len(recent)}")
        for entry in recent[:5]:
            print(f"  [{entry.timestamp:%Y-%m-%d %H:%M}] {entry.event_type} | {entry.agent_name} | {entry.action}")
    except Exception as e:
        print(f"Audit store not available: {e}")
    finally:
        await store.close()


async def _cmd_agents(args: argparse.Namespace) -> None:
    """List registered agents."""
    from sovereign_swarm.protocol.registry import bootstrap_default_registry

    _print_header()

    registry = bootstrap_default_registry()
    agents = registry.list_agents()
    if not agents:
        print("No agents registered (bootstrap skipped everything).")
        return
    print(f"{len(agents)} agent(s) registered:\n")
    for card in agents:
        print(f"  {card.name} (v{card.version}) — {card.description}")
        if card.domains:
            print(f"    Domains: {', '.join(card.domains)}")
        if card.supported_intents:
            print(f"    Intents: {', '.join(card.supported_intents)}")


async def _cmd_patches(args: argparse.Namespace) -> None:
    """List skill patches with stats."""
    _print_header()
    print("Skill patch store not yet implemented — coming in sovereign_swarm.learning")


async def _cmd_graph_status(args: argparse.Namespace) -> None:
    """Show DAG with node statuses."""
    from sovereign_swarm.audit.store import AuditStore
    from sovereign_swarm.config import get_settings

    _print_header()

    graph_id = args.graph_id
    print(f"Graph: {graph_id}")
    print()

    settings = get_settings()
    store = AuditStore(db_path=settings.data_dir / "swarm_audit.db")
    try:
        await store.initialize()
        entries = await store.query(filters={"graph_id": graph_id}, limit=50)
        if not entries:
            print("  No audit entries found for this graph.")
            return
        for entry in entries:
            print(
                f"  [{entry.timestamp:%H:%M:%S}] {entry.event_type:20s} "
                f"agent={entry.agent_name:20s} status={entry.status}"
            )
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await store.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sovereign-swarm",
        description="Persistent adaptive learning multi-agent swarm",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Show active graphs, agent count, patch count")
    sub.add_parser("agents", help="List registered agents")
    sub.add_parser("patches", help="List skill patches with stats")

    gs = sub.add_parser("graph-status", help="Show DAG with node statuses")
    gs.add_argument("graph_id", help="Graph ID to inspect")

    args = parser.parse_args()

    dispatch = {
        "status": _cmd_status,
        "agents": _cmd_agents,
        "patches": _cmd_patches,
        "graph-status": _cmd_graph_status,
    }

    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    asyncio.run(handler(args))


if __name__ == "__main__":
    main()
