#!/usr/bin/env bash
# Cong kiem tra bang may. Day la cong that su, khong phai y kien cua LLM.
# In ra JSON o dong cuoi cung de flow.py doc.
#
# Tu nhan dien loai project. Muon chi dinh tay thi sua "gates" trong .flow/config.json
# hoac dat bien: FLOW_TEST_CMD, FLOW_LINT_CMD, FLOW_TYPECHECK_CMD, FLOW_BUILD_CMD

set -uo pipefail
# Phai chay trong thu muc DU AN. Script co the nam ngoai du an (che do plugin).
cd "${FLOW_PROJECT_DIR:-$PWD}" || exit 1

LOGDIR="$(mktemp -d)"
trap 'rm -rf "$LOGDIR"' EXIT

PASSED=()
FAILED=()
SKIPPED=()

has() { command -v "$1" >/dev/null 2>&1; }

pkg_has_script() {
  [ -f package.json ] || return 1
  grep -qE "\"$1\"[[:space:]]*:" package.json
}

run_step() {
  local name="$1" cmd="$2"
  # Cat khoang trang hai dau: lenh rong hoac chi co khoang trang la BO QUA,
  # khong duoc tinh la mot buoc kiem tra da chay va dat.
  cmd="$(printf '%s' "$cmd" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')"
  if [ -z "$cmd" ]; then
    SKIPPED+=("$name")
    return 0
  fi
  echo "==> $name: $cmd" >&2
  # Bat buoc chay trong subshell: lenh con co the chua 'exit', 'set -e',
  # 'cd', hoac thay doi bien - khong duoc de no giet hoac lam lech gate.sh.
  if ( eval "$cmd" ) >"$LOGDIR/$name.log" 2>&1; then
    PASSED+=("$name")
  else
    FAILED+=("$name")
  fi
}

# --- chon runner cho project JS/TS -----------------------------------------
JS_RUN=""
if [ -f package.json ]; then
  if [ -f pnpm-lock.yaml ] && has pnpm; then JS_RUN="pnpm"
  elif [ -f yarn.lock ] && has yarn; then JS_RUN="yarn"
  elif has npm; then JS_RUN="npm run"
  fi
fi

# --- lint -------------------------------------------------------------------
LINT="${FLOW_LINT_CMD:-}"
if [ -z "$LINT" ]; then
  if [ -n "$JS_RUN" ] && pkg_has_script lint; then LINT="$JS_RUN lint"
  elif has ruff && { [ -f pyproject.toml ] || [ -f ruff.toml ]; }; then LINT="ruff check ."
  elif has golangci-lint && [ -f go.mod ]; then LINT="golangci-lint run"
  elif [ -f Cargo.toml ] && has cargo; then LINT="cargo clippy -- -D warnings"
  fi
fi
run_step lint "$LINT"

# --- typecheck --------------------------------------------------------------
TC="${FLOW_TYPECHECK_CMD:-}"
if [ -z "$TC" ]; then
  if [ -n "$JS_RUN" ] && pkg_has_script typecheck; then TC="$JS_RUN typecheck"
  elif [ -f tsconfig.json ] && has npx; then TC="npx --no-install tsc --noEmit"
  elif has mypy && [ -f pyproject.toml ] && grep -q "mypy" pyproject.toml 2>/dev/null; then TC="mypy ."
  elif [ -f go.mod ] && has go; then TC="go vet ./..."
  fi
fi
run_step typecheck "$TC"

# --- test -------------------------------------------------------------------
TEST="${FLOW_TEST_CMD:-}"
if [ -z "$TEST" ]; then
  if [ -n "$JS_RUN" ] && pkg_has_script test; then TEST="$JS_RUN test"
  elif has pytest && { [ -d tests ] || [ -d test ] || [ -f pytest.ini ] || [ -f pyproject.toml ]; }; then TEST="pytest -q"
  elif [ -f go.mod ] && has go; then TEST="go test ./..."
  elif [ -f Cargo.toml ] && has cargo; then TEST="cargo test"
  fi
fi
run_step test "$TEST"

# --- build ------------------------------------------------------------------
BUILD="${FLOW_BUILD_CMD:-}"
if [ -z "$BUILD" ]; then
  if [ -n "$JS_RUN" ] && pkg_has_script build; then BUILD="$JS_RUN build"
  elif [ -f go.mod ] && has go; then BUILD="go build ./..."
  elif [ -f Cargo.toml ] && has cargo; then BUILD="cargo build"
  fi
fi
run_step build "$BUILD"

# --- ket qua JSON -----------------------------------------------------------
json_array() {
  local first=1
  printf '['
  for x in "$@"; do
    [ $first -eq 1 ] || printf ','
    printf '"%s"' "$x"
    first=0
  done
  printf ']'
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()[-4000:]))' 2>/dev/null \
    || printf '""'
}

{
  printf '{'
  printf '"ok":%s,' "$([ ${#FAILED[@]} -eq 0 ] && echo true || echo false)"
  # Khong co kiem tra nao chay khong co nghia la dat. Verifier phai biet dieu nay.
  printf '"no_checks_ran":%s,' "$([ ${#PASSED[@]} -eq 0 ] && echo true || echo false)"
  printf '"passed":%s,' "$(json_array "${PASSED[@]+"${PASSED[@]}"}")"
  printf '"failed":%s,' "$(json_array "${FAILED[@]+"${FAILED[@]}"}")"
  printf '"skipped":%s,' "$(json_array "${SKIPPED[@]+"${SKIPPED[@]}"}")"
  printf '"logs":{'
  first=1
  for name in "${FAILED[@]+"${FAILED[@]}"}"; do
    [ $first -eq 1 ] || printf ','
    printf '"%s":%s' "$name" "$(json_escape < "$LOGDIR/$name.log")"
    first=0
  done
  printf '}}'
  printf '\n'
}

[ ${#FAILED[@]} -eq 0 ]
