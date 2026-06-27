"""Utilities for loading prompt templates from disk."""

from pathlib import Path


PROMPT_DIR = Path(__file__).resolve().parent


def load_prompt(name: str) -> str:
    """Load a prompt template relative to the prompts directory."""
    return (PROMPT_DIR / name).read_text(encoding="utf-8").strip()

