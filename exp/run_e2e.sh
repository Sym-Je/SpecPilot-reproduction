#!/usr/bin/env bash
# 一条命令跑完短期实验：G4 forcing 自检 → 三轮 RSI 闭环 → 账本校验。
#
# 用法：
#   bash exp/run_e2e.sh            # 归档旧账本后从头跑
#   KEEP=1 bash exp/run_e2e.sh     # 保留旧账本（记忆生效，机制会被跳过）
#
# 环境：SPECPILOT_PYTHON 指定解释器（默认用 alice-sglang 的 python）。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${SPECPILOT_PYTHON:-/gpfs/users/jixinpeng/miniconda3/envs/alice-sglang/bin/python}"
ROUNDS="${ROUNDS:-3}"
MAXNEW="${MAXNEW:-256}"
cd "$ROOT"

if [[ "${KEEP:-0}" != "1" ]]; then
  STAMP=$(date +%Y%m%d-%H%M%S)
  mkdir -p ledger/archive memory/archive
  [[ -f ledger/rsi.jsonl ]] && mv ledger/rsi.jsonl "ledger/archive/rsi-$STAMP.jsonl"
  [[ -f memory/entries/rsi.json ]] && mv memory/entries/rsi.json "memory/archive/rsi-$STAMP.json"
  echo "[e2e] 旧账本归档为 $STAMP"
fi
mkdir -p ledger memory/entries

echo "=== G4: token forcing 自检 ==="
"$PY" gates/g4_forcing.py

echo
echo "=== RSI: ${ROUNDS} 轮闭环 ==="
"$PY" orchestrator/loop.py --rounds "$ROUNDS" --max-new "$MAXNEW"

echo
echo "=== 账本校验 ==="
"$PY" - <<'PY'
import json, sys
sys.path.insert(0, ".")
from controller.ledger import Ledger
L = Ledger("ledger/rsi.jsonl")
probs = L.verify()
recs = L.records()
kinds = [r["kind"] for r in recs]
print(f"records={len(recs)} kinds={ {k: kinds.count(k) for k in set(kinds)} }")
print("hash chain:", "OK" if not probs else probs)
sys.exit(0 if not probs else 1)
PY
echo
echo "=== 记忆 ==="
"$PY" -c "import json;e=json.load(open('memory/entries/rsi.json'));print(json.dumps([{k:v for k,v in x.items() if k in ('mechanism','status','gain','lower_gain','forcing_lossless')} for x in e],indent=2,ensure_ascii=False))"
