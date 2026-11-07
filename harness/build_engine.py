#!/usr/bin/env python3
"""组装某个 setting 的 stock / final 派生引擎树（P1）。

    python harness/build_engine.py SETTING {stock,final} OUT_DIR
    python harness/build_engine.py h100_c1_qwen38-27b_dflash2 stock /tmp/e  # 组装 + 打印 tree sha

产出的树是 `<OUT_DIR>/{python,lab}`：
  python/  ← 上游 `python/`（stock 引擎，**只读复制，从不修改**）
  lab/     ← 上游 `research/dflash_lab`
  + 若 config.dspark: 叠加 `overlays/dspark_stock`
  + 若 kind=final:    叠加 `settings/<setting>/files`
最后写 `TREE_SHA`，内容是 canonical content hash：

    sha256(json({relpath: sha256(file)}, sort_keys, separators=(',',':')))

**两个硬性保证**（由 `gates/g6_engine_build.py` 验收）：
  1. 同一输入构建两次 → 同一个 TREE_SHA（可重现，缓存才能按它分桶）
  2. kind=stock 时 python/ 与上游逐文件 sha256 相同（默认值真的复现 stock，
     对应 AGENTS.md 铁律 3）

跳过 `__pycache__` / `*.pyc` / `.git` 等运行时产物：上游树被 PYTHONPATH 直接 import 过，
里面已经有 .pyc，不排除会让哈希随"谁 import 过"而变。

注意：这里只组装**文件**。final 的语义开关（`config.final.env` 里 46 个 SPECPILOT_*）
和 block size 由 `harness/sglang/serve.sh` 用环境变量注入，不在树上。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = Path("/gpfs/users/jixinpeng/SpecDec/upstream/SpecPilot-main")
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", "build", "dist", ".mypy_cache", ".ruff_cache"}
SKIP_SUFFIX = (".pyc", ".pyo", ".egg-info")


def _skip(rel: Path) -> bool:
    return any(p in SKIP_DIRS or p.endswith(SKIP_SUFFIX) for p in rel.parts)


def _sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_sha(root: Path) -> str:
    """canonical content hash：路径→文件 sha256 的排序 JSON 再取 sha256。"""
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if _skip(rel) or rel.name == "TREE_SHA":
            continue
        if p.is_symlink():
            out[str(rel)] = "symlink:" + str(p.readlink())
        elif p.is_file():
            out[str(rel)] = _sha_file(p)
    blob = json.dumps(out, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def overlay(src: Path, dst: Path, into: Path | None = None) -> int:
    """把 src 下的文件按相对路径覆盖到 dst。返回覆盖的文件数。"""
    n = 0
    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src)
        if not p.is_file() or _skip(rel):
            continue
        t = (into / rel) if into else (dst / rel)
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, t)
        t.chmod(0o755 if p.stat().st_mode & 0o100 else 0o644)
        n += 1
    return n


def settings_available() -> list[str]:
    return sorted(p.parent.name for p in (UPSTREAM / "settings").glob("*/config.json"))


def build(setting: str, kind: str, out: Path) -> dict:
    if kind not in ("stock", "final"):
        raise SystemExit(f"kind must be stock|final, got {kind!r}")
    if not UPSTREAM.is_dir():
        raise SystemExit(f"upstream tree not found: {UPSTREAM}")
    cfg_path = UPSTREAM / "settings" / setting / "config.json"
    if not cfg_path.exists():
        raise SystemExit(f"unknown setting {setting!r}; choose from: {', '.join(settings_available())}")
    cfg = json.loads(cfg_path.read_text())

    # 覆盖层路径相对 `files/`，但内容是 `python/...` 同构的，直接叠到 out/ 上
    out = out.resolve()
    if out.exists():
        raise SystemExit(f"{out} exists; remove it or pick a fresh directory")
    out.mkdir(parents=True)

    ignore = shutil.ignore_patterns(*SKIP_DIRS, "*.pyc", "*.pyo")
    shutil.copytree(UPSTREAM / "python", out / "python", symlinks=True, ignore=ignore)
    shutil.copytree(UPSTREAM / "research" / "dflash_lab", out / "lab", symlinks=True, ignore=ignore)

    n_dspark = n_final = 0
    if cfg.get("dspark"):
        n_dspark = overlay(UPSTREAM / "overlays" / "dspark_stock", out)
    if kind == "final":
        n_final = overlay(UPSTREAM / "settings" / setting / "files", out)

    sha = tree_sha(out)
    (out / "TREE_SHA").write_text(sha + "\n")
    return {"setting": setting, "kind": kind, "out": str(out), "tree_sha": sha,
            "dspark_overlay_files": n_dspark, "final_overlay_files": n_final,
            "block_size": cfg["stock"]["block_size"] if kind == "stock" else cfg["final"]["block_size"],
            "final_name": cfg["final"]["name"] if kind == "final" else None}


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[2] not in ("stock", "final"):
        print(__doc__)
        return 2
    info = build(argv[1], argv[2], Path(argv[3]))
    print(f"{info['setting']} {info['kind']}: {info['out']} "
          f"(tree sha {info['tree_sha']})")
    print(json.dumps({k: v for k, v in info.items() if k != "out"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
