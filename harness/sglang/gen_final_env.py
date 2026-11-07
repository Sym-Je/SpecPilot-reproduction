#!/usr/bin/env python3
"""从 settings/<setting>/config.json 的 `final` 段生成 shell export 文件。

为什么不让 p3_pair.sh 手抄 46 个 SPECPILOT_*：抄错一个不存在变量的值不会被任何东西报错，
只会让 final 臂悄悄退回 stock 行为，然后"复现失败"却查不出原因。config.json 是唯一真源。

输出（默认 $SP_DATA/work/env/<setting>-final.env）**不进 git**：它是派生文件，
且必须能和 config.json 的 sha256 对上，否则说明有人手改过。

用法:
  python harness/sglang/gen_final_env.py                     # 打印到 stdout
  python harness/sglang/gen_final_env.py --check             # 只校验已生成的与 config 一致
  python harness/sglang/gen_final_env.py --out FILE
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTING = "h100_c1_qwen38-27b_dflash2"


def config_path(setting: str) -> Path:
    p = ROOT / "assets" / "upstream" / "configs" / setting / "config.json"
    if not p.exists():
        raise SystemExit(f"no config for setting {setting!r}: {p}")
    return p


def render(cfg: dict, tree_sha: str) -> str:
    f = cfg["final"]
    lines = [
        "# 自动生成，勿手改：python harness/sglang/gen_final_env.py",
        f"# setting={cfg['setting']} candidate={f['name']} block={f['block_size']}",
    ]
    env = dict(sorted(f["env"].items()))
    env["SPECPILOT_BLOCK_SIZE"] = str(f["block_size"])
    env["XINFER_CANDIDATE"] = f["name"]
    if tree_sha:
        env["SP_TREE_SHA"] = tree_sha
    for k, v in env.items():
        lines.append(f"export {k}={shlex.quote(str(v))}")
    launch = f.get("launch_args") or []
    lines.append("SP_LAUNCH_ARGS=(" + " ".join(shlex.quote(x) for x in launch) + ")")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setting", default=os.environ.get("SP_SETTING", DEFAULT_SETTING))
    ap.add_argument("--out", default=None)
    ap.add_argument("--check", action="store_true", help="只校验已生成的文件与 config 一致")
    ap.add_argument("--tree-sha", default=os.environ.get("SP_TREE_SHA", ""))
    a = ap.parse_args()

    cp = config_path(a.setting)
    raw = cp.read_bytes()
    cfg = json.loads(raw)
    if "final" not in cfg:
        raise SystemExit(f"{cp} has no 'final' section (stock-only setting)")
    text = render(cfg, a.tree_sha)
    stamp = hashlib.sha256(raw).hexdigest()

    out = Path(a.out) if a.out else Path(
        os.environ.get("SPECPILOT_DATA", "/gpfs/users/jixinpeng/specpilot_data")
    ) / "work" / "env" / f"{a.setting}-final.env"

    if a.check:
        if not out.exists():
            raise SystemExit(f"REJECT: {out} 不存在，先跑不带 --check 的生成")
        # 只比 export 行内容，忽略注释与 SP_TREE_SHA（它随派生树变化）
        def body(t):
            return [ln for ln in t.splitlines()
                    if ln.startswith("export ") and not ln.startswith("export SP_TREE_SHA=")]
        if body(text) != body(out.read_text()):
            raise SystemExit(f"REJECT: {out} 与 {cp} 不一致（config 改过但没重新生成？）")
        print(f"ACCEPT: {out} 与 config 一致（config sha256={stamp[:16]}，"
              f"{len(cfg['final']['env'])} 个 SPECPILOT_*）")
        return

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"wrote {out}  ({len(cfg['final']['env'])} env + block={cfg['final']['block_size']}, "
          f"config sha256={stamp[:16]})", file=sys.stderr)


if __name__ == "__main__":
    main()
