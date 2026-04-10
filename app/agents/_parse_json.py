"""
Shared JSON extraction helper for all agents.
Claude sometimes wraps JSON in markdown code blocks or adds explanatory text.
This extracts the JSON reliably.
"""

import json
import re


def extract_json(text: str) -> dict:
    """
    Extract a JSON object from Claude's response text.
    Handles: pure JSON, markdown code blocks, text mixed with JSON.
    """
    if not text or not text.strip():
        return {}

    # Try direct parse first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block ```json ... ``` or ``` ... ```
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding JSON object pattern { ... }
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        candidate = brace_match.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            # Try to fix common issues: trailing commas
            cleaned = re.sub(r",\s*}", "}", candidate)
            cleaned = re.sub(r",\s*]", "]", cleaned)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass

    return {}
