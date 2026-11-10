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
