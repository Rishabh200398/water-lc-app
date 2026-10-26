"""Prompt-injection defenses for text the app did not write.

Pasted speaker or advisor replies, pasted articles and job posts, and web search results
are all *untrusted*. Four layers protect the app:

  1. screen():  lines that read like instructions to an AI ("ignore previous instructions",
                "approve $5,000", "email Cristina now") are removed before any agent sees
                the text, and logged to the security log for the co-leads to review.
  2. wrap():    what remains goes to the model inside <untrusted_data> tags, and every agent's
                instructions say that text inside those tags is information, never orders.
  3. No power:  agents that read untrusted text have no tools that spend money, change the
                ledger or send email. Money moves only through budget.py and a human click.
  4. check_output(): drafts are scanned for claims of approval or money that the
                untrusted text tried to plant, and flagged for the reviewer.
"""

from __future__ import annotations

import re
from typing import Any

import store

_PATTERNS = [
    (r"\bignore (all |any )?(the )?(previous|prior|above|earlier) (instructions|rules|messages)", "tries to override instructions"),
    (r"\b(disregard|forget) (all |your )?(previous |prior )?(instructions|rules)", "tries to override instructions"),
    (r"\byou are now\b|\bact as\b|\bnew instructions\b|\bdeveloper mode\b|\badmin mode\b", "tries to change the AI's role"),
    (r"\bsystem (prompt|note|message|override)\b", "pretends to be a system message"),
    (r"\b(note|message|instruction)s? (to|for) (the )?(ai|assistant|model|agent|chatbot)\b", "addresses the AI directly"),
    (r"\b(approve|authori[sz]e|pay|transfer|wire)\b.{0,40}\$\s?\d", "asks to approve or move money"),
    (r"\$\s?\d[\d,]*.{0,40}\b(approve|approved|authori[sz]ed)\b", "claims money was approved"),
    (r"\b(send|email|forward)\b.{0,40}\b(immediately|right away|now|without (approval|review))\b", "asks to send something without review"),
    (r"\bapproved by (jim|the advisor|advisor)\b", "claims advisor approval"),
    (r"\b(reveal|print|show)\b.{0,30}\b(system prompt|instructions|api key|password)\b", "asks for secrets"),
]


def screen(text: str, source: str) -> dict[str, Any]:
    """Split untrusted text into clean lines and quarantined lines."""
    kept, quarantined = [], []
    for line in text.splitlines():
        reasons = [why for pat, why in _PATTERNS if re.search(pat, line, re.IGNORECASE)]
        if reasons:
            quarantined.append({"line": line.strip(), "reasons": sorted(set(reasons))})
        else:
            kept.append(line)
    return {"source": source, "clean_text": "\n".join(kept).strip(), "quarantined": quarantined}


def log(s: dict[str, Any], result: dict[str, Any], ref: str | None) -> None:
    if result["quarantined"]:
        s["security_log"].append({
            "id": store.new_id("sec"),
            "ts": store.now(),
            "source": result["source"],
            "ref": ref,
            "quarantined": result["quarantined"],
        })


def wrap(text: str, label: str) -> str:
    safe = text.replace("</untrusted_data>", "")
    return f'<untrusted_data source="{label}">\n{safe}\n</untrusted_data>'


def check_output(text: str) -> list[str]:
    """Flags in an agent's draft that a reviewer should look at."""
    flags = []
    if re.search(r"approved by (jim|the advisor)|budget approved", text, re.IGNORECASE):
        flags.append("Draft claims an approval. Approvals only come from a co-lead's click in the app.")
    if re.search(r"ignore (all )?previous instructions|system note", text, re.IGNORECASE):
        flags.append("Draft repeats instruction-like text from a source.")
    return flags
