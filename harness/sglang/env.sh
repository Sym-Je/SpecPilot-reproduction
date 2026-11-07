#!/usr/bin/env bash
# SpecPilot × SGLang v0.5.20 环境约定。所有启动/测量脚本都 source 这个文件。
#
# 关键事实（本机 + NorthJob 通用）：
#   1. 引擎来自 **派生树**（harness/build_engine.py 组装），靠 PYTHONPATH 覆盖 pip 包；
#      未构建时回落到上游只读树（= stock 行为）。
#   2. torch 2.13+cu130 需要 R580 驱动；本机是 535，必须用 forward-compat libcuda；
#   3. Triton/JIT 需要 C 编译器；系统没有 gcc，用 conda-forge 装的那个；
#   4. JIT 链接 -lcudart 需要 nvidia/cu13/lib64/libcudart.so 软链接（setup_env.sh 同款）。
set -a
SP_ROOT=${SP_ROOT:-/gpfs/users/jixinpeng/SpecDec/SpecPilot}
SP_UPSTREAM=${SP_UPSTREAM:-/gpfs/users/jixinpeng/SpecDec/upstream/SpecPilot-main}
SP_ENV=${SP_ENV:-/gpfs/users/jixinpeng/miniconda3/envs/sp-sglang1520}
SP_DATA=${SPECPILOT_DATA:-/gpfs/users/jixinpeng/specpilot_data}
SP_TARGET=${SP_TARGET:-/gpfs/models/huggingface.co/Qwen/Qwen3.8-27B}
SP_DRAFT=${SP_DRAFT:-/gpfs/users/jixinpeng/models/z-lab/Qwen3.8-27B-DFlash2}
# 派生引擎树：SP_ENGINE 直接指定，否则按 SP_SETTING/SP_KIND 从工作目录取，最后回落到上游树
SP_SETTING=${SP_SETTING:-h100_c1_qwen38-27b_dflash2}
SP_KIND=${SP_KIND:-stock}
SP_ENGINE=${SP_ENGINE:-$SP_DATA/work/engines/${SP_SETTING}-${SP_KIND}}
if [[ ! -f "$SP_ENGINE/TREE_SHA" ]]; then
  echo "[env] 未找到派生树 $SP_ENGINE，回落到上游只读树（= stock）" >&2
  SP_ENGINE=""
fi

export PATH=$SP_ENV/bin:$PATH
export CC=$SP_ENV/bin/gcc CXX=$SP_ENV/bin/g++
export CUDA_HOME=$SP_ENV/lib/python3.12/site-packages/nvidia/cu13
export PATH=$CUDA_HOME/bin:$PATH
if [[ -n "$SP_ENGINE" ]]; then
  export PYTHONPATH=$SP_ENGINE/python:$SP_ENGINE/lab
  export SP_TREE_SHA=$(cat "$SP_ENGINE/TREE_SHA")
else
  export PYTHONPATH=$SP_UPSTREAM/python:$SP_UPSTREAM/research/dflash_lab
  export SP_TREE_SHA=upstream
fi
export LD_LIBRARY_PATH=$SP_DATA/shared/cuda-compat/usr/local/cuda-13.0/compat:$CUDA_HOME/lib64/stubs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false PYTHONUNBUFFERED=1
# 缓存按 tree sha 前缀分桶：stock / final 的 kernel 不同，共用一个缓存会互相污染
SP_CACHE_KEY=${SP_TREE_SHA:0:16}
export SGLANG_CACHE_DIR=$SP_DATA/shared/cache/engines/$SP_CACHE_KEY/sglang
export SGLANG_JIT_CACHE_DIR=$SP_DATA/shared/cache/engines/$SP_CACHE_KEY/sglang/jit
export TRITON_CACHE_DIR=$SP_DATA/shared/cache/engines/$SP_CACHE_KEY/triton
export FLASHINFER_WORKSPACE_BASE=$SP_DATA/shared/cache/engines/$SP_CACHE_KEY
export TORCH_EXTENSIONS_DIR=$SP_DATA/shared/cache/engines/$SP_CACHE_KEY/torch_extensions
export SGLANG_JIT_DEEPGEMM_PRECOMPILE=0
export SP_PY=$SP_ENV/bin/python
set +a
