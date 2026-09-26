#!/usr/bin/env bash
# Tu kiem tra AI Factory: dung mot repo gia trong thu muc tam, chay het
# day chuyen, xac minh hang rao tier chan dung cho.
#
#   bash scripts/selftest.sh
#
# Khong dong gi vao repo that.

set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
LAB="$(mktemp -d)"
trap 'rm -rf "$LAB"' EXIT

PASS=0
FAIL=0
G=$'\033[32m'; R=$'\033[31m'; D=$'\033[2m'; O=$'\033[0m'

check() {
  local label="$1" want="$2" got="$3"
  if [ "$want" = "$got" ]; then
    printf '  %sdat%s   %s\n' "$G" "$O" "$label"
    PASS=$((PASS+1))
  else
    printf '  %struot%s %s %s(mong %s, nhan %s)%s\n' "$R" "$O" "$label" "$D" "$want" "$got" "$O"
    FAIL=$((FAIL+1))
  fi
}

# --- dung phong thi nghiem ---------------------------------------------------
for d in scripts hooks profiles skills agents; do cp -r "$SRC/$d" "$LAB/"; done
cd "$LAB"
rm -rf scripts/__pycache__
git init -q 2>/dev/null
git config user.email "selftest@local" 2>/dev/null
git config user.name "selftest" 2>/dev/null
echo "# lab" > README.md && git add -A && git commit -qm init 2>/dev/null

export FLOW_PROJECT_DIR="$LAB"
export FLOW_TEST_CMD="echo '3 tests passed'"
python3 "$SRC/scripts/flow.py" init --dir "$LAB" >/dev/null 2>&1
unset FLOW_SMTP_USER FLOW_SMTP_PASS FLOW_WEBHOOK_URL FLOW_TELEGRAM_TOKEN 2>/dev/null

F() { python3 scripts/flow.py "$@" 2>/dev/null; }
hook() { printf '%s' "$1" | python3 hooks/tier_guard.py >/dev/null 2>&1; echo $?; }
tier_of() { F tier "$@" | python3 -c 'import json,sys;print(json.load(sys.stdin)["tier"])' 2>/dev/null; }

echo
echo "1. Phan cap rui ro"
check "file thuong la Tier 1"            1 "$(tier_of --paths src/utils/format.ts)"
check "file test la Tier 0"              0 "$(tier_of --paths src/a.test.ts)"
check "auth la Tier 2"                   2 "$(tier_of --paths src/auth/session.ts)"
check "migration la Tier 2"              2 "$(tier_of --paths migrations/003.sql)"
check "cai dependency la Tier 2"         2 "$(tier_of --command 'npm install redis')"
check "git push la Tier 2"               2 "$(tier_of --command 'git push origin main')"
check "chay test la Tier 0"              0 "$(tier_of --command 'pytest -q')"
check "file test khong keo tut ca task"  1 "$(tier_of --paths src/a.ts src/a.test.ts)"

echo
echo "2. Nap ke hoach"
F start "tu kiem tra" >/dev/null
cat > "$LAB/draft.json" <<'EOF'
{"tasks":[
 {"id":"T1","title":"Them ham tien ich","files":["src/util.ts"],"depends_on":[],"acceptance":["test pass"]},
 {"id":"T2","title":"Doi schema users","files":["migrations/010_users.sql"],"depends_on":["T1"],"tier":0,"acceptance":["migration chay"]}
]}
EOF
F plan-import "$LAB/draft.json" >/dev/null
T2TIER=$(F status --json | python3 -c 'import json,sys;print([t["tier"] for t in json.load(sys.stdin)["tasks"] if t["id"]=="T2"][0])')
check "he thong ghi de tier planner tu cham" 2 "$T2TIER"

echo
echo "3. Hang rao chan"
F claim T1 >/dev/null
check "ghi file thuong: cho qua"    0 "$(hook '{"tool_name":"Write","tool_input":{"file_path":"src/util.ts"}}')"
check "ghi migration: chan"         2 "$(hook '{"tool_name":"Write","tool_input":{"file_path":"migrations/010_users.sql"}}')"
check "npm install: chan"           2 "$(hook '{"tool_name":"Bash","tool_input":{"command":"npm install redis"}}')"
check "rm -rf: chan"                2 "$(hook '{"tool_name":"Bash","tool_input":{"command":"rm -rf build"}}')"
check "doc file: khong dinh den"    0 "$(hook '{"tool_name":"Read","tool_input":{"file_path":"migrations/010_users.sql"}}')"

echo
echo "4. Pham vi phieu duyet"
F claim T2 >/dev/null
F approve T2 --note "selftest" >/dev/null
python3 -c "import sys;sys.path.insert(0,'$SRC/scripts');import flow_core as fc;fc.set_current(fc.get_current()['run_id'],'T2')"
check "viec da duyet: cho qua"              0 "$(hook '{"tool_name":"Write","tool_input":{"file_path":"migrations/010_users.sql"}}')"
check "migration KHAC: van chan"            2 "$(hook '{"tool_name":"Write","tool_input":{"file_path":"migrations/011_khac.sql"}}')"
check "duyet migration khong mo duong push" 2 "$(hook '{"tool_name":"Bash","tool_input":{"command":"git push"}}')"

echo
echo "5. Che do tu dong ton trong nguong"
F auto on --max-tier 1 >/dev/null
python3 -c "import sys;sys.path.insert(0,'$SRC/scripts');import flow_core as fc;fc.set_current(fc.get_current()['run_id'],'T9')"
check "auto bat, Tier 2 van chan" 2 "$(hook '{"tool_name":"Bash","tool_input":{"command":"npm install redis"}}')"
F auto on --max-tier 2 >/dev/null
check "auto max-tier 2, cho qua"  0 "$(hook '{"tool_name":"Bash","tool_input":{"command":"npm install redis"}}')"
F auto off >/dev/null

echo
echo "6. Cong kiem tra bang may"
GATE_OK=$(bash "$SRC/scripts/gate.sh" 2>/dev/null | tail -1 | python3 -c 'import json,sys;print(json.load(sys.stdin)["ok"])')
check "cong chay va tra JSON" "True" "$GATE_OK"
GATE_BAD=$(FLOW_TEST_CMD="echo loi; exit 1" bash "$SRC/scripts/gate.sh" 2>/dev/null | tail -1 | python3 -c 'import json,sys;print(json.load(sys.stdin)["ok"])')
check "test fail thi cong truot" "False" "$GATE_BAD"
NOCHK=$(FLOW_TEST_CMD=" " bash "$SRC/scripts/gate.sh" 2>/dev/null | tail -1 | python3 -c 'import json,sys;print(json.load(sys.stdin)["no_checks_ran"])')
check "bao khi khong co kiem tra nao" "True" "$NOCHK"

echo
echo "7. Vong khep kin"
python3 -c "import sys;sys.path.insert(0,'$SRC/scripts');import flow_core as fc;fc.set_current(fc.get_current()['run_id'],'T1')"
mkdir -p src && echo 'export const x = 1;' > src/util.ts
F done T1 --commit >/dev/null 2>&1
ST=$(F status --json | python3 -c 'import json,sys;print([t["status"] for t in json.load(sys.stdin)["tasks"] if t["id"]=="T1"][0])')
check "chua qua cong thi khong duoc danh dau xong" "running" "$ST"
F gate T1 >/dev/null
F done T1 --commit >/dev/null
ST=$(F status --json | python3 -c 'import json,sys;print([t["status"] for t in json.load(sys.stdin)["tasks"] if t["id"]=="T1"][0])')
check "qua cong roi thi xong duoc" "done" "$ST"
check "co commit that" "1" "$(git log --oneline 2>/dev/null | grep -c 'T1:')"

echo
echo "8. Dashboard"
# Cong ngau nhien con trong: khong dung may chu cu con song o cong mac dinh.
PORT=$(python3 -c "import json,socket
s=socket.socket();s.bind(('127.0.0.1',0));p=s.getsockname()[1];s.close()
c=json.load(open('.flow/config.json'));c.setdefault('dashboard',{})['port']=p
json.dump(c,open('.flow/config.json','w'),ensure_ascii=False,indent=2);print(p)")
# Python tu ghi PID that cua no: tren Git Bash $! la PID cua MSYS/shim,
# kill vao do khong giet duoc python.exe.
DPIDF="$LAB/dashboard.pid"
python3 -c "import os,runpy,sys
open(sys.argv[1],'w').write(str(os.getpid()))
sys.argv=[sys.argv[2],'--no-open'];runpy.run_path(sys.argv[0],run_name='__main__')" \
  "$DPIDF" "$SRC/scripts/dashboard.py" >/dev/null 2>&1 &
DPID=$!
stop_dashboard() {
  local pid; pid=$(cat "$DPIDF" 2>/dev/null)
  if [ -n "$pid" ]; then
    if command -v taskkill >/dev/null 2>&1; then
      taskkill //F //PID "$pid" >/dev/null 2>&1
    else
      kill "$pid" 2>/dev/null
    fi
  fi
  kill "$DPID" 2>/dev/null; wait "$DPID" 2>/dev/null
  rm -f "$DPIDF"
}
trap 'stop_dashboard; rm -rf "$LAB"' EXIT
for _ in $(seq 1 50); do
  curl -s -o /dev/null "http://127.0.0.1:$PORT/" 2>/dev/null && break
  sleep 0.2
done
CODE=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/" 2>/dev/null)
check "trang chinh tra ve 200" "200" "${CODE:-000}"
NT=$(curl -s "http://127.0.0.1:$PORT/api/state" 2>/dev/null | python3 -c 'import json,sys;print(len(json.load(sys.stdin)["tasks"]))' 2>/dev/null || echo x)
check "API tra ve du task" "2" "$NT"
stop_dashboard
trap 'rm -rf "$LAB"' EXIT

echo
echo "9. Tiep tuc run cu"
RID=$(python3 -c "import json;print(json.load(open('.flow/current.json'))['run_id'])")
check "resume doc lai duoc run" "$RID" "$(F resume "$RID" | python3 -c 'import json,sys;print(json.load(sys.stdin)["run_id"])')"
check "runs liet ke duoc" "1" "$(F runs | grep -c "$RID")"

echo
echo "10. Chon tuyen"
route(){ F route "$@" | python3 -c 'import json,sys;print(json.load(sys.stdin)["tuyen"])' 2>/dev/null; }
RID=$(python3 -c "import json;print(json.load(open('.flow/current.json'))['run_id'])")
check "chua khao sat -> tuyen Du"      "Du"       "$(route --files src/a.ts)"
echo "# khao sat" > ".flow/runs/$RID/01-research.md"
check "1 file Tier 0 -> Nhanh"         "Nhanh"    "$(route --files src/a.test.ts)"
check "3 file Tier 1 -> Gon"           "Gon"      "$(route --files src/a.ts src/b.ts src/c.ts)"
check "Tier 2 -> Du"                   "Du"       "$(route --files migrations/1.sql)"
check "chi muon hieu -> Khao sat"      "Khao sat" "$(route --explore-only)"
check "6 file -> Du"                   "Du"       "$(route --files a.ts b.ts c.ts d.ts e.ts f.ts)"

echo
echo "11. Hang doi duyet (bam luc Claude khong chay)"
python3 -c "import sys;sys.path.insert(0,'$SRC/scripts');import flow_core as fc
fc.queue_push('decision',{'task_id':'T2','decision':'approved','note':'ok'})
fc.queue_push('feedback',{'task_id':'T2','text':'nho them index'})" 2>/dev/null
IB=$(F inbox)
check "inbox ap dung quyet dinh" "1" "$(echo "$IB" | grep -c '"decision": "approved"')"
check "inbox ghi nhan xet"       "1" "$(echo "$IB" | grep -c 'feedback')"
check "hang doi da rong sau khi doc" "0" "$(ls .flow/queue/*.json 2>/dev/null | wc -l | tr -d ' ')"
check "nhan xet vao dung file"   "1" "$(grep -c 'nho them index' ".flow/runs/$RID/tasks/T2/feedback.md" 2>/dev/null || echo 0)"

echo
echo "12. Profile va ban giao"
F profile greenfield >/dev/null
check "greenfield: migration ha xuong Tier 1" "1" "$(tier_of --paths migrations/1.sql)"
check "greenfield: git push van Tier 2"       "2" "$(tier_of --command 'git push')"
F profile production >/dev/null
check "production: migration ve Tier 2"       "2" "$(tier_of --paths migrations/1.sql)"
F hand-off T1 >/dev/null
check "co file ban giao" "1" "$([ -f ".flow/runs/$RID/handoff.md" ] && echo 1 || echo 0)"
check "ban giao chi ra task ke tiep" "1" "$(grep -c 'Ke tiep' ".flow/runs/$RID/handoff.md" 2>/dev/null || echo 0)"

echo
echo "13. Che do plugin (script nam NGOAI du an)"
LAB2="$(mktemp -d)"; cd "$LAB2"; git init -q 2>/dev/null
git config user.email s@l 2>/dev/null; git config user.name s 2>/dev/null
unset FLOW_PROJECT_DIR
check "du an chua init: khong chan (dung y do)" 0 \
  "$(printf '{"tool_name":"Bash","tool_input":{"command":"rm -rf x"}}' | python3 "$SRC/hooks/tier_guard.py" >/dev/null 2>&1; echo $?)"
python3 "$SRC/scripts/flow.py" init >/dev/null 2>&1
check "init tao duoc .flow/config.json" 1 "$([ -f .flow/config.json ] && echo 1 || echo 0)"
check "init tao duoc cau noi .flow/flow" 1 "$([ -x .flow/flow ] && echo 1 || echo 0)"
check "cau noi chay duoc" 1 "$(./.flow/flow tier --paths a.ts >/dev/null 2>&1 && echo 1 || echo 0)"
check "init them vao .gitignore" 1 "$(grep -c '.flow/runs/' .gitignore 2>/dev/null || echo 0)"
check "da init, chua co run: VAN chan Tier 2" 2 \
  "$(printf '{"tool_name":"Bash","tool_input":{"command":"git push"}}' | python3 "$SRC/hooks/tier_guard.py" >/dev/null 2>&1; echo $?)"
check "da init: file thuong cho qua" 0 \
  "$(printf '{"tool_name":"Write","tool_input":{"file_path":"src/a.ts"}}' | python3 "$SRC/hooks/tier_guard.py" >/dev/null 2>&1; echo $?)"
check "init lan 2 khong ghi de" 1 \
  "$(python3 "$SRC/scripts/flow.py" init 2>/dev/null | grep -c da_khoi_tao)"
cd "$LAB"; rm -rf "$LAB2"; export FLOW_PROJECT_DIR="$LAB"

echo
echo "--------------------------------------------"
if [ "$FAIL" -eq 0 ]; then
  printf '%sTat ca %d muc deu dat.%s Bo nay chay duoc tren may ban.\n' "$G" "$PASS" "$O"
  exit 0
else
  printf '%s%d muc truot%s tren tong %d.\n' "$R" "$FAIL" "$O" "$((PASS+FAIL))"
  exit 1
fi
