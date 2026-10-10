# Local verification — 2026-10-10

These results apply to the pinned ERPNext v15.122.0 commit `bfd8100d42162048248b7b947f2e21fdf7999a91` and Frappe v15.122.0 commit `b0b5b99a1d9d2cb3d54b32293d3854bf2c15f4a4`. They were run on task-local synthetic Frappe sites, not on customer data. No test, service, or provider call was started to write this document.

| Stage | Observed result | Execution path and evidence |
| --- | --- | --- |
| Original selected ERPNext module | 41 tests passed | Pinned original checkout on `test_site`; retained private baseline evidence |
| Copied selected source | 41 tests passed in 154.855 seconds, exit 0 | The recorded copied-source oracle prepended the separate copied ERPNext/Frappe checkout and ran the upstream module on `copy_test_site` |
| Review integration | Seven tests passed in 23.812 seconds, exit 0 | `bench --site copy_test_site run-tests --app erpnext --module adaptation.test_review_trail --case TestReviewTrail`; private privacy-execution receipt |
| Source integrity and cleanup | All 15 manifest entries matched pinned copied bytes and Git modes; pinned checkout clean; task-owned MariaDB/Redis stopped and site config restored | The review integration receipt above; [`PROVENANCE.json`](PROVENANCE.json) gives file hashes |

The focused integration runner prepended the candidate directory and the **separate full pinned ERPNext/Frappe checkout** to `PYTHONPATH`. [`adaptation/test_review_trail.py`](adaptation/test_review_trail.py) imports the upstream test fixture from that checkout, including its Payment Reconciliation controller. It checks the candidate's copied 15-file snapshot against the pin, but the seven-test run did not import its Python from `source/`. The 41-test copied oracle used the matching selected files in the copied runtime checkout. The candidate excerpt is a preserved source component with an executable oracle; it is not a self-contained Python installation.

The seven tests verify that approval of a 40 allocation changes a 200 invoice to 160 outstanding and a 55 payment to 15 unallocated through ERPNext; defer/reject leave balances unchanged; a changed reason, allocation, or source balance rejects stale approval; repeat and invalid decisions reject; a Guest cannot execute; a reader shared only one invoice cannot read the private full-review Note or see other voucher details in its Comment; and a forced Comment failure rolls back the ledger and review records. The Note's stored canonical JSON round-trips to the approved digest. A retained private independent recheck records resolution of the previously found Comment disclosure path for this tested access route.

For an already prepared compatible task-local bench and synthetic `copy_test_site`, the focused command is:

```text
bench --site copy_test_site run-tests --app erpnext --module adaptation.test_review_trail --case TestReviewTrail
```

This command requires the pinned full ERPNext/Frappe environment, site database, services, and candidate path on `PYTHONPATH`; it is not a fresh-install instruction. The private runner in the receipt sets those prerequisites, checks copied-source hashes before and after, temporarily enables tests, and restores configuration and stops task-owned services. Original and copied baseline commands target the upstream module `erpnext.accounts.doctype.payment_reconciliation.test_payment_reconciliation` on their respective isolated sites.

The tested adaptation files had SHA-256 `e09a750a7a7277ab9f4bed1359d392293692e10f68c45a7ceb533073ecfcab98` (`review_trail.py`) and `9f5a5dbecb02283db638785c6b84b9b9f623f5e0a8f933e45bac5e6cec59b5c6` (`test_review_trail.py`) before and after the seven-test run. The private runtime log and receipt were saved with mode 600. A sanitized, machine-readable [result summary](verification/results.json) is included; machine paths and private runtime logs are excluded.

No full ERPNext suite, fresh installation, PDF path, production concurrency test, customer workflow, or immutable-audit assessment was performed. The Note and Comments are mutable under Frappe permissions, and the preview digest does not identify the human who inspected it. The private access test covers the tested default permission route, not custom sharing or permission hooks.
