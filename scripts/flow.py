#!/usr/bin/env python3
"""flow.py - dieu khien AI Factory tu dong lenh.

Moi agent doc va ghi trang thai qua file nay, khong tu nho trong dau.

    .flow/flow start "Y tuong cua toi"
    .flow/flow tier --paths src/auth/login.ts
    .flow/flow plan-import ke-hoach.json
    .flow/flow next
    .flow/flow claim T1
    .flow/flow gate T1
    .flow/flow ask T1 "Muon chay migration them cot email"
    .flow/flow wait T1
    .flow/flow done T1 --commit
    .flow/flow status
    .flow/flow auto on --max-tier 1
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import flow_core as fc  # noqa: E402

try:
    import notify as nt
except Exception:  # noqa: BLE001 - thong bao khong bao gio duoc lam vo workflow
    nt = None  # type: ignore[assignment]


def _notice(build: str, *args: object, **kw: object) -> None:
    """Dung va gui mot thong bao co cau truc. Khong bao gio lam vo workflow."""
    if nt is None:
        print(f"[notify tat] {build}", file=sys.stderr)
        return
    try:
        nt.send_notice(getattr(nt, build)(*args, **kw))
    except Exception as e:  # noqa: BLE001
        print(f"[notify] loi: {e}", file=sys.stderr)


GREEN, AMBER, RED, DIM, BOLD, OFF = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"

STATUS_COLOR = {
    "done": GREEN,
    "running": "\033[36m",
    "awaiting_approval": AMBER,
    "gate_failed": RED,
    "review_failed": RED,
    "blocked": DIM,
    "pending": DIM,
}


# ---------------------------------------------------------------- start / init


def cmd_start(args: argparse.Namespace) -> int:
    run_id = fc.new_run_id()
    d = fc.RUNS / run_id
    (d / "tasks").mkdir(parents=True, exist_ok=True)
    (d / "approvals").mkdir(parents=True, exist_ok=True)

    (d / "00-idea.md").write_text(
        f"# Y tuong goc\n\n_Ghi luc {fc.now()}_\n\n{args.idea}\n",
        encoding="utf-8",
    )
    fc._atomic_write(
        d / "state.json",
        json.dumps({"run_id": run_id, "phase": "explore", "started_at": fc.now(), "idea": args.idea},
                   ensure_ascii=False, indent=2),
    )
    fc.save_tasks({"run_id": run_id, "tasks": []}, run_id)
    fc.set_current(run_id)
    fc.log_event("run_started", args.idea[:200], run_id=run_id)

    print(f"{BOLD}Run moi:{OFF} {run_id}")
    print(f"Thu muc: {d}")
    print("\nBuoc tiep theo cho agent dieu phoi:")
    print("  1. Giao flow-explorer khao sat, ghi ra 01-research.md")
    print("  2. Giao flow-planner lap ke hoach, ghi ra 02-plan.md + tasks.json")
    print("  3. .flow/flow plan-import <file tasks.json>")
    return 0


# ---------------------------------------------------------------- tier


def cmd_tier(args: argparse.Namespace) -> int:
    tier, reason = fc.classify(paths=args.paths, command=args.command, text=args.text)
    cfg = fc.load_config()
    out = {
        "tier": tier,
        "label": fc.tier_label(tier, cfg),
        "reason": reason,
        "auto_allows": fc.auto_allows(tier, cfg),
        "needs_human": tier >= 2 and not fc.auto_allows(tier, cfg),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------- plan


def cmd_plan_import(args: argparse.Namespace) -> int:
    """Nhan tasks.json tu planner, tinh lai tier bang luat tinh roi luu."""
    raw = json.loads(Path(args.file).read_text(encoding="utf-8"))
    tasks = raw.get("tasks", raw if isinstance(raw, list) else [])
    cfg = fc.load_config()
    run_id = fc.get_current().get("run_id")

    seen: set[str] = set()
    normalised = []
    for i, t in enumerate(tasks, 1):
        tid = str(t.get("id") or f"T{i}").strip()
        if tid in seen:
            print(f"{RED}Trung id task: {tid}{OFF}", file=sys.stderr)
            return 1
        seen.add(tid)

        paths = t.get("files") or []
        tier, reason = fc.classify(
            paths=paths,
            text=f"{t.get('title', '')} {t.get('description', '')}",
            cfg=cfg,
        )
        normalised.append({
            "id": tid,
            "title": t.get("title", "").strip(),
            "description": t.get("description", "").strip(),
            "files": paths,
            "depends_on": t.get("depends_on", []),
            "acceptance": t.get("acceptance", []),
            "parallel_group": t.get("parallel_group"),
            "tier": tier,
            "tier_reason": reason,
            "tier_suggested_by_planner": t.get("tier"),
            "status": "pending",
            "attempts": 0,
            "created_at": fc.now(),
        })

    # canh bao khi hai task cung ghi mot file va co the chay song song
    conflicts = _file_conflicts(normalised)
    for msg in conflicts:
        print(f"{AMBER}Canh bao:{OFF} {msg}")

    fc.save_tasks({"run_id": run_id, "tasks": normalised}, run_id)
    fc.log_event("plan_imported", f"{len(normalised)} task", run_id=run_id)

    print(f"{BOLD}Da nap {len(normalised)} task.{OFF}\n")
    _print_table(normalised, cfg)
    n2 = sum(1 for t in normalised if t["tier"] >= 2)
    if n2:
        print(f"\n{AMBER}{n2} task can ban duyet truoc khi chay.{OFF}")
    return 0


def _file_conflicts(tasks: list[dict]) -> list[str]:
    out = []
    by_group: dict[object, list[dict]] = {}
    for t in tasks:
        by_group.setdefault(t.get("parallel_group"), []).append(t)
    for group, ts in by_group.items():
        if group is None or len(ts) < 2:
            continue
        for i in range(len(ts)):
            for j in range(i + 1, len(ts)):
                shared = set(ts[i]["files"]) & set(ts[j]["files"])
                if shared:
                    out.append(
                        f"{ts[i]['id']} va {ts[j]['id']} cung nhom song song nhung deu ghi {sorted(shared)}"
                        " - nen tach nhom hoac chia lai file."
                    )
    return out


# ---------------------------------------------------------------- vong doi task


def cmd_next(args: argparse.Namespace) -> int:
    data = fc.load_tasks()
    t = fc.next_task(data)
    if not t:
        remaining = [x for x in data["tasks"] if x["status"] != "done"]
        if not remaining:
            print(json.dumps({"status": "all_done"}, ensure_ascii=False))
        else:
            print(json.dumps({"status": "blocked", "remaining": [x["id"] for x in remaining]}, ensure_ascii=False))
        return 0

    cfg = fc.load_config()
    needs_human = t["tier"] >= 2 and not fc.auto_allows(t["tier"], cfg)
    print(json.dumps({
        "status": "ready",
        "task": t,
        "needs_human_approval": needs_human,
        "auto_mode": cfg["auto_mode"],
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    data = fc.load_tasks()
    t = fc.find_task(data, args.task_id)
    if not t:
        print(f"{RED}Khong co task {args.task_id}{OFF}", file=sys.stderr)
        return 1

    cfg = fc.load_config()
    if t["tier"] >= 2 and not fc.auto_allows(t["tier"], cfg):
        a = fc.read_approval(args.task_id)
        if not a or a.get("decision") != "approved":
            t["status"] = "awaiting_approval"
            fc.save_tasks(data)
            fc.request_approval(
                args.task_id,
                t["title"],
                t.get("tier_reason", ""),
                tier=t["tier"],
                details={"files": t["files"], "description": t["description"]},
            )
            _notify_approval(t)
            print(json.dumps({
                "status": "awaiting_approval",
                "message": f"Task {args.task_id} la Tier {t['tier']}, phai duoc duyet truoc. "
                           f"Chay: .flow/flow wait {args.task_id}",
            }, ensure_ascii=False, indent=2))
            return 2

    t["status"] = "running"
    t["started_at"] = fc.now()
    t["attempts"] = t.get("attempts", 0) + 1
    fc.save_tasks(data)
    fc.set_current(data["run_id"], args.task_id)
    fc.log_event("task_started", t["title"], task_id=args.task_id)

    task_dir = fc.run_dir() / "tasks" / args.task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"status": "running", "task": t, "task_dir": str(task_dir)}, ensure_ascii=False, indent=2))
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    """Agent chu dong xin y kien ban giua chung."""
    try:
        data = fc.load_tasks()
        t = fc.find_task(data, args.task_id)
        if t:
            t["status"] = "awaiting_approval"
            fc.save_tasks(data)
    except SystemExit:
        pass  # khong co run dang chay (vd: viec roi rac) - van xin duyet duoc
    fc.request_approval(args.task_id, args.question, args.reason or "agent chu dong hoi",
                        tier=args.tier, details={"options": args.options or []})
    if fc.load_config()["notify"].get("on_approval_needed"):
        _notice("approval_notice", args.task_id, args.question, args.reason or "agent chủ động hỏi",
                args.tier, question=True, options=args.options or [])
    print(json.dumps({"status": "asked", "task_id": args.task_id,
                      "next": f".flow/flow wait {args.task_id}"}, ensure_ascii=False))
    return 0


def cmd_wait(args: argparse.Namespace) -> int:
    """Cho duyet trong mot cua so NGAN roi tra quyen ve.

    Khong chan hang gio: cong cu Bash cua Claude Code co timeout rieng, mot
    tien trinh cho 2 tieng se bi giet va agent nhan mot loi kho hieu thay vi
    biet la dang cho nguoi. Cho ngan roi bao ro trang thai thi an toan hon.
    """
    cfg = fc.load_config()
    window = args.timeout or int(cfg["limits"].get("wait_window_seconds", 90))
    window = min(window, 240)  # tran cung, tranh bi harness giet giua chung

    print(f"{DIM}Cho ban quyet dinh, cua so {window}s...{OFF}", file=sys.stderr)
    a = fc.wait_for_approval(args.task_id, window)

    data = fc.load_tasks()
    t = fc.find_task(data, args.task_id)

    if a.get("decision") == "approved":
        if t:
            t["status"] = "pending"
            fc.save_tasks(data)
        print(json.dumps({**a, "next_step": "Da duoc duyet. Chay tiep task nay."},
                         ensure_ascii=False, indent=2))
        return 0

    if a.get("decision") == "rejected":
        if t:
            t["status"] = "skipped"
            fc.save_tasks(data)
        print(json.dumps({**a, "next_step": "Bi tu choi. Bo qua task nay, bao cao lai cho nguoi dung."},
                         ensure_ascii=False, indent=2))
        return 3

    # Het cua so ma chua co phan hoi
    port = cfg["dashboard"]["port"]
    print(json.dumps({
        "task_id": args.task_id,
        "decision": "still_waiting",
        "next_step": (
            "CHUA co phan hoi. DUNG chay lai lenh wait lien tuc - lam vay chi "
            "dot thoi gian va token. Thay vao do: dung lai, bao cho nguoi dung "
            "rang co viec dang cho ho duyet, va ket thuc luot. Khi ho duyet xong "
            "va bao ban chay tiep, hay chay lai tu day."
        ),
        "nguoi_dung_can_lam": [
            f"Mo http://127.0.0.1:{port} roi bam Duyet",
            f"hoac chay: .flow/flow approve {args.task_id}",
        ],
    }, ensure_ascii=False, indent=2))
    return 4


def cmd_gate(args: argparse.Namespace) -> int:
    """Chay cong kiem tra bang may. Day moi la cong that, khong phai y kien cua LLM."""
    script = fc.FLOW_HOME / "scripts" / "gate.sh"
    # shutil.which, khong phai "bash" tran: tren Windows, CreateProcess uu tien
    # C:\Windows\System32\bash.exe (WSL launcher stub) truoc ca PATH, nen "bash"
    # tran se goi nham WSL thay vi Git Bash that.
    bash = shutil.which("bash") or "bash"
    proc = subprocess.run(
        [bash, script.as_posix()], capture_output=True, text=True, cwd=fc.ROOT,
        env=dict(os.environ, FLOW_PROJECT_DIR=fc.ROOT.as_posix()),
    )
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        result = {"ok": False, "error": "gate.sh khong tra ve JSON hop le",
                  "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]}

    task_dir = fc.run_dir() / "tasks" / args.task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    fc._atomic_write(task_dir / "gate.json", json.dumps(result, ensure_ascii=False, indent=2))

    data = fc.load_tasks()
    t = fc.find_task(data, args.task_id)
    if t:
        t["gate"] = {k: v for k, v in result.items() if k != "logs"}
        if not result.get("ok"):
            t["status"] = "gate_failed"
        fc.save_tasks(data)

    if result.get("ok"):
        fc.log_event("gate_passed", args.task_id, task_id=args.task_id)
        print(f"{GREEN}Cong may: dat{OFF}", file=sys.stderr)
    else:
        fc.log_event("gate_failed", json.dumps(result.get("failed", []))[:200], task_id=args.task_id)
        print(f"{RED}Cong may: truot{OFF}", file=sys.stderr)
        cfg = fc.load_config()
        if cfg["notify"].get("on_task_fail"):
            _notice("fail_notice", t or {"id": args.task_id, "title": args.task_id}, result, stage="gate")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def cmd_done(args: argparse.Namespace) -> int:
    data = fc.load_tasks()
    t = fc.find_task(data, args.task_id)
    if not t:
        print(f"{RED}Khong co task {args.task_id}{OFF}", file=sys.stderr)
        return 1

    gate_file = fc.run_dir() / "tasks" / args.task_id / "gate.json"
    if not args.force:
        if not gate_file.exists():
            print(f"{RED}Chua chay cong kiem tra. Chay 'flow.py gate {args.task_id}' truoc.{OFF}", file=sys.stderr)
            return 1
        if not json.loads(gate_file.read_text(encoding="utf-8")).get("ok"):
            print(f"{RED}Cong kiem tra chua dat. Sua roi chay lai gate.{OFF}", file=sys.stderr)
            return 1

    t["status"] = "done"
    t["finished_at"] = fc.now()
    fc.save_tasks(data)
    fc.log_event("task_done", t["title"], task_id=args.task_id)

    if args.commit:
        msg = args.message or f"{args.task_id}: {t['title']}"
        subprocess.run(["git", "add", "-A"], cwd=fc.ROOT, check=False)
        r = subprocess.run(["git", "commit", "-m", msg], cwd=fc.ROOT,
                           capture_output=True, text=True, check=False)
        if r.returncode == 0:
            sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=fc.ROOT,
                                 capture_output=True, text=True, check=False).stdout.strip()
            t["commit"] = sha
            fc.save_tasks(data)
            fc.log_event("committed", f"{sha} {msg}", task_id=args.task_id)
            print(f"{GREEN}Da commit {sha}{OFF}", file=sys.stderr)
        else:
            print(f"{AMBER}Khong commit duoc: {r.stdout or r.stderr}{OFF}", file=sys.stderr)

    cfg = fc.load_config()
    nxt = fc.next_task(data)
    auto_next = bool(nxt) and fc.auto_allows(nxt["tier"], cfg)

    if cfg["notify"].get("on_task_pass"):
        _notice("pass_notice", data, args.task_id, next_task=nxt, auto_next=auto_next)
    if not nxt and cfg["notify"].get("on_run_done"):
        _notice("run_done_notice", data)

    print(json.dumps({
        "status": "done",
        "task_id": args.task_id,
        "commit": t.get("commit"),
        "next_task": nxt["id"] if nxt else None,
        "next_tier": nxt["tier"] if nxt else None,
        "auto_continue": auto_next,
        "message": ("Che do tu dong dang bat, chay tiep task ke tiep ngay." if auto_next
                    else "Dung lai, cho ban xac nhan." if nxt
                    else "Het task."),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_fail(args: argparse.Namespace) -> int:
    data = fc.load_tasks()
    t = fc.find_task(data, args.task_id)
    if not t:
        return 1
    t["status"] = "review_failed"
    t["last_error"] = args.reason
    fc.save_tasks(data)
    fc.log_event("task_failed", args.reason[:300], task_id=args.task_id)

    cfg = fc.load_config()
    if cfg["notify"].get("on_task_fail"):
        _notice("fail_notice", t, {"reason": args.reason}, stage="review")

    max_att = int(cfg["limits"]["max_fix_attempts"])
    print(json.dumps({
        "status": "failed",
        "attempts": t.get("attempts", 0),
        "max_attempts": max_att,
        "should_stop": t.get("attempts", 0) >= max_att,
        "message": ("Da het so lan sua cho phep. Dung lai va bao nguoi." if t.get("attempts", 0) >= max_att
                    else "Con duoc sua tiep."),
    }, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------- trang thai


def cmd_inbox(args: argparse.Namespace) -> int:
    """Doc hang doi quyet dinh tu bang dieu khien web. Chay dau moi luot."""
    items = fc.queue_drain()
    applied = []

    for it in items:
        kind = it.get("kind")
        if kind == "decision":
            tid, dec = it.get("task_id"), it.get("decision")
            if not (tid and dec):
                continue
            fc.decide_approval(tid, dec, it.get("note", ""))
            try:
                data = fc.load_tasks()
                t = fc.find_task(data, tid)
                if t:
                    t["status"] = "pending" if dec == "approved" else "skipped"
                    fc.save_tasks(data)
            except SystemExit:
                pass
            applied.append({"task_id": tid, "decision": dec, "note": it.get("note", "")})

        elif kind == "feedback":
            tid = it.get("task_id")
            text = it.get("text", "")
            if tid and text:
                try:
                    d = fc.run_dir() / "tasks" / tid
                    d.mkdir(parents=True, exist_ok=True)
                    with (d / "feedback.md").open("a", encoding="utf-8") as f:
                        f.write(f"\n## Nhan xet {fc.now()}\n\n{text}\n")
                    fc.log_event("feedback", text[:200], task_id=tid)
                    applied.append({"task_id": tid, "feedback": text[:200]})
                except SystemExit:
                    pass

    cur = fc.get_current()
    out: dict[str, object] = {"queue_applied": applied}

    if not cur.get("run_id"):
        out["run"] = None
        out["next_step"] = "Chua co run nao. Neu nguoi dung neu y tuong moi, chay flow.py start."
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    data = fc.load_tasks()
    nxt = fc.next_task(data)
    pend = fc.pending_approvals()
    done = sum(1 for t in data["tasks"] if t["status"] == "done")

    out["run"] = {
        "run_id": cur["run_id"],
        "tien_do": f"{done}/{len(data['tasks'])}",
        "task_ke_tiep": nxt["id"] if nxt else None,
        "dang_cho_duyet": [a["task_id"] for a in pend],
    }
    has_handoff = (fc.run_dir() / "handoff.md").exists()
    out["co_handoff"] = has_handoff
    out["next_step"] = (
        "Co viec dang cho nguoi duyet, bao ho truoc khi lam gi khac." if pend
        else "Doc handoff.md roi lam tiep." if has_handoff and nxt
        else "Chay flow.py next de lay task ke tiep." if nxt
        else "Run nay da xong het task."
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    """De xuat tuyen chay dua tren so lieu, khong dua tren cam giac."""
    cfg = fc.load_config()
    files = args.files or []
    tier, reason = fc.classify(paths=files, text=args.intent, cfg=cfg)

    has_tests = any(
        list(fc.ROOT.glob(p))
        for p in ("**/test", "**/tests", "**/*.test.*", "**/*.spec.*", "**/test_*.py")
    )
    researched = False
    try:
        researched = (fc.run_dir() / "01-research.md").exists()
    except SystemExit:
        pass

    n = len(files)
    if args.explore_only:
        route, why = "Khao sat", "nguoi dung chi muon hieu, chua sua"
    elif tier >= 2 or not researched or n > 5 or n == 0:
        bits = []
        if tier >= 2:
            bits.append(f"Tier {tier}")
        if not researched:
            bits.append("vung chua khao sat")
        if n > 5:
            bits.append(f"{n} file")
        if n == 0:
            bits.append("chua ro pham vi")
        route, why = "Du", ", ".join(bits)
    elif n <= 1 and tier == 0:
        route, why = "Nhanh", "1 file, Tier 0"
    else:
        route, why = "Gon", f"{n} file, Tier {tier}, vung da biet"

    steps = {
        "Khao sat": ["flow-explorer"],
        "Du": ["flow-explorer", "flow-planner", "flow-coder", "flow-verifier"],
        "Gon": ["flow-planner", "flow-coder", "flow-verifier"],
        "Nhanh": ["flow-coder", "gate"],
    }[route]

    if tier >= 2 and "flow-verifier" not in steps:
        steps = ["flow-coder", "flow-verifier"]
        why += " (nang tuyen vi Tier 2 bat buoc qua verifier)"
    if has_tests and "gate" not in steps and "flow-verifier" not in steps:
        steps.append("gate")

    print(json.dumps({
        "tuyen": route,
        "ly_do": why,
        "cac_buoc": steps,
        "tier": tier,
        "tier_reason": reason,
        "so_file": n,
        "repo_co_test": has_tests,
        "da_khao_sat": researched,
        "can_nguoi_duyet": tier >= 2 and not fc.auto_allows(tier, cfg),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_handoff(args: argparse.Namespace) -> int:
    """Ghi ban giao mot trang cho phien Claude ke tiep."""
    data = fc.load_tasks()
    run_id = data.get("run_id")
    d = fc.run_dir()
    t = fc.find_task(data, args.task_id) if args.task_id else None
    nxt = fc.next_task(data)

    done = [x for x in data["tasks"] if x["status"] == "done"]
    left = [x for x in data["tasks"] if x["status"] != "done"]

    lines = [
        f"# Ban giao - {run_id}",
        f"\n_Ghi luc {fc.now()}. Phien Claude moi doc file nay dau tien._\n",
        "## Dang o dau\n",
        f"- Xong {len(done)}/{len(data['tasks'])} task",
    ]
    if t:
        lines.append(f"- Vua xong: **{t['id']} {t['title']}**"
                     + (f" (commit `{t['commit']}`)" if t.get("commit") else ""))
    if nxt:
        lines.append(f"- Ke tiep: **{nxt['id']} {nxt['title']}** (Tier {nxt['tier']})")
        lines.append(f"- File duoc phep ghi: {', '.join(nxt['files']) or 'chua khai bao'}")
    else:
        lines.append("- Khong con task nao cho")

    lines.append("\n## Doc lai nhung file nay\n")
    for f, why in [
        ("00-idea.md", "nguoi dung ban dau muon gi"),
        ("02-plan.md", "ke hoach va phuong an da loai bo"),
        ("01-research.md", "quy uoc cua repo, chi doc khi dong vao vung la"),
    ]:
        if (d / f).exists():
            lines.append(f"- `.flow/runs/{run_id}/{f}` - {why}")
    if t and (d / "tasks" / t["id"] / "notes.md").exists():
        lines.append(f"- `.flow/runs/{run_id}/tasks/{t['id']}/notes.md` - quyet dinh ky thuat vua roi")

    if left:
        lines.append("\n## Con lai\n")
        for x in left:
            mark = "**can duyet** " if x["tier"] >= 2 else ""
            lines.append(f"- `{x['id']}` {x['title']} - {x['status']}, Tier {x['tier']} {mark}".rstrip())

    pend = fc.pending_approvals()
    if pend:
        lines.append("\n## Dang cho nguoi duyet\n")
        for a in pend:
            lines.append(f"- `{a['task_id']}` {a['what']}  \n  ly do: {a['reason']}")

    lines.append("\n## Buoc dau tien cua phien moi\n")
    lines.append("```bash\n.flow/flow inbox\n```\n")

    fc._atomic_write(d / "handoff.md", "\n".join(lines) + "\n")
    fc.log_event("handoff", f"ghi ban giao sau {args.task_id or '-'}")

    print(json.dumps({
        "file": str(d / "handoff.md"),
        "next_task": nxt["id"] if nxt else None,
        "goi_y_cho_nguoi_dung": (
            f"Xong {t['id'] if t else 'task'} roi. Nen cat phien moi cho "
            f"{nxt['id'] if nxt else 'viec sau'}: go `/clear` roi nhan "
            f"\"tiep tuc {nxt['id'] if nxt else ''}\"."
        ),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    cfg = fc.load_config()
    if not args.name:
        print(json.dumps({
            "dang_dung": cfg.get("profile", "khong ro"),
            "auto_mode": cfg["auto_mode"],
            "doi_bang": ".flow/flow profile production|greenfield",
        }, ensure_ascii=False, indent=2))
        return 0

    src = fc.FLOW_HOME / "profiles" / f"{args.name}.json"
    if not src.exists():
        avail = [p.stem for p in (fc.FLOW_HOME / "profiles").glob("*.json")]
        print(f"{RED}Khong co profile '{args.name}'. Co: {', '.join(avail)}{OFF}", file=sys.stderr)
        return 1

    new = json.loads(src.read_text(encoding="utf-8"))
    new["profile"] = args.name
    new.setdefault("dashboard", cfg.get("dashboard", {"host": "127.0.0.1", "port": 7788}))
    fc.save_config(new)
    fc.log_event("profile", f"doi sang {args.name}")

    a = new["auto_mode"]
    print(f"{BOLD}Da doi sang profile '{args.name}'.{OFF}")
    print(f"  Tu dong: {'bat, den Tier ' + str(a['max_tier']) if a['enabled'] else 'tat'}")
    if a["enabled"] and a["max_tier"] >= 2:
        print(f"  {AMBER}AI duoc tu chay migration, doi dependency ma khong hoi ban.{OFF}")
    return 0


def cmd_usage(args: argparse.Namespace) -> int:
    try:
        from usage import collect
    except ImportError as e:
        print(f"{RED}Khong nap duoc usage.py: {e}{OFF}", file=sys.stderr)
        return 1
    data = collect(fc.ROOT, only_latest=not args.all)
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    """Ghi nhan xet cua nguoi dung ve mot task."""
    d = fc.run_dir() / "tasks" / args.task_id
    d.mkdir(parents=True, exist_ok=True)
    with (d / "feedback.md").open("a", encoding="utf-8") as f:
        f.write(f"\n## Nhan xet {fc.now()}\n\n{args.text}\n")
    fc.log_event("feedback", args.text[:200], task_id=args.task_id)
    print(json.dumps({"ok": True, "file": str(d / "feedback.md")}, ensure_ascii=False))
    return 0


SHIM = """#!/usr/bin/env bash
# Cau noi den AI Factory. Sinh ra boi `flow.py init`, khong sua bang tay.
# Chay lai init neu ban cap nhat plugin va duong dan doi.
FLOW_PY="__FLOW_PY__"

if [ ! -f "$FLOW_PY" ]; then
  # Plugin da cap nhat va doi duong dan cache - tu tim lai
  FOUND=$(find "$HOME/.claude" -name flow_core.py -path '*ai-factory*' 2>/dev/null | head -1)
  if [ -n "$FOUND" ]; then
    FLOW_PY="$(dirname "$FOUND")/flow.py"
    sed -i.bak "s|^FLOW_PY=.*|FLOW_PY=\\"$FLOW_PY\\"|" "$0" 2>/dev/null && rm -f "$0.bak"
  else
    echo "Khong tim thay AI Factory. Cai lai plugin roi chay init mot lan nua." >&2
    exit 1
  fi
fi

export FLOW_PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$FLOW_PY" "$@"
"""


def cmd_init(args: argparse.Namespace) -> int:
    """Khoi tao AI Factory cho du an dang o. Chay mot lan cho moi du an."""
    target = Path(args.dir).resolve() if args.dir else Path.cwd().resolve()
    flow_dir = target / ".flow"

    if (flow_dir / "config.json").exists() and not args.force:
        cfg = json.loads((flow_dir / "config.json").read_text(encoding="utf-8"))
        print(json.dumps({
            "status": "da_khoi_tao",
            "profile": cfg.get("profile"),
            "message": "Du an nay da co .flow/. Them --force neu muon dat lai cau hinh.",
        }, ensure_ascii=False, indent=2))
        return 0

    profile = args.profile or "production"
    src = fc.FLOW_HOME / "profiles" / f"{profile}.json"
    if not src.exists():
        avail = sorted(p.stem for p in (fc.FLOW_HOME / "profiles").glob("*.json"))
        print(f"{RED}Khong co profile '{profile}'. Co: {', '.join(avail)}{OFF}", file=sys.stderr)
        return 1

    for sub in ("runs", "queue"):
        (flow_dir / sub).mkdir(parents=True, exist_ok=True)

    cfg = json.loads(src.read_text(encoding="utf-8"))
    cfg["profile"] = profile
    cfg.setdefault("dashboard", {"host": "127.0.0.1", "port": 7788})
    cfg.setdefault("approve_mode", "queue")
    (flow_dir / "config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

    # Cau noi: sau buoc nay moi lenh chi con `.flow/flow <gi do>`
    shim = flow_dir / "flow"
    shim.write_text(SHIM.replace("__FLOW_PY__", str(fc.FLOW_HOME / "scripts" / "flow.py")),
                    encoding="utf-8")
    shim.chmod(0o755)

    # gitignore: giu config, bo trang thai chay
    gi = target / ".gitignore"
    want = [".flow/runs/", ".flow/queue/", ".flow/approvals_adhoc/", ".flow/current.json",
             ".flow/telegram_bot.json", ".flow/flow", ".env.flow"]
    have = gi.read_text(encoding="utf-8") if gi.exists() else ""
    missing = [w for w in want if w not in have]
    if missing:
        with gi.open("a", encoding="utf-8") as f:
            f.write(("\n" if have and not have.endswith("\n") else "") + "\n# AI Factory\n")
            f.write("\n".join(missing) + "\n")

    print(json.dumps({
        "status": "xong",
        "du_an": str(target),
        "profile": profile,
        "lenh_tu_gio": ".flow/flow status",
        "da_them_vao_gitignore": missing,
        "nen_commit": [".flow/config.json"],
        "buoc_tiep": [
            "Neu la codebase dang chay that thi giu profile production.",
            "Du an moi: .flow/flow profile greenfield",
            "Mo bang dieu khien: .flow/flow dashboard",
        ],
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    """Mo bang dieu khien. De o day de khong phai nho duong dan script."""
    cmd = [sys.executable, str(fc.FLOW_HOME / "scripts" / "dashboard.py")]
    if args.allow_spawn:
        cmd.append("--allow-spawn")
    if args.no_open:
        cmd.append("--no-open")
    env = dict(os.environ, FLOW_PROJECT_DIR=str(fc.ROOT))
    return subprocess.call(cmd, cwd=fc.ROOT, env=env)


def cmd_telegram(args: argparse.Namespace) -> int:
    """Chay bot Telegram de xem va duyet tu xa."""
    cmd = [sys.executable, str(fc.FLOW_HOME / "scripts" / "telegram_bot.py")]
    env = dict(os.environ, FLOW_PROJECT_DIR=str(fc.ROOT))
    return subprocess.call(cmd, cwd=fc.ROOT, env=env)


def cmd_runs(args: argparse.Namespace) -> int:
    """Liet ke cac run da co, moi nhat truoc."""
    if not fc.RUNS.exists():
        print("Chua co run nao.")
        return 0
    cur = fc.get_current().get("run_id")
    rows = []
    for d in sorted(fc.RUNS.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        idea, done, total = "", 0, 0
        try:
            idea = json.loads((d / "state.json").read_text(encoding="utf-8")).get("idea", "")
        except (OSError, json.JSONDecodeError):
            pass
        try:
            ts = json.loads((d / "tasks.json").read_text(encoding="utf-8")).get("tasks", [])
            total = len(ts)
            done = sum(1 for t in ts if t.get("status") == "done")
        except (OSError, json.JSONDecodeError):
            pass
        rows.append((d.name, done, total, idea))

    if not rows:
        print("Chua co run nao.")
        return 0

    print(f"{DIM}{'RUN':<22} {'TIEN DO':<9} VIEC{OFF}")
    for name, done, total, idea in rows[: args.limit]:
        mark = f"{GREEN}*{OFF}" if name == cur else " "
        prog = f"{done}/{total}" if total else "-"
        print(f"{mark}{name:<21} {prog:<9} {idea[:56]}")
    print(f"\n{DIM}* = run dang mo. Chuyen sang run khac: flow.py resume <RUN>{OFF}")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    """Mo lai mot run cu de lam tiep."""
    d = fc.RUNS / args.run_id
    if not d.is_dir():
        print(f"{RED}Khong co run {args.run_id}. Xem danh sach: flow.py runs{OFF}", file=sys.stderr)
        return 1

    fc.set_current(args.run_id)
    fc.log_event("run_resumed", args.run_id, run_id=args.run_id)
    data = fc.load_tasks(args.run_id)
    nxt = fc.next_task(data)
    pend = fc.pending_approvals(args.run_id)

    print(json.dumps({
        "run_id": args.run_id,
        "tasks_total": len(data.get("tasks", [])),
        "tasks_done": sum(1 for t in data.get("tasks", []) if t.get("status") == "done"),
        "next_task": nxt["id"] if nxt else None,
        "pending_approvals": [a["task_id"] for a in pend],
        "doc_lai_nhung_file_nay": [
            f".flow/runs/{args.run_id}/00-idea.md",
            f".flow/runs/{args.run_id}/01-research.md",
            f".flow/runs/{args.run_id}/02-plan.md",
        ],
        "next_step": ("Co viec dang cho nguoi duyet, bao nguoi dung truoc." if pend
                      else "Doc lai cac file tren de lay lai context, roi chay flow.py next."
                      if nxt else "Run nay da xong het task."),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cur = fc.get_current()
    if not cur.get("run_id"):
        print("Chua co run nao.")
        return 0
    data = fc.load_tasks()
    cfg = fc.load_config()

    if args.json:
        print(json.dumps({
            "run_id": cur["run_id"],
            "auto_mode": cfg["auto_mode"],
            "tasks": data["tasks"],
            "pending_approvals": fc.pending_approvals(),
        }, ensure_ascii=False, indent=2))
        return 0

    auto = cfg["auto_mode"]
    auto_txt = (f"{GREEN}bat{OFF} (tu chay den Tier {auto['max_tier']})" if auto["enabled"]
                else f"{DIM}tat{OFF}")
    print(f"{BOLD}Run{OFF} {cur['run_id']}   {BOLD}Che do tu dong:{OFF} {auto_txt}\n")
    _print_table(data["tasks"], cfg)

    pend = fc.pending_approvals()
    if pend:
        print(f"\n{AMBER}{BOLD}Dang cho ban quyet dinh:{OFF}")
        for a in pend:
            print(f"  [{a['task_id']}] {a['what']}")
            print(f"      ly do: {a['reason']}")
        print(f"\n  Duyet:    .flow/flow approve <task_id>")
        print(f"  Tu choi:  .flow/flow reject <task_id> --note \"...\"")
        print(f"  Hoac mo:  python scripts/dashboard.py")
    return 0


def _print_table(tasks: list[dict], cfg: dict) -> None:
    if not tasks:
        print(f"{DIM}Chua co task nao.{OFF}")
        return
    w = max((len(t["title"]) for t in tasks), default=10)
    w = min(max(w, 20), 52)
    print(f"{DIM}{'ID':<5} {'TIER':<5} {'TRANG THAI':<18} {'VIEC':<{w}}{OFF}")
    for t in tasks:
        c = STATUS_COLOR.get(t["status"], "")
        title = t["title"][:w]
        mark = {0: "\u00b7", 1: "\u2013", 2: "!"}.get(t["tier"], "?")
        print(f"{t['id']:<5} {mark} {t['tier']:<3} {c}{t['status']:<18}{OFF} {title:<{w}}")
    print(f"\n{DIM}Tier 0 tu chay  |  Tier 1 tu chay roi bao cao  |  Tier 2 phai duoc ban duyet{OFF}")


def cmd_auto(args: argparse.Namespace) -> int:
    cfg = fc.load_config()
    cfg["auto_mode"]["enabled"] = args.state == "on"
    if args.max_tier is not None:
        cfg["auto_mode"]["max_tier"] = args.max_tier
    fc.save_config(cfg)
    a = cfg["auto_mode"]
    fc.log_event("auto_mode", f"{'bat' if a['enabled'] else 'tat'}, max_tier={a['max_tier']}")
    if a["enabled"] and a["max_tier"] >= 2:
        print(f"{RED}Canh bao: max_tier=2 nghia la AI duoc tu chay ca migration, "
              f"doi dependency, thay auth ma khong hoi ban.{OFF}")
    print(json.dumps(a, ensure_ascii=False, indent=2))
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    a = fc.decide_approval(args.task_id, "approved", args.note or "")
    try:
        data = fc.load_tasks()
        t = fc.find_task(data, args.task_id)
        if t and t["status"] == "awaiting_approval":
            t["status"] = "pending"
            fc.save_tasks(data)
    except SystemExit:
        pass  # khong co run dang chay - phieu roi rac van duyet duoc binh thuong
    print(json.dumps(a, ensure_ascii=False, indent=2))
    return 0


def cmd_reject(args: argparse.Namespace) -> int:
    a = fc.decide_approval(args.task_id, "rejected", args.note or "")
    try:
        data = fc.load_tasks()
        t = fc.find_task(data, args.task_id)
        if t:
            t["status"] = "skipped"
            fc.save_tasks(data)
    except SystemExit:
        pass
    print(json.dumps(a, ensure_ascii=False, indent=2))
    return 0


def cmd_event(args: argparse.Namespace) -> int:
    fc.log_event(args.kind, args.message, task_id=args.task_id)
    return 0


# ---------------------------------------------------------------- thong bao


def _notify_approval(t: dict) -> None:
    cfg = fc.load_config()
    if not cfg["notify"].get("on_approval_needed"):
        return
    _notice("approval_notice", t.get("id"), t.get("title", ""), t.get("tier_reason", ""),
            t.get("tier", 2), paths=None)


# ---------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="flow.py", description="Dieu khien AI Factory")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("start", help="Bat dau run moi tu mot y tuong")
    s.add_argument("idea")
    s.set_defaults(func=cmd_start)

    s = sub.add_parser("tier", help="Hoi xem viec nay thuoc tier nao")
    s.add_argument("--paths", nargs="*", default=[])
    s.add_argument("--command")
    s.add_argument("--text")
    s.set_defaults(func=cmd_tier)

    s = sub.add_parser("plan-import", help="Nap tasks.json tu planner")
    s.add_argument("file")
    s.set_defaults(func=cmd_plan_import)

    s = sub.add_parser("next", help="Task ke tiep co the chay")
    s.set_defaults(func=cmd_next)

    s = sub.add_parser("claim", help="Nhan task de bat dau lam")
    s.add_argument("task_id")
    s.set_defaults(func=cmd_claim)

    s = sub.add_parser("ask", help="Xin y kien nguoi giua chung")
    s.add_argument("task_id")
    s.add_argument("question")
    s.add_argument("--reason")
    s.add_argument("--tier", type=int, default=2)
    s.add_argument("--options", nargs="*")
    s.set_defaults(func=cmd_ask)

    s = sub.add_parser("wait", help="Cho quyet dinh cua nguoi")
    s.add_argument("task_id")
    s.add_argument("--timeout", type=int)
    s.set_defaults(func=cmd_wait)

    s = sub.add_parser("gate", help="Chay cong kiem tra bang may")
    s.add_argument("task_id")
    s.set_defaults(func=cmd_gate)

    s = sub.add_parser("done", help="Danh dau xong, tuy chon commit")
    s.add_argument("task_id")
    s.add_argument("--commit", action="store_true")
    s.add_argument("--message")
    s.add_argument("--force", action="store_true", help="Bo qua yeu cau phai qua cong")
    s.set_defaults(func=cmd_done)

    s = sub.add_parser("fail", help="Bao task that bai")
    s.add_argument("task_id")
    s.add_argument("reason")
    s.set_defaults(func=cmd_fail)

    s = sub.add_parser("init", help="Khoi tao AI Factory cho du an nay. Chay mot lan.")
    s.add_argument("--dir")
    s.add_argument("--profile", choices=["production", "greenfield"])
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("dashboard", help="Mo bang dieu khien web")
    s.add_argument("--allow-spawn", action="store_true", dest="allow_spawn")
    s.add_argument("--no-open", action="store_true", dest="no_open")
    s.set_defaults(func=cmd_dashboard)

    s = sub.add_parser("telegram", help="Chay bot Telegram: xem tinh hinh va duyet tu xa")
    s.set_defaults(func=cmd_telegram)

    s = sub.add_parser("inbox", help="Doc hang doi quyet dinh tu web. Chay dau moi luot.")
    s.set_defaults(func=cmd_inbox)

    s = sub.add_parser("route", help="De xuat tuyen chay dua tren so lieu")
    s.add_argument("--files", nargs="*", default=[])
    s.add_argument("--intent", default="")
    s.add_argument("--explore-only", action="store_true", dest="explore_only")
    s.set_defaults(func=cmd_route)

    s = sub.add_parser("hand-off", help="Ghi ban giao cho phien Claude ke tiep")
    s.add_argument("task_id", nargs="?")
    s.set_defaults(func=cmd_handoff)

    s = sub.add_parser("profile", help="Xem hoac doi bo cau hinh (production / greenfield)")
    s.add_argument("name", nargs="?")
    s.set_defaults(func=cmd_profile)

    s = sub.add_parser("usage", help="Token da dung va uoc tinh chi phi")
    s.add_argument("--all", action="store_true")
    s.set_defaults(func=cmd_usage)

    s = sub.add_parser("note", help="Ghi nhan xet cua nguoi dung ve mot task")
    s.add_argument("task_id")
    s.add_argument("text")
    s.set_defaults(func=cmd_note)

    s = sub.add_parser("runs", help="Liet ke cac run da co")
    s.add_argument("--limit", type=int, default=15)
    s.set_defaults(func=cmd_runs)

    s = sub.add_parser("resume", help="Mo lai mot run cu de lam tiep")
    s.add_argument("run_id")
    s.set_defaults(func=cmd_resume)

    s = sub.add_parser("status", help="Xem bang trang thai")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("auto", help="Bat tat che do tu dong chay tiep")
    s.add_argument("state", choices=["on", "off"])
    s.add_argument("--max-tier", type=int, dest="max_tier")
    s.set_defaults(func=cmd_auto)

    s = sub.add_parser("approve", help="Duyet mot task dang cho")
    s.add_argument("task_id")
    s.add_argument("--note")
    s.set_defaults(func=cmd_approve)

    s = sub.add_parser("reject", help="Tu choi mot task dang cho")
    s.add_argument("task_id")
    s.add_argument("--note")
    s.set_defaults(func=cmd_reject)

    s = sub.add_parser("event", help="Ghi mot dong vao nhat ky")
    s.add_argument("kind")
    s.add_argument("message")
    s.add_argument("--task-id", dest="task_id")
    s.set_defaults(func=cmd_event)

    return p


def _utf8_stdio() -> None:
    # Windows: stdout bi chuyen huong dung cp1252, in tieng Viet co dau se vo.
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")


if __name__ == "__main__":
    _utf8_stdio()
    _args = build_parser().parse_args()
    sys.exit(_args.func(_args))
