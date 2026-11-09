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
with Claude Opus 5.5. Native DSH tool loops connect to a capability-gated MCP
broker. Every model request crosses a native `llm/stream` budget hook. Direct
NorthGate HTTPS is used; this adapter does not start a network relay.

The task ceiling is USD 500, enforced by conservative, persistent, nonrefundable
request reservations plus observed shared-key billing deltas. This does not
change the gateway account/token quota. Shared-key use elsewhere may stop the
campaign early. Failed requests and process restarts cannot reclaim reservations.

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

Acceptance (from the runtime directory's parent workspace):

```bash
.venv/bin/python -m unittest discover -s "$RUN" -p 'test_*.py'
.venv/bin/python "$RUN/prepare_baseline.py" --check
.venv/bin/python "$RUN/audit_baseline.py"
```

The model/MCP preflight consumes paid API calls and must run only with an
explicitly authorized task budget. The scheduler refuses duplicate state;
failed/uncertain submissions require inspection instead of automatic resubmission.
