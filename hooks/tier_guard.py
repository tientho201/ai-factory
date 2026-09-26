#!/usr/bin/env python3
"""Hook PreToolUse - hang rao cung cua AI Factory.

Day la thu duy nhat thuc su chan duoc agent. Loi dan trong prompt chi la
goi y; agent co the quen hoac hieu sai. Hook thi khong.

Cach hoat dong:
  1. Doc JSON tu stdin (Claude Code gui vao).
  2. Lay duong dan file hoac lenh bash sap chay.
  3. Phan tier bang luat tinh trong .flow/config.json.
  4. Tier < 2  -> cho qua (exit 0).
     Tier >= 2 -> neu che do tu dong cho phep, hoac da co phieu duyet: cho qua.
                  nguoc lai: tao phieu cho duyet, gui mail, exit 2 de chan.

Exit 2 chan tool call va day noi dung stderr ve cho Claude doc.
"""

from __future__ import annotations

import json
import os
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
except Exception as e:  # noqa: BLE001
    print(f"[tier_guard] khong nap duoc flow_core: {e}", file=sys.stderr)
    sys.exit(0)  # khong chan khi chinh hook bi hong

try:
    from notify import send as notify_send
except Exception:  # noqa: BLE001
    def notify_send(*_a: object, **_k: object) -> bool:
        return False


PATH_TOOLS = {"Write", "Edit", "NotebookEdit", "MultiEdit"}
CMD_TOOLS = {"Bash", "PowerShell"}


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    tool = event.get("tool_name", "")
    ti = event.get("tool_input", {}) or {}

    paths: list[str] = []
    command: str | None = None

    if tool in PATH_TOOLS:
        for key in ("file_path", "path", "notebook_path"):
            if ti.get(key):
                paths.append(str(ti[key]))
        for e in ti.get("edits", []) or []:
            if isinstance(e, dict) and e.get("file_path"):
                paths.append(str(e["file_path"]))
    elif tool in CMD_TOOLS:
        command = ti.get("command") or ti.get("script")
    else:
        return 0

    if not paths and not command:
        return 0

    try:
        cfg = fc.load_config()
    except SystemExit:
        return 0

    tier, reason = fc.classify(paths=paths, command=command, cfg=cfg)

    if tier < 2:
        return 0

    # Tier 2 tro len: kiem tra xem da duoc phep chua
    if fc.auto_allows(tier, cfg):
        fc.log_event(
            "tier2_auto_allowed",
            f"{tool}: {(command or ', '.join(paths))[:200]}",
            reason=reason,
        )
        return 0

    cur = fc.get_current()
    task_id = cur.get("task_id") or "adhoc"
    what = (command or ", ".join(paths))[:300]

    # Da co phieu duyet cho DUNG viec nay chua? Duyet viec khac khong tinh.
    try:
        if fc.is_approved(task_id, what, paths=paths):
            fc.log_event("tier2_approved_ok", what[:200], reason=reason)
            return 0
    except SystemExit:
        pass  # chua co run -> khong the da duoc duyet -> chan tiep ben duoi

    # Lap phieu cho duyet. Neu khong lap duoc vi chua co run nao dang chay,
    # VAN CHAN. Hang rao khong duoc phu thuoc vao viec co dang chay quy trinh
    # hay khong - nguoc lai thi chi can lam viec ngoai quy trinh la thoat rao.
    ticket_ok = True
    try:
        fc.request_approval(
            task_id,
            what,
            reason,
            tier=tier,
            details={"tool": tool, "paths": paths, "command": command},
        )
    except (SystemExit, OSError) as e:
        ticket_ok = False
        print(f"[tier_guard] khong lap duoc phieu ({e}) nhung van chan.", file=sys.stderr)

    port = cfg.get("dashboard", {}).get("port", 7788)
    if ticket_ok and cfg.get("notify", {}).get("on_approval_needed"):
        notify_send(
            f"[AI Factory] Chan Tier {tier}: {what[:50]}",
            f"Agent muon chay mot viec duoc xep Tier {tier} nen he thong da chan lai.\n\n"
            f"Cong cu: {tool}\n"
            f"Noi dung: {what}\n"
            f"Ly do xep tier: {reason}\n"
            f"Task: {task_id}\n\n"
            f"Duyet tai: http://127.0.0.1:{port}\n"
            f"Hoac chay: python scripts/flow.py approve {task_id}\n",
        )

    print(
        f"CHAN BOI TIER GUARD.\n"
        f"Hanh dong nay duoc xep Tier {tier} ({fc.tier_label(tier, cfg)}).\n"
        f"Ly do: {reason}\n"
        f"Noi dung: {what}\n\n"
        f"Da tao phieu cho duyet cho task '{task_id}' va gui thong bao cho nguoi dung.\n"
        f"KHONG duoc tim cach lach qua hang rao nay (doi duong dan, chia nho lenh, "
        f"dung cong cu khac). Thay vao do hay lam mot trong hai viec:\n"
        f"  - Chay: python scripts/flow.py wait {task_id}   (cho nguoi bam duyet)\n"
        f"  - Hoac bao cao lai cho nguoi dung va dung tai day.\n"
        f"Neu co cach lam khac khong cham vao vung Tier 2, hay de xuat cach do.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
