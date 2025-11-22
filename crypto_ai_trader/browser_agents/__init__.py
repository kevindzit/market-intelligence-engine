"""
Browser agent orchestration package.

This namespace houses higher-level conversation drivers that sit on top of
``crypto_ai_trader.browser_ai.BrowserAI``.  Nothing in here mutates the
original browser_llm console utility; instead we expose programmatic helpers
for the autonomous trading stack.
"""

from .conversation_driver import (
    BrowserConversationDriver,
    ConversationDriverConfig,
    DriverCommand,
    DriverCommandType,
    DriverParseResult,
)
try:
    from .data_interface import BrowserDataInterface
except Exception:  # pragma: no cover - optional dependency (psycopg2)
    BrowserDataInterface = None
from .conversation_orchestrator import (
    ConversationOrchestrator,
    OrchestratorResult,
    build_data_orchestrator,
    build_demo_orchestrator,
)
from .decision_logger import BrowserDecisionLogger

__all__ = [
    "BrowserConversationDriver",
    "ConversationDriverConfig",
    "DriverCommand",
    "DriverCommandType",
    "DriverParseResult",
    "BrowserDataInterface",
    "ConversationOrchestrator",
    "OrchestratorResult",
    "build_demo_orchestrator",
    "build_data_orchestrator",
    "BrowserDecisionLogger",
]
