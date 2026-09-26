"""Loi dung chung cho AI Factory.

Moi thu trong he thong doc/ghi qua day: duong dan, config, phan tier,
doc/ghi tasks.json, ghi events.jsonl. Khong co state nao nam trong dau agent.
"""

from __future__ import annotations

import fnmatch
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Duong dan
# --------------------------------------------------------------------------


# FLOW_HOME = noi chua scripts/ va profiles/. Dung chung cho MOI du an.
# Khi cai bang plugin, day la cache cua plugin, khong phai thu muc du an.
FLOW_HOME = Path(__file__).resolve().parent.parent


def project_root() -> Path:
    """Tim goc DU AN - noi chua .flow/. Khac han FLOW_HOME.

    Thu tu tim, quan trong vi script co the nam ngoai du an (che do plugin):
      1. bien moi truong tro thang den du an
      2. di nguoc len tu thu muc dang lam viec
      3. di nguoc len tu vi tri script (truong hop chep thang vao repo)
      4. thu muc dang lam viec
    """
    env = os.environ.get("FLOW_PROJECT_DIR") or os.environ.get("CLAUDE_PROJECT_DIR")
    if env and (Path(env) / ".flow").is_dir():
        return Path(env).resolve()

    for start in (Path.cwd().resolve(), Path(__file__).resolve().parent):
        for parent in [start, *start.parents]:
            if (parent / ".flow").is_dir():
                return parent

    return Path(env).resolve() if env else Path.cwd().resolve()


ROOT = project_root()


def is_initialised() -> bool:
    return (ROOT / ".flow" / "config.json").is_file()
FLOW = ROOT / ".flow"
RUNS = FLOW / "runs"
CONFIG_PATH = FLOW / "config.json"
CURRENT_PATH = FLOW / "current.json"
ADHOC_APPROVALS = FLOW / "approvals_adhoc"


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise SystemExit(
            f"Du an nay chua duoc khoi tao ({CONFIG_PATH} khong ton tai).\n"
            f"Chay mot lan: python3 \"{FLOW_HOME}/scripts/flow.py\" init")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(cfg: dict[str, Any]) -> None:
    _atomic_write(CONFIG_PATH, json.dumps(cfg, ensure_ascii=False, indent=2))


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------
# Phan tier: luat tinh, khong phu thuoc vao phan doan cua model
# --------------------------------------------------------------------------


def _match_path(path: str, patterns: list[str]) -> str | None:
    p = str(path).replace("\\", "/").lstrip("./")
    for pat in patterns:
        if fnmatch.fnmatch(p, pat) or fnmatch.fnmatch("/" + p, pat) or fnmatch.fnmatch(Path(p).name, pat):
            return pat
    return None


def _match_text(text: str, needles: list[str]) -> str | None:
    low = (text or "").lower()
    for n in needles:
        if n.lower() in low:
            return n
    return None


def classify(
    *,
    paths: list[str] | None = None,
    command: str | None = None,
    text: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> tuple[int, str]:
    """Tra ve (tier, ly_do).

    Tier cao nhat khop duoc thang. Khong khop gi -> default_tier.
    Day la ham quyet dinh duy nhat trong he thong: hook, CLI va dashboard
    deu goi no, nen ket qua luon nhat quan.
    """
    cfg = cfg or load_config()
    rules = cfg.get("tier_rules", {})
    default = int(cfg.get("default_tier", 1))
    tiers_desc = sorted((int(t) for t in rules), reverse=True)

    def tier_of_path(pth: str) -> tuple[int, str]:
        for tier in tiers_desc:
            hit = _match_path(pth, rules[str(tier)].get("paths", []))
            if hit:
                return tier, f"'{pth}' khop mau '{hit}'"
        return default, f"'{pth}' khong khop luat nao"

    def tier_of_command(cmd: str) -> tuple[int, str]:
        for tier in tiers_desc:
            rule = rules[str(tier)]
            hit = _match_text(cmd, rule.get("commands", []))
            if hit:
                return tier, f"lenh chua '{hit}'"
            hit = _match_text(cmd, rule.get("keywords", []))
            if hit:
                return tier, f"lenh chua tu khoa '{hit}'"
        return default, "lenh khong khop luat nao"

    # Tier cua ca nhom = tier cua hang muc NGUY HIEM NHAT trong nhom.
    # Mot file test an toan khong duoc keo tut tier cua ca task.
    candidates: list[tuple[int, str]] = []

    if command:
        candidates.append(tier_of_command(command))
    for pth in paths or []:
        candidates.append(tier_of_path(pth))
    if text:
        for tier in tiers_desc:
            hit = _match_text(text, rules[str(tier)].get("keywords", []))
            if hit:
                candidates.append((tier, f"noi dung chua tu khoa '{hit}'"))
                break

    if not candidates:
        return default, "khong co gi de danh gia, dung tier mac dinh"

    return max(candidates, key=lambda c: c[0])


def tier_label(tier: int, cfg: dict[str, Any] | None = None) -> str:
    cfg = cfg or load_config()
    return cfg.get("tier_labels", {}).get(str(tier), f"Tier {tier}")


def auto_allows(tier: int, cfg: dict[str, Any] | None = None) -> bool:
    """Che do tu dong co cho phep tier nay chay khong hoi khong."""
    cfg = cfg or load_config()
    auto = cfg.get("auto_mode", {})
    return bool(auto.get("enabled")) and tier <= int(auto.get("max_tier", 1))


# --------------------------------------------------------------------------
# Run hien tai
# --------------------------------------------------------------------------


def set_current(run_id: str, task_id: str | None = None) -> None:
    _atomic_write(
        CURRENT_PATH,
        json.dumps({"run_id": run_id, "task_id": task_id, "at": now()}, ensure_ascii=False, indent=2),
    )


def get_current() -> dict[str, Any]:
    if not CURRENT_PATH.exists():
        return {}
    try:
        return json.loads(CURRENT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def run_dir(run_id: str | None = None) -> Path:
    run_id = run_id or get_current().get("run_id")
    if not run_id:
        raise SystemExit("Chua co run nao. Chay: python scripts/flow.py start \"y tuong cua ban\"")
    return RUNS / run_id


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M") + "-" + uuid.uuid4().hex[:4]


# --------------------------------------------------------------------------
# Tasks
# --------------------------------------------------------------------------

TASK_STATUSES = (
    "pending",          # chua bat dau
    "running",          # dang lam
    "awaiting_approval",  # dang cho ban bam duyet
    "gate_failed",      # cong kiem tra bang may truot
    "review_failed",    # verifier tu choi
    "done",             # xong, da qua cong
    "blocked",          # phu thuoc chua xong hoac bi chan
    "skipped",
)


def tasks_path(run_id: str | None = None) -> Path:
    return run_dir(run_id) / "tasks.json"


def load_tasks(run_id: str | None = None) -> dict[str, Any]:
    p = tasks_path(run_id)
    if not p.exists():
        return {"run_id": run_id or get_current().get("run_id"), "tasks": []}
    return json.loads(p.read_text(encoding="utf-8"))


def save_tasks(data: dict[str, Any], run_id: str | None = None) -> None:
    _atomic_write(tasks_path(run_id), json.dumps(data, ensure_ascii=False, indent=2))


def find_task(data: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    for t in data.get("tasks", []):
        if t.get("id") == task_id:
            return t
    return None


def next_task(data: dict[str, Any]) -> dict[str, Any] | None:
    """Task ke tiep co the chay: pending + moi phu thuoc da done."""
    done = {t["id"] for t in data.get("tasks", []) if t.get("status") == "done"}
    for t in data.get("tasks", []):
        if t.get("status") not in ("pending", "blocked"):
            continue
        if all(d in done for d in t.get("depends_on", [])):
            return t
    return None


# --------------------------------------------------------------------------
# Su kien
# --------------------------------------------------------------------------


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def log_event(kind: str, message: str, *, run_id: str | None = None, **extra: Any) -> None:
    try:
        d = run_dir(run_id)
    except SystemExit:
        return
    d.mkdir(parents=True, exist_ok=True)
    rec = {"at": now(), "kind": kind, "message": message, **extra}
    with (d / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_events(run_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    p = run_dir(run_id) / "events.jsonl"
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


# --------------------------------------------------------------------------
# Hang doi: quyet dinh nguoi dung bam tren web luc Claude khong chay
# --------------------------------------------------------------------------

QUEUE = FLOW / "queue"


def queue_push(kind: str, payload: dict[str, Any]) -> Path:
    """Bang dieu khien web ghi vao day. Claude doc o dau moi luot."""
    QUEUE.mkdir(parents=True, exist_ok=True)
    p = QUEUE / f"{int(time.time() * 1000)}-{kind}.json"
    _atomic_write(p, json.dumps({"kind": kind, "at": now(), **payload},
                                ensure_ascii=False, indent=2))
    return p


def queue_drain() -> list[dict[str, Any]]:
    """Doc va xoa moi muc trong hang doi. Goi mot lan o dau luot."""
    if not QUEUE.is_dir():
        return []
    out = []
    for p in sorted(QUEUE.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
        try:
            p.unlink()
        except OSError:
            pass
    return out


# --------------------------------------------------------------------------
# Phe duyet
# --------------------------------------------------------------------------


def approvals_dir(run_id: str | None = None) -> Path:
    """Thu muc chua phieu duyet.

    Neu dang trong mot run thi dung .flow/runs/<id>/approvals/ nhu binh
    thuong. Neu KHONG co run nao dang chay (vd: mot lenh Tier 2 roi rac
    ngoai quy trinh, nhu git push thu cong) thi rot ve mot thu muc chung
    o cap du an (.flow/approvals_adhoc/) thay vi nem loi - hang rao tier
    guard khong duoc phep phu thuoc vao viec co run hay khong.
    """
    try:
        d = run_dir(run_id) / "approvals"
    except SystemExit:
        d = ADHOC_APPROVALS
    d.mkdir(parents=True, exist_ok=True)
    return d


def request_approval(
    task_id: str,
    what: str,
    reason: str,
    *,
    tier: int = 2,
    run_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> Path:
    """Tao phieu cho duyet. Dashboard doc phieu nay va hien nut."""
    p = approvals_dir(run_id) / f"{task_id}.json"

    # Giu lai danh sach nhung viec da duoc duyet truoc do trong cung task.
    approved_items: list[str] = []
    if p.exists():
        try:
            old = json.loads(p.read_text(encoding="utf-8"))
            approved_items = old.get("approved_items", [])
            if old.get("decision") is None and old.get("what") == what:
                return p  # dang co phieu cho dung viec nay, khong tao trung
        except json.JSONDecodeError:
            pass

    payload = {
        "task_id": task_id,
        "what": what,
        "reason": reason,
        "tier": tier,
        "requested_at": now(),
        "decision": None,
        "decided_at": None,
        "note": None,
        "approved_items": approved_items,
        "details": details or {},
    }
    _atomic_write(p, json.dumps(payload, ensure_ascii=False, indent=2))
    log_event("approval_requested", what, run_id=run_id, task_id=task_id, tier=tier, reason=reason)
    return p


def read_approval(task_id: str, run_id: str | None = None) -> dict[str, Any] | None:
    p = approvals_dir(run_id) / f"{task_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def decide_approval(task_id: str, decision: str, note: str = "", run_id: str | None = None) -> dict[str, Any]:
    p = approvals_dir(run_id) / f"{task_id}.json"
    data = read_approval(task_id, run_id) or {
        "task_id": task_id, "what": "", "reason": "", "tier": 2, "approved_items": [],
    }
    data["decision"] = decision
    data["decided_at"] = now()
    data["note"] = note

    # Chi ghi nhan DUNG viec vua duoc duyet. Duyet mot viec khong mo duong
    # cho moi viec khac trong cung task.
    if decision == "approved":
        items = data.setdefault("approved_items", [])
        what = data.get("what", "")
        if what and what not in items:
            items.append(what)
        scope_files = (data.get("details") or {}).get("files") or []
        for f in scope_files:
            if f not in items:
                items.append(f)

    _atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2))
    log_event("approval_decided", f"{decision}: {data.get('what', '')}", run_id=run_id, task_id=task_id, note=note)
    return data


def is_approved(task_id: str, what: str, *, paths: list[str] | None = None,
                run_id: str | None = None) -> bool:
    """Viec cu the nay da duoc duyet trong pham vi task nay chua.

    Duyet mot viec chi co gia tri cho dung viec do, cong voi nhung file da
    khai bao trong task luc duyet. Moi viec khac phai xin duyet lai.
    """
    a = read_approval(task_id, run_id)
    if not a or a.get("decision") != "approved":
        return False

    items = a.get("approved_items") or []
    if what in items:
        return True

    # Ghi vao file nam trong pham vi da duyet thi cho qua.
    if paths and all(p in items for p in paths):
        return True

    return False


def wait_for_approval(task_id: str, timeout_s: int, run_id: str | None = None, poll: float = 2.0) -> dict[str, Any]:
    """Cho ban bam nut tren dashboard. Tra ve phieu da co quyet dinh, hoac timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        a = read_approval(task_id, run_id)
        if a and a.get("decision"):
            return a
        time.sleep(poll)
    return {"task_id": task_id, "decision": "timeout", "note": f"Khong co phan hoi sau {timeout_s}s"}


def pending_approvals(run_id: str | None = None) -> list[dict[str, Any]]:
    try:
        d = approvals_dir(run_id)
    except SystemExit:
        return []
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            a = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not a.get("decision"):
            out.append(a)
    return out
