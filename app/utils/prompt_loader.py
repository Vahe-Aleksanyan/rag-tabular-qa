from __future__ import annotations
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    return path.read_text(encoding="utf-8").strip()
