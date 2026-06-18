"""Stage D3 — log template mining with Drain3 (logpai).

This is the engine that turns "massive volume" into "signal". Drain3 clusters
messages that differ only in their variable parts, assigning each cluster a stable
id and a template like:

    "Execution failed. Status: 503 Service Unavailable. CircuitBreaker [<*>] is OPEN..."

So 237 distinct 503 lines collapse to ONE template_id with cluster_size=237, while
the single `ConnectionTimeoutException` line is its own template with cluster_size=1.
Rarity (inverse frequency) then makes the cause trivially rankable above the flood.

We pre-mask high-cardinality tokens (ids, IPs, durations, sessions) so cosmetic
variation doesn't fragment a cluster. Drain3 runs fully in-memory, no LLM, online.
"""
from __future__ import annotations

from drain3 import TemplateMiner
from drain3.masking import MaskingInstruction
from drain3.template_miner_config import TemplateMinerConfig

# Mask variable, high-cardinality substrings BEFORE clustering so lines differing
# only in these values land in the same template. Order matters (most specific first).
_MASKING = [
    (r"user:session:\d+", "SESSION"),
    (r"cl_\d+", "CLIENT"),
    (r"\d+ms", "DURATION"),
    (r"(\d{1,3}\.){3}\d{1,3}", "IP"),
    (r"\b\d+\b", "NUM"),
]


def _build_config() -> TemplateMinerConfig:
    cfg = TemplateMinerConfig()
    cfg.masking_instructions = [
        MaskingInstruction(pattern, mask) for pattern, mask in _MASKING
    ]
    cfg.profiling_enabled = False
    return cfg


class DrainMiner:
    """Stateful wrapper. One instance mines one corpus; cluster ids are stable per run."""

    def __init__(self) -> None:
        self._miner = TemplateMiner(config=_build_config())

    def mine(self, message: str) -> tuple[str, str]:
        """Return (template_id, template_text) for a message. Online — updates clusters."""
        if not message:
            return "T0", ""
        result = self._miner.add_log_message(message)
        cid = result.get("cluster_id")
        template = result.get("template_mined", message)
        return f"T{cid}", template
