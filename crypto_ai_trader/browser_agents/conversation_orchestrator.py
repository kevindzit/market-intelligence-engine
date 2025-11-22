"""
Lightweight orchestration layer for browser-based LLM conversations.

This module keeps Phase 1 deliberately simple: it shows how to glue the
``BrowserConversationDriver`` to an application loop that can feed context,
process ``REQUEST`` commands, and stop once the model issues a ``COMPLETE``.

Future iterations will swap out the placeholder request handlers with real
database adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .conversation_driver import (
    BrowserConversationDriver,
    ConversationDriverConfig,
    DriverCommand,
    DriverParseResult,
)
from .data_interface import BrowserDataInterface

RequestHandler = Callable[[DriverCommand], str]
CompletionValidator = Callable[[DriverCommand], Optional[str]]


@dataclass
class OrchestratorResult:
    """Return payload from :meth:`ConversationOrchestrator.run`."""

    completion: Optional[DriverCommand]
    transcript: List[Dict[str, str]]


@dataclass
class ConversationOrchestrator:
    """
    Runs a single conversation end-to-end.

    Parameters
    ----------
    driver_config:
        Configuration passed to :class:`BrowserConversationDriver`.
    handlers:
        Mapping from command name (case-insensitive) to a function that returns
        the payload we should send back to the LLM.
    """

    driver_config: ConversationDriverConfig
    handlers: Dict[str, RequestHandler] = field(default_factory=dict)
    completion_validator: Optional[CompletionValidator] = None

    NEXT_ACTION_INSTRUCTION = (
        "Respond with exactly one line: either `REQUEST: <data_type> | token={token} | window=<duration>` for more data "
        "or `COMPLETE: decision | action=<BUY/SELL/HOLD/SHORT> | confidence=<0-1> | position_size=<0-1> | "
        "stop_loss_pct=<value> | take_profit_pct=<value> | reasoning=<short text>`."
    )

    PROTOCOL_MESSAGES = (
        "FORMAT REMINDER: Reply with a single `REQUEST` for more data or a `COMPLETE` decision line (token={token}).",
        "FORMAT ERROR: Your last message was ignored because it was not a REQUEST or COMPLETE. Respond now with one valid line.",
        "FINAL WARNING: Immediately send either `REQUEST: <data_type> | token={token} | window=<duration>` or the `COMPLETE` schema. Any other text will terminate the session.",
    )

    def __post_init__(self) -> None:
        self.driver = BrowserConversationDriver(self.driver_config)
        self.current_token: Optional[str] = None
        self.default_handler: Optional[RequestHandler] = None
        self.requests_served: int = 0

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def register_handler(self, name: str, handler: RequestHandler) -> None:
        self.handlers[name.lower()] = handler

    def set_default_handler(self, handler: RequestHandler) -> None:
        self.default_handler = handler

    def set_completion_validator(self, validator: CompletionValidator) -> None:
        self.completion_validator = validator

    def run(
        self,
        initial_prompt: str,
        auto_prime: bool = True,
        token: Optional[str] = None,
    ) -> OrchestratorResult:
        """
        Execute the conversation until a ``COMPLETE`` command appears.

        Returns
        -------
        OrchestratorResult
            Includes the final ``COMPLETE`` command (if any) plus the full
            transcript captured by the driver.
        """
        self.current_token = token
        self.driver.start()
        if auto_prime:
            self.driver.prime()

        initial_payload = self._format_for_llm(
            initial_prompt, enforce_protocol=True, token=self.current_token
        )
        parse_result = self.driver.send(initial_payload)
        idle_attempts = 0
        max_idle_attempts = len(self.PROTOCOL_MESSAGES)

        while True:
            completion = self._find_completion(parse_result)
            if completion:
                if self.completion_validator:
                    error_message = self.completion_validator(completion)
                    if error_message:
                        error_payload = self._format_for_llm(
                            error_message, enforce_protocol=True
                        )
                        parse_result = self.driver.send(error_payload)
                        continue
                return OrchestratorResult(
                    completion=completion, transcript=self.driver.transcript
                )

            request = self._next_request(parse_result)
            if not request:
                if idle_attempts >= max_idle_attempts:
                    return OrchestratorResult(
                        completion=None, transcript=self.driver.transcript
                    )

                message_template = self._protocol_prompt(idle_attempts)
                idle_attempts += 1
                reminder_payload = self._format_for_llm(
                    message_template,
                    enforce_protocol=True,
                )
                parse_result = self.driver.send(reminder_payload)
                continue

            idle_attempts = 0

            payload = self._handle_request(request)
            if not payload:
                payload = (
                    f"DATA: Unable to satisfy request '{request.name}'. "
                    "Please proceed with available information."
                )

            formatted_payload = self._format_for_llm(
                payload, enforce_protocol=True, token=self.current_token
            )
            parse_result = self.driver.send(formatted_payload)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _handle_request(self, command: DriverCommand) -> str:
        handler = self.handlers.get(command.name.lower())
        if handler:
            self.requests_served += 1
            return handler(command)
        if self.default_handler:
            if 'token' not in command.params and self.current_token:
                command.params['token'] = self.current_token
            self.requests_served += 1
            return self.default_handler(command)

        params_str = ", ".join(f"{k}={v}" for k, v in command.params.items())
        return (
            f"DATA: Placeholder response for {command.name}"
            + (f" ({params_str})" if params_str else "")
        )

    @staticmethod
    def _find_completion(result: DriverParseResult) -> Optional[DriverCommand]:
        for command in result.commands:
            if command.type == "complete":
                return command
        return None

    @staticmethod
    def _next_request(result: DriverParseResult) -> Optional[DriverCommand]:
        for command in result.commands:
            if command.type == "request":
                return command
        return None

    def _protocol_prompt(self, idle_attempt: int) -> str:
        """
        Provide a progressively firmer reminder, plus a concrete example the model can copy.
        """

        token_hint = self.current_token or "<TOKEN>"
        index = min(idle_attempt, len(self.PROTOCOL_MESSAGES) - 1)
        base = self.PROTOCOL_MESSAGES[index].format(token=token_hint)

        if self.requests_served == 0:
            example = (
                f"Example (copy this literally to continue): "
                f"`REQUEST: summary | token={token_hint} | window=6h`."
            )
        else:
            example = (
                "Example completion if data is limited: "
                "`COMPLETE: decision | action=HOLD | confidence=0.25 | "
                "position_size=0.10 | stop_loss_pct=3 | take_profit_pct=6 | "
                "reasoning=insufficient data`."
            )
        return f"{base} {example}"

    def _format_for_llm(
        self, text: str, enforce_protocol: bool = True, token: Optional[str] = None
    ) -> str:
        """
        Append the standard protocol reminder so the LLM answers with REQUEST/COMPLETE lines.
        """

        clean = (text or "").strip()
        if not clean or not enforce_protocol:
            return clean

        lowered = clean.lower()
        if "next action:" in lowered and "request" in lowered and "complete" in lowered:
            return clean

        token_hint = token or self.current_token or "<TOKEN>"
        return f"{clean}\n\nNEXT ACTION: {self.NEXT_ACTION_INSTRUCTION.format(token=token_hint)}"


# ---------------------------------------------------------------------- #
# Simple mock responder for offline testing
# ---------------------------------------------------------------------- #
class DemoResponder:
    """
    Tiny state machine that mimics an LLM for local testing.

    Sequence:
        1) On priming prompt -> acknowledges instructions.
        2) On first data chunk -> asks for sentiment.
        3) After sentiment provided -> returns a COMPLETE command.
    """

    def __init__(self):
        self.stage = 0

    def __call__(self, _: str) -> str:
        if self.stage == 0:
            self.stage += 1
            return "REQUEST: sentiment | token=BTC | window=24h"
        self.stage += 1
        return (
            "COMPLETE: decision | action=BUY | confidence=0.78 | position_size=0.40 | "
            "stop_loss_pct=3 | take_profit_pct=6 | reasoning=Momentum continuation"
        )


def build_demo_orchestrator() -> ConversationOrchestrator:
    """
    Convenience helper that wires the orchestrator to the demo responder.

    Useful for unit tests or for validating the orchestration loop without
    launching a real browser session.
    """

    responder = DemoResponder()
    driver_config = ConversationDriverConfig(
        provider="claude",
        priming_prompt="You are a demo trading agent. Follow the command protocol.",
        mock_responder=responder,
    )

    orchestrator = ConversationOrchestrator(driver_config=driver_config)

    def sentiment_handler(command: DriverCommand) -> str:
        token = command.params.get("token", "UNKNOWN")
        window = command.params.get("window", "1h")
        return (
            "CONTEXT: Sentiment snapshot\n"
            f"- Token: {token}\n"
            f"- Window: {window}\n"
            "- Avg Sentiment: +0.42\n"
            "- Tweet Count: 1,234\n"
        )

    orchestrator.register_handler("sentiment", sentiment_handler)
    orchestrator.set_completion_validator(_decision_completion_validator)
    return orchestrator


__all__ = [
    "ConversationOrchestrator",
    "OrchestratorResult",
    "build_demo_orchestrator",
    "build_data_orchestrator",
    "build_verification_orchestrator",
]


def build_data_orchestrator(
    data_intelligence,
    provider: str = "claude",
    priming_prompt: Optional[str] = None,
    session_dir: Optional[str] = None,
) -> ConversationOrchestrator:
    """
    Construct an orchestrator wired to the production data interface.
    """

    interface = BrowserDataInterface(data_intelligence)
    driver_config = ConversationDriverConfig(
        provider=provider,
        priming_prompt=priming_prompt,
        session_dir=session_dir,
    )
    orchestrator = ConversationOrchestrator(driver_config=driver_config)

    def make_handler(command_name: str) -> RequestHandler:
        return lambda command: interface.handle_command(command_name, command.params)

    orchestrator.register_handler("sentiment", make_handler("sentiment"))
    orchestrator.register_handler("price", make_handler("price"))
    orchestrator.register_handler("summary", make_handler("summary"))
    orchestrator.set_default_handler(
        lambda command: interface.full_snapshot(
            command.params.get("token", "UNKNOWN"),
            command.params,
        )
    )

    orchestrator.set_completion_validator(_decision_completion_validator)
    return orchestrator


def build_verification_orchestrator(
    data_intelligence,
    provider: str = "chatgpt",
    priming_prompt: Optional[str] = None,
    session_dir: Optional[str] = None,
) -> ConversationOrchestrator:
    """
    Construct an orchestrator for the risk-verification agent.
    """

    interface = BrowserDataInterface(data_intelligence)
    driver_config = ConversationDriverConfig(
        provider=provider,
        priming_prompt=priming_prompt,
        session_dir=session_dir,
    )
    orchestrator = ConversationOrchestrator(driver_config=driver_config)

    def make_handler(command_name: str) -> RequestHandler:
        return lambda command: interface.handle_command(command_name, command.params)

    orchestrator.register_handler("sentiment", make_handler("sentiment"))
    orchestrator.register_handler("price", make_handler("price"))
    orchestrator.register_handler("summary", make_handler("summary"))
    orchestrator.set_default_handler(
        lambda command: interface.full_snapshot(
            command.params.get("token", "UNKNOWN"),
            command.params,
        )
    )

    orchestrator.set_completion_validator(_verdict_completion_validator)
    return orchestrator


def _decision_completion_validator(command: DriverCommand) -> Optional[str]:
    """
    Ensure the Tier-1 agent emits the exact decision schema.
    """

    required_fields = [
        "action",
        "confidence",
        "position_size",
        "stop_loss_pct",
        "take_profit_pct",
        "reasoning",
    ]
    name = (command.name or "").strip().lower()
    errors: List[str] = []

    if name != "decision":
        errors.append("the COMPLETE line must start with `decision`.")

    missing = [field for field in required_fields if field not in command.params]
    if missing:
        errors.append(
            "missing fields: " + ", ".join(missing)
        )

    action = command.params.get("action", "").strip().upper()
    if action and action not in {"BUY", "SELL", "HOLD", "SHORT"}:
        errors.append("action must be BUY, SELL, HOLD, or SHORT.")

    confidence_error = _validate_ratio(command.params.get("confidence"), "confidence")
    if confidence_error:
        errors.append(confidence_error)

    position_error = _validate_ratio(
        command.params.get("position_size"), "position_size"
    )
    if position_error:
        errors.append(position_error)

    stop_loss_error = _validate_float(command.params.get("stop_loss_pct"), "stop_loss_pct")
    if stop_loss_error:
        errors.append(stop_loss_error)

    take_profit_error = _validate_float(
        command.params.get("take_profit_pct"), "take_profit_pct"
    )
    if take_profit_error:
        errors.append(take_profit_error)

    reasoning = command.params.get("reasoning", "").strip()
    if reasoning == "":
        errors.append("reasoning must describe the thesis in a few words.")

    if not errors:
        return None

    error_details = " ".join(errors)
    return (
        "FORMAT ERROR: "
        f"{error_details} Respond again with a single line exactly like "
        "'COMPLETE: decision | action=<BUY/SELL/HOLD/SHORT> | confidence=<0-1> | "
        "position_size=<0-1> | stop_loss_pct=<value> | take_profit_pct=<value> | reasoning=<short text>'."
    )


def _verdict_completion_validator(command: DriverCommand) -> Optional[str]:
    """
    Ensure the Tier-2 verifier emits PASS/FAIL verdicts with reasons.
    """

    name = (command.name or "").strip().lower()
    errors: List[str] = []
    if name != "verdict":
        errors.append("the COMPLETE line must start with `verdict`.")

    status = command.params.get("status", "").strip().upper()
    if status not in {"PASS", "FAIL"}:
        errors.append("status must be PASS or FAIL.")

    reason = command.params.get("reason", "").strip()
    if reason == "":
        errors.append("reason must briefly justify the verdict.")

    if not errors:
        return None

    error_details = " ".join(errors)
    return (
        "FORMAT ERROR: "
        f"{error_details} Reply with a single line exactly like "
        "'COMPLETE: verdict | status=PASS/FAIL | reason=<short explanation>'."
    )


def _validate_ratio(value: Optional[str], field: str) -> Optional[str]:
    if value is None:
        return f"{field} is required."
    try:
        ratio = float(value.strip())
    except ValueError:
        return f"{field} must be a number between 0 and 1."
    if not 0 <= ratio <= 1:
        return f"{field} must be between 0 and 1."
    return None


def _validate_float(value: Optional[str], field: str) -> Optional[str]:
    if value is None:
        return f"{field} is required."
    clean = value.strip().rstrip("%")
    if clean == "":
        return f"{field} is required."
    try:
        float(clean)
    except ValueError:
        return f"{field} must be a numeric value."
    return None
