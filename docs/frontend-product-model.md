# Yire frontend product model

Yire is a payables and treasury control workspace. The interface is designed around the decisions a finance user needs to make, not the internal stages the backend executes.

## People and jobs

- AP Clerk: uploads invoices and prepares payout batches.
- Treasury Controller: reviews exceptions and approves policy overrides.
- Chief Treasurer: authorizes and releases payouts.
- Auditor: verifies controls, accounting balance, bank proof, and signed evidence.

## Inputs

- Invoice or credit-note PDFs and ZIP batches.
- Purchase orders and goods-receipt quantities.
- Supplier identity, tax, and masked bank details.
- Exception-resolution action and an accountable reason.
- Role, organization, and idempotency context for payout requests.

## Outputs shown to users

- Needs review: a bill is blocked and the user can see why and what to do next.
- Ready to pay: checks passed, but money has not moved.
- Paid: the backend recorded settlement or a bank UTR. Approval alone never counts as paid.
- Amount to pay: invoice gross less tax withheld and supplier credits.
- Tax to deposit and GST held for verification.
- Audit trail, accounting export, and signed evidence for verification.

## Display rules

- The treasury balance is labelled as planning capacity because it is configured by the backend and is not a live bank feed.
- Technical standards remain available in detail views and downloads, not in the primary decision surface.
- Empty and unavailable data is shown honestly. The frontend does not create demo suppliers, payments, UTRs, or payout batches when the API returns no data.
- The visual system uses macOS-style neutral layers, system typography, thin edge shadows, restrained blue action accents, and blur only on navigation/tool surfaces.
- KPI cards and the payment flow adapt Amicro's mono-rounded patterns to this dependency-free frontend and are driven by API values.
- Motion uses transitions.dev number pop-in, sliding-tab, and text-reveal patterns with full reduced-motion support.
