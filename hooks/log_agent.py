#!/usr/bin/env python3
"""Hook SubagentStart / SubagentStop - ghi nhat ky ai lam gi luc nao.

Khong chan gi ca, chi ghi. Nho vay dashboard hien duoc timeline that
thay vi phai tin vao loi ke cua agent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Chay duoc ca khi la .claude/hooks/ trong repo lan khi la plugin cache
_here = Path(__file__).resolve().parent
for _c in (_here.parent / "scripts", _here.parent.parent / "scripts"):
    if (_c / "flow_core.py").exists():
        sys.path.insert(0, str(_c))
        break
else:
    sys.path.insert(0, str(_here.parent / "scripts"))

try:
    import flow_core as fc
except Exception:  # noqa: BLE001
    sys.exit(0)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    name = event.get("hook_event_name", "")
    agent = event.get("agent_type") or event.get("agent_id") or "?"
    cur = fc.get_current()

    if name == "SubagentStart":
        fc.log_event("agent_start", f"{agent} bat dau", task_id=cur.get("task_id"), agent=agent)
    elif name == "SubagentStop":
        fc.log_event("agent_stop", f"{agent} ket thuc", task_id=cur.get("task_id"), agent=agent)
    elif name == "Stop":
        fc.log_event("turn_end", "Claude ket thuc luot tra loi", task_id=cur.get("task_id"))

    return 0


if __name__ == "__main__":
    sys.exit(main())
