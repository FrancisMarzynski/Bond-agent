# E2E Remediation Roadmap

This file is the execution order for the detailed remediation plans created from `.planning/E2E_REPORT_2026-04-28.md`.

## Recommended Order

1. [`e2e-remediation-streaming-and-hitl.md`](./e2e-remediation-streaming-and-hitl.md)
   - Why first:
     - fixes the highest-priority production blocker
     - injects `thread_id` into graph state
     - standardizes low-corpus HITL contract
     - stabilizes browser behavior required for reliable follow-up E2E

2. [`e2e-remediation-responsive-layouts.md`](./e2e-remediation-responsive-layouts.md)
   - Why second:
     - removes the viewport constraints that currently make Author/Shadow hard to test outside desktop
     - depends only lightly on plan 1, mainly for clearer stage/recovery banners during manual validation

3. [`e2e-remediation-corpus-and-metadata-hardening.md`](./e2e-remediation-corpus-and-metadata-hardening.md)
   - Why third:
     - medium-priority backend hardening
     - benefits from the `thread_id` fix in plan 1 for stronger end-to-end metadata confidence
     - can be validated after transport and UI are already stable

## Dependency Notes

- Plan 1 is the only true blocker for the rest.
- Plan 2 can be implemented in parallel with Plan 3 if staffing allows, but sequence-first execution is safer.
- Plan 3 should assume the `thread_id` fix from Plan 1 is already merged.

## Acceptance Gate Between Plans

- Do not start Plan 2 until Plan 1 passes:
  - API tests for chat/history
  - frontend lint
  - manual Author and Shadow browser validation without duplicate `POST` replay

- Do not mark the whole remediation complete until:
  - all three plans pass their own validation commands
  - the E2E report can be rerun without reproducing the original high-priority failures
