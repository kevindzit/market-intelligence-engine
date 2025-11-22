"""
Utility for persisting browser-agent decisions in a structured, easy-to-review format.

Each decision is stored twice:
1. A full JSON file (includes transcript) for deep inspection.
2. A line in ``summary.jsonl`` capturing high-level metrics (token, action, confidence).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Dict


@dataclass
class BrowserDecisionLogger:
    log_dir: str

    def __post_init__(self) -> None:
        os.makedirs(self.log_dir, exist_ok=True)
        self.summary_path = os.path.join(self.log_dir, "summary.jsonl")

    def log(self, decision: Dict) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        token = decision.get("token", "UNKNOWN").upper()
        filename = f"{timestamp}_{token}.json"
        full_path = os.path.join(self.log_dir, filename)

        try:
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(decision, f, indent=2)
        except Exception as exc:
            print(f"[BROWSER AGENT] Failed to write decision file: {exc}")

        summary = {
            "ts": timestamp,
            "token": token,
            "action": decision.get("action", "HOLD"),
            "confidence": decision.get("confidence"),
            "position_size": decision.get("position_size"),
            "source": decision.get("source"),
            "reason": decision.get("reasoning", "")[:200],
            "transcript_file": filename,
        }

        try:
            with open(self.summary_path, "a", encoding="utf-8") as summary_file:
                summary_file.write(json.dumps(summary) + "\n")
        except Exception as exc:
            print(f"[BROWSER AGENT] Failed to append summary: {exc}")


__all__ = ["BrowserDecisionLogger"]
