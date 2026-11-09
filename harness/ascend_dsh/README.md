# Local Ascend / DSH experiment adapter

Source snapshot of the executable adapter used by the local Ascend campaign. This
is a deployment-specific harness, not a portable replacement for the protected
paper controller. Source hashes are in `source-manifest.json`.

The real runtime files are staged into `<workspace>/profiling/<campaign>/`.
`prepare_baseline.py` derives the workspace from that layout. The workspace must
supply its private frozen dataset, deployment launch script, runtime network
guard, campaign plan, local ModelScope model, installed vLLM/vLLM-Ascend, AIPerf,
DSH environments and the shared NPU lock. Those deployment inputs and raw data
are intentionally outside this public source snapshot. Do not execute this copy
in place or substitute another deployment without reviewing the paths/protocol.

The outer scheduler runs a real DSH Master session and serial Direction sessions
with Claude Opus 5.5, optionally continuing with exact `gpt-6.1-sol` only after
Claude's admission budget is exhausted. Native DSH tool loops connect to a capability-gated MCP
broker. Every model request crosses a native `llm/stream` budget hook. Direct
NorthGate HTTPS is used; this adapter does not start a network relay.

The Claude total ceiling is USD 200, enforced by conservative, persistent, nonrefundable
request reservations plus observed shared-key billing deltas. This does not
change the gateway account/token quota. Shared-key use elsewhere may stop the
campaign early. Failed requests and process restarts cannot reclaim reservations.

The separately authorized GPT phase has a USD 500 ceiling and its own ledger,
created at activation, not at preflight. `gpt_handoff.py watch` observes the
durable Claude budget-denial event and takes the existing driver lock only after
Claude exits and all NPU experiments finish restoration. It inherits decisions,
completed rounds, broker allocations and receipts; it does not rerun baseline or
reset the three-direction limit. Normal completion, unrelated errors, or a
frozen/opened validation set do not trigger another paid model phase.

`gpt_call.py` uses DSH's native pi-ai `openai-responses` adapter with exact
`gpt-6.1-sol`, `xhigh`, `store=false` (verified on the wire), and no HTTP proxy or
automatic model fallback. SDK retries are disabled. GPT uses fresh native
sessions linked to the original Claude trajectory rather than replaying
provider-specific encrypted reasoning across vendors. `gpt_wire_probe.py` is
an offline integration fixture with a dummy key and loopback server; it checks
real MCP tool execution, encrypted reasoning replay and fresh-process resume.
Passing this fixture is not a paid gateway inference or scientific result.

The GPT billing reader uses the supplied gateway's `/v1/usage` actual USD counter.
An observed aggregate nominal/actual ratio and conservative 10/50 USD-per-million
input/output reservation ceilings are checked; these are not a contractual
provider tariff or account-wide spending limit. Shared-key charges, uncertain
usage or pricing evidence can stop this task early. Credentials live outside the
repository in a private file, never in configuration, tools or public artifacts.

The broker permits bounded installed-engine source reads, scratch writes, CPU
analysis, configuration experiments and diagnostic CPU+NPU profiling. CPU code
runs inside a chroot with dropped UID and seccomp; the current container lacks
Landlock. Native shell/file tools are disabled. Source patches can be submitted
for independent admission, but are not automatically executed.

All NPU work queues on the machine-wide lock. Trusted runners produce AIPerf
results and restore the baseline. A final held-out runner is invoked only after
research stops and an independently checked candidate freeze is persisted. Its
results are never sent back to the model for more tuning. Serial screens and
held-out comparisons are not formal paired promotion and do not certify semantic
accuracy or losslessness.

`experiment_lifecycle.py` distinguishes the runner's early failure write from
its completed cleanup. The broker reports `restoring_baseline` while restoration
is pending, and the outer scheduler waits before accepting a finished direction.
Restoration failure still blocks further research. Bounded error lines from the
fixed candidate startup log and any recorded operator intervention accompany the
failed receipt; this does not grant general log or filesystem access. A saved
completed direction report can be resumed after cleanup without another model
call or resetting its allocations.

Acceptance (from the runtime directory's parent workspace):

```bash
.venv/bin/python -m unittest discover -s "$RUN" -p 'test_*.py'
.venv/bin/python "$RUN/prepare_baseline.py" --check
.venv/bin/python "$RUN/audit_baseline.py"
```

The model/MCP preflight consumes paid API calls and must run only with an
explicitly authorized task budget. The scheduler refuses duplicate state;
failed/uncertain submissions require inspection instead of automatic resubmission.

The user lowered the original USD 500 authorization to USD 200 on 2026-11-09.
The live billing ledger is authoritative; frozen run plans and launch-time
scheduler metadata may retain the original authorization. Existing reservations
and spend are retained, and the runtime clamps any stale higher ledger limit.

`resume_claude.py` preserves a failed output-truncation turn and resumes the same
native session without adding tool or experiment allocation. A completed answer
with one premature root-closing brace can be recovered by one audited syntactic
deletion; the original receipt remains unchanged. This does not manufacture a
scientific report or retry a failed NPU experiment.

A native `SERVER` error explicitly reporting an upstream 60-second stream stall
can resume the same session with a short continuation prompt, at most two extra
attempts per invocation. Each attempt is separately admitted and failed-call
reservations remain charged. Authentication errors, budget errors and unknown
failures are not retried by this rule. Native receipts and retry events remain
durable; the transport recovery does not authorize a model switch.
