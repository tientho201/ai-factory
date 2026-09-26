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
        return {"available": False, "note": "khong nap duoc usage.py",
                "total": {}, "sessions": []}

ALLOW_SPAWN = "--allow-spawn" in sys.argv

PAGE = r"""<!doctype html>
<html lang="vi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Factory</title>
<style>
:root{
  --ink:#10151a;--panel:#182028;--panel2:#1e2831;--line:#2a343f;
  --text:#dbe2e8;--muted:#8093a2;--dim:#5b6d7b;
  --wait:#e0a33c;--ok:#4e9e6a;--bad:#c85a4e;--live:#5c93cf;--r:3px;
}
@media(prefers-color-scheme:light){:root{
  --ink:#eaecee;--panel:#fbfbfa;--panel2:#f1f3f5;--line:#d4d9dd;
  --text:#1c252c;--muted:#5e6f7c;--dim:#8998a4;
  --wait:#b1770f;--ok:#2e7849;--bad:#a63e33;--live:#37699f;}}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--text);
 font:15px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
 font-variant-numeric:tabular-nums}
.mono,code{font-family:ui-monospace,"SF Mono",Consolas,monospace}

/* dai canh bao: thu duy nhat can nhin tu xa */
#band{padding:14px 26px;border-bottom:1px solid var(--line);background:var(--panel);
 color:var(--muted);font-size:14px;display:flex;gap:18px;align-items:center;flex-wrap:wrap}
#band.alert{background:var(--wait);color:#141009;border-bottom:none;padding:20px 26px;
 animation:in .3s ease-out}
@keyframes in{from{opacity:0;transform:translateY(-6px)}}
@media(prefers-reduced-motion:reduce){#band.alert{animation:none}}
#band.alert .what{font-size:19px;font-weight:650;letter-spacing:-.01em}
#band.alert .why{font-size:13px;opacity:.72;margin-top:3px}
#band .grow{flex:1;min-width:230px}
.btn{font:inherit;font-weight:600;border:1px solid transparent;padding:9px 20px;
 border-radius:var(--r);cursor:pointer}
.btn-yes{background:#141009;color:#f5e9d3}
.btn-no{background:transparent;color:#141009;border-color:rgba(0,0,0,.35)}
.btn:disabled{opacity:.5;cursor:default}
.btn:focus-visible{outline:2px solid currentColor;outline-offset:2px}

main{display:grid;grid-template-columns:250px 1fr;min-height:calc(100vh - 54px)}
@media(max-width:860px){main{grid-template-columns:1fr}aside{border-right:none!important}}
aside{border-right:1px solid var(--line);padding:22px 18px;background:var(--panel)}
section{padding:22px 26px;min-width:0}
h1{font-size:15px;font-weight:650;margin:0 0 2px}
.runid{font-size:12px;color:var(--dim);margin-bottom:22px}
.blk{margin-bottom:24px}
.blk h2{font-size:12px;font-weight:600;color:var(--muted);margin:0 0 9px}
.counts{display:flex;gap:15px}
.cnt b{display:block;font-size:23px;font-weight:600;line-height:1.1}
.cnt span{font-size:11px;color:var(--muted)}

/* cong tac */
.sw{display:flex;align-items:center;gap:9px;cursor:pointer;user-select:none}
.sw input{position:absolute;opacity:0;width:0}
.tr{width:36px;height:20px;border-radius:10px;background:var(--line);position:relative;flex:none;transition:background .15s}
.kn{position:absolute;top:3px;left:3px;width:14px;height:14px;border-radius:50%;background:var(--panel2);transition:transform .15s}
.sw input:checked+.tr{background:var(--ok)}
.sw input:checked+.tr .kn{transform:translateX(16px)}
.sw input:focus-visible+.tr{outline:2px solid var(--live);outline-offset:2px}
select{font:inherit;font-size:13px;margin-top:9px;width:100%;padding:6px 8px;
 background:var(--panel2);color:var(--text);border:1px solid var(--line);border-radius:var(--r)}
.note{font-size:12px;color:var(--muted);margin-top:7px;line-height:1.45}
.warn{color:var(--bad);font-size:12px;margin-top:7px;display:none}

/* task: vien trai day mong theo tier */
.task{background:var(--panel);margin-bottom:2px;border-left:3px solid var(--dim)}
.task.t1{border-left-width:5px;border-left-color:var(--live)}
.task.t2{border-left-width:9px;border-left-color:var(--wait)}
.task.wait{background:var(--panel2)}
.row{display:flex;gap:13px;align-items:flex-start;padding:12px 15px;cursor:pointer}
.row .id{font-size:12px;color:var(--muted);width:32px;flex:none;padding-top:2px}
.row .bd{flex:1;min-width:0}
.row .ti{font-weight:550}
.row .mt{font-size:12px;color:var(--dim);margin-top:3px;word-break:break-all}
.row .st{font-size:12px;font-weight:600;flex:none;padding-top:2px}
.st.done{color:var(--ok)}.st.running{color:var(--live)}.st.awaiting_approval{color:var(--wait)}
.st.gate_failed,.st.review_failed{color:var(--bad)}
.st.pending,.st.blocked,.st.skipped{color:var(--dim)}
.detail{display:none;padding:0 15px 15px 60px;font-size:13px;color:var(--muted);
 border-top:1px solid var(--line);margin-top:2px;padding-top:12px}
.task.open .detail{display:block}
.detail h4{font-size:12px;color:var(--text);margin:12px 0 5px;font-weight:600}
.detail p{margin:5px 0;white-space:pre-wrap}
.gates{display:flex;gap:7px;flex-wrap:wrap;margin:5px 0}
.g{font-size:11px;padding:2px 8px;border-radius:2px;border:1px solid var(--line)}
.g.p{color:var(--ok);border-color:var(--ok)}
.g.f{color:var(--bad);border-color:var(--bad)}
.g.s{color:var(--dim)}
textarea{width:100%;font:inherit;font-size:13px;padding:8px;background:var(--panel2);
 color:var(--text);border:1px solid var(--line);border-radius:var(--r);resize:vertical;min-height:58px}
.detail .btn{margin-top:7px;background:var(--panel2);color:var(--text);border-color:var(--line);
 font-size:13px;padding:6px 14px}

.legend{font-size:12px;color:var(--dim);margin-top:13px;display:flex;gap:17px;flex-wrap:wrap}
.legend i{display:inline-block;width:3px;height:11px;margin-right:6px;vertical-align:-1px;background:var(--dim)}
.legend .l1 i{width:5px;background:var(--live)}
.legend .l2 i{width:9px;background:var(--wait)}

/* so do phu thuoc */
#dep{width:100%;overflow-x:auto}
#dep svg{display:block;min-width:100%}

/* nhat ky */
.ev{font-size:12px;color:var(--muted);padding:5px 0;border-bottom:1px solid var(--line);display:flex;gap:11px}
.ev time{color:var(--dim);flex:none}
.ev .k{flex:none;width:120px;color:var(--text);opacity:.78}
.ev .d{flex:none;color:var(--dim);width:48px;text-align:right}

/* token */
.tok{display:flex;gap:20px;flex-wrap:wrap;font-size:13px}
.tok div b{display:block;font-size:19px;font-weight:600}
.tok div span{font-size:11px;color:var(--muted)}
.empty{color:var(--dim);font-size:14px;padding:24px 0}
.hint{font-size:12px;color:var(--dim);margin-top:9px;line-height:1.5}
</style></head><body>

<div id="band">Dang tai...</div>

<main>
<aside>
  <h1>AI Factory</h1>
  <div class="runid mono" id="runid">-</div>

  <div class="blk"><h2>Tien do</h2>
    <div class="counts">
      <div class="cnt"><b id="c1">0</b><span>xong</span></div>
      <div class="cnt"><b id="c2">0</b><span>con lai</span></div>
      <div class="cnt"><b id="c3">0</b><span>truot</span></div>
    </div>
  </div>

  <div class="blk"><h2>Bam duyet thi</h2>
    <select id="mode">
      <option value="queue">Vao hang doi (re nhat)</option>
      <option value="direct">Agent thay ngay</option>
      <option value="spawn">Tu khoi dong phien moi</option>
    </select>
    <div class="note" id="modenote"></div>
  </div>

  <div class="blk"><h2>Chay tiep khong hoi</h2>
    <label class="sw"><input type="checkbox" id="auto">
      <span class="tr"><span class="kn"></span></span><span id="autolbl">Tat</span></label>
    <select id="mt">
      <option value="0">Chi Tier 0</option>
      <option value="1">Den Tier 1</option>
      <option value="2">Ca Tier 2</option>
    </select>
    <div class="note" id="autonote"></div>
    <div class="warn" id="warn">AI duoc tu chay migration, doi dependency va sua auth
      ma khong hoi ban.</div>
  </div>

  <div class="blk"><h2>Token phien nay</h2>
    <div id="tok"><div class="note">dang doc...</div></div>
  </div>
</aside>

<section>
  <div class="blk"><h2>Cong viec</h2>
    <div id="tasks"><div class="empty">Chua co task nao.</div></div>
    <div class="legend">
      <span class="l0"><i></i>Tier 0 tu chay</span>
      <span class="l1"><i></i>Tier 1 tu chay roi bao cao</span>
      <span class="l2"><i></i>Tier 2 phai duoc ban duyet</span>
    </div>
    <div class="hint">Bam vao mot task de xem bao cao, ket qua test va de lai nhan xet.</div>
  </div>

  <div class="blk"><h2>Task nao chan task nao</h2><div id="dep"></div></div>
  <div class="blk"><h2>Nhat ky</h2><div id="events"><div class="empty">Chua co gi.</div></div></div>
</section>
</main>

<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const ST={done:'xong',running:'dang chay',awaiting_approval:'cho ban duyet',
 gate_failed:'truot cong may',review_failed:'review tra lai',pending:'cho',
 blocked:'bi chan',skipped:'bo qua'};
const MODENOTE={
 queue:'Bam xong, ban quay lai chat go "tiep". Claude doc hang doi roi chay tiep. Khong ton gi luc cho.',
 direct:'Agent dang chay lenh cho se thay ngay. Doi lai no dot token trong luc quay vong cho.',
 spawn:'Server tu chay mot phien Claude moi. Chi hoat dong khi server khoi dong voi --allow-spawn.'};
let busy=false, open=new Set();

const api=(p,b)=>fetch(p,b?{method:'POST',headers:{'Content-Type':'application/json'},
 body:JSON.stringify(b)}:{}).then(r=>r.json());
const fmt=n=>n>=1e6?(n/1e6).toFixed(2)+'M':n>=1e3?(n/1e3).toFixed(1)+'k':String(n||0);

function band(s){
 const b=$('#band'), p=s.pending_approvals||[];
 if(!p.length){
  b.className='';
  const run=s.tasks.some(t=>t.status==='running');
  b.textContent=run?'Dang chay. Khong co gi can ban lam.'
   :(s.tasks.length?'Khong co gi can ban lam.':'Chua co run nao.');
  document.title='AI Factory'; return;
 }
 const a=p[0];
 b.className='alert';
 b.innerHTML=`<div class="grow"><div class="what">${esc(a.what)}</div>
  <div class="why">Task ${esc(a.task_id)} &middot; Tier ${a.tier} &middot; ${esc(a.reason)}</div></div>
  <button class="btn btn-yes" data-do="approved" data-id="${esc(a.task_id)}">Duyet</button>
  <button class="btn btn-no" data-do="rejected" data-id="${esc(a.task_id)}">Tu choi</button>`;
 document.title=`(${p.length}) Can ban duyet`;
}

function gateChips(g){
 if(!g)return '';
 const c=[];
 (g.passed||[]).forEach(x=>c.push(`<span class="g p">${esc(x)} dat</span>`));
 (g.failed||[]).forEach(x=>c.push(`<span class="g f">${esc(x)} truot</span>`));
 (g.skipped||[]).forEach(x=>c.push(`<span class="g s">${esc(x)} bo qua</span>`));
 if(g.no_checks_ran)c.push('<span class="g f">khong co kiem tra nao chay</span>');
 return c.length?`<div class="gates">${c.join('')}</div>`:'';
}

function tasks(s){
 const el=$('#tasks');
 if(!s.tasks.length){el.innerHTML='<div class="empty">Chua co task nao.</div>';return}
 el.innerHTML=s.tasks.map(t=>{
  const r=s.reports?.[t.id]||{};
  return `<div class="task t${t.tier} ${t.status==='awaiting_approval'?'wait':''} ${open.has(t.id)?'open':''}" data-t="${esc(t.id)}">
   <div class="row" data-toggle="${esc(t.id)}">
    <div class="id mono">${esc(t.id)}</div>
    <div class="bd"><div class="ti">${esc(t.title)}</div>
     <div class="mt">${esc((t.files||[]).join('  '))||'&nbsp;'}</div></div>
    <div class="st ${t.status}">${ST[t.status]||t.status}</div>
   </div>
   <div class="detail">
    ${gateChips(t.gate)}
    ${t.tier>=2?`<h4>Vi sao can ban duyet</h4><p>${esc(t.tier_reason||'')}</p>`:''}
    ${r.review?`<h4>Verifier ket luan</h4><p>${esc(r.review)}</p>`:''}
    ${r.notes?`<h4>Coder ghi lai</h4><p>${esc(r.notes)}</p>`:''}
    ${r.feedback?`<h4>Nhan xet cua ban</h4><p>${esc(r.feedback)}</p>`:''}
    ${t.commit?`<h4>Commit</h4><p class="mono">${esc(t.commit)}</p>`:''}
    <h4>De lai nhan xet</h4>
    <textarea data-fb="${esc(t.id)}" placeholder="Cho nay lam chua dung, nen doi thanh..."></textarea>
    <button class="btn" data-send="${esc(t.id)}">Gui nhan xet</button>
   </div></div>`}).join('');
}

function dep(s){
 const el=$('#dep'), ts=s.tasks||[];
 if(!ts.length){el.innerHTML='<div class="empty">Chua co task nao.</div>';return}
 // xep theo tang: tang = do sau phu thuoc
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
 const W=170,H=52,PAD=14;
 const nx=Math.max(...Object.keys(cols).map(Number))+1;
 const ny=Math.max(...Object.values(cols).map(a=>a.length));
 const pos={};
 Object.entries(cols).forEach(([c,arr])=>arr.forEach((t,i)=>{
  pos[t.id]={x:PAD+Number(c)*W,y:PAD+i*H}}));
 const col=t=>t.status==='done'?'var(--ok)':t.status==='running'?'var(--live)':
  ['gate_failed','review_failed'].includes(t.status)?'var(--bad)':
  t.tier>=2?'var(--wait)':'var(--dim)';
 let svg=`<svg viewBox="0 0 ${PAD*2+nx*W} ${PAD*2+ny*H}" height="${PAD*2+ny*H}">`;
 ts.forEach(t=>(t.depends_on||[]).forEach(d=>{
  if(!pos[d]||!pos[t.id])return;
  const a=pos[d],b=pos[t.id];
  svg+=`<path d="M${a.x+128} ${a.y+17} C${a.x+150} ${a.y+17} ${b.x-20} ${b.y+17} ${b.x} ${b.y+17}"
   fill="none" stroke="var(--line)" stroke-width="1.5"/>`}));
 ts.forEach(t=>{const p=pos[t.id];
  svg+=`<g><rect x="${p.x}" y="${p.y}" width="128" height="34" rx="2"
   fill="var(--panel)" stroke="${col(t)}" stroke-width="${t.tier>=2?2.5:1}"/>
   <text x="${p.x+9}" y="${p.y+15}" fill="var(--muted)" font-size="10"
    font-family="ui-monospace,monospace">${esc(t.id)}</text>
   <text x="${p.x+9}" y="${p.y+27}" fill="var(--text)" font-size="11">${esc(t.title.slice(0,17))}</text></g>`});
 el.innerHTML=svg+'</svg>';
}

function events(s){
 const el=$('#events'), ev=(s.events||[]).slice(-16).reverse();
 if(!ev.length){el.innerHTML='<div class="empty">Chua co gi.</div>';return}
 el.innerHTML=ev.map(e=>`<div class="ev">
  <time>${esc((e.at||'').slice(11,16))}</time>
  <span class="k">${esc(e.agent||e.kind)}</span>
  <span style="flex:1">${esc((e.message||'').slice(0,110))}</span>
  <span class="d">${e.dur?esc(e.dur):''}</span></div>`).join('');
}

function tokens(s){
 const u=s.usage||{}, el=$('#tok');
 if(!u.available){el.innerHTML=`<div class="note">${esc(u.note||'chua co so lieu')}</div>`;return}
 const t=u.total||{};
 el.innerHTML=`<div class="tok">
  <div><b>${fmt(t.total_tokens)}</b><span>token</span></div>
  <div><b>$${(t.cost||0).toFixed(2)}</b><span>uoc tinh</span></div>
  <div><b>${t.turns||0}</b><span>luot goi</span></div></div>
  <div class="note">cache doc ${fmt(t.cache_read)} - phan re nhat.
  ${t.total_tokens>400000?'<br><b>Phien dai roi, nen cat phien moi cho task sau.</b>':''}</div>`;
}

function controls(s){
 if(busy)return;
 const a=s.auto_mode||{};
 $('#auto').checked=!!a.enabled;
 $('#mt').value=String(a.max_tier??1);
 $('#autolbl').textContent=a.enabled?'Bat':'Tat';
 $('#autonote').textContent=a.enabled
  ?`Task tu Tier ${a.max_tier} tro xuong tu chay tiep.`
  :'Moi task xong deu dung lai cho ban.';
 $('#warn').style.display=(a.enabled&&a.max_tier>=2)?'block':'none';
 $('#mode').value=s.approve_mode||'queue';
 $('#modenote').textContent=MODENOTE[s.approve_mode||'queue']
  +(s.approve_mode==='spawn'&&!s.spawn_allowed?' CHUA BAT - khoi dong lai server voi --allow-spawn.':'');
}

async function refresh(){
 try{
  const s=await api('/api/state');
  $('#runid').textContent=s.run_id||'-';
  const d=s.tasks.filter(t=>t.status==='done').length;
  $('#c1').textContent=d;
  $('#c2').textContent=s.tasks.length-d;
  $('#c3').textContent=s.tasks.filter(t=>['gate_failed','review_failed'].includes(t.status)).length;
  band(s);tasks(s);dep(s);events(s);tokens(s);controls(s);
 }catch(e){}
}

document.addEventListener('click',async e=>{
 const tg=e.target.closest('[data-toggle]');
 if(tg){const id=tg.dataset.toggle;open.has(id)?open.delete(id):open.add(id);
  document.querySelector(`.task[data-t="${id}"]`)?.classList.toggle('open');return}

 const snd=e.target.closest('[data-send]');
 if(snd){const id=snd.dataset.send;
  const ta=document.querySelector(`[data-fb="${id}"]`);
  if(!ta?.value.trim())return;
  snd.disabled=true;snd.textContent='Da gui';
  await api('/api/feedback',{task_id:id,text:ta.value});
  ta.value='';setTimeout(()=>{snd.disabled=false;snd.textContent='Gui nhan xet';refresh()},900);
  return}

 const b=e.target.closest('[data-do]');
 if(!b)return;
 b.disabled=true;
 const r=await api('/api/decide',{task_id:b.dataset.id,decision:b.dataset.do});
 if(r.message)alert(r.message);
 refresh();
});

$('#mode').addEventListener('change',async()=>{
 busy=true;await api('/api/mode',{mode:$('#mode').value});busy=false;refresh()});
const pushAuto=async()=>{busy=true;
 await api('/api/auto',{enabled:$('#auto').checked,max_tier:+$('#mt').value});
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
        return "Khong tim thay lenh 'claude' trong PATH."
    prompt = (f"Nguoi dung vua duyet task {task_id} tren bang dieu khien. "
              f"Chay `python scripts/flow.py inbox` roi lam tiep task do.")

    def run() -> None:
        try:
            subprocess.run([exe, "-p", prompt], cwd=fc.ROOT, timeout=3600,
                           capture_output=True, check=False)
            fc.log_event("spawn_done", f"phien moi cho {task_id} ket thuc", task_id=task_id)
        except Exception as e:  # noqa: BLE001
            fc.log_event("spawn_failed", str(e)[:200], task_id=task_id)

    threading.Thread(target=run, daemon=True).start()
    fc.log_event("spawn", f"khoi dong phien Claude moi cho {task_id}", task_id=task_id)
    return f"Da khoi dong phien Claude moi cho {task_id}. Ket qua se hien o nhat ky."


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
            self._json({"error": "not found"}, 404)

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
                idx = rv.lower().rfind("## ket luan")
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
            self._json({"error": "json khong hop le"}, 400)
            return

        cfg = fc.load_config()

        if self.path == "/api/decide":
            tid, dec = body.get("task_id"), body.get("decision")
            if dec not in ("approved", "rejected") or not tid:
                self._json({"error": "thieu task_id hoac decision"}, 400)
                return

            mode = cfg.get("approve_mode", "queue")
            msg = ""

            if mode == "direct":
                # ghi thang phieu duyet: agent dang chay `flow wait` se thay ngay
                fc.decide_approval(tid, dec, body.get("note", ""))
                self._sync_task(tid, dec)
                msg = "Da ghi quyet dinh. Agent dang cho se thay trong vai giay."
            else:
                # hang doi: Claude doc o dau luot sau
                fc.queue_push("decision", {"task_id": tid, "decision": dec,
                                           "note": body.get("note", "")})
                fc.decide_approval(tid, dec, body.get("note", ""))
                self._sync_task(tid, dec)
                msg = ("Da ghi vao hang doi. Quay lai chat go \"tiep\" de Claude chay tiep."
                       if mode == "queue" else "")
                if mode == "spawn" and dec == "approved":
                    msg = _spawn_claude(tid) if ALLOW_SPAWN else (
                        "Che do tu khoi dong chua bat. Khoi dong lai server voi --allow-spawn, "
                        "hoac quay lai chat go \"tiep\".")

            self._json({"ok": True, "message": msg})

        elif self.path == "/api/feedback":
            tid, text = body.get("task_id"), (body.get("text") or "").strip()
            if not (tid and text):
                self._json({"error": "thieu task_id hoac text"}, 400)
                return
            fc.queue_push("feedback", {"task_id": tid, "text": text})
            try:
                td = fc.run_dir() / "tasks" / tid
                td.mkdir(parents=True, exist_ok=True)
                with (td / "feedback.md").open("a", encoding="utf-8") as f:
                    f.write(f"\n## Nhan xet {fc.now()}\n\n{text}\n")
                fc.log_event("feedback", text[:200], task_id=tid)
            except SystemExit:
                pass
            self._json({"ok": True})

        elif self.path == "/api/mode":
            m = body.get("mode")
            if m not in ("queue", "direct", "spawn"):
                self._json({"error": "mode khong hop le"}, 400)
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
                         f"{'bat' if cfg['auto_mode']['enabled'] else 'tat'}, "
                         f"max_tier={cfg['auto_mode']['max_tier']} (tu web)")
            self._json({"ok": True, "auto_mode": cfg["auto_mode"]})

        else:
            self._json({"error": "not found"}, 404)

    def _sync_task(self, tid: str, dec: str) -> None:
        try:
            data = fc.load_tasks()
            t = fc.find_task(data, tid)
            if t:
                t["status"] = "pending" if dec == "approved" else "skipped"
                fc.save_tasks(data)
        except SystemExit:
            pass


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
