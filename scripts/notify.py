#!/usr/bin/env python3
"""Gui thong bao ra ngoai. Nguyen tac: khong bao gio nem loi ra workflow.

Cau hinh bang bien moi truong (dat trong .env.flow hoac shell):

    FLOW_SMTP_USER=ban@gmail.com
    FLOW_SMTP_PASS=<app password 16 ky tu, KHONG phai mat khau Gmail>
    FLOW_NOTIFY_TO=ban@gmail.com
    FLOW_SMTP_HOST=smtp.gmail.com      (mac dinh)
    FLOW_SMTP_PORT=587                 (mac dinh)

Tuy chon them, gui song song:
    FLOW_WEBHOOK_URL=https://hooks.slack.com/...   hoac Discord, hoac bat ky
    FLOW_TELEGRAM_TOKEN=123:ABC
    FLOW_TELEGRAM_CHAT_ID=456

Lay app password Gmail: myaccount.google.com > Security > 2-Step Verification
> App passwords. Bat buoc phai bat xac thuc 2 buoc truoc.

Chay thu:  python scripts/notify.py --test
"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
import sys
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path


def _load_env_file() -> None:
    """Doc .env.flow o goc project neu co, khong ghi de bien da ton tai."""
    for base in (Path.cwd(), Path(__file__).resolve().parent.parent):
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


def _send_email(subject: str, body: str) -> bool:
    user = os.environ.get("FLOW_SMTP_USER")
    pwd = os.environ.get("FLOW_SMTP_PASS")
    to = os.environ.get("FLOW_NOTIFY_TO") or user
    if not (user and pwd and to):
        return False

    host = os.environ.get("FLOW_SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("FLOW_SMTP_PORT", "587"))

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content(body)

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
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310
            return 200 <= r.status < 300
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"[notify] webhook that bai: {e}", file=sys.stderr)
        return False


def _send_webhook(subject: str, body: str) -> bool:
    url = os.environ.get("FLOW_WEBHOOK_URL")
    if not url:
        return False
    text = f"*{subject}*\n```\n{body[:3000]}\n```"
    return _post_json(url, {"text": text, "content": text})  # text: Slack, content: Discord


def _send_telegram(subject: str, body: str) -> bool:
    token = os.environ.get("FLOW_TELEGRAM_TOKEN")
    chat = os.environ.get("FLOW_TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    return _post_json(
        f"https://api.telegram.org/bot{token}/sendMessage",
        {"chat_id": chat, "text": f"{subject}\n\n{body[:3500]}"},
    )


def send(subject: str, body: str, *, channels: list[str] | None = None) -> bool:
    """Gui qua moi kenh da cau hinh. Tra ve True neu it nhat mot kenh thanh cong."""
    channels = channels or ["email", "webhook", "telegram"]
    results = []
    if "email" in channels:
        results.append(_send_email(subject, body))
    if "webhook" in channels:
        results.append(_send_webhook(subject, body))
    if "telegram" in channels:
        results.append(_send_telegram(subject, body))

    ok = any(results)
    if not ok:
        print(f"[notify] khong kenh nao duoc cau hinh. Bo qua: {subject}", file=sys.stderr)
    return ok


if __name__ == "__main__":
    if "--test" in sys.argv:
        ok = send(
            "[AI Factory] Thu thong bao",
            "Neu ban doc duoc dong nay, kenh thong bao da chay.\n"
            "Ban se nhan mail kieu nay khi task truot hoac khi co viec can ban duyet.",
        )
        print("Thanh cong" if ok else "That bai. Kiem tra lai bien moi truong trong .env.flow")
        sys.exit(0 if ok else 1)
    send(sys.argv[1] if len(sys.argv) > 1 else "AI Factory",
         sys.argv[2] if len(sys.argv) > 2 else "")
