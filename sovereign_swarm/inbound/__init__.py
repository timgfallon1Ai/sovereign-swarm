"""Inbound email handling — SendGrid Inbound Parse + matcher + router + publish gate."""

from sovereign_swarm.inbound.matcher import InboundMatch, match_inbound
from sovereign_swarm.inbound.publish_gate import (
    GateAction,
    GateTier,
    PublishDecision,
    decide,
)
from sovereign_swarm.inbound.router import InboundRouter
from sovereign_swarm.inbound.sendgrid_parser import InboundEmail, parse_sendgrid_webhook

__all__ = [
    "GateAction",
    "GateTier",
    "InboundEmail",
    "InboundMatch",
    "InboundRouter",
    "PublishDecision",
    "decide",
    "match_inbound",
    "parse_sendgrid_webhook",
]
