"""Persist a human review around ERPNext's existing reconciliation execution.

This is a private integration component, not an endpoint or an immutable audit log.
The caller must present the digest of the exact review content shown to the human.
"""

import hashlib
import html
import json
from decimal import Decimal

import frappe


CONTEXT = (
	"company", "party_type", "party", "receivable_payable_account",
	"default_advance_account", "cost_center", "project", "bank_cash_account",
	"from_invoice_date", "to_invoice_date", "from_payment_date", "to_payment_date",
	"minimum_invoice_amount", "maximum_invoice_amount", "minimum_payment_amount",
	"maximum_payment_amount", "invoice_limit", "payment_limit", "invoice_name", "payment_name",
)
ALLOCATION = (
	"reference_type", "reference_name", "reference_row", "invoice_type", "invoice_number",
	"allocated_amount", "amount", "unreconciled_amount", "difference_amount",
	"difference_account", "gain_loss_posting_date", "debit_or_credit_note_posting_date",
	"exchange_rate", "currency", "cost_center", "is_advance",
)
AMOUNTS = {"allocated_amount", "amount", "unreconciled_amount", "difference_amount", "exchange_rate"}


def _value(value, field):
	if field in AMOUNTS or field == "outstanding_amount":
		return str(Decimal(str(value or 0)))
	return str(value or "")


def _row(row, fields):
	return {field: _value(row.get(field), field) for field in fields}


def _snapshot(doc):
	dimensions = tuple(d.fieldname for d in doc.dimensions)
	allocations = [_row(row, ALLOCATION + dimensions) for row in doc.get("allocation")]
	selected_payments = {(r["reference_type"], r["reference_name"], r["reference_row"]) for r in allocations}
	selected_invoices = {(r["invoice_type"], r["invoice_number"]) for r in allocations}
	payments = [_row(row, ("reference_type", "reference_name", "reference_row", "amount")) for row in doc.get("payments")]
	invoices = [_row(row, ("invoice_type", "invoice_number", "outstanding_amount")) for row in doc.get("invoices")]
	return {
		"context": _row(doc, CONTEXT + dimensions),
		"allocation": allocations,
		"payments": [r for r in payments if (r["reference_type"], r["reference_name"], r["reference_row"]) in selected_payments],
		"invoices": [r for r in invoices if (r["invoice_type"], r["invoice_number"]) in selected_invoices],
	}


def _review_json(snapshot, decision, reason):
	return json.dumps(
		{"review": snapshot, "decision": decision, "reason": reason.strip()},
		sort_keys=True, separators=(",", ":"),
	)


def review_preview(doc, decision, reason):
	"""Return exactly what the human must inspect before approving its SHA-256."""
	if decision not in {"approve", "defer", "reject"} or not isinstance(reason, str) or not reason.strip():
		raise ValueError("A valid decision and human review reason are required")
	if doc.doctype != "Payment Reconciliation" or not doc.get("allocation"):
		raise ValueError("Payment Reconciliation with selected allocations required")
	payload = _review_json(_snapshot(doc), decision, reason)
	return {"payload": payload, "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest()}


def review_digest(doc, decision, reason):
	"""Return the digest of :func:`review_preview` for existing callers."""
	return review_preview(doc, decision, reason)["sha256"]


def _targets(rows):
	return sorted({(r["reference_type"], r["reference_name"]) for r in rows} |
		{(r["invoice_type"], r["invoice_number"]) for r in rows})


def _check_permissions(rows):
	if not frappe.has_permission("Payment Reconciliation", "write"):
		raise frappe.PermissionError("Payment Reconciliation write permission required")
	for doctype, name in _targets(rows):
		voucher = frappe.get_doc(doctype, name)
		for permission in ("read", "write"):
			if not frappe.has_permission(doctype, permission, doc=voucher):
				raise frappe.PermissionError(f"{permission} permission required for {doctype} {name}")


def _selected_balances(snapshot):
	payments = {(r["reference_type"], r["reference_name"], r["reference_row"]): r["amount"] for r in snapshot["payments"]}
	invoices = {(r["invoice_type"], r["invoice_number"]): r["outstanding_amount"] for r in snapshot["invoices"]}
	if len(payments) != len(snapshot["payments"]) or len(invoices) != len(snapshot["invoices"]):
		raise ValueError("Duplicate source voucher rows")
	return payments, invoices


def _recheck_balances(doc, before):
	selected_payments = {(r["reference_type"], r["reference_name"], r["reference_row"]) for r in before["allocation"]}
	selected_invoices = {(r["invoice_type"], r["invoice_number"]) for r in before["allocation"]}
	old_payments, old_invoices = _selected_balances(before)
	if not selected_payments <= old_payments.keys() or not selected_invoices <= old_invoices.keys():
		raise ValueError("Selected voucher absent from reviewed balances")
	doc.get_unreconciled_entries()
	new_payments, new_invoices = _selected_balances(_snapshot(doc))
	if any(old_payments[key] != new_payments.get(key) for key in selected_payments) or any(
		old_invoices[key] != new_invoices.get(key) for key in selected_invoices
	):
		raise ValueError("Voucher balances changed after review")


def record_review(doc, expected_digest, decision, reason):
	"""Record approve/defer/reject; only approve invokes original ``doc.reconcile()``.

	The database savepoint undoes ledger, Note, and Comment writes if any step raises,
	even when the caller catches that exception. No commit is issued here.
	"""
	if decision not in {"approve", "defer", "reject"}:
		raise ValueError("Invalid review decision")
	if not isinstance(reason, str) or not reason.strip():
		raise ValueError("A human review reason is required")
	if doc.doctype != "Payment Reconciliation":
		raise ValueError("Expected Payment Reconciliation document")
	before = _snapshot(doc)
	rows = before["allocation"]
	if not rows:
		raise ValueError("At least one selected allocation is required")
	canonical_review = _review_json(before, decision, reason)
	digest = hashlib.sha256(canonical_review.encode("utf-8")).hexdigest()
	if not isinstance(expected_digest, str) or expected_digest != digest:
		raise ValueError("Review content changed or was not approved")
	_check_permissions(rows)
	if not frappe.has_permission("Note", "create"):
		raise frappe.PermissionError("Private Note create permission required")
	subject = f"Payment reconciliation review {digest}"

	savepoint = "reconciliation_review"
	frappe.db.savepoint(savepoint)
	try:
		# Lock in a stable order so concurrent calls through this wrapper serialize.
		for doctype, name in _targets(rows):
			frappe.get_doc(doctype, name, for_update=True)
		if frappe.db.get_value("Note", {"title": subject}, "name", for_update=True):
			raise ValueError("This allocation review was already recorded")
		for doctype, name in _targets(rows):
			if frappe.db.get_value("Comment", {
				"reference_doctype": doctype, "reference_name": name, "subject": subject,
			}, "name", for_update=True):
				raise ValueError("This allocation review was already recorded")
		_recheck_balances(doc, before)
		if decision == "approve":
			if frappe.db.get_single_value("Accounts Settings", "auto_reconcile_payments"):
				raise ValueError("ERPNext automatic reconciliation is active")
			# Reuse ERPNext's auto-job check, allocation validation, and ledger execution.
			doc.reconcile()
		note = frappe.get_doc({
			"doctype": "Note", "title": subject, "public": 0,
			"content": "<p>Canonical reviewed data (JSON):</p><pre>"
			+ html.escape(canonical_review) + "</pre>",
		}).insert()
		if note.public or note.owner != frappe.session.user:
			raise ValueError("Private review Note ownership changed")
		content = (
			f"<p>Payment reconciliation: {html.escape(decision)}. "
			f"Review by {html.escape(frappe.session.user)}. "
			f"Allocation SHA-256: {digest}. "
			f"Private Note: {html.escape(note.name)}.</p>"
		)
		comments = []
		for doctype, name in _targets(rows):
			comments.append(frappe.get_doc({
				"doctype": "Comment", "comment_type": "Comment", "subject": subject,
				"reference_doctype": doctype, "reference_name": name, "content": content,
			}).insert(ignore_permissions=True).name)
		return {"decision": decision, "digest": digest, "note": note.name, "comments": comments}
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise
