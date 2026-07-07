# Nova — Part 2 PRD: CG Inbox Workflow

*Builds directly on Part 1's agents (Extractor, Validator, Router, Cross-Validator) and query layer — nothing below is a rebuild, only a new trigger and a workflow-shaped UI on top of what already ships.*

## Personas — what each person cares about *in this workflow*

**Sarah — Cargo Group (CG) Operator.** Opens every supplier email, downloads every PDF, cross-checks fields against rules she mostly remembers rather than looks up. Doesn't care about "agents" — cares whether a shipment came out clean, exactly what's wrong if it didn't, and whether she can fix it in one click. Opening the original PDF to double-check the agent's work is a failure.

**Michael — Shipping Unit (SU) coordinator.** Job feels done at send. Doesn't use Nova at all, but every extra amendment cycle (2–4 per shipment, 4–24 hours each) is his problem too — it delays his customer's cargo. Wants one complete list of what to fix, first time.

## Trigger — what we considered, what we shipped

The brief is explicit that "the trigger is the missing piece, not the model," so the 3–4 hour budget went there, not into re-proving extraction/validation. **Considered:** a real inbound mailbox (IMAP/Gmail Pub-Sub/Microsoft Graph) — rejected for this window; OAuth, MIME parsing, and webhook infra would consume most of the time budget on plumbing instead of the actual multi-doc / cross-validation behavior being evaluated. **Chosen:** a watched folder (`data/inbox/`, via `watchdog`) plus a "Simulate Incoming Email" button that copies a canned SU folder into it — the same trigger contract (`email.json` + PDF attachments → `run_pipeline(source="email", ...)`) a real inbound parser would call, so swapping the trigger later is a plumbing change, not a pipeline rewrite. **Found while testing, fixed:** macOS's native FSEvents backend can fail to attach under certain sandboxed launch contexts and silently stop delivering folder-drop events — the emitter thread dies quietly with no exception surfaced to the caller. Fixed by detecting emitter-thread liveness right after startup and falling back to a `PollingObserver` automatically, so a folder dropped after the watcher starts is never missed. **Production plan:** point a real SES/Graph-API inbound webhook at the same folder contract; zero pipeline code changes required.

## Jobs-to-be-Done

1. **When** a new shipment email arrives with trade documents attached, **I want** (Sarah) every attachment extracted and cross-validated the moment it lands, **so that** I never open a PDF just to find out if a shipment is clean.
2. **When** a shipment has discrepancies, **I want** (Sarah) a ready-to-send reply naming every field, found vs. expected, **so that** Michael's team fixes everything in one round instead of a fourth follow-up.

## North-Star Metric

**Median time from "email received" to "CG reply sent" per shipment.** Today: 4–24 hours per amendment cycle (2–4 cycles normal). Target for a 2-week pilot: **under 15 minutes** for the median shipment — measured directly from `shipments.received_at` to the `approve`/`send-amendment` action timestamp, no proxy metrics needed.

## Failure Mode — and how it's stopped

**Worst case:** the agent sends an approval or amendment email on its own — including a wrong one — with no human in the loop. Unacceptable on day one; a silently auto-sent wrong approval could clear a real HS-code or consignee error straight to customs.

**Considered:** disabling the Send button in the UI only — rejected, trivially bypassed by calling the API directly; a secondary-approval workflow (two humans must sign off) — rejected as unnecessary friction at pilot scale. **Chosen, enforced below the UI:** no code path anywhere in this build calls out to an email provider. `PUT /api/shipments/{id}/approve` and `PUT /api/shipments/{id}/send-amendment` only flip a database status and store the operator's (possibly edited) text — there is no SMTP or mail-API integration in the codebase at all today. "The agent never sends" isn't a policy switch that could be flipped by mistake; it's the literal absence of send capability until we deliberately wire one in. **Production plan:** add real outbound sending behind those same two endpoints only, still gated behind the explicit CG click — never inside the pipeline itself.
