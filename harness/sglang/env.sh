#!/usr/bin/env bash
# SpecPilot × SGLang v0.5.20 环境约定。所有启动/测量脚本都 source 这个文件。
#
# 关键事实（本机 + NorthJob 通用）：
#   1. 引擎来自上游冻结树 python/（含 dflash_worker_v2），靠 PYTHONPATH 覆盖 pip 包；
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

export PATH=$SP_ENV/bin:$PATH
export CC=$SP_ENV/bin/gcc CXX=$SP_ENV/bin/g++
export CUDA_HOME=$SP_ENV/lib/python3.12/site-packages/nvidia/cu13
export PATH=$CUDA_HOME/bin:$PATH
export PYTHONPATH=$SP_UPSTREAM/python:$SP_UPSTREAM/research/dflash_lab
export LD_LIBRARY_PATH=$SP_DATA/shared/cuda-compat/usr/local/cuda-13.0/compat:$CUDA_HOME/lib64/stubs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
export HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false PYTHONUNBUFFERED=1
export SGLANG_CACHE_DIR=$SP_DATA/shared/cache/sglang
export SGLANG_JIT_CACHE_DIR=$SP_DATA/shared/cache/sglang/jit
export TRITON_CACHE_DIR=$SP_DATA/shared/cache/triton
export FLASHINFER_WORKSPACE_BASE=$SP_DATA/shared/cache
export TORCH_EXTENSIONS_DIR=$SP_DATA/shared/cache/torch_extensions
export SGLANG_JIT_DEEPGEMM_PRECOMPILE=0
export SP_PY=$SP_ENV/bin/python
set +a
