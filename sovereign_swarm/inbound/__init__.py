"""Inbound email handling — SendGrid Inbound Parse + matcher + router."""

from sovereign_swarm.inbound.matcher import InboundMatch, match_inbound
from sovereign_swarm.inbound.router import InboundRouter
from sovereign_swarm.inbound.sendgrid_parser import InboundEmail, parse_sendgrid_webhook

__all__ = [
    "InboundEmail",
    "InboundMatch",
    "InboundRouter",
    "match_inbound",
    "parse_sendgrid_webhook",
]
