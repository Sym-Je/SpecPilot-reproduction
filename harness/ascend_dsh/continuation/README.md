# Ascend continuation adapter

This is the source snapshot of the continuation authorized on 2026-11-10. Stage
these files with the existing Ascend adapter dependencies into a new private
runtime directory; do not execute this source snapshot in place. The staged
`prepare_baseline.ROOT` must identify the deployment workspace independently of
the runtime directory. Baseline manifests still reference the frozen dev inputs.

The continuation shares the original Claude billing directory (USD 200 cumulative,
including previous calls). Exact `gpt-6.1-sol` can start only after a durable Claude
budget denial and keeps its separate USD 500 ceiling. No ledger reset or automatic
holdout opening is performed. The old three-direction ceiling is removed. Each
individual direction retains bounded actions/experiments, while the Master may
allocate subsequent directions. Missing capabilities or source-patch proposals
are surfaced to the supervising assistant for implementation/admission; they are
not silently executed or reported as completed optimization.

Profiling uses the requested development stratum and concurrent request count,
with an output cap of 128. `max_iterations` bounds collection to 1–32 worker steps,
frontend profiling and stacks are disabled, and raw rank data is exported serially
outside daemon workers. Receipts include actual workload activity and per-rank
outputs. Missing ranks or data-loss warnings prohibit complete attribution.
Diagnostic timings are not unprofiled throughput or formal paired promotion.

Acceptance was run from the private deployment runtime: eight continuation tests
passed (request identity/scope, altered-input rejection, real launch arguments,
sampling/resource boundaries, unchanged baseline launch, shared cumulative billing,
rank/loss quality checks, serial restoration); five unchanged startup-guard tests
also passed. NPU validation of this new profiler is still pending. Tests require
private deployment inputs and dependencies and are not portable repository tests.

The previous holdout is retired. A fresh 40-request holdout was frozen from unused
original-validation groups with no group or exact-prompt overlap with the previous
100 selected requests. Its prompts/results are not exposed to research roles.
No new performance gain is claimed by this source checkpoint.

The first continuation profile subsequently completed on the exact graph-enabled
baseline, long-input replay at offered concurrency 32, with all eight rank CSV and
timeline exports and no export data-loss warnings. The request activity recorded
32 submitted requests but a smaller peak of active server requests; offered
concurrency must not be relabeled as active decode batch size. Detailed step/phase
attribution and performance gains remain unqualified. The serving baseline was
restored successfully, and the next decode-window experiment is queued on the
shared lock behind a separate quantization collection task.

The postprocessing helpers aggregate operator types using exact decimal timestamp
arithmetic and interval unions (two focused tests passed), publish actual workload
activity, and verify compressed timelines by full decompressed SHA256 before
removing the uncompressed derived file. The archive manifest maps original paths
to gzip paths; raw profiler files and kernel CSVs remain intact. Background heavy
compression acquires the machine timing lock to avoid perturbing benchmarks.

The subsequent three baseline captures exported all eight ranks successfully.
The offered-C32 decode capture had seven active requests and 25 completed at its
trigger; it is a tail window, not sustained active batch32. The first direction's
provider refusal was preserved without repeated NPU work; its supervisor closure
is explicitly not a model-authored scientific conclusion.

The user additionally authorized parallel research. `parallel_research.py` asks a
scientific Master to allocate two complementary source/trace/isolated-CPU lanes
alongside the original serial NPU direction. An `analysis_only` broker allocation
removes NPU launch/wait capabilities, and shared baseline CSVs are explicitly
allowlisted and SHA-pinned. Analysts receive frozen evidence, not each other's
reports. `parallel_evidence.py` shares attributed completed proposals and supervisor
corrections with later primary-role evidence reads. No old live MCP process is
claimed to hot reload. Proposals require review and serial measurement; the
parallel supervisor neither edits primary state nor auto-deploys patches.

All lanes share the existing locked Claude ledger. A trusted scheduler can activate the
shared GPT phase only after a durable Claude budget denial, without rewriting the
primary driver state or interrupting its experiment. Budgets are not multiplied
by worker count. New validation remains sealed. Native
DSH trajectories, calls, allocation, process state and reports remain private.
Eight new boundary tests plus 13 related tests passed (21 total); this is focused
adapter acceptance, not full repository coverage or evidence of a speedup.

Both initial parallel analyses completed without claiming measured gains. A prose
preamble immediately adjacent to A1's terminal JSON was recovered from the
unchanged native receipt without a repeated model call. The parser now accepts
that bounded format and rejects trailing prose/incomplete JSON. Installed AscendC
C++/headers are available through an explicit read-only source tree; analysis
roles still cannot launch devices or execute source patches. A bounded follow-up
checks the installed hyper-connection kernels' exact dispatch/aliasing contracts.
Twenty-four focused adapter tests pass; native kernels remain unmodified.

Native GPT contexts that exceed the unchanged 512 KiB admission bound now roll
over through an attributed, size-bounded checkpoint while keeping the same
broker role, tool allocation, scratch, experiment IDs and cumulative ledger.
Original native trajectories remain intact. Only the specific input-size failure
triggers rollover, not refusal or budget exhaustion. A primary resume reuses its
unfinished direction allocation. Settlement of an already admitted request may
complete after a primary failure, while new admission keeps all existing gates.
Twenty-seven focused checks pass; resumed native roles have emitted new tool
receipts. These recovery changes do not constitute a model performance gain.
