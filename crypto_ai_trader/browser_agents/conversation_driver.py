"""
High-level conversation driver for browser-hosted LLMs.

The goal of this module is to wrap the low-level :class:`BrowserAI` class with
logic that can:

1. Prime a model with a standard instruction set.
2. Feed incremental context chunks (either inline or via file uploads in a
   later phase).
3. Parse structured commands that the model emits (e.g. REQUEST, COMPLETE).
4. Record transcripts for downstream analysis/learning.

Phase 1 focuses on the scaffolding – no trading logic yet.  Future phases will
plug this driver into the AI trader orchestration layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
import time
from typing import TYPE_CHECKING, Callable, Dict, List, Literal, Optional

if TYPE_CHECKING:  # pragma: no cover - only for type checking
    from crypto_ai_trader.browser_ai import BrowserAI


DriverCommandType = Literal["request", "complete"]


@dataclass
class DriverCommand:
    """
    Structured directive parsed from the model's response.

    Commands follow a lightweight line-based protocol::

        REQUEST: sentiment | token=BTC | window=24h
        COMPLETE: {"action": "BUY", "confidence": 0.78}

    The ``name`` portion is always the token immediately after the verb
    (``sentiment`` or ``{"action": ...}`` in the examples above).  Additional
    pipe-delimited segments become key/value attributes.
    """

    type: DriverCommandType
    name: str
    params: Dict[str, str] = field(default_factory=dict)
    raw: str = ""


@dataclass
class DriverParseResult:
    """Return value from :meth:`BrowserConversationDriver.parse_response`."""

    raw_text: str
    commands: List[DriverCommand] = field(default_factory=list)


@dataclass
class ConversationDriverConfig:
    """Runtime options for :class:`BrowserConversationDriver`."""

    provider: str = "claude"
    model_selector: Optional[str] = None
    priming_prompt: Optional[str] = None
    response_timeout: int = 45
    session_dir: Optional[str] = None  # where cookies/local storage live
    mock_responder: Optional[Callable[[str], str]] = None


class BrowserConversationDriver:
    """
    Drives a single browser-hosted LLM conversation.

    The driver is intentionally state-light: it owns one ``BrowserAI`` instance,
    tracks a transcript, and exposes helper methods for sending prompts and
    parsing any structured directives that come back.
    """

    COMMAND_PATTERN = re.compile(r"^\s*(REQUEST|COMPLETE)\s*:(.+)$", re.IGNORECASE)

    def __init__(self, config: ConversationDriverConfig):
        self.config = config
        self.browser_ai: Optional["BrowserAI"] = None
        self.transcript: List[Dict[str, str]] = []
        self.using_mock = self.config.mock_responder is not None
        self._ensure_session_dir()

    # --------------------------------------------------------------------- #
    # Lifecycle helpers
    # --------------------------------------------------------------------- #
    def _ensure_session_dir(self) -> None:
        if not self.config.session_dir:
            base = os.path.join(os.getcwd(), ".browser_sessions")
            os.makedirs(base, exist_ok=True)
            self.config.session_dir = os.path.join(
                base, f"{self.config.provider}_session"
            )
        os.makedirs(self.config.session_dir, exist_ok=True)

    def start(self) -> bool:
        """
        Initialize the underlying browser session (if not already active).

        Returns
        -------
        bool
            True if the browser is ready for prompts.
        """
        if self.using_mock:
            return True

        if self.browser_ai and self.browser_ai.is_initialized:
            return True

        from crypto_ai_trader.browser_ai import BrowserAI

        self.browser_ai = BrowserAI(
            provider=self.config.provider,
            session_dir=self.config.session_dir,
        )
        return self.browser_ai.initialize()

    def close(self) -> None:
        """Shut down the browser session and persist cookies/storage."""
        if self.using_mock or not self.browser_ai:
            return
        try:
            self.browser_ai.cleanup()
        finally:
            self.browser_ai = None

    # --------------------------------------------------------------------- #
    # Conversation primitives
    # --------------------------------------------------------------------- #
    def send(self, prompt: str) -> DriverParseResult:
        """
        Send a prompt and parse the response for commands.

        Parameters
        ----------
        prompt:
            Text to inject into the browser conversation.
        """
        if not self.using_mock:
            if not self.browser_ai or not self.browser_ai.is_initialized:
                raise RuntimeError("Browser session not started – call start() first.")

        self.transcript.append({"role": "user", "content": prompt, "ts": self._ts()})
        if self.using_mock:
            responder = self.config.mock_responder
            if responder is None:
                raise RuntimeError("Mock responder not configured.")
            response = responder(prompt)
        else:
            response = self.browser_ai.send_prompt(
                prompt, timeout=self.config.response_timeout
            )
        if response is None:
            raise RuntimeError("Browser AI returned no response.")

        self.transcript.append(
            {"role": "assistant", "content": response, "ts": self._ts()}
        )
        return self.parse_response(response)

    def prime(self) -> Optional[DriverParseResult]:
        """
        Optionally send the configured priming prompt.

        Some conversations might only need to send incremental context, so
        this method returns ``None`` if no priming string was supplied.
        """
        if not self.config.priming_prompt:
            return None
        return self.send(self.config.priming_prompt)

    # --------------------------------------------------------------------- #
    # Parsing / utility helpers
    # --------------------------------------------------------------------- #
    def parse_response(self, text: str) -> DriverParseResult:
        """
        Extract structured commands from a raw LLM response.

        This parser deliberately stays simple for Phase 1: it scans each line
        for ``REQUEST`` or ``COMPLETE`` markers and collects any key/value
        metadata after the first pipe.  Future iterations can move to JSON or
        XML envelopes without touching callers.
        """
        commands: List[DriverCommand] = []
        for line in text.splitlines():
            match = self.COMMAND_PATTERN.match(line)
            if not match:
                continue

            verb, payload = match.groups()
            pieces = [p.strip() for p in payload.split("|") if p.strip()]
            if not pieces:
                continue

            name = pieces[0].strip() if pieces[0] else "general"
            params: Dict[str, str] = {}
            for piece in pieces[1:]:
                if "=" not in piece:
                    continue
                key, value = piece.split("=", 1)
                params[key.strip().lower()] = value.strip()

            command = DriverCommand(
                type="request" if verb.upper().startswith("REQUEST") else "complete",
                name=name,
                params=params,
                raw=line.strip(),
            )
            commands.append(command)

        return DriverParseResult(raw_text=text, commands=commands)

    @staticmethod
    def _ts() -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


__all__ = [
    "BrowserConversationDriver",
    "ConversationDriverConfig",
    "DriverCommand",
    "DriverCommandType",
    "DriverParseResult",
]
