# Research and implementation references

## Amount matching and review

Wu et al., *The Subset Sum Matching Problem*, ECAI 2025, DOI [10.3233/FAIA250892](https://journals.sagepub.com/doi/full/10.3233/FAIA250892), with the extended version on [arXiv:2508.19218v1](https://arxiv.org/abs/2508.19218v1).

The paper studies matches between sets of amounts, including multiple disjoint matches and unmatched amounts. We use it as background for distinguishing a numerical candidate from the intended business allocation. Requiring a human decision and reason is our design choice; the paper does not evaluate this review workflow.

The [official ECAI accepted-paper list](https://ecai2025.org/accepted-papers/) identifies the main paper as M3679. The arXiv entry states that its version includes supplementary material. Conference acceptance applies to the main paper and does not establish that every extended appendix was reviewed. Discovery and selected raw-paper inspection used the alphaXiv plugin; the arXiv entry and conference list were rechecked on 2026-10-10.

The paper's whole-element matching formulation does not replace ERPNext's partial-payment allocations. No solver, benchmark score, accounting guarantee, or immutable-audit claim is adopted from it.

## Copied implementation

The financial execution path is the copied ERPNext v15.122.0 Payment Reconciliation component at commit `bfd8100d42162048248b7b947f2e21fdf7999a91`. [PROVENANCE.json](PROVENANCE.json) records the exact files and license. The surrounding pinned ERPNext and Frappe runtime remains necessary; this source excerpt is not independently installable.

The selected original and copied reconciliation baselines each passed 41 tests. Those results cover the existing component and do not establish that a later review-trail adaptation is correct.
