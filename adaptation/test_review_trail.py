"""Focused integration tests for the private review wrapper on copy_test_site."""

import hashlib
import html
import re
from unittest.mock import patch

import frappe
from frappe.core.doctype.comment.comment import Comment
from frappe.tests.utils import FrappeTestCase

from erpnext.accounts.doctype.payment_reconciliation import test_payment_reconciliation as upstream_tests

from adaptation.review_trail import record_review, review_digest, review_preview


test_dependencies = ["Item"]


class TestReviewTrail(FrappeTestCase):
	def setUp(self):
		self.fixture = upstream_tests.TestPaymentReconciliation("test_payment_against_invoice")
		self.fixture.setUp()
		self.invoice = self.fixture.create_sales_invoice(qty=1, rate=200)
		self.payment = self.fixture.create_payment_entry(amount=55).save().submit()
		self.pr = self._review_doc(40)

	def tearDown(self):
		frappe.db.rollback()

	def _review_doc(self, amount):
		pr = self.fixture.create_payment_reconciliation()
		pr.get_unreconciled_entries()
		pr.allocate_entries(frappe._dict({
			"invoices": [row.as_dict() for row in pr.invoices],
			"payments": [row.as_dict() for row in pr.payments],
		}))
		pr.allocation[0].allocated_amount = amount
		return pr

	def test_approve_preserves_partial_financial_execution_and_comments(self):
		preview = review_preview(self.pr, "approve", "Matched reference checked")
		digest = preview["sha256"]
		self.assertEqual(review_digest(self.pr, "approve", "Matched reference checked"), digest)
		result = record_review(self.pr, digest, "approve", "Matched reference checked")
		self.invoice.reload()
		self.payment.reload()
		self.assertEqual(self.invoice.outstanding_amount, 160)
		self.assertEqual(self.payment.unallocated_amount, 15)
		self.assertEqual(len(result["comments"]), 2)
		note = frappe.get_doc("Note", result["note"])
		self.assertEqual(note.public, 0)
		self.assertEqual(note.owner, frappe.session.user)
		payload = html.unescape(re.search(r"<pre[^>]*>(.*?)</pre>", note.content, re.S).group(1))
		self.assertEqual(payload, preview["payload"])
		self.assertEqual(hashlib.sha256(payload.encode("utf-8")).hexdigest(), digest)
		for comment_name in result["comments"]:
			comment = frappe.get_doc("Comment", comment_name)
			self.assertEqual(comment.subject, f"Payment reconciliation review {digest}")
			self.assertIn(note.name, comment.content)
			self.assertNotIn("Matched reference checked", comment.content)
			self.assertNotIn(preview["payload"], comment.content)

	def test_defer_and_reject_leave_balances_and_reject_repeat(self):
		for decision in ("defer", "reject"):
			reason = f"Human {decision} decision"
			digest = review_digest(self.pr, decision, reason)
			record_review(self.pr, digest, decision, reason)
			with self.assertRaisesRegex(ValueError, "already recorded"):
				record_review(self.pr, digest, decision, reason)
		self.invoice.reload()
		self.payment.reload()
		self.assertEqual(self.invoice.outstanding_amount, 200)
		self.assertEqual(self.payment.unallocated_amount, 55)

	def test_stale_digest_and_changed_source_balance_rejected(self):
		digest = review_digest(self.pr, "approve", "Reviewed")
		with self.assertRaisesRegex(ValueError, "changed"):
			record_review(self.pr, digest, "approve", "Different reason")
		self.pr.allocation[0].allocated_amount = 41
		with self.assertRaisesRegex(ValueError, "changed"):
			record_review(self.pr, digest, "approve", "Reviewed")
		self.pr.allocation[0].allocated_amount = 40
		other = self._review_doc(10)
		other.reconcile()
		with self.assertRaisesRegex(ValueError, "balances changed"):
			record_review(self.pr, digest, "approve", "Reviewed")
		self.invoice.reload()
		self.assertEqual(self.invoice.outstanding_amount, 190)

	def test_permission_failure_does_not_reconcile(self):
		digest = review_digest(self.pr, "approve", "Reviewed")
		original_user = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				record_review(self.pr, digest, "approve", "Reviewed")
		finally:
			frappe.set_user(original_user)
		self.invoice.reload()
		self.assertEqual(self.invoice.outstanding_amount, 200)

	def test_invalid_or_reasonless_decision_is_rejected(self):
		with self.assertRaisesRegex(ValueError, "Invalid review decision"):
			record_review(self.pr, "irrelevant", "post", "Reviewed")
		with self.assertRaisesRegex(ValueError, "reason is required"):
			record_review(self.pr, "irrelevant", "approve", "  ")
		self.invoice.reload()
		self.assertEqual(self.invoice.outstanding_amount, 200)

	def test_single_voucher_reader_cannot_read_full_review_note(self):
		other_invoice = self.fixture.create_sales_invoice(qty=1, rate=100)
		self.pr.get_unreconciled_entries()
		row = self.pr.append("allocation", {})
		row.reference_type = self.payment.doctype
		row.reference_name = self.payment.name
		row.reference_row = self.pr.allocation[0].reference_row
		row.invoice_type = other_invoice.doctype
		row.invoice_number = other_invoice.name
		row.amount = row.unreconciled_amount = 55
		row.allocated_amount = 10
		row.currency = "INR"
		reason = "Private cross-voucher reason"
		digest = review_digest(self.pr, "defer", reason)
		result = record_review(self.pr, digest, "defer", reason)
		reader = frappe.get_doc({
			"doctype": "User", "email": "invoice-review-reader@example.test",
			"first_name": "Invoice Review Reader", "send_welcome_email": 0,
			"roles": [{"role": "Desk User"}],
		}).insert(ignore_permissions=True)
		frappe.share.add(self.invoice.doctype, self.invoice.name, reader.name, read=1, notify=0)
		self.assertTrue(frappe.has_permission(self.invoice.doctype, "read", doc=self.invoice, user=reader.name))
		self.assertFalse(frappe.has_permission(other_invoice.doctype, "read", doc=other_invoice, user=reader.name))
		note = frappe.get_doc("Note", result["note"])
		self.assertFalse(frappe.has_permission("Note", "read", doc=note, user=reader.name))
		original_user = frappe.session.user
		try:
			frappe.set_user(reader.name)
			with self.assertRaises(frappe.PermissionError):
				note.check_permission("read")
			self.assertFalse(frappe.get_list("Note", filters={"name": note.name}))
			visible = frappe.get_all("Comment", fields=["content"], filters={
				"reference_doctype": self.invoice.doctype, "reference_name": self.invoice.name,
			})
		finally:
			frappe.set_user(original_user)
		comments = [r.content for r in visible if digest in r.content]
		self.assertEqual(len(comments), 1)
		self.assertNotIn(other_invoice.name, comments[0])
		self.assertNotIn(reason, comments[0])
		self.assertNotIn("10 INR", comments[0])

	def test_comment_failure_rolls_back_ledger_even_if_caught(self):
		digest = review_digest(self.pr, "approve", "Reviewed")
		with patch.object(Comment, "after_insert", side_effect=RuntimeError("comment write failed")):
			with self.assertRaisesRegex(RuntimeError, "comment write failed"):
				record_review(self.pr, digest, "approve", "Reviewed")
		self.invoice.reload()
		self.payment.reload()
		self.assertEqual(self.invoice.outstanding_amount, 200)
		self.assertEqual(self.payment.unallocated_amount, 55)
		self.assertFalse(frappe.db.exists("Comment", {
			"reference_doctype": "Sales Invoice", "reference_name": self.invoice.name,
			"subject": f"Payment reconciliation review {digest}",
		}))
		self.assertFalse(frappe.db.exists("Note", {"title": f"Payment reconciliation review {digest}"}))
