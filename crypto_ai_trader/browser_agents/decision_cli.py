"""
Command-line helper to run the browser-based decision agent for a single token.

This utility will:
1. Initialize ``DataIntelligence`` using the default config.
2. Build the data-backed browser orchestrator.
3. Send a quick summary as the initial context.
4. Print the model's requests, our responses, and the final completion payload.

Usage:
    python -m crypto_ai_trader.browser_agents.decision_cli --token BTC
"""

from __future__ import annotations

import argparse
import json
from typing import Optional

from crypto_ai_trader import config
from crypto_ai_trader.data_intelligence import DataIntelligence
from .conversation_orchestrator import build_data_orchestrator
from .data_interface import BrowserDataInterface


DEFAULT_PRIMING_PROMPT = """You are an AI trading analyst operating inside a browser chat.

A quick market summary for the token arrives immediately after this priming message. Treat it as CONTEXT and then begin issuing commands.

RESPONSE CONTRACT (no exceptions):
1. Every reply must be a single line with no extra prose or formatting.
2. Allowed outputs:
   - REQUEST: <data_type> | token=<TOKEN> | window=<duration>
   - COMPLETE: decision | action=<BUY/SELL/HOLD/SHORT> | confidence=<0-1> | position_size=<0-1> | stop_loss_pct=<value> | take_profit_pct=<value> | reasoning=<<=20 words>
3. Send as many REQUEST lines as needed. After each CONTEXT block you must immediately send another REQUEST or the final COMPLETE line.
4. COMPLETE is sent only once when the decision is final.
5. Do not include salutations, explanations, thinking text, or multiple messages.

Your very next response must follow this contract (normally a REQUEST for the next dataset)."""


def run(token: str, provider: Optional[str] = None) -> None:
    provider = provider or getattr(config, "BROWSER_AI_PROVIDER", "claude")
    db_config = {
        "host": config.DB_HOST,
        "port": int(config.DB_PORT),
        "database": config.DB_NAME,
        "user": config.DB_USER,
        "password": config.DB_PASSWORD,
    }

    data_intel = DataIntelligence(db_config)
    data_interface = BrowserDataInterface(data_intel)

    orchestrator = build_data_orchestrator(
        data_intelligence=data_intel,
        provider=provider,
        priming_prompt=DEFAULT_PRIMING_PROMPT,
        session_dir=None,
    )

    initial_context = data_interface.quick_summary(token)

    print(f"[INFO] Starting browser agent for {token} using provider '{provider}'")
    result = orchestrator.run(initial_prompt=initial_context, token=token)

    print("\n=== FINAL DECISION ===")
    if result.completion:
        completion = {
            "type": result.completion.type,
            "name": result.completion.name,
            "params": result.completion.params,
            "raw": result.completion.raw,
        }
        print(json.dumps(completion, indent=2))
    else:
        print("No completion command was returned.")

    print("\n=== TRANSCRIPT ===")
    for entry in result.transcript:
        role = entry.get("role")
        content = entry.get("content", "").strip()
        print(f"[{role.upper()}] {content}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run browser decision agent for a token.")
    parser.add_argument("--token", required=True, help="Token symbol (e.g., BTC)")
    parser.add_argument(
        "--provider",
        default=None,
        help="Browser provider (claude, chatgpt, deepseek, gemini). Defaults to config setting.",
    )
    args = parser.parse_args()
    run(token=args.token.upper(), provider=args.provider)


if __name__ == "__main__":
    main()
