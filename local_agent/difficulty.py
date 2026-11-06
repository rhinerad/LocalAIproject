"""Conservative trigger for a stronger, one-shot planning pass."""
from __future__ import annotations
import re

_SIGNALS = re.compile(r"\b(?:architect(?:ure|ural)?|refactor|implement|debug|diagnos|"
                      r"multi[- ]step|end[- ]to[- ]end|compare|integrat|orchestrat|"
                      r"test(?:ing)?|repository|codebase|plan and|workflow)\b", re.I)
def needs_escalation(text: str) -> bool:
    text=str(text or "")
    return len(text) >= 700 or len(_SIGNALS.findall(text)) >= 2
