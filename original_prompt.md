<USER_REQUEST>
/ui-ux-pro-max /ui-styling and  FRONTEND DESIGN FOR AUTONOMOUS ACCOUNTS PAYABLE & FINANCE PLATFORM also use the skills 

You are acting as a:

* Principal Product Designer
* Enterprise UX Designer
* Senior Frontend Engineer
* Financial Systems UX Architect
* Accessibility Engineer
* Product Manager
* Design Systems Engineer

You are designing and implementing the frontend for an EXISTING Autonomous Accounts Payable & Statutory Finance Agent.

The backend is already sophisticated and hardened.

The frontend must make that complexity:

CLEAR
SIMPLE
TRUSTWORTHY
ACTIONABLE

The frontend must NOT expose backend complexity simply because it exists.

The product should feel like:

> A clean enterprise Accounts Payable operating system where users can manually submit financial documents, understand what the system decided, resolve exceptions, approve transactions, release payments, and independently audit every decision.

---

# 1. PRIMARY DESIGN PRINCIPLE

The backend is complex.

The frontend must not be.

Every screen should answer ONE primary question.

The user should never need to understand terms such as:

CAS
OCC
CFDS
Merkle DAG
transactional outbox
idempotency key
canonical serialization
provider request hash

unless they intentionally open advanced auditor/forensic information.

Use plain business language first.

Technical evidence belongs behind progressive disclosure.

---

# 2. VISUAL LANGUAGE

The interface must be:

* light
* professional
* enterprise-oriented
* calm
* trustworthy
* modern
* minimal

DO NOT use dark mode as the default design.

DO NOT use emojis anywhere in the professional product interface.

Do NOT use emoji status indicators.

Use:

* restrained line icons
* subtle borders
* clear typography
* whitespace
* compact tables
* professional badges
* neutral surfaces
* one controlled accent color
* red only for serious action/blocking/error
* amber for review/warning
* green sparingly for confirmed completion

Avoid:

* oversized cards everywhere
* gradients
* gaming-style UI
* neon colors
* excessive shadows
* glassmorphism
* decorative dashboards
* crypto/AI visual clichés
* unnecessary animations

---

# 3. INFORMATION DENSITY

This is an enterprise financial product.

Desktop is primary.

Optimize for approximately:

1280px–1600px desktop widths

but keep it responsive for tablet and mobile.

Use:

tables for operational queues

drawers for quick inspection

detail pages for deep work

tabs for related information

Do not turn every table row into a giant card.

---

# 4. KEEP TOP-LEVEL NAVIGATION TO SIX AREAS

The main application navigation must contain ONLY:

1. Command Center
2. Ingestion
3. AP Workspace
4. Exceptions & Approvals
5. Treasury
6. Auditor

Settings/system configuration should live under:

Settings / Admin

rather than becoming another major navigation destination.

Final sidebar concept:

YIRE

Command Center

Ingestion

AP Workspace

Exceptions & Approvals

Treasury

Auditor

---

Settings

Use professional line icons only.

No emojis.

---

# 5. GLOBAL HEADER

The top header should include:

* current page title
* global search
* `+ Add` button
* environment indicator where needed
* notifications
* user/profile menu

Global search placeholder:

"Search invoice, vendor, PO, GRN, payment or UTR"

Do not display raw database IDs unless helpful.

---

# 6. GLOBAL + ADD BUTTON

The `+ Add` button must be accessible from every primary screen.

Clicking it opens:

Add to YIRE

Upload Documents
Invoice
Purchase Order
Goods Receipt
Credit Note
Vendor

No emoji icons.

Use simple line icons.

All creation flows feed the existing backend.

Do not duplicate business logic in frontend forms.

---

# 7. INPUT SCOPE — MANUAL INGESTION ONLY

For the current release:

MANUAL INGESTION ONLY.

Implement:

* drag-and-drop file upload
* file chooser
* manual invoice entry
* manual PO entry
* manual GRN/goods receipt entry
* manual credit note entry
* manual vendor entry
* supporting document upload

Do NOT implement:

* email inbox automation
* vendor email parsing
* vendor self-service portal
* ERP automatic sync
* SFTP
* Google Drive polling
* mailbox monitoring

These can be future roadmap features.

Do not clutter the current interface with non-functional future integrations.

---

# 8. SCREEN 1 — COMMAND CENTER

Purpose:

> What is happening in Accounts Payable right now, and what requires attention?

This is the landing page.

Do NOT make it overly analytical.

---

## TOP KPI STRIP

Show approximately five concise KPIs:

Open Payables
Ready to Pay
Awaiting Approval
Exceptions
Needs Reconciliation

Example:

Open Payables
₹2.48 Cr

Ready to Pay
₹41.2 L

Awaiting Approval
12

Exceptions
7

Needs Reconciliation
1

Avoid huge oversized cards.

Keep them horizontally compact.

---

## NEEDS ATTENTION

This should be the most important section.

Show only actionable items.

Example:

Payment outcome needs verification
PAY-482
₹4,80,000
Waiting for bank confirmation

[Review]

PO amount exceeds allowed variance
INV-392
₹1,18,000

[Review]

Vendor bank details require verification
INV-441

[Review]

Avoid backend jargon such as:

AMBIGUOUS_STATE
PO_VARIANCE_BREACH
BANK_TRUST_LEVEL_FAILURE

Translate them.

Examples:

`AMBIGUOUS`
→
"Payment outcome needs verification"

`PO_VARIANCE_BREACH`
→
"Invoice price exceeds PO tolerance"

`SIMULATION_TRUST_REJECTED`
→
"Production bank verification required"

---

## AP PIPELINE

Show a compact status pipeline:

Uploaded
Processing
Matched
Approval
Ready to Pay
Paid

Use counts.

Clicking a stage should filter AP Workspace.

---

## UPCOMING CASH

Show:

Today
Next 7 Days
Next 30 Days

with total payment obligations.

Keep it simple.

Do not create a treasury forecasting application on this page.

---

# 9. SCREEN 2 — INGESTION

Purpose:

> Add financial documents and records to the system.

This should be simple and welcoming.

---

## MAIN UPLOAD AREA

Large central upload area:

Add Documents

Drag and drop files here

or

[ Choose Files ]

Show actual supported formats.

Example:

PDF, PNG, JPG, ZIP

Only show CSV/XLSX if backend actually supports them.

---

## DOCUMENT TYPE

Default:

Auto Detect

Options:

Invoice
Purchase Order
Goods Receipt
Credit Note
Supporting Document

Auto Detect should be the default where backend classification supports it.

---

## UPLOAD QUEUE

After selection show:

File Name
Detected Type
Vendor
Status
Action

Example:

acme-invoice-482.pdf
Invoice
Acme Technology
Ready

[Review]

---

## PROCESSING STATES

Translate backend processing into business wording.

Use:

Uploading
Reading document
Checking vendor
Matching PO and receipt
Calculating taxes
Checking for duplicates
Ready for review
Needs attention

Do NOT show:

OCR_PIPELINE_STAGE_4
VECTOR_EXTRACTION
RULE_ENGINE_EXECUTION

---

# 10. MANUAL INVOICE FORM

Fields should include only user-enterable inputs actually needed by backend.

Possible layout:

Invoice Number
Vendor
Invoice Date
Due Date
Currency

Line Items

Description
Quantity
Unit Price
GST Rate
Amount

Purchase Order
Goods Receipt

Supporting Document

[Save Draft]
[Submit for Processing]

The frontend may calculate visual subtotal previews for convenience only if clearly non-authoritative.

The backend remains authoritative for financial calculation.

---

# 11. MANUAL PURCHASE ORDER FORM

Fields:

PO Number
Vendor
PO Date
Currency

Line Items:

Description
Quantity
Unit Price
Tax if required

Authorized Total

Supporting Document

Buttons:

[Save Draft]
[Create Purchase Order]

Do not mix receipt information into the PO form.

---

# 12. MANUAL GOODS RECEIPT FORM

Use clear language:

Goods Receipt

Purchase Order
Receipt Date

Line Items:

Item
Ordered
Received
Accepted
Rejected

Buttons:

[Save Draft]
[Record Receipt]

Do not expose internal allocation IDs.

---

# 13. MANUAL CREDIT NOTE FORM

Fields:

Credit Note Number
Vendor
Related Invoice if applicable
Date
Credit Type
Amount
Reason
Supporting Document

Use understandable credit categories.

Do not expose backend enum names directly if they are technical.

---

# 14. MANUAL VENDOR FORM

Vendor Name
Legal Name
PAN
GSTIN
Address
Contact
Bank Details

Bank changes must be clearly identified as sensitive.

If bank verification exists, do NOT label an unverified manually entered account as verified.

Show:

Verification required

until backend confirms otherwise.

---

# 15. SCREEN 3 — AP WORKSPACE

Purpose:

> View and manage all Accounts Payable records.

This screen replaces separate invoice, PO, GRN and vendor dashboards.

Use four tabs:

Invoices
Purchase Orders
Goods Receipts
Vendors

Default:

Invoices

---

# 16. AP WORKSPACE — INVOICE TABLE

Use a professional data table.

Columns:

Invoice
Vendor
Amount
Due Date
Match
Tax
Approval
Status

Example:

INV-482
Acme Ltd
₹1.18 L
12 Sep
Matched
Checked
Awaiting Approval
Approval

Filters:

All
Needs Attention
Processing
Awaiting Approval
Ready to Pay
Paid

Advanced filters:

Vendor
Amount
Due Date
TDS Section
PO
Risk
Payment Status

---

# 17. INVOICE QUICK DRAWER

Clicking a row should open a right-side drawer.

Show:

Invoice number
Vendor
Amount
Due date
PO
GRN
Current status
Main exception if any

Buttons:

[Open Invoice]
[View Document]

Do not overload the drawer.

---

# 18. FULL INVOICE DETAIL PAGE

This is the flagship product screen.

Header:

INV-482

Acme Technology Pvt Ltd

₹1,18,000

Due 12 Sep 2026

Current status:
Ready for Approval

Linked:
PO-93821
GRN-3321

Tabs:

Overview
Matching
Tax & Credits
Accounting
Payment
Audit

---

# 19. INVOICE OVERVIEW TAB

Show a clear financial waterfall.

Example:

Base Amount                 ₹1,00,000
GST                            ₹18,000
--------------------------------------

Gross                        ₹1,18,000

TDS                            -₹2,000
Credit Applied                 -₹5,000
Retention                           ₹0
--------------------------------------

Net Payable                  ₹1,11,000

Use:

Net Payable

not:

PAYMENT_ECONOMIC_OBLIGATION_FINAL_MINOR_UNITS

---

## PIPELINE STATUS

Display:

Document
Duplicate Check
PO / Receipt Match
Tax Check
Approval
Payment

Use a clean progress line.

Example:

Document      Complete
Duplicate     Clear
Matching      Complete
Tax           Complete
Approval      Waiting
Payment       Not Started

Clicking a stage may navigate to corresponding tab.

---

# 20. MATCHING TAB

Purpose:

> Explain whether the invoice agrees with the purchase order and goods received.

Show:

Purchase Order
PO-93821
Matched

Goods Receipt
GRN-3321
Matched

Quantity:

Ordered
100

Received
80

Previously Invoiced
60

This Invoice
15

Remaining
5

Price:

PO Rate
₹1,000

Invoice Rate
₹1,000

Difference
₹0

Allowed Difference
2%

Use:

"Price difference"

instead of:

"TOLERANCE_COMPUTATION"

If mismatch:

Invoice price is 5% above the purchase order.
Allowed difference is 2%.

Payment is currently blocked.

---

# 21. TAX & CREDITS TAB

Show:

TDS

Section
194J

Description
Technical Services

Rate
2%

Taxable Amount
₹1,00,000

TDS
₹2,000

GST

GST
₹18,000

GSTR-2B
Matched

Credits

CN-291
₹5,000 applied

Remaining Credit
₹2,000

Retention if applicable.

Use plain English explanatory text.

---

# 22. ACCOUNTING TAB

Show generated accounting output.

Example:

Journal JRN-92822

Professional Expense
Debit ₹1,00,000

Input GST
Debit ₹18,000

Vendor Payable
Credit ₹1,18,000

Status:

Balanced

Accounting checks passed

Posted

If a journal has been corrected:

Original Journal
→
Reversal
→
Replacement

Never visually overwrite the original.

---

# 23. PAYMENT TAB

Show:

Payment Intent
PAY-82912

Net Payable
₹1,11,000

Payment Method
IMPS

Bank
HDFC
Account ending 8921

Bank Verification
Verified for production

Payment Policy
2026.2

Status
Ready for Payment

Do NOT show full bank account number by default.

Do NOT show provider idempotency keys to ordinary users.

---

# 24. AUDIT TAB INSIDE INVOICE

Normal business view:

Decision Integrity

Invoice evidence
Verified

PO / Receipt evidence
Verified

Accounting
Validated

Policy versions
Recorded

Signature
Valid

Button:

[View Forensic Evidence]

Only then display technical cryptographic details.

---

# 25. PURCHASE ORDERS TAB

Table columns:

PO
Vendor
Authorized Amount
Invoiced
Remaining
Status

Click PO.

Detail:

Authorized quantity
Received quantity
Invoiced quantity
Remaining quantity

Linked invoices
Linked receipts
Revision history

Do not create another top-level dashboard.

---

# 26. GOODS RECEIPTS TAB

Columns:

Receipt
PO
Vendor
Received
Accepted
Already Invoiced
Available
Status

Detail view should clearly show:

Received
Accepted
Rejected
Previously invoiced
Available to invoice

---

# 27. VENDORS TAB

Columns:

Vendor
Open Payables
Paid YTD
Bank Status
Risk

Vendor detail tabs:

Overview
Invoices
Purchase Orders
Bank
Credits
History

Show sensitive bank changes prominently.

Example:

Bank account changed
2 Sep 2026

Verification pending

Do not automatically label manual changes safe.

---

# 28. SCREEN 4 — EXCEPTIONS & APPROVALS

Purpose:

> Resolve anything that prevented automatic processing and complete maker-checker approvals.

Combine exceptions and approvals.

Tabs:

Needs Review
Awaiting My Approval
Resolved

---

# 29. NEEDS REVIEW

Each item should explain:

What happened?
Why did the system stop?
What does the user need to do?

Example:

Invoice price exceeds purchase order

Invoice Rate
₹1,050

PO Rate
₹1,000

Difference
5%

Allowed
2%

System action:
Payment blocked

Actions:

[Request Correction]
[Reject Invoice]
[Send for Override Approval]

Use plain language.

---

# 30. APPROVAL VIEW

Example:

Exception Approval

Invoice
INV-392

Vendor
ABC Ltd

Amount
₹7,80,000

Reason:
Price exceeds purchase order tolerance

Requested by:
Rahul Sharma

Supporting evidence:
PO Amendment.pdf

You are the checker.

Buttons:

[Reject]
[Request Information]
[Approve Override]

Do not allow frontend role manipulation to bypass maker-checker.

Backend remains authoritative.

---

# 31. OVERRIDE UX

Overrides should always display:

Reason
Evidence
Requested by
Approved by
Scope
Timestamp

Never silently convert an override into ordinary approval.

---

# 32. SCREEN 5 — TREASURY

Purpose:

> Release approved payments and reconcile payment outcomes.

Tabs:

Ready to Pay
Processing
Reconciliation
Settled

---

# 33. READY TO PAY

Table:

Vendor
Invoice
Amount
Due
Payment Method
Bank Status

Example:

Acme Ltd
INV-482
₹1.11 L
Today
IMPS
Verified

Click row.

Show release summary:

Vendor
Invoice
Amount
Bank
Payment Method
Accounting
Approval
Tax
Payment Policy

Checklist:

Bank verified
Approvals complete
Accounting posted
Tax checks complete

Button:

[Release Payment]

The button submits a backend command.

Frontend does NOT decide eligibility.

---

# 34. PROCESSING

Show:

Payment
PAY-8291

Vendor
Acme

Amount
₹1,11,000

Status:
Submitted to bank

Submitted:
12:42

Avoid showing raw provider JSON.

---

# 35. RECONCILIATION

Critical UX.

If backend payment state is:

UNKNOWN
AMBIGUOUS

show:

Payment outcome needs verification

The payment request may have reached the bank, but the final result has not yet been confirmed.

Do not create another payment.

Amount
₹4,80,000

Submitted
14:42

Current action
Waiting for authoritative bank confirmation

Button:

[Reconcile Payment]

NEVER show:

[Pay Again]

for an unresolved ambiguous payment.

---

# 36. SETTLED

Show:

Payment
PAY-8291

Amount
₹1,11,000

Status
Settled

UTR
HDFC829271827

Settled
5 Sep 2026, 12:43

Allow:

[View Invoice]
[View Audit Record]

---

# 37. SCREEN 6 — AUDITOR

Purpose:

> Independently verify that transactions, controls, accounting, approvals and evidence are operating correctly.

Auditor should be read-only by default.

Auditor actions should include:

Inspect
Verify
Filter
Replay
Export
Raise Finding

Auditor should NOT see:

Pay
Release Payment
Edit Journal
Delete
Modify Signed Record

---

# 38. AUDITOR TABS

Use four tabs:

Overview
Transactions
Controls
Forensic Evidence

Historical replay should be available from a transaction.

---

# 39. AUDITOR OVERVIEW

Show concise audit health metrics.

Examples:

Transactions Reviewed
1,284

Cryptographic Evidence Valid
100%

Balanced Journals
100%

Policy Version Resolved
100%

Open Audit Findings
3

Historical Replay Mismatches
0

Do not create fake 100% values.

These must come from backend evidence.

---

# 40. CONTROL HEALTH

Show controls such as:

Payment duplicate prevention
Healthy

Credit conservation
Healthy

PO allocation
Healthy

Goods receipt allocation
Healthy

Maker-checker
Healthy

Webhook verification
Healthy

Posted journal immutability
Healthy

Historical replay
Healthy

Click a control to see evidence.

Do not expose raw test terminology first.

---

# 41. AUDITOR TRANSACTIONS

Searchable table:

Invoice
Vendor
Amount
Decision
Evidence
Payment

Filters:

Vendor
Date
TDS Section
Policy Version
Override Used
Payment State
Signature Status
Bank Verification

Click transaction → Audit Record.

---

# 42. AUDIT RECORD

Header:

INV-482

Audited & Admissible

Vendor
Acme Technology

Gross
₹1,18,000

Net Payout
₹1,11,000

UTR
HDFC...

Then show:

Invoice Evidence
Verified

Vendor Identity
Verified

PO Match
Verified

Goods Receipt Match
Verified

TDS
194J — 2%

GSTR-2B
Matched

Credits
Validated

Accounting
Validated

Bank Verification
Production Verified

Maker-Checker
Complete

Payment
Settled

---

# 43. AUDITOR FINANCIAL RECONCILIATION

Show the financial conservation clearly.

Example:

Approved Obligation             ₹1,18,000

Cash Paid                       ₹1,11,000
TDS Withheld                       ₹2,000
Credit Applied                     ₹5,000
Retention                              ₹0
-----------------------------------------

Total                           ₹1,18,000

Result:
Financial reconciliation verified

This is easier to understand than exposing mathematical invariant names.

---

# 44. AUDITOR PROCUREMENT CHECK

Example:

PO Authorized
100

Goods Accepted
80

Previously Invoiced
60

Current Invoice
15

Remaining
5

Result:

Purchase order not over-allocated

Goods receipt not over-allocated

---

# 45. AUDITOR ACCOUNTING CHECK

Show:

Debits
₹1,18,000

Credits
₹1,18,000

Result:

Balanced

Accounting treatment validated

Posted record unchanged

---

# 46. AUDIT CONTROLS TAB

Show operating controls with actual runtime evidence.

Example:

Duplicate Payment Prevention

Transactions checked
1,284

Duplicate economic payments
0

Status
Operating normally

Credit Conservation

Credits checked
421

Over-consumption
0

Status
Operating normally

Do not use green status purely because tests passed once.

Use real available system evidence.

---

# 47. AUDIT FINDINGS

Allow auditor:

[Raise Finding]

Form:

Transaction
Severity
Category
Finding
Supporting Evidence

States:

Open
Acknowledged
Remediated
Verified
Closed

Finding must be separate from the immutable transaction.

Auditor finding must NOT mutate financial history.

---

# 48. FORENSIC EVIDENCE

Keep advanced evidence behind:

[View Forensic Evidence]

Show:

Serialization Profile
CFDS-v1

Invoice Document Hash
Decision Hash
Provider Request Hash
Previous Event Hash

Signature
Valid

Algorithm
Ed25519

Key ID
Key Version

Signed At

Policy Versions:

Matching Policy
Tax Policy
Payment Policy
Accounting Policy

Use monospace formatting only for hashes/technical IDs.

---

# 49. HISTORICAL REPLAY

Available from audit record:

[Replay Decision]

Modes:

Historical Replay
What-If

Historical Replay:

Uses original vendor state, PO, receipt, policies and evidence.

Show:

Original Result
₹1,11,000

Replay Result
₹1,11,000

Result:
Exact Match

What-If:

Clearly display:

SIMULATION ONLY

Cannot authorize a production payment.

Do not allow What-If output to look identical to production authorization.

---

# 50. AUDIT EXPORT

Button:

[Export Audit Package]

Future/implemented output may include:

Invoice
PO
Goods Receipt
Credit Notes
Decision Summary
Tax Calculation
Journal
Payment Record
UTR
Policy Versions
Bank Verification
Override Evidence
Decision Hash
Signature
Timeline

Only expose export formats actually supported.

---

# 51. SETTINGS / ADMIN

Keep outside main navigation.

Possible tabs:

Policies
System Health
Environment
Users & Roles

This is not a seventh operational dashboard.

---

# 52. SYSTEM HEALTH

Simple admin view:

Firestore
Healthy

RazorpayX
Test / Live configuration state

KMS
Connected

Document Processing
Healthy

Outbox Worker
Healthy

Reconciliation
Healthy

Webhook
Healthy

Avoid exposing low-level logs by default.

---

# 53. STATUS LANGUAGE TRANSLATION

Build a frontend mapping layer.

Examples:

SUBMISSION_PENDING
→
Preparing payment

SUBMITTED
→
Submitted to bank

SETTLED
→
Paid

AMBIGUOUS / UNKNOWN
→
Payment outcome needs verification

PO_VARIANCE_BREACH
→
Invoice price exceeds purchase order allowance

NAME_MATCH_AMBIGUITY
→
Vendor identity requires review

BANK_TRUST_MISSING
→
Bank verification required

WEBHOOK_SIGNATURE_INVALID
→
Bank notification could not be verified

Do not show raw enum strings unless advanced/debug view.

---

# 54. NO FRONTEND FINANCIAL AUTHORITY

Critical architecture rule:

The frontend is NOT the financial decision engine.

Do NOT calculate authoritative:

TDS
GST
credits
retention
PO allocation
GRN allocation
payment eligibility
accounting
policy selection

in browser code.

Frontend may display estimates/previews only when clearly labeled.

Authoritative values come from backend.

---

# 55. BACKEND COMMAND MODEL

Sensitive buttons should issue backend commands.

Examples:

Approve Invoice
Reject Invoice
Approve Override
Release Payment
Reconcile Payment
Raise Audit Finding

Backend must revalidate:

authentication
role
state
version
preconditions
maker-checker
financial invariants

Never trust the browser because a button was hidden.

---

# 56. OPTIMISTIC UI

Avoid optimistic UI for irreversible financial actions.

For payment release:

Button clicked
→ show "Submitting"
→ wait for authoritative backend response

Do NOT immediately show "Paid".

For approvals:

wait until backend confirms transition.

---

# 57. DOCUMENT VIEWER

For invoice review, use a split view where possible:

Left:
uploaded document

Right:
extracted fields and decision summary

Clicking an extracted value may highlight its source location if backend provides lineage.

This is valuable for explainable AI.

Do not fabricate bounding boxes if backend does not expose them.

---

# 58. TIMELINE

Every invoice should have an activity timeline.

Example:

10:21
Invoice uploaded

10:22
Vendor identified

10:22
Purchase order matched

10:22
Tax calculated

11:04
Submitted for approval

11:17
Approved

11:20
Accounting posted

11:21
Payment submitted

11:22
Payment settled

Use human-friendly wording.

---

# 59. NOTIFICATIONS

Professional notification center.

Examples:

Invoice INV-391 requires your approval.

Payment PAY-293 needs reconciliation.

Vendor bank details changed.

Payment PAY-313 settled.

Do not use emojis.

Route by user role.

---

# 60. ROLE-BASED DEFAULTS

AP Analyst
→ AP Workspace

Approver
→ Exceptions & Approvals

Treasury
→ Treasury

Auditor
→ Auditor

Admin
→ Command Center / Settings

Do not duplicate entire applications.

Same interface structure, different default screen and permissions.

---

# 61. RESPONSIVE DESIGN

Desktop:

full sidebar
tables
drawers
split document view

Tablet:

collapsible sidebar
reduced table columns
drawers

Mobile:

navigation drawer
critical cards/rows
simplified details

Do not attempt to show 12-column enterprise tables unchanged on mobile.

Use responsive row/card transformation where required.

---

# 62. ACCESSIBILITY

Implement:

* keyboard navigation
* visible focus states
* semantic HTML
* accessible form labels
* sufficient color contrast
* status not indicated by color alone
* screen-reader-friendly error messages

Do not use icons without text for critical actions.

---

# 63. BUTTON HIERARCHY

Use consistent actions.

Primary:

Submit
Approve
Release Payment
Reconcile Payment
Save

Secondary:

Review
View Document
Request Information
Export

Destructive:

Reject
Cancel

Do not use ambiguous labels like:

Execute
Run
Proceed

when a specific business action can be named.

---

# 64. CONFIRMATION FOR HIGH-RISK ACTIONS

Require clear confirmation for:

Release Payment
Approve Override
Reject Invoice
Change Vendor Bank Details
Close Audit Finding where appropriate

Example:

Release ₹4,80,000 to Acme Technology?

Bank:
HDFC ending 8921

Invoice:
INV-482

[Cancel]
[Release Payment]

Do not rely on generic:

"Are you sure?"

---

# 65. ERROR MESSAGES

Errors should explain:

What happened
What remains safe
What user can do

Bad:

PAYMENT_STATE_TRANSITION_409

Good:

This payment cannot be released because it is already being processed.

No second payment has been created.

[View Payment]

---

# 66. EMPTY STATES

Examples:

No exceptions require attention.

No payments require reconciliation.

No invoices have been uploaded yet.

[Add Documents]

Keep empty states professional.

No cartoons or emojis.

---

# 67. DESIGN SYSTEM

Create reusable components:

AppShell
Sidebar
TopHeader
Metric
StatusBadge
DataTable
FilterBar
SearchInput
Drawer
Tabs
DetailHeader
FinancialWaterfall
PipelineStatus
Timeline
DocumentViewer
ApprovalPanel
ConfirmationDialog
AuditControlCard
FindingPanel
EmptyState
LoadingState
ErrorState

Do not build one-off inconsistent components for every page.

---

# 68. EXISTING STACK

Inspect the existing frontend.

Preserve its technology stack unless there is a confirmed blocking limitation.

If the repository currently uses:

HTML
Tailwind CSS
Vanilla JavaScript

continue using that stack.

Do NOT migrate to React/Vue/Next/etc. merely for preference.

If the existing application already uses another framework, preserve it.

---

# 69. DATA LOADING

Use backend APIs as authoritative sources.

Create clean client service functions.

Handle:

loading
success
empty
error
authorization failure
stale state/version conflict

If backend reports version conflict:

refresh current state
explain that the record changed
do not overwrite silently

---

# 70. FRONTEND PERFORMANCE

Use:

pagination
server-side filtering where appropriate
lazy loading of forensic evidence
lazy loading of large documents

Do not load the entire invoice database onto Command Center.

---

# 71. PROFESSIONAL COPY STYLE

Use concise finance language.

Examples:

"Ready for Payment"

"Requires Approval"

"Bank Verification Required"

"Purchase Order Matched"

"Payment Outcome Needs Verification"

Avoid:

"AI thinks..."
"Robot verified..."
"Blockchain secured..."
"Ultra secure..."
"100% safe..."

Do not overclaim.

---

# 72. REMOVE EMOJIS

This is explicit.

Do NOT use:

check mark emojis
warning emojis
money emojis
robot emojis
shield emojis
colored-circle emojis

Use:

professional icons
badges
text labels

Examples:

Status: Verified
Status: Needs Review
Status: Blocked

---

# 73. DO NOT CLUTTER THE UI WITH BACKEND FEATURES

Do not display:

Firestore document IDs
Pub/Sub IDs
transaction lock IDs
provider idempotency key
raw signature
raw webhook body
hash chains

on normal finance screens.

These belong only in advanced forensic/admin views.

---

# 74. FINAL USER JOURNEY

The frontend must support this story cleanly:

1. User manually uploads invoice / PO / receipt / credit note.
2. System processes document.
3. AP Workspace shows extracted and matched information.
4. User understands financial waterfall.
5. System either:

   * clears invoice, or
   * creates an understandable exception.
6. Exception is resolved.
7. Maker/checker approval completes.
8. Accounting becomes visible.
9. Treasury sees payment ready.
10. Payment is released.
11. Bank status becomes visible.
12. UNKNOWN payment enters reconciliation rather than "Pay Again."
13. Settled payment displays UTR.
14. Auditor independently verifies transaction and evidence.
15. Transaction closes.

---

# 75. IMPLEMENTATION ORDER

Build in this order:

Phase 1
App shell
navigation
design system
global search

* Add

Phase 2
Command Center

Phase 3
Ingestion
manual forms
upload flow

Phase 4
AP Workspace
invoice table
invoice detail
PO/GRN/vendors

Phase 5
Exceptions & Approvals

Phase 6
Treasury
reconciliation

Phase 7
Auditor

Phase 8
Settings/System
responsive behavior
accessibility
final polish

Do not redesign everything simultaneously.

---

# 76. FRONTEND TESTING

Add tests for critical user flows:

Manual invoice upload

Manual PO creation

Manual GRN creation

Invoice detail

Exception resolution

Maker-checker

Ready-to-pay flow

Payment release confirmation

UNKNOWN payment has NO "Pay Again" action

Reconciliation

Auditor transaction inspection

Historical replay vs What-If visual separation

Role-based access

Keyboard navigation

Responsive layout

No duplicate payment due to repeated UI click

---

# 77. DOUBLE-CLICK / REPEAT ACTION PROTECTION

Disable/restrict repeated submission while command is in flight.

Example:

[Release Payment]

clicked once:

[Submitting...]

Do not permit repeated clicks to create repeated backend commands.

Backend idempotency remains authoritative.

Frontend protection is secondary UX defense.

---

# 78. FINAL DESIGN REVIEW

Before completion inspect every page and ask:

Does this page have one clear purpose?

Can a finance professional understand it without knowing backend architecture?

Is critical information visible?

Is technical detail hidden until requested?

Are actions obvious?

Are dangerous actions clearly distinguished?

Is any information duplicated across multiple dashboards unnecessarily?

Are there emojis?

Is there unnecessary visual decoration?

Can the workflow be completed without jumping through many screens?

---

# 79. REQUIRED FINAL DELIVERABLE

Provide:

## A. Screen Map

Six screens and routes.

## B. Component Map

Reusable components.

## C. API Mapping

Which backend endpoint powers each component.

## D. Role Matrix

Who can view/act.

## E. Status Translation Map

Backend state → plain-language UI wording.

## F. Manual Input Flow

Invoice
PO
GRN
Credit Note
Vendor

## G. User Action Map

Every primary button and backend command.

## H. Responsive Behavior

## I. Accessibility

## J. Tests

Commands and results.

## K. Screenshots / Visual Verification

Desktop
tablet
mobile

where tooling supports it.

---

# FINAL PRODUCT PRINCIPLE

The backend should feel powerful.

The frontend should feel simple.

The user should understand:

WHAT HAPPENED
WHY IT HAPPENED
WHAT NEEDS ATTENTION
WHAT ACTION IS AVAILABLE
WHAT MONEY WILL MOVE
WHETHER IT WAS SUCCESSFUL
HOW IT CAN BE AUDITED

without needing to understand the distributed-systems architecture underneath it.

Six screens maximum.

Manual ingestion now.

Automation later.

Professional enterprise design.

Light interface.

No emojis.

No technical clutter.

No financial logic duplicated in the browser.

Backend remains the source of truth.

</USER_REQUEST>
<ADDITIONAL_METADATA>
The current local time is: 2026-09-05T14:15:39+05:30.

The user has mentioned some items in the form @[ITEM]. Here is extra information about the items that were mentioned by the user, in the order that they appear:

/ui-ux-pro-max is a [Slash Command]:
<SKILL>The user requested you read and use the "ui-ux-pro-max" skill. The path to the skill file is:
e:\antigravity\test1\.agent\skills\ui-ux-pro-max\SKILL.md</SKILL>
/ui-styling is a [Slash Command]:
<SKILL>The user requested you read and use the "ui-styling" skill. The path to the skill file is:
e:\antigravity\test1\.agent\skills\ui-styling\SKILL.md</SKILL>
</ADDITIONAL_METADATA>
<USER_SETTINGS_CHANGE>
The user changed setting `Model Selection` from Gemini 3.8 Flash (Medium) to Gemini 3.8 Flash (High). No need to comment on this change if the user doesn't ask about it. If reporting what model you are, please use a human readable name instead of the exact string.
</USER_SETTINGS_CHANGE>