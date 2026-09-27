#!/usr/bin/env python3
"""Bot Telegram cho AI Factory: xem tinh hinh va duyet tu xa.

    .flow/flow telegram          (hoac: python scripts/telegram_bot.py)

Bot chay tren may cua ban va tu hoi Telegram (long polling), nen KHONG mo
cong nao ra ngoai. Dung chung FLOW_TELEGRAM_TOKEN / FLOW_TELEGRAM_CHAT_ID
voi phan thong bao.

Lenh:
  /status        tong quan run
  /pending       viec dang cho duyet, kem nut Duyet / Tu choi
  /tasks         danh sach task
  /task T1       chi tiet mot task (review, ghi chu, kiem thu)
  /log [n]       n su kien gan nhat
  /id            cho biet chat id / user id (de cau hinh)

Bao ve:
  - Chi chat trong FLOW_TELEGRAM_CHAT_ID moi doc duoc.
  - Duyet chi tu chat rieng voi dung chu chat, hoac user id trong
    FLOW_TELEGRAM_APPROVERS (khi dung trong nhom).
  - Moi quyet dinh phai bam xac nhan lan hai.
  - Nut gan voi dau van tay cua DUNG phieu: nut cu khong duyet duoc phieu moi.
  - FLOW_TELEGRAM_READONLY=1 de tat hoan toan viec duyet tu xa.
"""

from __future__ import annotations

import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import flow_core as fc  # noqa: E402
import notify as nt  # noqa: E402

E = html.escape

EV = {"run_started": "Bắt đầu run", "run_resumed": "Mở lại run", "plan_imported": "Nạp kế hoạch",
      "task_started": "Bắt đầu task", "task_done": "Hoàn thành task", "task_failed": "Task thất bại",
      "gate_passed": "Qua kiểm thử", "gate_failed": "Trượt kiểm thử", "committed": "Đã commit",
      "feedback": "Nhận xét", "handoff": "Bàn giao phiên", "profile": "Đổi cấu hình",
      "auto_mode": "Chế độ tự động", "approval_requested": "Yêu cầu duyệt",
      "approval_decided": "Đã có quyết định", "tier2_auto_allowed": "Tự cho qua Tier 2",
      "tier2_approved_ok": "Tier 2 đã được duyệt", "agent_start": "Agent bắt đầu",
      "agent_stop": "Agent kết thúc", "turn_end": "Kết thúc lượt", "spawn": "Mở phiên mới",
      "spawn_done": "Phiên mới kết thúc", "spawn_failed": "Mở phiên lỗi"}
MODE_VI = {"queue": "hàng đợi", "direct": "agent thấy ngay", "spawn": "tự mở phiên mới"}
HELP = ("<b>AI Factory</b> — các lệnh:\n"
        "/status — tổng quan run\n"
        "/pending — việc đang chờ bạn duyệt\n"
        "/tasks — danh sách task\n"
        "/task T1 — chi tiết một task\n"
        "/log 20 — các sự kiện gần nhất\n"
        "/id — xem chat id của bạn")


def _ids(env: str) -> set[str]:
    return {x.strip() for x in (os.environ.get(env) or "").replace(";", ",").split(",") if x.strip()}


def _ago(iso: str) -> str:
    try:
        s = (datetime.now().astimezone() - datetime.fromisoformat(iso)).total_seconds()
    except (ValueError, TypeError):
        return ""
    if s < 60:
        return "vừa xong"
    if s < 3600:
        return f"{int(s // 60)} phút trước"
    if s < 86400:
        return f"{int(s // 3600)} giờ trước"
    return f"{int(s // 86400)} ngày trước"


def _bar(done: int, total: int, width: int = 10) -> str:
    if not total:
        return ""
    k = round(width * done / total)
    return "▓" * k + "░" * (width - k)


class Bot:
    def __init__(self, token: str, chats: set[str], approvers: set[str], readonly: bool) -> None:
        api = (os.environ.get("FLOW_TELEGRAM_API") or "https://api.telegram.org").rstrip("/")
        self.base = f"{api}/bot{token}/"
        self.chats, self.approvers, self.readonly = chats, approvers, readonly
        self.offset: int | None = None

    # ------------------------------------------------------------ Telegram API

    def api(self, method: str, payload: dict[str, Any], timeout: int = 20) -> Any:
        req = urllib.request.Request(
            self.base + method, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                desc = json.loads(e.read().decode("utf-8")).get("description", "")
            except Exception:  # noqa: BLE001
                desc = ""
            if e.code == 409:
                print("[telegram] Xung dot: dang co mot bot khac (hoac webhook) dung chung token nay. "
                      "Chi chay MOT tien trinh bot cho moi token.", file=sys.stderr)
            elif method != "answerCallbackQuery":
                print(f"[telegram] {method} loi HTTP {e.code}: {desc}", file=sys.stderr)
            return None
        except (urllib.error.URLError, OSError, ValueError) as e:
            print(f"[telegram] {method} loi mang: {e}", file=sys.stderr)
            return None
        return data.get("result") if data.get("ok") else None

    def send(self, chat_id: Any, text: str, buttons: list | None = None, reply_to: int | None = None) -> None:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text[:4000], "parse_mode": "HTML",
                                   "disable_web_page_preview": True}
        if buttons:
            payload["reply_markup"] = self._kb(buttons)
        if reply_to:
            payload["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        self.api("sendMessage", payload)

    @staticmethod
    def _kb(buttons: list) -> dict[str, Any]:
        return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]}

    # ------------------------------------------------------------ trang thai

    def _save_state(self) -> None:
        try:
            fc.FLOW.mkdir(parents=True, exist_ok=True)
            fc._atomic_write(fc.TELEGRAM_STATE, json.dumps(
                {"offset": self.offset, "alive_at": time.time(), "pid": os.getpid()}, indent=2))
        except OSError as e:
            print(f"[telegram] khong ghi duoc trang thai: {e}", file=sys.stderr)

    def _load_offset(self) -> None:
        try:
            self.offset = json.loads(fc.TELEGRAM_STATE.read_text(encoding="utf-8")).get("offset")
        except (OSError, ValueError):
            self.offset = None
        if self.offset is None:
            # Lan dau: bo qua tin cu, chi xu ly tu bay gio.
            res = self.api("getUpdates", {"offset": -1, "timeout": 0})
            self.offset = (res[-1]["update_id"] + 1) if res else None

    # ------------------------------------------------------------ quyen

    def can_read(self, chat_id: Any) -> bool:
        return str(chat_id) in self.chats

    def can_decide(self, chat: dict, user_id: Any) -> bool:
        if self.readonly or not self.can_read(chat.get("id")):
            return False
        if self.approvers:
            return str(user_id) in self.approvers
        return chat.get("type") == "private" and str(user_id) == str(chat.get("id"))

    # ------------------------------------------------------------ vong lap

    def run(self) -> None:
        me = self.api("getMe", {})
        if not me:
            print("Khong ket noi duoc Telegram. Kiem tra FLOW_TELEGRAM_TOKEN va mang.", file=sys.stderr)
            sys.exit(1)
        self._load_offset()
        self._save_state()
        print(f"Bot @{me.get('username')} dang chay cho du an {fc.ROOT.name}. "
              f"Chat duoc phep: {', '.join(sorted(self.chats))}. "
              f"Duyet tu xa: {'TAT' if self.readonly else 'BAT'}. Ctrl+C de dung.")
        backoff = 2
        while True:
            payload: dict[str, Any] = {"timeout": 50, "allowed_updates": ["message", "callback_query"]}
            if self.offset is not None:
                payload["offset"] = self.offset
            updates = self.api("getUpdates", payload, timeout=65)
            self._save_state()
            if updates is None:
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)
                continue
            backoff = 2
            for u in updates:
                self.offset = u["update_id"] + 1
                self._save_state()
                try:
                    if "callback_query" in u:
                        self.on_callback(u["callback_query"])
                    elif "message" in u:
                        self.on_message(u["message"])
                except Exception as e:  # noqa: BLE001 - mot tin loi khong duoc giet bot
                    print(f"[telegram] loi xu ly update {u.get('update_id')}: {e!r}", file=sys.stderr)

    # ------------------------------------------------------------ tin nhan

    def on_message(self, m: dict) -> None:
        chat, text = m.get("chat") or {}, (m.get("text") or "").strip()
        if not text.startswith("/"):
            if self.can_read(chat.get("id")):
                self.send(chat["id"], HELP)
            return
        cmd, _, arg = text.partition(" ")
        cmd = cmd.split("@", 1)[0].lower()
        arg = arg.strip()

        if cmd == "/id":
            self.send(chat.get("id"), f"Chat id: <code>{E(str(chat.get('id')))}</code>\n"
                                      f"User id: <code>{E(str((m.get('from') or {}).get('id')))}</code>")
            return
        if not self.can_read(chat.get("id")):
            print(f"[telegram] bo qua tin tu chat la {chat.get('id')}", file=sys.stderr)
            return

        handlers = {"/start": lambda: HELP, "/help": lambda: HELP, "/status": self.status,
                    "/tasks": self.tasks, "/task": lambda: self.task(arg), "/log": lambda: self.log(arg)}
        if cmd == "/pending":
            self.pending(chat, (m.get("from") or {}).get("id"))
            return
        fn = handlers.get(cmd)
        self.send(chat["id"], fn() if fn else f"Không hiểu lệnh {E(cmd)}.\n\n{HELP}")

    # ------------------------------------------------------------ noi dung

    def _run_state(self) -> tuple[dict, list[dict]]:
        ctx = nt._context()
        return ctx, ctx.get("tasks") or []

    def status(self) -> str:
        if not fc.is_initialised():
            return "Dự án chưa chạy <code>init</code>."
        ctx, tasks = self._run_state()
        cfg = ctx.get("cfg") or {}
        auto = cfg.get("auto_mode") or {}
        pend = fc.pending_approvals()
        out = [f"<b>AI Factory · {E(ctx['project'])}</b>"]
        if ctx.get("branch"):
            out.append(f"Nhánh: <code>{E(ctx['branch'])}</code>")
        if not ctx.get("run_id"):
            out.append("Run: chưa có run nào đang chạy")
        else:
            done = sum(1 for t in tasks if t.get("status") == "done")
            fail = sum(1 for t in tasks if t.get("status") in ("gate_failed", "review_failed"))
            out.append(f"Run: <code>{E(ctx['run_id'])}</code>")
            if ctx.get("idea"):
                out.append(f"Ý tưởng: {E(nt._cut(ctx['idea'], 200))}")
            out.append(f"Tiến độ: {_bar(done, len(tasks))} {done}/{len(tasks)} task"
                       + (f" · <b>{fail} thất bại</b>" if fail else ""))
            running = [t for t in tasks if t.get("status") == "running"]
            if running:
                out.append("Đang chạy: " + ", ".join(f"<code>{E(t['id'])}</code> {E(t['title'])}" for t in running))
            try:
                ev = fc.read_events(limit=1)
            except SystemExit:
                ev = []
            if ev:
                e = ev[-1]
                out.append(f"Hoạt động gần nhất: {E(EV.get(e.get('kind'), e.get('kind', '')))} "
                           f"({_ago(e.get('at', ''))})")
        out.append(f"Chờ duyệt: <b>{len(pend)}</b> phiếu" + (" → /pending" if pend else ""))
        out.append(f"Tự động: {'bật đến Tier ' + str(auto.get('max_tier')) if auto.get('enabled') else 'tắt'}"
                   f" · Duyệt: {MODE_VI.get(cfg.get('approve_mode', 'queue'), '')}")
        return "\n".join(out)

    def tasks(self) -> str:
        ctx, tasks = self._run_state()
        if not tasks:
            return "Chưa có task nào."
        lines = [f"<b>Task của run {E(ctx.get('run_id') or '')}</b>"]
        for t in tasks[:60]:
            st = nt.STATUS_VI.get(t.get("status", ""), t.get("status", ""))
            lines.append(f"<code>{E(t['id'])}</code> T{t.get('tier', '?')} · <b>{E(st)}</b> · {E(nt._cut(t.get('title', ''), 70))}")
        lines.append("\nXem chi tiết: /task &lt;id&gt;")
        return "\n".join(lines)

    def task(self, tid: str) -> str:
        if not tid:
            return "Cú pháp: /task T1"
        try:
            data = fc.load_tasks()
        except SystemExit:
            return "Chưa có run nào."
        t = fc.find_task(data, tid) or fc.find_task(data, tid.upper())
        if not t:
            return f"Không có task {E(tid)}. Xem /tasks"
        tid = t["id"]
        st = nt.STATUS_VI.get(t.get("status", ""), t.get("status", ""))
        out = [f"<b>{E(tid)} · {E(t.get('title', ''))}</b>",
               f"Trạng thái: <b>{E(st)}</b> · Tier {t.get('tier', '?')} · lần thử {t.get('attempts', 0)}"]
        if t.get("tier_reason"):
            out.append(f"Lý do tier: {E(t['tier_reason'])}")
        if t.get("commit"):
            out.append(f"Commit: <code>{E(t['commit'])}</code>")
        if t.get("description"):
            out += ["", "<b>Mô tả</b>", E(nt._cut(t["description"], 600))]
        if t.get("files"):
            out += ["", "<b>File</b>", "<pre>" + E("\n".join(t["files"][:20])) + "</pre>"]
        if t.get("acceptance"):
            out += ["", "<b>Tiêu chí nghiệm thu</b>"] + [f"- {E(a)}" for a in t["acceptance"][:10]]
        g = t.get("gate") or {}
        if g:
            chips = ([f"✓ {x}" for x in g.get("passed") or []] + [f"✗ {x}" for x in g.get("failed") or []]
                     + [f"– {x}" for x in g.get("skipped") or []])
            out += ["", "<b>Kiểm thử</b>", E("  ".join(chips) or "chưa chạy")]
        if t.get("last_error"):
            out += ["", "<b>Lỗi gần nhất</b>", E(nt._cut(nt.redact(t["last_error"]), 400))]
        d = fc.run_dir() / "tasks" / tid
        rv = _read(d / "review.md")
        if rv:
            low = rv.lower()
            i = max(low.rfind("## ket luan"), low.rfind("## kết luận"))
            out += ["", "<b>Verifier</b>", E(nt._cut((rv[i:] if i >= 0 else rv).strip(), 700))]
        nts = _read(d / "notes.md")
        if nts:
            out += ["", "<b>Ghi chú của coder</b>", E(nt._cut(nts.strip(), 600))]
        fb = _read(d / "feedback.md")
        if fb:
            out += ["", "<b>Nhận xét của bạn</b>", E(nt._tail(fb.strip(), 400))]
        return "\n".join(out)

    def log(self, arg: str) -> str:
        n = int(arg) if arg.isdigit() else 15
        n = max(1, min(n, 40))
        try:
            ev = fc.read_events(limit=n)
        except SystemExit:
            return "Chưa có run nào."
        if not ev:
            return "Chưa có hoạt động nào."
        lines = [f"<b>{len(ev)} sự kiện gần nhất</b>"]
        for e in reversed(ev):
            who = e.get("agent") or ""
            lines.append(f"<code>{E((e.get('at') or '')[11:16])}</code> <b>{E(EV.get(e.get('kind'), e.get('kind', '')))}</b>"
                         + (f" [{E(who)}]" if who else "")
                         + (f" <code>{E(e['task_id'])}</code>" if e.get("task_id") else "")
                         + (f" — {E(nt._cut(nt.redact(e.get('message') or ''), 110))}" if e.get("message") else ""))
        return "\n".join(lines)

    def pending(self, chat: dict, user_id: Any) -> None:
        pend = fc.pending_approvals()
        if not pend:
            self.send(chat["id"], "Không có việc nào đang chờ bạn duyệt.")
            return
        allow = self.can_decide(chat, user_id)
        for a in pend[:10]:
            det = a.get("details") or {}
            n = nt.approval_notice(a.get("task_id", ""), a.get("what", ""), a.get("reason", ""),
                                   int(a.get("tier", 2)), tool=det.get("tool"), command=det.get("command"),
                                   paths=det.get("paths") or None, question="options" in det,
                                   options=det.get("options") or None,
                                   requested_at=a.get("requested_at"))
            self.send(chat["id"], nt.render_telegram(n), buttons=nt.approval_buttons(a) if allow else None)
        if len(pend) > 10:
            self.send(chat["id"], f"Còn {len(pend) - 10} phiếu khác, xem trên bảng điều khiển.")

    # ------------------------------------------------------------ nut bam

    def on_callback(self, q: dict) -> None:
        msg = q.get("message") or {}
        chat, user = msg.get("chat") or {}, q.get("from") or {}
        data = q.get("data") or ""
        answer = lambda text, alert=False: self.api(  # noqa: E731
            "answerCallbackQuery", {"callback_query_id": q["id"], "text": text, "show_alert": alert})
        set_kb = lambda kb: self.api("editMessageReplyMarkup", {  # noqa: E731
            "chat_id": chat.get("id"), "message_id": msg.get("message_id"),
            "reply_markup": self._kb(kb) if kb else {"inline_keyboard": []}})

        if not self.can_decide(chat, user.get("id")):
            answer("Bạn không có quyền duyệt từ xa." if not self.readonly
                   else "Duyệt từ xa đang tắt (FLOW_TELEGRAM_READONLY).", True)
            print(f"[telegram] tu choi nut bam tu user {user.get('id')} chat {chat.get('id')}", file=sys.stderr)
            return

        try:
            action, key, tid = data.split(":", 2)
        except ValueError:
            answer("Nút không hợp lệ.")
            return
        a = fc.read_approval(tid)
        if not a or a.get("decision") or fc.approval_key(a) != key:
            answer("Phiếu này đã được xử lý hoặc đã thay đổi. Gõ /pending để xem phiếu hiện tại.", True)
            set_kb(None)
            return

        if action in ("a", "r"):
            set_kb(nt.approval_buttons(a, confirm=action))
            answer("Bấm lần nữa để xác nhận.")
        elif action == "x":
            set_kb(nt.approval_buttons(a))
            answer("Đã huỷ.")
        elif action in ("ac", "rc"):
            dec = "approved" if action == "ac" else "rejected"
            who = user.get("username") or user.get("first_name") or str(user.get("id"))
            res = fc.apply_decision(tid, dec, f"qua Telegram bởi {who}", source="telegram")
            set_kb(None)
            answer("Đã duyệt." if dec == "approved" else "Đã từ chối.")
            nxt = {"queue": "Claude sẽ áp dụng ở lượt kế tiếp — quay lại khung chat và gõ “tiếp”.",
                   "direct": "Agent đang chờ sẽ thấy quyết định trong vài giây.",
                   "spawn": "Hãy mở bảng điều khiển hoặc khung chat để Claude làm tiếp."}.get(res["mode"], "")
            self.send(chat["id"],
                      f"<b>{'ĐÃ DUYỆT' if dec == 'approved' else 'ĐÃ TỪ CHỐI'}</b> <code>{E(tid)}</code>\n"
                      f"{E(nt._cut(nt.redact(a.get('what', '')), 300))}\n\n{E(nxt)}",
                      reply_to=msg.get("message_id"))
        else:
            answer("Nút không hợp lệ.")


def _read(p: Path, limit: int = 3000) -> str:
    try:
        return p.read_text(encoding="utf-8")[:limit]
    except OSError:
        return ""


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    if not fc.is_initialised():
        print("Du an chua init. Chay: .flow/flow init", file=sys.stderr)
        return 1
    token = os.environ.get("FLOW_TELEGRAM_TOKEN")
    chats = _ids("FLOW_TELEGRAM_CHAT_ID")
    if not token:
        print("Thieu FLOW_TELEGRAM_TOKEN trong .env.flow. Tao bot voi @BotFather de lay token.",
              file=sys.stderr)
        return 1
    if not chats:
        print("CHE DO CAI DAT: chua co FLOW_TELEGRAM_CHAT_ID nen bot chi tra loi /id.\n"
              "Nhan /id cho bot, chep chat id vao .env.flow roi chay lai.", file=sys.stderr)
    readonly = (os.environ.get("FLOW_TELEGRAM_READONLY") or "").strip().lower() in ("1", "true", "yes")
    try:
        Bot(token, chats, _ids("FLOW_TELEGRAM_APPROVERS"), readonly).run()
    except KeyboardInterrupt:
        print("\nDa dung bot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
