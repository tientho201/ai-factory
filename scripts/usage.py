#!/usr/bin/env python3
"""Doc luong token da dung tu transcript cua Claude Code.

Claude Code ghi transcript dang JSONL trong ~/.claude/projects/<slug>/.
Moi dong co the chua truong `usage` voi so token. Module nay cong lai.

Viet phong thu: neu Claude Code doi cau truc file, ham tra ve so 0 kem ghi chu
thay vi nem loi. Do token la tien ich, khong duoc lam vo workflow.

    python scripts/usage.py            # phien hien tai
    python scripts/usage.py --all      # toan bo project
    python scripts/usage.py --json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Gia tham khao, don vi USD tren 1 trieu token. Sua o day neu gia thay doi.
# Day chi de uoc luong tuong doi, khong phai hoa don that.
PRICES = {
    "opus":   {"in": 15.0, "out": 75.0, "cache_write": 18.75, "cache_read": 1.50},
    "sonnet": {"in": 3.0,  "out": 15.0, "cache_write": 3.75,  "cache_read": 0.30},
    "haiku":  {"in": 1.0,  "out": 5.0,  "cache_write": 1.25,  "cache_read": 0.10},
}


def _price_for(model: str) -> dict[str, float]:
    m = (model or "").lower()
    for key in ("opus", "sonnet", "haiku"):
        if key in m:
            return PRICES[key]
    return PRICES["sonnet"]


def project_slug(project_dir: Path) -> str:
    """Claude Code doi duong dan project thanh ten thu muc."""
    return str(project_dir.resolve()).replace("/", "-").replace("\\", "-").replace(":", "-")


def transcript_dirs(project_dir: Path) -> list[Path]:
    base = Path.home() / ".claude" / "projects"
    if not base.is_dir():
        return []
    slug = project_slug(project_dir)
    exact = base / slug
    if exact.is_dir():
        return [exact]
    # du phong: khop gan dung theo ten thu muc cuoi
    tail = project_dir.resolve().name
    return [d for d in base.iterdir() if d.is_dir() and d.name.endswith(tail)]


def _walk_usage(obj: object) -> list[dict]:
    """Tim moi khoi `usage` o bat ky do sau nao. Chong thay doi cau truc."""
    found = []
    if isinstance(obj, dict):
        u = obj.get("usage")
        if isinstance(u, dict) and any(
            k in u for k in ("input_tokens", "output_tokens", "cache_read_input_tokens")
        ):
            found.append({"usage": u, "model": obj.get("model") or ""})
        for v in obj.values():
            found.extend(_walk_usage(v))
    elif isinstance(obj, list):
        for v in obj:
            found.extend(_walk_usage(v))
    return found


def read_session(path: Path) -> dict:
    tot = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0,
           "turns": 0, "cost": 0.0, "models": set()}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {**tot, "models": []}

    for ln in lines:
        if not ln.strip():
            continue
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        for hit in _walk_usage(rec):
            u, model = hit["usage"], hit["model"] or rec.get("model", "")
            i = int(u.get("input_tokens") or 0)
            o = int(u.get("output_tokens") or 0)
            cw = int(u.get("cache_creation_input_tokens") or 0)
            cr = int(u.get("cache_read_input_tokens") or 0)
            if not (i or o or cw or cr):
                continue
            p = _price_for(model)
            tot["input"] += i
            tot["output"] += o
            tot["cache_write"] += cw
            tot["cache_read"] += cr
            tot["turns"] += 1
            tot["cost"] += (i * p["in"] + o * p["out"]
                            + cw * p["cache_write"] + cr * p["cache_read"]) / 1_000_000
            if model:
                tot["models"].add(model)

    tot["models"] = sorted(tot["models"])
    return tot


def collect(project_dir: Path, *, only_latest: bool = True) -> dict:
    sessions = []
    for d in transcript_dirs(project_dir):
        for f in d.rglob("*.jsonl"):
            if "subagents" in f.parts and only_latest:
                continue  # dem rieng ben duoi
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            sessions.append((mtime, f))

    if not sessions:
        return {"available": False,
                "note": "Khong doc duoc transcript. Co the Claude Code luu o cho khac, "
                        "hoac phien nay chua ghi gi.",
                "total": _empty(), "sessions": []}

    sessions.sort(reverse=True)
    picked = sessions[:1] if only_latest else sessions

    out, total = [], _empty()
    for mtime, f in picked:
        s = read_session(f)
        if not s["turns"]:
            continue
        s["file"] = f.name
        s["mtime"] = mtime
        out.append(s)
        for k in ("input", "output", "cache_write", "cache_read", "turns"):
            total[k] += s[k]
        total["cost"] += s["cost"]

    total["total_tokens"] = (total["input"] + total["output"]
                             + total["cache_write"] + total["cache_read"])
    return {"available": bool(out), "total": total, "sessions": out,
            "note": "" if out else "Tim thay transcript nhung chua co so lieu token."}


def _empty() -> dict:
    return {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0,
            "turns": 0, "cost": 0.0, "total_tokens": 0}


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


if __name__ == "__main__":
    pd = Path(os.environ.get("FLOW_PROJECT_DIR") or os.environ.get("CLAUDE_PROJECT_DIR") or Path.cwd())
    data = collect(pd, only_latest="--all" not in sys.argv)

    if "--json" in sys.argv:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        sys.exit(0)

    if not data["available"]:
        print(data["note"])
        sys.exit(0)

    t = data["total"]
    print(f"Token:      {_fmt(t['total_tokens'])} tong")
    print(f"  vao       {_fmt(t['input'])}")
    print(f"  ra        {_fmt(t['output'])}")
    print(f"  cache ghi {_fmt(t['cache_write'])}")
    print(f"  cache doc {_fmt(t['cache_read'])}  (re nhat, cang nhieu cang tot)")
    print(f"Luot goi:   {t['turns']}")
    print(f"Uoc tinh:   ${t['cost']:.2f}  (gia tham khao, khong phai hoa don that)")
