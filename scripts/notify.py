#!/usr/bin/env python3
"""Gui thong bao ra ngoai. Nguyen tac: khong bao gio nem loi ra workflow.

Cau hinh bang bien moi truong (dat trong .env.flow hoac shell):

    FLOW_SMTP_USER=ban@gmail.com
    FLOW_SMTP_PASS=<app password 16 ky tu, KHONG phai mat khau Gmail>
    FLOW_NOTIFY_TO=ban@gmail.com       (nhieu nguoi: cach nhau dau phay)
    FLOW_SMTP_HOST=smtp.gmail.com      (mac dinh)
    FLOW_SMTP_PORT=587                 (mac dinh)

Tuy chon them, gui song song:
    FLOW_WEBHOOK_URL=https://hooks.slack.com/...   Slack, Discord, hoac bat ky.
                                                   Nhieu URL: cach nhau dau phay.
    FLOW_WEBHOOK_KIND=slack|discord|generic        (mac dinh: doan theo URL)
    FLOW_TELEGRAM_TOKEN=123:ABC
    FLOW_TELEGRAM_CHAT_ID=456
    FLOW_DASHBOARD_URL=https://...                 link dashboard ghi trong thong bao
                                                   (vd qua tunnel), mac dinh 127.0.0.1

Lay app password Gmail: myaccount.google.com > Security > 2-Step Verification
> App passwords. Bat buoc phai bat xac thuc 2 buoc truoc.

Chay thu:  python scripts/notify.py --test
           python scripts/notify.py --preview approval   (in ra, khong gui)
"""

from __future__ import annotations

import html
import json
import os
import re
import smtplib
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Any


def _load_env_file() -> None:
    """Doc .env.flow o goc project neu co, khong ghi de bien da ton tai."""
    bases = []
    for key in ("FLOW_PROJECT_DIR", "CLAUDE_PROJECT_DIR"):
        if os.environ.get(key):
            bases.append(Path(os.environ[key]))
    bases += [Path.cwd(), Path(__file__).resolve().parent.parent]
    for base in bases:
        f = base / ".env.flow"
        if not f.exists():
            continue
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))
        return


_load_env_file()


# --------------------------------------------------------------------------
# Mo hinh thong bao: mot noi dung, moi kenh tu dung giao dien rieng
# --------------------------------------------------------------------------

KINDS = {
    #            nhan ngan          mau
    "approval": ("CẦN BẠN DUYỆT", "#f59e0b"),
    "fail":     ("THẤT BẠI",      "#dc2626"),
    "pass":     ("HOÀN THÀNH",    "#16a34a"),
    "run_done": ("XONG RUN",      "#2563eb"),
    "info":     ("THÔNG BÁO",     "#6b7280"),
}


@dataclass
class Notice:
    kind: str
    title: str
    lead: str = ""
    fields: list[tuple[str, str]] = field(default_factory=list)
    # (tieu de, noi dung, hien dang code?)
    sections: list[tuple[str, str, bool]] = field(default_factory=list)
    # (mo ta, lenh hoac URL)
    actions: list[tuple[str, str]] = field(default_factory=list)
    link: str = ""
    footer: str = ""

    @property
    def label(self) -> str:
        return KINDS.get(self.kind, KINDS["info"])[0]

    @property
    def color(self) -> str:
        return KINDS.get(self.kind, KINDS["info"])[1]

    @property
    def subject(self) -> str:
        return f"[AI Factory] {self.label}: {self.title}"[:180]


_SECRET_PATTERNS = [
    re.compile(r"(?i)\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|PASS|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY)[A-Z0-9_]*)"
               r"(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)"),
    re.compile(r"(?i)(authorization:\s*(?:bearer|basic|token)\s+)\S+"),
    re.compile(r"(?i)(--(?:password|token|secret|api-key)[= ])\S+"),
    re.compile(r"(https?://)[^/\s:@]+:[^/\s@]+@"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}"
               r"|xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,})\b"),
]


def redact(text: str) -> str:
    """Che nhung chuoi trong giong secret truoc khi gui ra ngoai may."""
    s = text or ""
    s = _SECRET_PATTERNS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}***", s)
    s = _SECRET_PATTERNS[1].sub(r"\1***", s)
    s = _SECRET_PATTERNS[2].sub(r"\1***", s)
    s = _SECRET_PATTERNS[3].sub(r"\1***:***@", s)
    s = _SECRET_PATTERNS[4].sub("***", s)
    return s


def _is_cmd(s: str) -> bool:
    return s.startswith((".flow/", "python", "git ", "bash "))


def _cut(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[: max(0, n - 1)] + "…"


def _tail(s: str, n: int) -> str:
    s = (s or "").rstrip()
    return s if len(s) <= n else "…" + s[-(n - 1):]


# ---------------------------------------------------------------- render


def render_text(n: Notice) -> str:
    out = [f"{n.label} — {n.title}", ""]
    if n.lead:
        out += [n.lead, ""]
    if n.fields:
        w = max(len(k) for k, _ in n.fields)
        out += [f"{k.ljust(w)} : {v}" for k, v in n.fields] + [""]
    for head, body, _code in n.sections:
        out += [f"== {head} ==", body.rstrip(), ""]
    if n.actions:
        out.append("== Bạn cần làm ==")
        out += [f"- {d}: {c}" for d, c in n.actions] + [""]
    if n.footer:
        out.append(n.footer)
    return "\n".join(out).rstrip() + "\n"


def render_html(n: Notice) -> str:
    e = html.escape
    rows = "".join(
        f'<tr><td style="padding:6px 12px 6px 0;color:#6b7280;white-space:nowrap;vertical-align:top">{e(k)}</td>'
        f'<td style="padding:6px 0;color:#111827;font-weight:500">{e(v)}</td></tr>'
        for k, v in n.fields)
    secs = ""
    for head, body, code in n.sections:
        content = (f'<pre style="margin:0;padding:12px;background:#f3f4f6;border:1px solid #e5e7eb;border-radius:8px;'
                   f'font:12.5px/1.5 Consolas,Menlo,monospace;white-space:pre-wrap;word-break:break-word;color:#111827">'
                   f'{e(body)}</pre>' if code else
                   f'<div style="font-size:14px;line-height:1.6;color:#374151;white-space:pre-wrap">{e(body)}</div>')
        secs += (f'<div style="margin-top:20px"><div style="font-size:11px;font-weight:700;letter-spacing:.06em;'
                 f'text-transform:uppercase;color:#6b7280;margin-bottom:6px">{e(head)}</div>{content}</div>')
    acts = ""
    if n.actions:
        items = "".join(
            f'<li style="margin:6px 0"><span style="color:#374151">{e(d)}:</span> '
            + (f'<a href="{e(c)}" style="color:#2563eb">{e(c)}</a>' if c.startswith("http") else
               f'<code style="background:#f3f4f6;border:1px solid #e5e7eb;border-radius:4px;padding:1px 6px;'
               f'font:12.5px Consolas,Menlo,monospace">{e(c)}</code>' if _is_cmd(c) else e(c))
            + "</li>" for d, c in n.actions)
        acts = (f'<div style="margin-top:22px;padding:14px 16px;background:#f9fafb;border:1px solid #e5e7eb;'
                f'border-radius:10px"><div style="font-weight:700;color:#111827;margin-bottom:4px">Bạn cần làm</div>'
                f'<ul style="margin:0;padding-left:18px;font-size:14px">{items}</ul></div>')
    button = (f'<a href="{e(n.link)}" style="display:inline-block;margin-top:20px;padding:10px 18px;'
              f'background:{n.color};color:#fff;text-decoration:none;border-radius:8px;font-weight:600">'
              f'Mở bảng điều khiển</a>' if n.link else "")
    return f"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#f3f4f6;padding:24px 12px;font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif">
<div style="max-width:640px;margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb">
<div style="height:6px;background:{n.color}"></div>
<div style="padding:24px 28px">
<div style="display:inline-block;font-size:11px;font-weight:700;letter-spacing:.08em;color:{n.color};border:1px solid {n.color};border-radius:999px;padding:3px 10px">{e(n.label)}</div>
<h1 style="margin:12px 0 6px;font-size:20px;line-height:1.35;color:#111827">{e(n.title)}</h1>
{f'<p style="margin:0 0 16px;font-size:14px;line-height:1.6;color:#374151">{e(n.lead)}</p>' if n.lead else ''}
{f'<table style="border-collapse:collapse;font-size:14px;margin-top:8px">{rows}</table>' if rows else ''}
{secs}{acts}{button}
</div>
{f'<div style="padding:14px 28px;background:#f9fafb;border-top:1px solid #e5e7eb;font-size:12px;color:#6b7280">{e(n.footer)}</div>' if n.footer else ''}
</div></body></html>"""


def _slack_esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_slack(n: Notice) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": _cut(f"{n.label}: {n.title}", 150)}},
    ]
    if n.lead:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": _cut(_slack_esc(n.lead), 3000)}})
    for i in range(0, len(n.fields), 10):
        blocks.append({"type": "section", "fields": [
            {"type": "mrkdwn", "text": _cut(f"*{_slack_esc(k)}*\n{_slack_esc(v)}", 2000)}
            for k, v in n.fields[i:i + 10]]})
    for head, body, code in n.sections:
        txt = f"```{_cut(_slack_esc(body), 2800)}```" if code else _cut(_slack_esc(body), 2900)
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*{_slack_esc(head)}*\n{txt}"}})
    if n.actions:
        lines = "\n".join(
            f"• {_slack_esc(d)}: " + (f"<{c}|{_slack_esc(c)}>" if c.startswith("http") else
                                     f"`{_slack_esc(c)}`" if _is_cmd(c) else _slack_esc(c))
            for d, c in n.actions)
        blocks += [{"type": "divider"},
                   {"type": "section", "text": {"type": "mrkdwn", "text": _cut(f"*Bạn cần làm*\n{lines}", 3000)}}]
    if n.footer:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": _cut(_slack_esc(n.footer), 2000)}]})
    return {"text": _cut(f"{n.label}: {n.title}", 300), "blocks": blocks[:50]}


def render_discord(n: Notice) -> dict[str, Any]:
    fields: list[dict[str, Any]] = [
        {"name": _cut(k, 256), "value": _cut(v or "—", 1024), "inline": len(v or "") <= 40}
        for k, v in n.fields]
    for head, body, code in n.sections:
        val = f"```\n{_cut(body, 1000)}\n```" if code else _cut(body, 1024)
        fields.append({"name": _cut(head, 256), "value": val, "inline": False})
    if n.actions:
        val = "\n".join(f"• {d}: " + (f"`{c}`" if _is_cmd(c) else c) for d, c in n.actions)
        fields.append({"name": "Bạn cần làm", "value": _cut(val, 1024), "inline": False})
    embed: dict[str, Any] = {
        "title": _cut(f"{n.label}: {n.title}", 256),
        "description": _cut(n.lead, 4000),
        "color": int(n.color.lstrip("#"), 16),
        "fields": fields[:25],
    }
    if n.link.startswith("https://"):
        embed["url"] = n.link
    if n.footer:
        embed["footer"] = {"text": _cut(n.footer, 2048)}
    # Discord gioi han tong 6000 ky tu moi embed: cat bot field neu vuot.
    while len(json.dumps(embed, ensure_ascii=False)) > 5800 and embed["fields"]:
        embed["fields"].pop()
    return {"username": "AI Factory", "content": _cut(f"**{n.label}**: {n.title}", 300), "embeds": [embed]}


def render_telegram(n: Notice) -> str:
    e = html.escape
    out = [f"<b>{e(n.label)}</b>", f"<b>{e(n.title)}</b>"]
    if n.lead:
        out += ["", e(n.lead)]
    if n.fields:
        out += [""] + [f"<b>{e(k)}:</b> {e(v)}" for k, v in n.fields]
    for head, body, code in n.sections:
        out += ["", f"<b>{e(head)}</b>", f"<pre>{e(_cut(body, 900))}</pre>" if code else e(_cut(body, 900))]
    if n.actions:
        out += ["", "<b>Bạn cần làm</b>"] + [
            f"• {e(d)}: " + (f"<code>{e(c)}</code>" if _is_cmd(c) else e(c)) for d, c in n.actions]
    if n.footer:
        out += ["", f"<i>{e(n.footer)}</i>"]
    text = "\n".join(out)
    if len(text) > 4000:
        # cat phan giua, giu tieu de va huong dan o cuoi
        text = "\n".join(out[:2] + ([e(n.lead)] if n.lead else []) +
                         ["", "<i>(Nội dung dài, xem đầy đủ trên email hoặc bảng điều khiển)</i>"] +
                         (["", "<b>Bạn cần làm</b>"] + [f"• {e(d)}: " + (f"<code>{e(c)}</code>" if _is_cmd(c) else e(c))
                                                        for d, c in n.actions]
                          if n.actions else []))
    return text


# ---------------------------------------------------------------- kenh gui


def _send_email(subject: str, body: str, html_body: str | None = None) -> bool:
    user = os.environ.get("FLOW_SMTP_USER")
    pwd = os.environ.get("FLOW_SMTP_PASS")
    to = os.environ.get("FLOW_NOTIFY_TO") or user
    if not (user and pwd and to):
        return False

    host = os.environ.get("FLOW_SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("FLOW_SMTP_PORT", "587"))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"AI Factory <{user}>"
    msg["To"] = ", ".join(a.strip() for a in to.split(",") if a.strip())
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    try:
        ctx = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=20) as s:
                s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.starttls(context=ctx)
                s.login(user, pwd)
                s.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[notify] gui mail that bai: {e}", file=sys.stderr)
        return False


def _post_json(url: str, payload: dict) -> bool:
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8",
                     "User-Agent": "ai-factory-notify/2.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
            return 200 <= r.status < 300
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        print(f"[notify] webhook that bai: HTTP {e.code} {detail}", file=sys.stderr)
        return False
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"[notify] webhook that bai: {e}", file=sys.stderr)
        return False


def _webhook_kind(url: str) -> str:
    forced = (os.environ.get("FLOW_WEBHOOK_KIND") or "").strip().lower()
    if forced in ("slack", "discord", "generic"):
        return forced
    u = url.lower()
    if "hooks.slack.com" in u:
        return "slack"
    if "discord.com/api/webhooks" in u or "discordapp.com/api/webhooks" in u:
        return "discord"
    return "generic"


def _webhook_urls() -> list[str]:
    raw = os.environ.get("FLOW_WEBHOOK_URL") or ""
    return [u.strip() for u in re.split(r"[,\s]+", raw) if u.strip()]


def _send_webhook(n: Notice) -> bool:
    urls = _webhook_urls()
    if not urls:
        return False
    ok = False
    for url in urls:
        kind = _webhook_kind(url)
        if kind == "slack":
            payload = render_slack(n)
        elif kind == "discord":
            payload = render_discord(n)
        else:
            text = render_text(n)
            payload = {"text": text, "content": _cut(text, 2000), "notice": {
                "kind": n.kind, "title": n.title, "lead": n.lead, "fields": dict(n.fields),
                "sections": [{"title": h, "body": b} for h, b, _ in n.sections],
                "actions": [{"label": d, "value": c} for d, c in n.actions], "link": n.link}}
        ok = _post_json(url, payload) or ok
    return ok


def _send_telegram(n: Notice) -> bool:
    token = os.environ.get("FLOW_TELEGRAM_TOKEN")
    chat = os.environ.get("FLOW_TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    return _post_json(
        f"https://api.telegram.org/bot{token}/sendMessage",
        {"chat_id": chat, "text": render_telegram(n), "parse_mode": "HTML",
         "disable_web_page_preview": True},
    )


def send_notice(n: Notice, *, channels: list[str] | None = None) -> bool:
    """Gui mot thong bao co cau truc qua moi kenh da cau hinh."""
    try:
        channels = channels or ["email", "webhook", "telegram"]
        results = []
        if "email" in channels:
            results.append(_send_email(n.subject, render_text(n), render_html(n)))
        if "webhook" in channels:
            results.append(_send_webhook(n))
        if "telegram" in channels:
            results.append(_send_telegram(n))
        ok = any(results)
        if not ok:
            print(f"[notify] khong kenh nao gui duoc. Bo qua: {n.subject}", file=sys.stderr)
        return ok
    except Exception as e:  # noqa: BLE001
        print(f"[notify] loi khi gui: {e}", file=sys.stderr)
        return False


def send(subject: str, body: str, *, channels: list[str] | None = None) -> bool:
    """Giu tuong thich: gui thong bao dang chu thuan."""
    return send_notice(Notice(kind="info", title=subject.replace("[AI Factory] ", ""), lead=body),
                       channels=channels)


# --------------------------------------------------------------------------
# Dung noi dung tu trang thai .flow - cang day du cang tot cho nguoi duyet
# --------------------------------------------------------------------------

TIER_VI = {0: "tự chạy", 1: "tự chạy, báo cáo sau", 2: "bắt buộc bạn duyệt trước"}

STATUS_VI = {"done": "Hoàn thành", "running": "Đang chạy", "awaiting_approval": "Chờ duyệt",
             "gate_failed": "Trượt kiểm thử", "review_failed": "Bị trả lại", "pending": "Đang chờ",
             "blocked": "Bị chặn", "skipped": "Đã bỏ qua"}


def _fc():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import flow_core as fc  # noqa: PLC0415
    return fc


def _git(*args: str) -> str:
    try:
        fc = _fc()
        r = subprocess.run(["git", *args], cwd=fc.ROOT, capture_output=True, text=True,
                           timeout=5, check=False)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def _context(task_id: str | None = None) -> dict[str, Any]:
    """Gom ngu canh: du an, nhanh, run, y tuong, task, tien do. Khong bao gio nem loi."""
    ctx: dict[str, Any] = {"project": "", "branch": "", "run_id": None, "idea": "", "task": None,
                           "tasks": [], "cfg": {}, "dashboard": "", "pending": 0}
    try:
        fc = _fc()
        ctx["project"] = fc.ROOT.name
        ctx["branch"] = _git("rev-parse", "--abbrev-ref", "HEAD")
        ctx["dashboard"] = os.environ.get("FLOW_DASHBOARD_URL") or "http://127.0.0.1:7788"
        # Du an chua init thi dung lai o day: goi tiep se tu tao .flow/.
        if not fc.is_initialised():
            return ctx
        ctx["cfg"] = cfg = fc.load_config()
        port = cfg.get("dashboard", {}).get("port", 7788)
        ctx["dashboard"] = os.environ.get("FLOW_DASHBOARD_URL") or f"http://127.0.0.1:{port}"
        ctx["pending"] = len(fc.pending_approvals())
        cur = fc.get_current()
        ctx["run_id"] = cur.get("run_id")
        if ctx["run_id"]:
            d = fc.run_dir()
            idea = d / "00-idea.md"
            if idea.exists():
                lines = [ln.strip() for ln in idea.read_text(encoding="utf-8").splitlines()]
                body = [ln for ln in lines if ln and not ln.startswith("#")
                        and not (ln.startswith("_") and ln.endswith("_"))]
                ctx["idea"] = _cut("\n".join(body), 600)
            data = fc.load_tasks()
            ctx["tasks"] = data.get("tasks", [])
            if task_id:
                ctx["task"] = fc.find_task(data, task_id)
    except (Exception, SystemExit):  # noqa: BLE001 - run_dir nem SystemExit khi chua co run
        pass
    return ctx


def _progress(tasks: list[dict]) -> str:
    if not tasks:
        return "—"
    done = sum(1 for t in tasks if t.get("status") == "done")
    return f"{done}/{len(tasks)} task xong ({round(done * 100 / len(tasks))}%)"


def _base_fields(ctx: dict, task_id: str | None) -> list[tuple[str, str]]:
    f: list[tuple[str, str]] = []
    if ctx["project"]:
        f.append(("Dự án", ctx["project"]))
    if ctx["branch"]:
        f.append(("Nhánh git", ctx["branch"]))
    f.append(("Run", ctx["run_id"] or "không có (lệnh ngoài quy trình)"))
    t = ctx["task"]
    if task_id:
        f.append(("Task", f"{task_id} · {t['title']}" if t else task_id))
    if ctx["tasks"]:
        f.append(("Tiến độ run", _progress(ctx["tasks"])))
    return f


def _now_local() -> str:
    try:
        return _fc().now().replace("T", " ")[:19]
    except Exception:  # noqa: BLE001
        return ""


def _task_sections(t: dict | None) -> list[tuple[str, str, bool]]:
    if not t:
        return []
    s: list[tuple[str, str, bool]] = []
    if t.get("description"):
        s.append(("Mô tả task", _cut(t["description"], 1500), False))
    if t.get("files"):
        s.append(("File trong phạm vi task", "\n".join(t["files"][:30]), True))
    if t.get("acceptance"):
        s.append(("Tiêu chí nghiệm thu", "\n".join(f"- {a}" for a in t["acceptance"][:15]), False))
    if t.get("depends_on"):
        s.append(("Phụ thuộc", ", ".join(t["depends_on"]), False))
    return s


def approval_notice(task_id: str, what: str, reason: str, tier: int = 2, *,
                    tool: str | None = None, command: str | None = None,
                    paths: list[str] | None = None, question: bool = False,
                    options: list[str] | None = None) -> Notice:
    ctx = _context(task_id)
    cfg, t = ctx["cfg"], ctx["task"]
    tier_lbl = TIER_VI.get(tier, "")
    auto = cfg.get("auto_mode") or {}

    fields = _base_fields(ctx, task_id)
    fields += [
        ("Mức rủi ro", f"Tier {tier}" + (f" · {tier_lbl}" if tier_lbl else "")),
        ("Nguồn", "Agent chủ động hỏi" if question else
         (f"Hàng rào tier chặn công cụ {tool}" if tool else "Task cần duyệt trước khi chạy")),
        ("Yêu cầu lúc", _now_local()),
        ("Chế độ tự động", f"bật đến Tier {auto.get('max_tier')}" if auto.get("enabled") else "tắt"),
        ("Phiếu đang chờ", f"{max(ctx['pending'], 1)} phiếu"),
    ]

    sections: list[tuple[str, str, bool]] = []
    if question:
        sections.append(("Câu hỏi của agent", redact(what), False))
        if options:
            sections.append(("Các phương án", "\n".join(f"{i}. {o}" for i, o in enumerate(options, 1)), False))
    elif command:
        sections.append(("Lệnh bị chặn", redact(command), True))
    elif paths:
        sections.append(("File sắp bị ghi", "\n".join(paths), True))
    else:
        sections.append(("Việc cần duyệt", redact(what), False))
    sections.append(("Vì sao cần bạn duyệt", reason or "(không ghi lý do)", False))
    sections += _task_sections(t)
    if ctx["idea"]:
        sections.append(("Ý tưởng gốc của run", ctx["idea"], False))

    mode = cfg.get("approve_mode", "queue")
    after = {"queue": "Sau khi bấm duyệt, quay lại khung chat Claude và gõ \"tiếp\"",
             "direct": "Agent đang chờ sẽ tự thấy quyết định sau vài giây",
             "spawn": "Máy chủ sẽ tự mở phiên Claude mới để làm tiếp"}.get(mode, "")
    actions = [("Mở bảng điều khiển", ctx["dashboard"] or "http://127.0.0.1:7788"),
               ("Duyệt bằng lệnh", f".flow/flow approve {task_id}"),
               ("Từ chối bằng lệnh", f".flow/flow reject {task_id} --note \"lý do\"")]
    if after:
        actions.append(("Sau đó", after))

    title = t["title"] if t and not question and not command and not paths else what
    return Notice(
        kind="approval",
        title=_cut(f"{task_id} · {redact(title)}", 150),
        lead=("Agent đang dừng lại chờ ý kiến của bạn. Không có gì chạy tiếp cho tới khi bạn quyết định."
              if question else
              f"Agent đã dừng trước một hành động rủi ro Tier {tier}. Không có gì chạy tiếp cho tới khi bạn "
              f"duyệt hoặc từ chối."),
        fields=fields, sections=sections, actions=actions, link=ctx["dashboard"],
        footer="Duyệt chỉ có hiệu lực cho đúng hành động này. Hành động khác sẽ phải xin duyệt lại. "
               "Chuỗi giống mật khẩu/token trong lệnh đã được che.",
    )


def fail_notice(t: dict, result: dict, *, stage: str = "gate") -> Notice:
    task_id = t.get("id", "?")
    ctx = _context(task_id)
    t = ctx["task"] or t
    max_att = (ctx["cfg"].get("limits") or {}).get("max_fix_attempts", "?")
    fields = _base_fields(ctx, task_id)
    fields += [("Giai đoạn", "Cổng kiểm thử tự động" if stage == "gate" else "Review của verifier"),
               ("Lần thử", f"{t.get('attempts', 0)}/{max_att}"),
               ("Mức rủi ro", f"Tier {t.get('tier', '?')}"),
               ("Lúc", _now_local())]

    sections: list[tuple[str, str, bool]] = []
    if stage == "gate":
        checks = [f"✗ {x}" for x in result.get("failed") or []]
        checks += [f"✓ {x}" for x in result.get("passed") or []]
        checks += [f"– {x} (bỏ qua)" for x in result.get("skipped") or []]
        if checks:
            sections.append(("Kết quả từng bước kiểm tra", "\n".join(checks), True))
        logs = result.get("logs") or {}
        for name in (result.get("failed") or [])[:3]:
            if logs.get(name):
                sections.append((f"Log {name} (đoạn cuối)", redact(_tail(str(logs[name]), 1400)), True))
        if result.get("error"):
            sections.append(("Lỗi", redact(f"{result['error']}\n{result.get('stderr', '')}".strip()), True))
    else:
        sections.append(("Lý do trả lại", redact(result.get("reason", "(không rõ)")), False))
    sections += _task_sections(t)

    should_stop = isinstance(max_att, int) and t.get("attempts", 0) >= max_att
    lead = (f"Task {task_id} " + ("không qua cổng kiểm thử tự động." if stage == "gate"
                                   else "bị verifier trả lại.")
            + (" Đã hết số lần sửa cho phép — agent sẽ dừng và chờ bạn." if should_stop
               else " Agent sẽ tự sửa và thử lại."))
    return Notice(
        kind="fail", title=_cut(f"{task_id} · {t.get('title', task_id)}", 150), lead=lead,
        fields=fields, sections=sections,
        actions=[("Xem chi tiết", ctx["dashboard"] or "http://127.0.0.1:7788"),
                 ("Góp ý cho agent", f".flow/flow note {task_id} \"cách sửa bạn muốn\"")],
        link=ctx["dashboard"],
        footer="Bạn không cần làm gì nếu agent còn lượt sửa. Góp ý sẽ được agent đọc trước khi sửa lại.",
    )


def _task_table(tasks: list[dict], highlight: str | None = None) -> str:
    lines = []
    for t in tasks:
        mark = "→" if t.get("id") == highlight else " "
        st = STATUS_VI.get(t.get("status", ""), t.get("status", ""))
        commit = f"  [{t['commit']}]" if t.get("commit") else ""
        lines.append(f"{mark} {t.get('id', ''):<4} T{t.get('tier', '?')}  {st:<15} {_cut(t.get('title', ''), 60)}{commit}")
    return "\n".join(lines)


def pass_notice(data: dict, task_id: str, *, next_task: dict | None = None, auto_next: bool = False) -> Notice:
    ctx = _context(task_id)
    t = ctx["task"] or next((x for x in data.get("tasks", []) if x.get("id") == task_id), {}) or {}
    fields = _base_fields(ctx, task_id)
    if t.get("commit"):
        fields.append(("Commit", t["commit"]))
    fields.append(("Task kế tiếp", f"{next_task['id']} · {next_task['title']} (Tier {next_task['tier']})"
                   if next_task else "không còn"))
    if next_task:
        fields.append(("Chạy tiếp", "tự động" if auto_next else "chờ bạn xác nhận"))
    return Notice(
        kind="pass", title=_cut(f"{task_id} · {t.get('title', '')}", 150),
        lead="Task đã qua cổng kiểm thử và được verifier cho qua.",
        fields=fields, sections=[("Tình trạng các task", _task_table(data.get("tasks", []), task_id), True)],
        actions=[("Xem báo cáo", ctx["dashboard"] or "http://127.0.0.1:7788")], link=ctx["dashboard"],
    )


def run_done_notice(data: dict) -> Notice:
    ctx = _context()
    tasks = data.get("tasks", [])
    done = [t for t in tasks if t.get("status") == "done"]
    other = [t for t in tasks if t.get("status") != "done"]
    fields = _base_fields(ctx, None) + [("Hoàn thành", f"{len(done)} task"),
                                         ("Bỏ qua / chưa xong", f"{len(other)} task"),
                                         ("Commit", str(sum(1 for t in tasks if t.get("commit"))))]
    sections: list[tuple[str, str, bool]] = []
    if ctx["idea"]:
        sections.append(("Ý tưởng gốc", ctx["idea"], False))
    sections.append(("Kết quả từng task", _task_table(tasks), True))
    return Notice(
        kind="run_done", title=_cut(f"Run {data.get('run_id', '')} đã xong", 150),
        lead="Không còn task nào có thể chạy tiếp. Hãy xem lại báo cáo và các commit trước khi merge.",
        fields=fields, sections=sections,
        actions=[("Xem báo cáo", ctx["dashboard"] or "http://127.0.0.1:7788")], link=ctx["dashboard"],
    )


# ---------------------------------------------------------------- CLI


def _sample() -> Notice:
    return approval_notice(
        "T3", "git push --force origin main", "lệnh chứa 'git push'", 2, tool="Bash",
        command="GITHUB_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz1234 git push --force origin main")


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")

    if "--preview" in sys.argv:
        fmt = sys.argv[sys.argv.index("--preview") + 1] if len(sys.argv) > sys.argv.index("--preview") + 1 else "text"
        n = _sample()
        out = {"text": lambda: render_text(n), "html": lambda: render_html(n),
               "slack": lambda: json.dumps(render_slack(n), ensure_ascii=False, indent=2),
               "discord": lambda: json.dumps(render_discord(n), ensure_ascii=False, indent=2),
               "telegram": lambda: render_telegram(n)}.get(fmt, lambda: render_text(n))()
        print(out)
        sys.exit(0)

    if "--test" in sys.argv:
        ok = send_notice(Notice(
            kind="info", title="Thử kênh thông báo",
            lead="Nếu bạn đọc được tin này, kênh thông báo đã hoạt động. Bạn sẽ nhận tin như thế này "
                 "khi có việc cần duyệt, khi task thất bại và khi một run hoàn thành.",
            fields=[("Email", "bật" if os.environ.get("FLOW_SMTP_USER") else "chưa cấu hình"),
                    ("Webhook", ", ".join(_webhook_kind(u) for u in _webhook_urls()) or "chưa cấu hình"),
                    ("Telegram", "bật" if os.environ.get("FLOW_TELEGRAM_TOKEN") else "chưa cấu hình")],
        ))
        print("Thanh cong" if ok else "That bai. Kiem tra lai bien moi truong trong .env.flow")
        sys.exit(0 if ok else 1)
    send(sys.argv[1] if len(sys.argv) > 1 else "AI Factory",
         sys.argv[2] if len(sys.argv) > 2 else "")
