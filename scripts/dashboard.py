#!/usr/bin/env python3
"""Bang dieu khien AI Factory.

    python scripts/dashboard.py

Bam duyet tren trang KHONG goi truc tiep vao Claude - Claude Code khong lang
nghe o dau ca. Thay vao do trang ghi quyet dinh vao .flow/queue/, va Claude doc
hang doi do o dau moi luot bang `flow.py inbox`.

Ba che do noi, gat tren trang:
  hang doi  - bam xong ban quay lai chat go "tiep". Khong ton gi luc cho.
  truc tiep - agent dang chay `flow wait` se thay ngay. Ton token quay vong.
  tu chay   - server tu khoi dong `claude -p` mot phien moi. Bat bang --allow-spawn.

Chi lang nghe tren 127.0.0.1, khong co dang nhap.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import flow_core as fc  # noqa: E402

try:
    from usage import collect as collect_usage
except Exception:  # noqa: BLE001
    def collect_usage(*_a: object, **_k: object) -> dict:
        return {"available": False, "note": "Không nạp được usage.py",
                "total": {}, "sessions": []}

ALLOW_SPAWN = "--allow-spawn" in sys.argv

PAGE = r"""<!doctype html>
<html lang="vi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Factory · Bảng điều khiển</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
:root{
  --bg:#f4f5f7;--surface:#ffffff;--surface-2:#f7f8fa;--hover:#f1f3f6;
  --border:#e4e7ec;--border-strong:#d0d5dd;
  --text:#101828;--text-2:#475467;--text-3:#8a94a6;
  --accent:#2e6be6;--accent-soft:#eaf1fd;
  --ok:#12805c;--ok-soft:#e7f6ef;
  --warn:#b25e09;--warn-soft:#fef4e6;--warn-strong:#f59e0b;
  --bad:#c8322b;--bad-soft:#fdecea;
  --shadow:0 1px 2px rgba(16,24,40,.05);
  --shadow-lg:0 12px 32px -8px rgba(16,24,40,.18);
  --r:12px;--r-sm:8px;
  --sans:"Be Vietnam Pro","Segoe UI",system-ui,-apple-system,Roboto,"Helvetica Neue",Arial,sans-serif;
  --mono:"JetBrains Mono",ui-monospace,"SF Mono",Consolas,monospace;
}
@media(prefers-color-scheme:dark){:root{
  --bg:#0b0f15;--surface:#121821;--surface-2:#161d27;--hover:#1a2230;
  --border:#232c38;--border-strong:#303b4a;
  --text:#e7ecf2;--text-2:#a5b1c0;--text-3:#6c7888;
  --accent:#6b9bff;--accent-soft:#17243d;
  --ok:#3ccb8b;--ok-soft:#10271e;
  --warn:#f0a93b;--warn-soft:#2d2111;--warn-strong:#f0a93b;
  --bad:#f2695f;--bad-soft:#2f1715;
  --shadow:none;--shadow-lg:0 12px 32px -8px rgba(0,0,0,.6);
}}
*{box-sizing:border-box}
html,body{margin:0}
body{background:var(--bg);color:var(--text);font:14px/1.55 var(--sans);
  -webkit-font-smoothing:antialiased;font-variant-numeric:tabular-nums}
.mono,code{font-family:var(--mono);font-size:.92em}
button{font:inherit}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* ---------- thanh tren ---------- */
.top{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:16px;
  padding:12px 28px;background:color-mix(in srgb,var(--surface) 88%,transparent);
  backdrop-filter:saturate(1.4) blur(10px);border-bottom:1px solid var(--border)}
.brand{display:flex;align-items:center;gap:11px;min-width:0}
.logo{width:34px;height:34px;border-radius:9px;flex:none;display:grid;place-items:center;
  background:linear-gradient(135deg,var(--accent),#7c5cff);color:#fff;font-weight:700;font-size:13px;letter-spacing:.02em}
.brand .name{font-weight:700;font-size:15px;line-height:1.2}
.brand .sub{font-size:12px;color:var(--text-3)}
.top .sp{flex:1}
.chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;
  border:1px solid var(--border);background:var(--surface-2);color:var(--text-2);font-size:12px;white-space:nowrap}
@media(max-width:640px){.top{padding:10px 16px;gap:10px}.brand .sub,.top .chip:not(.live){display:none}}
.live i{width:8px;height:8px;border-radius:50%;background:var(--text-3)}
.live.on i{background:var(--ok);box-shadow:0 0 0 3px var(--ok-soft)}
.live.off i{background:var(--bad);box-shadow:0 0 0 3px var(--bad-soft)}

/* ---------- dai canh bao ---------- */
.wrap{max-width:1360px;margin:0 auto;padding:22px 28px 48px}
@media(max-width:640px){.wrap{padding:16px 16px 40px}}
#band{margin-bottom:18px}
.status-line{display:flex;align-items:center;gap:10px;padding:11px 16px;border-radius:var(--r);
  background:var(--surface);border:1px solid var(--border);color:var(--text-2);font-size:13px}
.status-line .dot{width:8px;height:8px;border-radius:50%;background:var(--ok);flex:none}
.status-line.running .dot{background:var(--accent);animation:pulse 1.6s ease-in-out infinite}
.status-line.idle .dot{background:var(--text-3)}
@keyframes pulse{50%{opacity:.35}}
.alert{display:flex;gap:18px;align-items:center;flex-wrap:wrap;padding:16px 18px;border-radius:var(--r);
  background:var(--warn-soft);border:1px solid color-mix(in srgb,var(--warn) 35%,transparent);
  border-left:5px solid var(--warn-strong);animation:in .25s ease-out}
@keyframes in{from{opacity:0;transform:translateY(-4px)}}
@media(prefers-reduced-motion:reduce){.alert,.status-line.running .dot{animation:none}}
.alert .ic{width:36px;height:36px;border-radius:50%;flex:none;display:grid;place-items:center;
  background:var(--warn-strong);color:#fff;font-weight:700}
.alert .grow{flex:1;min-width:240px}
.alert .eyebrow{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--warn)}
.alert .what{font-size:16px;font-weight:600;margin:2px 0;word-break:break-word}
.alert .why{font-size:12.5px;color:var(--text-2)}
.alert .more{font-size:12px;color:var(--warn);margin-top:4px;font-weight:500}
.actions{display:flex;gap:8px}

.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;font-weight:600;font-size:13px;
  padding:8px 16px;border-radius:var(--r-sm);border:1px solid var(--border-strong);
  background:var(--surface);color:var(--text);cursor:pointer;transition:background .12s,border-color .12s,opacity .12s}
.btn:hover{background:var(--hover)}
.btn:disabled{opacity:.55;cursor:default}
.btn-primary{background:var(--ok);border-color:var(--ok);color:#fff}
.btn-primary:hover{background:color-mix(in srgb,var(--ok) 88%,#000)}
.btn-danger{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 40%,transparent);background:transparent}
.btn-danger:hover{background:var(--bad-soft)}

/* ---------- bo cuc ---------- */
.layout{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:20px;align-items:start}
@media(max-width:1020px){.layout{grid-template-columns:1fr}}
.stack{display:flex;flex-direction:column;gap:20px;min-width:0}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);box-shadow:var(--shadow);min-width:0}
.card-h{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:14px 18px;border-bottom:1px solid var(--border)}
.card-h h2{margin:0;font-size:14px;font-weight:600}
.card-h .count{font-size:12px;color:var(--text-3);font-weight:500}
.card-h .sp{flex:1}
.card-b{padding:16px 18px}
aside .card-b{padding:16px}
aside h3{margin:0 0 4px;font-size:13px;font-weight:600}
aside .desc{font-size:12px;color:var(--text-3);margin:0 0 12px}

/* ---------- chi so ---------- */
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
@media(max-width:720px){.kpis{grid-template-columns:repeat(2,1fr)}}
.kpi{padding:14px 16px}
.kpi .lb{font-size:12px;color:var(--text-2);display:flex;align-items:center;gap:7px}
.kpi .lb i{width:8px;height:8px;border-radius:2px;background:var(--text-3)}
.kpi b{display:block;font-size:26px;font-weight:700;line-height:1.15;margin-top:6px;letter-spacing:-.02em}
.kpi.ok .lb i{background:var(--ok)}.kpi.run .lb i{background:var(--accent)}
.kpi.bad .lb i{background:var(--bad)}.kpi.wait .lb i{background:var(--warn-strong)}
.kpi.bad b.nz{color:var(--bad)}.kpi.wait b.nz{color:var(--warn)}
.progress{padding:12px 18px 14px}
.progress .meta{display:flex;justify-content:space-between;font-size:12px;color:var(--text-2);margin-bottom:7px}
.bar{height:6px;border-radius:999px;background:var(--surface-2);border:1px solid var(--border);overflow:hidden}
.bar span{display:block;height:100%;background:linear-gradient(90deg,var(--ok),color-mix(in srgb,var(--ok) 70%,var(--accent)));
  border-radius:inherit;transition:width .4s ease}

/* ---------- task ---------- */
.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--text-3)}
.legend span{display:inline-flex;align-items:center;gap:6px}
.legend i{width:10px;height:10px;border-radius:3px}
.task{border-bottom:1px solid var(--border);position:relative}
.task:last-child{border-bottom:none}
.task::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:transparent}
.task.t1::before{background:var(--accent)}
.task.t2::before{background:var(--warn-strong)}
.task.wait{background:color-mix(in srgb,var(--warn-soft) 55%,transparent)}
.row{display:grid;grid-template-columns:52px minmax(0,1fr) auto auto 18px;gap:14px;align-items:center;
  padding:13px 18px;cursor:pointer;transition:background .12s}
.row:hover{background:var(--hover)}
.row .id{font-family:var(--mono);font-size:12px;color:var(--text-3);font-weight:500}
.row .ti{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row .files{display:flex;gap:5px;flex-wrap:wrap;margin-top:4px}
.row .files code{font-size:11px;padding:1px 6px;border-radius:4px;background:var(--surface-2);
  border:1px solid var(--border);color:var(--text-2);max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chev{color:var(--text-3);transition:transform .15s;font-size:12px}
.task.open .chev{transform:rotate(90deg)}
@media(max-width:640px){.row{grid-template-columns:44px minmax(0,1fr) 18px}.row .tier{display:none}.row .pill{grid-column:2;justify-self:start}}

.tier{font-size:11px;font-weight:600;padding:3px 8px;border-radius:6px;white-space:nowrap;
  background:var(--surface-2);color:var(--text-2);border:1px solid var(--border)}
.tier.t1{background:var(--accent-soft);color:var(--accent);border-color:transparent}
.tier.t2{background:var(--warn-soft);color:var(--warn);border-color:transparent}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:3px 10px;
  border-radius:999px;white-space:nowrap;background:var(--surface-2);color:var(--text-2)}
.pill i{width:6px;height:6px;border-radius:50%;background:currentColor}
.pill.done{background:var(--ok-soft);color:var(--ok)}
.pill.running{background:var(--accent-soft);color:var(--accent)}
.pill.running i{animation:pulse 1.4s ease-in-out infinite}
.pill.awaiting_approval{background:var(--warn-soft);color:var(--warn)}
.pill.gate_failed,.pill.review_failed{background:var(--bad-soft);color:var(--bad)}
.pill.pending,.pill.blocked,.pill.skipped{color:var(--text-3)}

.detail{display:none;padding:4px 18px 18px 84px}
.task.open .detail{display:block}
@media(max-width:640px){.detail{padding-left:18px}}
.sec{margin-top:14px}
.sec:first-child{margin-top:4px}
.sec h4{margin:0 0 6px;font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--text-3)}
.sec .box{white-space:pre-wrap;word-break:break-word;font-size:13px;color:var(--text-2);
  background:var(--surface-2);border:1px solid var(--border);border-radius:var(--r-sm);padding:10px 12px;
  max-height:260px;overflow:auto}
.verdict{display:inline-block;font-size:12px;font-weight:700;padding:2px 8px;border-radius:6px;margin-bottom:6px}
.verdict.pass{background:var(--ok-soft);color:var(--ok)}
.verdict.fail{background:var(--bad-soft);color:var(--bad)}
.gates{display:flex;gap:6px;flex-wrap:wrap}
.g{font-size:12px;font-weight:500;padding:3px 9px;border-radius:6px;display:inline-flex;align-items:center;gap:5px}
.g.p{background:var(--ok-soft);color:var(--ok)}
.g.f{background:var(--bad-soft);color:var(--bad)}
.g.s{background:var(--surface-2);color:var(--text-3);border:1px solid var(--border)}
textarea{width:100%;font:inherit;font-size:13px;padding:10px 12px;background:var(--surface);
  color:var(--text);border:1px solid var(--border-strong);border-radius:var(--r-sm);resize:vertical;min-height:72px}
textarea:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.fb-actions{display:flex;justify-content:flex-end;margin-top:8px}

.empty{display:flex;flex-direction:column;align-items:center;gap:6px;padding:36px 18px;text-align:center;color:var(--text-3)}
.empty b{color:var(--text-2);font-weight:600;font-size:14px}
.empty span{font-size:12.5px;max-width:420px}

/* ---------- so do ---------- */
#dep{overflow-x:auto}
#dep svg{display:block}

/* ---------- nhat ky ---------- */
.ev{display:grid;grid-template-columns:48px 150px minmax(0,1fr) 44px;gap:12px;align-items:baseline;
  padding:9px 18px;border-bottom:1px solid var(--border);font-size:12.5px}
.ev:last-child{border-bottom:none}
.ev time{font-family:var(--mono);font-size:11.5px;color:var(--text-3)}
.ev .k{font-weight:600;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ev .k small{display:block;font-weight:400;color:var(--text-3);font-size:11px}
.ev .m{color:var(--text-2);word-break:break-word}
.ev .d{text-align:right;color:var(--text-3);font-family:var(--mono);font-size:11.5px}
@media(max-width:640px){.ev{grid-template-columns:44px minmax(0,1fr)}.ev .m{grid-column:2}.ev .d{display:none}}

/* ---------- dieu khien ---------- */
.seg{display:flex;flex-direction:column;gap:6px}
.opt{display:flex;gap:10px;align-items:flex-start;padding:10px 12px;border:1px solid var(--border);
  border-radius:var(--r-sm);cursor:pointer;transition:border-color .12s,background .12s}
.opt:hover{background:var(--hover)}
.opt input{margin:3px 0 0;accent-color:var(--accent)}
.opt b{display:block;font-size:13px;font-weight:600}
.opt span{font-size:12px;color:var(--text-3)}
.opt:has(input:checked){border-color:var(--accent);background:var(--accent-soft)}
.sw{display:flex;align-items:center;justify-content:space-between;gap:12px;cursor:pointer;user-select:none}
.sw .lbl{font-size:13px;font-weight:600}
.sw input{position:absolute;opacity:0;width:0;height:0}
.tr{width:40px;height:22px;border-radius:11px;background:var(--border-strong);position:relative;flex:none;transition:background .15s}
.kn{position:absolute;top:3px;left:3px;width:16px;height:16px;border-radius:50%;background:#fff;
  box-shadow:0 1px 2px rgba(0,0,0,.25);transition:transform .15s}
.sw input:checked+.tr{background:var(--ok)}
.sw input:checked+.tr .kn{transform:translateX(18px)}
.sw input:focus-visible+.tr{outline:2px solid var(--accent);outline-offset:2px}
.field{margin-top:12px}
.field label{display:block;font-size:12px;color:var(--text-2);margin-bottom:5px;font-weight:500}
select{font:inherit;font-size:13px;width:100%;padding:8px 10px;background:var(--surface);color:var(--text);
  border:1px solid var(--border-strong);border-radius:var(--r-sm)}
select:disabled{opacity:.55}
.note{font-size:12px;color:var(--text-3);margin-top:10px;line-height:1.5}
.warnbox{display:none;margin-top:10px;font-size:12px;line-height:1.5;padding:9px 11px;border-radius:var(--r-sm);
  background:var(--bad-soft);color:var(--bad)}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.stat{padding:10px;border-radius:var(--r-sm);background:var(--surface-2);border:1px solid var(--border)}
.stat b{display:block;font-size:17px;font-weight:700;letter-spacing:-.01em}
.stat span{font-size:11px;color:var(--text-3)}
.tip{margin-top:10px;font-size:12px;padding:9px 11px;border-radius:var(--r-sm);background:var(--warn-soft);color:var(--warn);font-weight:500}

/* ---------- toast ---------- */
#toast{position:fixed;right:24px;bottom:24px;z-index:50;display:flex;flex-direction:column;gap:8px;max-width:380px}
.toast{padding:12px 14px;border-radius:10px;background:var(--text);color:var(--bg);font-size:13px;
  box-shadow:var(--shadow-lg);animation:in .2s ease-out}
.toast.err{background:var(--bad);color:#fff}
footer{margin-top:24px;text-align:center;font-size:12px;color:var(--text-3)}
</style></head><body>

<header class="top">
  <div class="brand">
    <div class="logo">AF</div>
    <div><div class="name">AI Factory</div><div class="sub">Bảng điều khiển dây chuyền agent</div></div>
  </div>
  <div class="sp"></div>
  <span class="chip" title="Mã run hiện tại">Run <span class="mono" id="runid">—</span></span>
  <span class="chip live" id="live"><i></i><span id="livetxt">Đang kết nối…</span></span>
</header>

<div class="wrap">
  <div id="band"></div>

  <div class="layout">
    <div class="stack">
      <div class="card">
        <div class="kpis">
          <div class="kpi ok"><div class="lb"><i></i>Hoàn thành</div><b id="k-done">0</b></div>
          <div class="kpi run"><div class="lb"><i></i>Còn lại</div><b id="k-left">0</b></div>
          <div class="kpi bad"><div class="lb"><i></i>Thất bại</div><b id="k-fail">0</b></div>
          <div class="kpi wait"><div class="lb"><i></i>Chờ bạn duyệt</div><b id="k-wait">0</b></div>
        </div>
        <div class="progress">
          <div class="meta"><span>Tiến độ run</span><span id="k-pct">0%</span></div>
          <div class="bar"><span id="k-bar" style="width:0"></span></div>
        </div>
      </div>

      <section class="card">
        <div class="card-h">
          <h2>Công việc</h2><span class="count" id="k-count"></span>
          <div class="sp"></div>
          <div class="legend">
            <span><i style="background:var(--border-strong)"></i>Tier 0 · tự chạy</span>
            <span><i style="background:var(--accent)"></i>Tier 1 · tự chạy, báo cáo sau</span>
            <span><i style="background:var(--warn-strong)"></i>Tier 2 · cần bạn duyệt</span>
          </div>
        </div>
        <div id="tasks"></div>
      </section>

      <section class="card">
        <div class="card-h"><h2>Sơ đồ phụ thuộc</h2><span class="count">Task bên phải chờ task bên trái hoàn thành</span></div>
        <div class="card-b" id="dep"></div>
      </section>

      <section class="card">
        <div class="card-h"><h2>Nhật ký hoạt động</h2><span class="count">16 sự kiện gần nhất</span></div>
        <div id="events"></div>
      </section>
    </div>

    <aside class="stack">
      <div class="card"><div class="card-b">
        <h3>Khi bạn bấm duyệt</h3>
        <p class="desc">Chọn cách Claude nhận quyết định của bạn.</p>
        <div class="seg" id="mode">
          <label class="opt"><input type="radio" name="mode" value="queue">
            <div><b>Đưa vào hàng đợi</b><span>Tiết kiệm nhất — Claude đọc ở lượt kế tiếp</span></div></label>
          <label class="opt"><input type="radio" name="mode" value="direct">
            <div><b>Agent thấy ngay</b><span>Nhanh, nhưng tốn token khi chờ</span></div></label>
          <label class="opt"><input type="radio" name="mode" value="spawn">
            <div><b>Tự mở phiên mới</b><span>Cần khởi động với --allow-spawn</span></div></label>
        </div>
        <div class="note" id="modenote"></div>
      </div></div>

      <div class="card"><div class="card-b">
        <label class="sw">
          <span><span class="lbl">Tự động chạy tiếp</span><br><span class="desc" style="margin:0">Không dừng lại hỏi sau mỗi task</span></span>
          <input type="checkbox" id="auto"><span class="tr"><span class="kn"></span></span>
        </label>
        <div class="field">
          <label for="mt">Mức rủi ro tối đa được tự chạy</label>
          <select id="mt">
            <option value="0">Chỉ Tier 0</option>
            <option value="1">Đến Tier 1</option>
            <option value="2">Cả Tier 2</option>
          </select>
        </div>
        <div class="note" id="autonote"></div>
        <div class="warnbox" id="warn">Cảnh báo: AI sẽ được tự chạy migration, thay đổi dependency và sửa phần xác thực mà không hỏi bạn.</div>
      </div></div>

      <div class="card"><div class="card-b">
        <h3>Token phiên này</h3>
        <p class="desc">Chi phí là ước tính, dùng để so sánh giữa các phiên.</p>
        <div id="tok"><div class="note">Đang đọc…</div></div>
      </div></div>
    </aside>
  </div>

  <footer>Chỉ lắng nghe trên 127.0.0.1 · Tự làm mới mỗi 2,5 giây</footer>
</div>

<div id="toast" role="status" aria-live="polite"></div>

<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const ST={done:'Hoàn thành',running:'Đang chạy',awaiting_approval:'Chờ duyệt',
 gate_failed:'Trượt kiểm thử',review_failed:'Bị trả lại',pending:'Đang chờ',
 blocked:'Bị chặn',skipped:'Đã bỏ qua'};
const EV={run_started:'Bắt đầu run',run_resumed:'Mở lại run',plan_imported:'Nạp kế hoạch',
 task_started:'Bắt đầu task',task_done:'Hoàn thành task',task_failed:'Task thất bại',
 gate_passed:'Qua kiểm thử',gate_failed:'Trượt kiểm thử',committed:'Đã commit',
 feedback:'Nhận xét',handoff:'Bàn giao phiên',profile:'Đổi cấu hình',auto_mode:'Chế độ tự động',
 approval_requested:'Yêu cầu duyệt',approval_decided:'Đã có quyết định',
 tier2_auto_allowed:'Tự cho qua Tier 2',tier2_approved_ok:'Tier 2 đã được duyệt',
 agent_start:'Agent bắt đầu',agent_stop:'Agent kết thúc',turn_end:'Kết thúc lượt',
 spawn:'Mở phiên mới',spawn_done:'Phiên mới kết thúc',spawn_failed:'Mở phiên lỗi'};
const TIER=['Tier 0','Tier 1','Tier 2'];
const MODENOTE={
 queue:'Bấm xong, quay lại khung chat và gõ “tiếp”. Claude đọc hàng đợi rồi làm tiếp — không tốn token trong lúc chờ.',
 direct:'Agent đang chạy lệnh chờ sẽ thấy quyết định sau vài giây. Đổi lại, agent tiêu token liên tục trong lúc chờ.',
 spawn:'Máy chủ tự mở một phiên Claude mới ngay khi bạn bấm duyệt.'};
const FAILED=['gate_failed','review_failed'];
let busy=false;
const open=new Set(), drafts={};

const api=(p,b)=>fetch(p,b?{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify(b)}:{}).then(r=>r.json());
const fmt=n=>{n=n||0;return n>=1e6?(n/1e6).toFixed(2).replace('.',',')+' tr':n>=1e3?(n/1e3).toFixed(1).replace('.',',')+' k':String(n)};
const hhmm=d=>d.toLocaleTimeString('vi-VN',{hour:'2-digit',minute:'2-digit',second:'2-digit'});

function toast(msg,err){
 if(!msg)return;
 const t=document.createElement('div');
 t.className='toast'+(err?' err':'');t.textContent=msg;
 $('#toast').appendChild(t);setTimeout(()=>t.remove(),err?6000:4500);
}

function setLive(ok){
 const l=$('#live');l.className='chip live '+(ok?'on':'off');
 $('#livetxt').textContent=ok?'Cập nhật '+hhmm(new Date()):'Mất kết nối máy chủ';
}

function band(s){
 const b=$('#band'), p=s.pending_approvals||[];
 if(!p.length){
  const run=s.tasks.some(t=>t.status==='running');
  const cls=run?'running':(s.tasks.length?'':'idle');
  const txt=run?'Đang chạy — hiện không có việc nào cần bạn xử lý.'
   :(s.tasks.length?'Mọi thứ ổn — không có việc nào cần bạn xử lý.':'Chưa có run nào. Hãy nêu ý tưởng trong khung chat để bắt đầu.');
  b.innerHTML=`<div class="status-line ${cls}"><span class="dot"></span>${txt}</div>`;
  document.title='AI Factory · Bảng điều khiển'; return;
 }
 const a=p[0];
 b.innerHTML=`<div class="alert" role="alert">
  <div class="ic">!</div>
  <div class="grow"><div class="eyebrow">Cần bạn duyệt · Task ${esc(a.task_id)} · Tier ${esc(a.tier)}</div>
   <div class="what">${esc(a.what)}</div>
   <div class="why">${esc(a.reason)}</div>
   ${p.length>1?`<div class="more">và ${p.length-1} yêu cầu khác đang chờ</div>`:''}</div>
  <div class="actions">
   <button class="btn btn-danger" data-do="rejected" data-id="${esc(a.task_id)}">Từ chối</button>
   <button class="btn btn-primary" data-do="approved" data-id="${esc(a.task_id)}">Duyệt</button>
  </div></div>`;
 document.title=`(${p.length}) Cần bạn duyệt · AI Factory`;
}

function kpis(s){
 const n=s.tasks.length, d=s.tasks.filter(t=>t.status==='done').length;
 const f=s.tasks.filter(t=>FAILED.includes(t.status)).length;
 const w=(s.pending_approvals||[]).length;
 $('#k-done').textContent=d;$('#k-left').textContent=n-d;
 const kf=$('#k-fail'),kw=$('#k-wait');
 kf.textContent=f;kf.className=f?'nz':'';kw.textContent=w;kw.className=w?'nz':'';
 const pct=n?Math.round(d*100/n):0;
 $('#k-pct').textContent=`${d}/${n} task · ${pct}%`;$('#k-bar').style.width=pct+'%';
 $('#k-count').textContent=n?`${n} task`:'';
}

function gateChips(g){
 if(!g)return '';
 const c=[];
 (g.passed||[]).forEach(x=>c.push(`<span class="g p">✓ ${esc(x)}</span>`));
 (g.failed||[]).forEach(x=>c.push(`<span class="g f">✕ ${esc(x)}</span>`));
 (g.skipped||[]).forEach(x=>c.push(`<span class="g s">– ${esc(x)} (bỏ qua)</span>`));
 if(g.no_checks_ran)c.push('<span class="g f">Không có bước kiểm tra nào được chạy</span>');
 return c.length?`<div class="sec"><h4>Kiểm thử tự động</h4><div class="gates">${c.join('')}</div></div>`:'';
}

function verdict(txt){
 const t=(txt||'').toLowerCase();
 if(/cho qua/.test(t))return '<span class="verdict pass">CHO QUA</span>';
 if(/tr[aả] l[aạ]i/.test(t))return '<span class="verdict fail">TRẢ LẠI</span>';
 return '';
}

function tasks(s){
 const el=$('#tasks'), act=document.activeElement;
 if(act&&act.tagName==='TEXTAREA'&&el.contains(act))return;
 if(!s.tasks.length){el.innerHTML=`<div class="empty"><b>Chưa có task nào</b>
  <span>Task sẽ xuất hiện ở đây khi planner nạp kế hoạch cho run hiện tại.</span></div>`;return}
 el.innerHTML=s.tasks.map(t=>{
  const r=s.reports?.[t.id]||{}, id=esc(t.id), tier=Math.min(+t.tier||0,2);
  const files=(t.files||[]).map(f=>`<code title="${esc(f)}">${esc(f)}</code>`).join('');
  return `<div class="task t${tier} ${t.status==='awaiting_approval'?'wait':''} ${open.has(t.id)?'open':''}" data-t="${id}">
   <div class="row" data-toggle="${id}" role="button" tabindex="0" aria-expanded="${open.has(t.id)}">
    <div class="id">${id}</div>
    <div style="min-width:0"><div class="ti" title="${esc(t.title)}">${esc(t.title)}</div>
     ${files?`<div class="files">${files}</div>`:''}</div>
    <span class="tier t${tier}">${TIER[tier]}</span>
    <span class="pill ${esc(t.status)}"><i></i>${ST[t.status]||esc(t.status)}</span>
    <span class="chev">▶</span>
   </div>
   <div class="detail">
    ${t.description?`<div class="sec"><h4>Mô tả</h4><div class="box">${esc(t.description)}</div></div>`:''}
    ${gateChips(t.gate)}
    ${tier>=2?`<div class="sec"><h4>Vì sao cần bạn duyệt</h4><div class="box">${esc(t.tier_reason||'')}</div></div>`:''}
    ${r.review?`<div class="sec"><h4>Kết luận của verifier</h4>${verdict(r.review)}<div class="box">${esc(r.review)}</div></div>`:''}
    ${r.notes?`<div class="sec"><h4>Ghi chú của coder</h4><div class="box">${esc(r.notes)}</div></div>`:''}
    ${r.feedback?`<div class="sec"><h4>Nhận xét của bạn</h4><div class="box">${esc(r.feedback)}</div></div>`:''}
    ${t.commit?`<div class="sec"><h4>Commit</h4><code>${esc(t.commit)}</code></div>`:''}
    <div class="sec"><h4>Để lại nhận xét</h4>
     <textarea data-fb="${id}" placeholder="Ví dụ: Chỗ này xử lý chưa đúng, nên đổi thành…">${esc(drafts[t.id]||'')}</textarea>
     <div class="fb-actions"><button class="btn" data-send="${id}">Gửi nhận xét</button></div></div>
   </div></div>`}).join('');
}

function dep(s){
 const el=$('#dep'), ts=s.tasks||[];
 if(!ts.length){el.innerHTML='<div class="empty" style="padding:18px"><span>Chưa có task để vẽ sơ đồ.</span></div>';return}
 const by={}; ts.forEach(t=>by[t.id]=t);
 const lvl={};
 const depth=(id,seen=new Set())=>{
  if(lvl[id]!==undefined)return lvl[id];
  if(seen.has(id))return 0;
  seen.add(id);
  const d=by[id]?.depends_on||[];
  const v=d.length?Math.max(...d.map(x=>depth(x,seen)))+1:0;
  return lvl[id]=v;
 };
 ts.forEach(t=>depth(t.id));
 const cols={}; ts.forEach(t=>(cols[lvl[t.id]]=cols[lvl[t.id]]||[]).push(t));
 const NW=168,NH=46,GX=56,GY=14,PAD=4;
 const nx=Math.max(...Object.keys(cols).map(Number))+1;
 const ny=Math.max(...Object.values(cols).map(a=>a.length));
 const pos={};
 Object.entries(cols).forEach(([c,arr])=>arr.forEach((t,i)=>{
  pos[t.id]={x:PAD+Number(c)*(NW+GX),y:PAD+i*(NH+GY)}}));
 const col=t=>t.status==='done'?'var(--ok)':t.status==='running'?'var(--accent)':
  FAILED.includes(t.status)?'var(--bad)':t.tier>=2?'var(--warn-strong)':'var(--border-strong)';
 const W=PAD*2+nx*NW+(nx-1)*GX, H=PAD*2+ny*NH+(ny-1)*GY;
 let svg=`<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Sơ đồ phụ thuộc giữa các task">
  <defs><marker id="ar" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
  <path d="M0 0L8 4L0 8z" fill="var(--border-strong)"/></marker></defs>`;
 ts.forEach(t=>(t.depends_on||[]).forEach(d=>{
  if(!pos[d]||!pos[t.id])return;
  const a=pos[d],b=pos[t.id],y1=a.y+NH/2,y2=b.y+NH/2,x1=a.x+NW,x2=b.x-2,m=(x1+x2)/2;
  svg+=`<path d="M${x1} ${y1} C${m} ${y1} ${m} ${y2} ${x2} ${y2}" fill="none" stroke="var(--border-strong)" stroke-width="1.5" marker-end="url(#ar)"/>`}));
 ts.forEach(t=>{const p=pos[t.id], title=t.title.length>20?t.title.slice(0,19)+'…':t.title;
  svg+=`<g><title>${esc(t.id)} · ${esc(t.title)} · ${ST[t.status]||esc(t.status)}</title>
   <rect x="${p.x}" y="${p.y}" width="${NW}" height="${NH}" rx="8" fill="var(--surface)" stroke="${col(t)}" stroke-width="${t.tier>=2?2:1.25}"/>
   <circle cx="${p.x+NW-12}" cy="${p.y+13}" r="4" fill="${col(t)}"/>
   <text x="${p.x+11}" y="${p.y+17}" fill="var(--text-3)" font-size="10.5" font-family="var(--mono)">${esc(t.id)}</text>
   <text x="${p.x+11}" y="${p.y+34}" fill="var(--text)" font-size="12" font-weight="500" font-family="var(--sans)">${esc(title)}</text></g>`});
 el.innerHTML=svg+'</svg>';
}

function events(s){
 const el=$('#events'), ev=(s.events||[]).slice(-16).reverse();
 if(!ev.length){el.innerHTML='<div class="empty"><span>Chưa có hoạt động nào.</span></div>';return}
 el.innerHTML=ev.map(e=>{
  const kind=EV[e.kind]||e.kind||'';
  const who=e.agent?`<small>${esc(e.agent)}</small>`:'';
  return `<div class="ev">
  <time>${esc((e.at||'').slice(11,16))}</time>
  <span class="k" title="${esc(e.kind)}">${esc(kind)}${who}</span>
  <span class="m">${esc((e.message||'').slice(0,160))}${e.task_id?` <code>${esc(e.task_id)}</code>`:''}</span>
  <span class="d">${e.dur?esc(e.dur):''}</span></div>`}).join('');
}

function tokens(s){
 const u=s.usage||{}, el=$('#tok');
 if(!u.available){el.innerHTML=`<div class="note" title="${esc(u.note||'')}" style="margin:0">Chưa đọc được số liệu token của phiên này.</div>`;return}
 const t=u.total||{};
 el.innerHTML=`<div class="stats">
  <div class="stat"><b>${fmt(t.total_tokens)}</b><span>token</span></div>
  <div class="stat"><b>$${(t.cost||0).toFixed(2)}</b><span>chi phí ước tính</span></div>
  <div class="stat"><b>${t.turns||0}</b><span>lượt gọi</span></div></div>
  <div class="note">Đọc từ cache: <b>${fmt(t.cache_read)}</b> token — phần rẻ nhất.</div>
  ${t.total_tokens>400000?'<div class="tip">Phiên đã dài. Nên cắt phiên mới cho task tiếp theo.</div>':''}`;
}

function controls(s){
 if(busy)return;
 const a=s.auto_mode||{}, m=s.approve_mode||'queue';
 $('#auto').checked=!!a.enabled;
 $('#mt').value=String(a.max_tier??1);
 $('#mt').disabled=!a.enabled;
 $('#autonote').textContent=a.enabled
  ?`Các task từ Tier ${a.max_tier} trở xuống sẽ tự chạy tiếp.`
  :'Đang tắt — mỗi task xong đều dừng lại chờ bạn.';
 $('#warn').style.display=(a.enabled&&a.max_tier>=2)?'block':'none';
 const r=document.querySelector(`#mode input[value="${m}"]`); if(r)r.checked=true;
 $('#modenote').textContent=MODENOTE[m]
  +(m==='spawn'&&!s.spawn_allowed?' Chưa bật — hãy khởi động lại máy chủ với --allow-spawn.':'');
}

async function refresh(){
 let s;
 try{s=await api('/api/state')}catch(e){setLive(false);return}
 setLive(true);
 $('#runid').textContent=s.run_id||'—';
 band(s);kpis(s);tasks(s);dep(s);events(s);tokens(s);controls(s);
}

function toggle(id){
 open.has(id)?open.delete(id):open.add(id);
 const el=document.querySelector(`.task[data-t="${CSS.escape(id)}"]`);
 if(el){el.classList.toggle('open');el.querySelector('.row')?.setAttribute('aria-expanded',open.has(id))}
}

document.addEventListener('click',async e=>{
 const tg=e.target.closest('[data-toggle]');
 if(tg){toggle(tg.dataset.toggle);return}

 const snd=e.target.closest('[data-send]');
 if(snd){const id=snd.dataset.send;
  const ta=document.querySelector(`[data-fb="${CSS.escape(id)}"]`);
  if(!ta?.value.trim()){ta?.focus();return}
  snd.disabled=true;snd.textContent='Đang gửi…';
  try{await api('/api/feedback',{task_id:id,text:ta.value});
   delete drafts[id];ta.value='';toast(`Đã gửi nhận xét cho ${id}.`)}
  catch(err){toast('Gửi nhận xét thất bại. Kiểm tra máy chủ.',true)}
  snd.disabled=false;snd.textContent='Gửi nhận xét';ta.blur();refresh();
  return}

 const b=e.target.closest('[data-do]');
 if(!b)return;
 b.parentElement.querySelectorAll('button').forEach(x=>x.disabled=true);
 try{const r=await api('/api/decide',{task_id:b.dataset.id,decision:b.dataset.do});
  toast(r.message||(b.dataset.do==='approved'?'Đã duyệt.':'Đã từ chối.'),!!r.error)}
 catch(err){toast('Không gửi được quyết định. Kiểm tra máy chủ.',true)}
 refresh();
});
document.addEventListener('keydown',e=>{
 const tg=e.target.closest?.('[data-toggle]');
 if(tg&&(e.key==='Enter'||e.key===' ')){e.preventDefault();toggle(tg.dataset.toggle)}
});
document.addEventListener('input',e=>{
 const ta=e.target.closest('[data-fb]'); if(ta)drafts[ta.dataset.fb]=ta.value;
});

$('#mode').addEventListener('change',async e=>{
 busy=true;
 try{await api('/api/mode',{mode:e.target.value})}catch(err){toast('Không lưu được chế độ duyệt.',true)}
 busy=false;refresh()});
const pushAuto=async()=>{busy=true;
 try{await api('/api/auto',{enabled:$('#auto').checked,max_tier:+$('#mt').value})}
 catch(err){toast('Không lưu được chế độ tự động.',true)}
 busy=false;refresh()};
$('#auto').addEventListener('change',pushAuto);
$('#mt').addEventListener('change',pushAuto);

refresh();setInterval(refresh,2500);
</script></body></html>
"""


def _read(p: Path, limit: int = 1200) -> str:
    try:
        return p.read_text(encoding="utf-8")[:limit]
    except OSError:
        return ""


def _spawn_claude(task_id: str) -> str:
    """Khoi dong mot phien Claude moi de lam tiep. Chi khi --allow-spawn."""
    exe = shutil.which("claude")
    if not exe:
        return "Không tìm thấy lệnh 'claude' trong PATH."
    prompt = (f"Nguoi dung vua duyet task {task_id} tren bang dieu khien. "
              f"Chay `python scripts/flow.py inbox` roi lam tiep task do.")

    def run() -> None:
        try:
            subprocess.run([exe, "-p", prompt], cwd=fc.ROOT, timeout=3600,
                           capture_output=True, check=False)
            fc.log_event("spawn_done", f"phiên mới cho {task_id} đã kết thúc", task_id=task_id)
        except Exception as e:  # noqa: BLE001
            fc.log_event("spawn_failed", str(e)[:200], task_id=task_id)

    threading.Thread(target=run, daemon=True).start()
    fc.log_event("spawn", f"khởi động phiên Claude mới cho {task_id}", task_id=task_id)
    return f"Đã khởi động phiên Claude mới cho {task_id}. Kết quả sẽ hiện trong nhật ký."


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_a: object) -> None:
        pass

    def _send(self, body: bytes, ctype: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: object, status: int = 200) -> None:
        self._send(json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"),
                   "application/json; charset=utf-8", status)

    # ------------------------------------------------------------------ GET

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path.startswith("/api/state"):
            self._json(self._state())
        else:
            self._json({"error": "Không tìm thấy"}, 404)

    def _state(self) -> dict:
        cfg = fc.load_config()
        cur = fc.get_current()
        # pending_approvals doc duoc ca khi chua co run nao (vd: mot lenh
        # Tier 2 roi rac nhu git push thu cong bi tier_guard chan) - phai
        # tinh truoc, khong duoc gop vao nhanh "chua co run thi tra rong".
        base = {
            "run_id": None, "tasks": [], "events": [], "pending_approvals": fc.pending_approvals(),
            "reports": {}, "auto_mode": cfg["auto_mode"],
            "approve_mode": cfg.get("approve_mode", "queue"),
            "spawn_allowed": ALLOW_SPAWN,
            "usage": collect_usage(fc.ROOT),
        }
        if not cur.get("run_id"):
            return base

        try:
            tasks = fc.load_tasks().get("tasks", [])
            events = fc.read_events(limit=60)
            pend = fc.pending_approvals()
            d = fc.run_dir()
        except SystemExit:
            return base

        reports = {}
        for t in tasks:
            td = d / "tasks" / t["id"]
            r = {}
            rv = _read(td / "review.md")
            if rv:
                # lay phan ket luan neu co, khong thi lay dau file
                low = rv.lower()
                idx = max(low.rfind("## ket luan"), low.rfind("## kết luận"))
                r["review"] = (rv[idx:] if idx >= 0 else rv)[:700]
            nt = _read(td / "notes.md")
            if nt:
                r["notes"] = nt[:700]
            fb = _read(td / "feedback.md")
            if fb:
                r["feedback"] = fb[:700]
            if r:
                reports[t["id"]] = r

        # thoi luong moi su kien, cho cot phai cua nhat ky
        prev = None
        for e in events:
            if prev:
                try:
                    from datetime import datetime
                    dt = (datetime.fromisoformat(e["at"]) - datetime.fromisoformat(prev)).total_seconds()
                    e["dur"] = f"{int(dt)}s" if dt < 90 else f"{int(dt/60)}p"
                except (ValueError, KeyError):
                    pass
            prev = e.get("at")

        base.update({"run_id": cur["run_id"], "task_id": cur.get("task_id"),
                     "tasks": tasks, "events": events, "pending_approvals": pend,
                     "reports": reports})
        return base

    # ----------------------------------------------------------------- POST

    def do_POST(self) -> None:  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "JSON không hợp lệ"}, 400)
            return

        cfg = fc.load_config()

        if self.path == "/api/decide":
            tid, dec = body.get("task_id"), body.get("decision")
            if dec not in ("approved", "rejected") or not tid:
                self._json({"error": "Thiếu task_id hoặc decision"}, 400)
                return

            mode = fc.apply_decision(tid, dec, body.get("note", ""), source="web")["mode"]
            if mode == "direct":
                msg = "Đã ghi quyết định. Agent đang chờ sẽ thấy trong vài giây."
            elif mode == "spawn" and dec == "approved":
                msg = _spawn_claude(tid) if ALLOW_SPAWN else (
                    "Chế độ tự mở phiên mới chưa bật. Khởi động lại máy chủ với --allow-spawn, "
                    "hoặc quay lại khung chat gõ “tiếp”.")
            elif mode == "queue":
                msg = "Đã đưa vào hàng đợi. Quay lại khung chat gõ “tiếp” để Claude làm tiếp."
            else:
                msg = ""

            self._json({"ok": True, "message": msg})

        elif self.path == "/api/feedback":
            tid, text = body.get("task_id"), (body.get("text") or "").strip()
            if not (tid and text):
                self._json({"error": "Thiếu task_id hoặc nội dung nhận xét"}, 400)
                return
            fc.queue_push("feedback", {"task_id": tid, "text": text})
            try:
                td = fc.run_dir() / "tasks" / tid
                td.mkdir(parents=True, exist_ok=True)
                with (td / "feedback.md").open("a", encoding="utf-8") as f:
                    f.write(f"\n## Nhận xét {fc.now()}\n\n{text}\n")
                fc.log_event("feedback", text[:200], task_id=tid)
            except SystemExit:
                pass
            self._json({"ok": True})

        elif self.path == "/api/mode":
            m = body.get("mode")
            if m not in ("queue", "direct", "spawn"):
                self._json({"error": "Chế độ không hợp lệ"}, 400)
                return
            cfg["approve_mode"] = m
            fc.save_config(cfg)
            self._json({"ok": True, "approve_mode": m, "spawn_allowed": ALLOW_SPAWN})

        elif self.path == "/api/auto":
            cfg["auto_mode"]["enabled"] = bool(body.get("enabled"))
            if body.get("max_tier") is not None:
                cfg["auto_mode"]["max_tier"] = int(body["max_tier"])
            fc.save_config(cfg)
            fc.log_event("auto_mode",
                         f"{'bật' if cfg['auto_mode']['enabled'] else 'tắt'}, "
                         f"max_tier={cfg['auto_mode']['max_tier']} (từ bảng điều khiển)")
            self._json({"ok": True, "auto_mode": cfg["auto_mode"]})

        else:
            self._json({"error": "Không tìm thấy"}, 404)


def _utf8_stdio() -> None:
    # Windows: stdout bi chuyen huong dung cp1252, in tieng Viet co dau se vo.
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    _utf8_stdio()
    cfg = fc.load_config()
    host = cfg["dashboard"].get("host", "127.0.0.1")
    port = int(cfg["dashboard"].get("port", 7788))
    srv = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"

    print(f"Bang dieu khien AI Factory: {url}")
    print(f"Che do duyet: {cfg.get('approve_mode', 'queue')}"
          + ("  (tu khoi dong phien moi: BAT)" if ALLOW_SPAWN else ""))
    print("Ctrl+C de dung.")

    if "--no-open" not in sys.argv:
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nDa dung.")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
