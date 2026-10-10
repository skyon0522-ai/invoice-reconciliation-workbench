# Invoice reconciliation with a human review trail

ERPNext can allocate a payment across invoices, including partial amounts. When an amount has more than one plausible destination, an operator still needs to inspect the exact allocation and record why it was accepted, deferred, or rejected. This source-derived library adds that review step around ERPNext's existing Payment Reconciliation controller. It does not implement another matching or accounting engine.

For example, in the focused local fixture, an invoice outstanding at 200 and a payment with 55 unallocated receive a reviewed allocation of 40. Approval invokes ERPNext's original `reconcile()` path; afterward the invoice has 160 outstanding and the payment has 15 unallocated. A defer or reject decision records the review without changing either balance.

## Try the review interface

Run this **inside an existing ERPNext/Frappe v15.122.0 site at the pins in [PROVENANCE.json](PROVENANCE.json)** after preparing a `Payment Reconciliation` document with selected allocation rows through ERPNext's normal workflow. Add this repository's root to that environment's `PYTHONPATH` so `adaptation` is importable. The caller must show the complete preview to the operator, obtain their decision, and pass the digest of that same preview back. The digest binds the reviewed context, voucher identities, selected source balances, allocations, decision, and reason; it does not authenticate the person who reviewed them.

```python
from adaptation.review_trail import record_review, review_preview

# pr is an ERPNext Payment Reconciliation document with selected allocations.
decision = "approve"  # or "defer" / "reject", as chosen by the operator
reason = "Matched the remittance reference"
preview = review_preview(pr, decision, reason)
print(preview["payload"])  # Display this exact JSON for human inspection.

# Only after the human confirms this payload and decision:
result = record_review(pr, preview["sha256"], decision, reason)
# The enclosing request or job owns the database commit.
```

This is a Python integration component, not an installed Frappe app, browser UI, or hosted service. No interface here verifies that `print` was read or that the caller actually obtained consent. Integrators must supply that human interaction and a compatible site; this repository does not provide a fresh-install procedure.

## How the component is assembled

- [`source/erpnext/accounts/doctype/payment_reconciliation/`](source/erpnext/accounts/doctype/payment_reconciliation/) and the three neighboring child DocTypes are an unmodified, 15-file ERPNext v15.122.0 excerpt (including the upstream test and license). [`PROVENANCE.json`](PROVENANCE.json) lists each copied file, upstream path, hash, and role. ERPNext remains the financial execution path.
- [`adaptation/review_trail.py`](adaptation/review_trail.py) creates the exact review preview, checks its SHA-256 and current voucher balances, checks permissions, and records the decision. Approval calls the original `doc.reconcile()` method, including its existing validation and partial-allocation behavior. Defer and reject do not invoke reconciliation.
- The complete reviewed JSON and human reason are stored in an existing private Frappe Note owned by the recording user. Each source voucher receives a Comment containing only the decision, operator, digest, and opaque Note reference. A user with access to one voucher's Comment does not thereby receive the other vouchers' allocations or the private reason through that Comment. A focused access test covers this path.
- The wrapper uses a database savepoint and rolls back ledger, Note, and Comment writes if any step raises, even if the caller catches that error. It does not commit. It locks selected voucher documents in a stable order before checking balances. This has not been validated against every external reconciliation writer or database isolation setting.

The excerpt cannot run alone: it imports other ERPNext accounting and payment modules and uses Frappe documents, permissions, query APIs, and a site database. The local tests used a separate full ERPNext/Frappe checkout at the same pins. The seven adaptation tests import that checkout's controller and fixtures; they verify the excerpt's bytes but do **not** import Python directly from the candidate's `source/` directory. The earlier selected 41-test copied-source oracle ran the matching source through the separate copied checkout. See [`VERIFICATION.md`](VERIFICATION.md) for the exact scope and commands.

## Verification and limits

The original selected ERPNext module passed 41 tests; the copied-source oracle passed the same 41 tests; and the current review integration passed seven focused tests on a synthetic `copy_test_site`. The latter cover partial allocation, review persistence, defer/reject, stale and repeated reviews, invalid inputs, permissions, privacy, and rollback. These are local results, not the full ERPNext suite, a fresh-install result, or a production audit.

The Note and Comments provide a durable review history within the site's ordinary persistence, but both can be edited or deleted by authorized users. The digest is content binding, not an immutable audit log or proof of the human's identity. Custom permission rules, Note sharing changes, and concurrent external writers need separate validation. No PDF handling was tested.

ERPNext's copied source remains under GPL-3.0 with its [`LICENSE`](LICENSE) and upstream notices. Frappe is a separate MIT-licensed runtime dependency, not vendored here. [`REFERENCES.md`](REFERENCES.md) cites the ECAI 2025 subset-sum matching paper as background for amount ambiguity; this library does not adopt its solver or claim that the paper validates its review or ledger behavior.
