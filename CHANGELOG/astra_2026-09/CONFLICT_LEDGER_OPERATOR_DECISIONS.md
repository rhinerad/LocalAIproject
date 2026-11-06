# Backrooms conflict ledger — operator decisions required

Source: `outputs_compile/conflict_ledger.json`  
These are **not** auto-resolved. Production must record an explicit choice before C069–C102 / camera / improv gates close.

| ID | Status | Decision needed | Options (pick one) |
|----|--------|-----------------|-------------------|
| `ending_revised_vs_body_attack` | unresolved_creative | Which C069–C102 body is authoritative? | A) Keep parsed MERGED/attachment bodies as-is (attack/static/mirroring). B) Replace with a separately supplied revised 34-shot ending (must be provided). C) Hybrid: keep bodies but annotate superseded beats in ledger only. |
| `static_transition_scope` | explicit_override | C070/C071 static hold vs Rule 6 brief C069-only static | A) Enforce brief static **only** at C069; rewrite/flag C070–C071 if they hold static. B) Grant explicit exception for C070–C071 (+ optional C102 cutoff). |
| `improvisation_lines` | unresolved_creative | C007 (and similar) improv directions | A) Approve fixed substitute dialogue text. B) Mark `improvisation_permitted=true` and skip exact-transcript QA for those lines. |
| `handheld_vs_external_fullbody_post_fall` | unresolved_creative | C015/C016 camera ownership after fall | A) Enforce Mode B/C from CORRECTED camera table (no external full-body). B) Allow documented exception shots with external view (list clip ids). |
| `c102_you_can_talk` | unresolved_creative | Entity “You can talk?” after earlier speech | A) Intentional comedy — keep. B) Stale ending — replace line. C) Cut C102 / shorten ending. |
| `appendix_stripping_risks` | explicit_override | Bible/story-rules extraction | A) Freeze a versioned Character Bible file extracted before appendix strip (recommended). B) Accept risk and cite pack appendix manually per job. |

## Recording a decision
Write answers into:
`live_jobs/conflict_ledger_decisions.json`

Example:
```json
{
  "ending_revised_vs_body_attack": {"choice": "A", "notes": "...", "decided_by": "Rhine", "decided_at": "ISO-8601"},
  "static_transition_scope": {"choice": "B", "notes": "Allow C070-C071 hold", "decided_by": "Rhine", "decided_at": "ISO-8601"}
}
```

Until decisions exist, compile remains valid but **unattended full ending production stays blocked**.
