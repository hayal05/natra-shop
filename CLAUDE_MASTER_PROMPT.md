# NATRA — MASTER DEVELOPMENT PROMPT

You are developing **NATRA**, a multi-seller digital products marketplace.

Build NATRA incrementally. **Do NOT build the entire application at once.**

---

## 1. FINAL PRODUCT VISION

NATRA will eventually have three roles:

### BUYER

Buyers do NOT create accounts.

No:

* Email
* Phone number
* Password
* Buyer login
* Cart

Buyer flow:

1. Open NATRA
2. Browse products
3. Open product details
4. Click **Buy Now**
5. See NATRA's CBE/Telebirr payment information
6. Make payment
7. Paste payment receipt URL
8. NATRA verifies the receipt
9. After successful verification, buyer receives/accesses the seller's public Google Drive product link

The payer name may be extracted from the receipt, but **must never be used as a unique identifier**.

---

## 2. SELLER

Sellers must create accounts.

Authentication:

* Email/password
* Google login may be added later

Seller will eventually have:

* Dashboard
* Products

  * Add Product
  * Listed Products
* Payment Method

  * CBE
  * Telebirr
* Earnings
* Settings

Seller product information:

* Product name
* Category
* Description
* Price
* Thumbnail
* Public Google Drive delivery link

Seller profile pictures will be stored in **Oracle Object Storage**.

Sellers upload their actual digital products to their own Google Drive.

NATRA stores the specific public Google Drive delivery link.

NATRA does NOT need:

* Seller Google password
* Access to the seller's entire Google Drive
* Google Drive OAuth
* Google Drive API

unless explicitly required in a future phase.

---

## 3. MASTER ADMIN

The Master Admin will eventually have:

* Dashboard
* Products Management
* Sellers
* Default Payment Methods

  * CBE
  * Telebirr
* Settlements
* Commissions
* Settings

Admin capabilities eventually include:

* View products
* View sellers
* Suspend sellers
* Remove sellers
* Set NATRA's CBE payment account
* Set NATRA's Telebirr payment account
* View sales
* View revenue
* View commissions
* View unsettled seller balances
* Manage commission rate
* Manage seller settlements

---

## 4. PAYMENT ARCHITECTURE

**BUYERS PAY NATRA, NOT SELLERS.**

The CBE and Telebirr accounts displayed to buyers belong to NATRA/Master Admin.

Seller payment information is used later for seller settlements and is NOT shown to buyers as the payment destination.

Example:

Product price = 500 ETB

Commission = 10%

NATRA commission = 50 ETB

Seller payable amount = 450 ETB

The 500 ETB is collected by NATRA.

After successful payment verification:

* Record gross sale
* Calculate/record NATRA commission
* Record seller payable balance
* Later, Master Admin manually pays the seller
* Admin marks the settlement as completed

Commission and settlement functionality are later-phase features.

---

# 5. PAYMENT RECEIPT VERIFICATION

In the final system, the buyer submits a payment receipt URL.

Examples:

Telebirr:
https://transactioninfo.ethiotelecom.et/receipt/...

CBE:
https://mbreciept.cbe.com.et/...

NATRA will retrieve and verify the receipt.

Use:

**Python + Playwright**

where browser automation is necessary.

Verification should eventually check:

* Payment provider
* Payment status
* Payment amount
* Transaction/reference number
* Invoice/receipt number where applicable
* Payment destination where available
* Payment date/details where relevant
* Duplicate payment

The actual transaction/reference/receipt identifier must be used for duplicate protection.

**Never use payer name as a unique payment identifier.**

Receipt verification is NOT part of Phase 1.

---

# 6. FIXED TECHNOLOGY STACK

These technologies are fixed unless the project owner explicitly changes them.

### Frontend

**React + TypeScript + Vite**

### Backend

**Python + FastAPI**

### Database

**Oracle Autonomous Database**

Use Python's:

**`oracledb`**

driver.

### Object Storage

**Oracle Object Storage**

Used for:

* Product thumbnails
* Seller profile pictures

### Receipt Verification

**Python + Playwright**

### Authentication

FastAPI with a secure JWT/session-based approach.

### Styling

CSS or Tailwind CSS.

### Production Server

**Oracle Cloud Free Tier Linux VM**

Use:

* Nginx
* Uvicorn
* FastAPI
* React production build

### Source Code

**Git + GitHub**

---

# 7. FIXED INFRASTRUCTURE

These decisions are fixed unless explicitly changed by the project owner.

### HOSTING

**Oracle Cloud Free Tier**

Do NOT design the project around:

* Render
* Vercel
* Netlify
* Firebase hosting
* Other hosting platforms

unless explicitly instructed.

### REPOSITORY

**GitHub**

The project must be able to:

1. Run locally
2. Be committed to GitHub
3. Be cloned from GitHub
4. Be deployed to Oracle Cloud Free Tier

Never depend on files that exist only on one local machine.

### DATABASE

**Oracle Autonomous Database**

This is the primary structured database.

### OBJECT STORAGE

**Oracle Object Storage**

Used for:

* Product thumbnails
* Seller profile pictures

Do not store image files directly inside the database.

### DIGITAL PRODUCT STORAGE

Actual digital products remain on the seller's own Google Drive.

NATRA stores the seller-provided public delivery link.

---

# 8. PHASE 1 — MINIMUM WORKING NATRA

Build ONLY the following.

## BUYER

1. Product homepage/grid
2. Product details
3. Buy Now
4. Show NATRA CBE/Telebirr payment information
5. Receipt URL input/submission

The homepage MUST be the product browsing page.

Products should appear in a clean grid.

No buyer account is required.

---

## SELLER

1. Register
2. Login
3. Add product
4. View own products

Phase 1 product fields:

* Name
* Price
* Description
* Thumbnail
* Public Google Drive link

---

## ADMIN

1. Admin login
2. View products
3. Set NATRA CBE payment information
4. Set NATRA Telebirr payment information

Keep the admin interface extremely simple.

---

# 9. DO NOT BUILD IN PHASE 1

Do NOT implement:

* Receipt verification
* Playwright verification
* Duplicate payment protection
* Commission calculation
* Seller earnings
* Seller settlements
* Buyer accounts
* Buyer email
* Buyer phone number
* Shopping cart
* Search
* Filters
* Notifications
* Reviews
* Messaging
* Advanced analytics
* Advanced dashboards
* Google Drive API
* Google Drive OAuth
* Recommendation systems
* Unnecessary integrations

If something is not required for Phase 1, leave it for later.

---

# 10. ONE SMALL TASK AT A TIME — CRITICAL RULE

Claude must handle **ONLY ONE small, clearly defined task per response/session step.**

A task must be small enough to:

* Implement in one manageable response
* Test easily
* Review easily
* Produce a limited number of code changes

### GOOD TASKS

Examples:

* Create the initial FastAPI project
* Configure Oracle database connection
* Create the users table/model
* Implement seller registration
* Implement seller login
* Create the product model
* Implement Add Product
* Create buyer product grid
* Create product details page
* Add admin payment settings

### BAD TASKS

Never combine:

* Entire seller system
* Entire buyer system
* Entire admin system
* Entire Phase 1
* Frontend + backend + database + authentication + deployment

into one response.

---

# 11. TASK COMPLETION RULE

After completing ONE task:

1. Test it.
2. Fix errors related to that task.
3. Update `CURRENT_STATUS.md`.
4. Explain what was completed.
5. State the next ONE small task.
6. STOP.

**Do NOT automatically start the next task.**

The next task must wait for the user's instruction.

---

# 12. DEVELOPMENT ORDER

Use this order unless explicitly changed.

### Task 1

Minimal project structure.

### Task 2

Backend starts successfully.

### Task 3

Frontend starts successfully.

### Task 4

Oracle database connection.

### Task 5

Initial database schema.

### Task 6

Seller registration.

### Task 7

Seller login.

### Task 8

Seller Add Product.

### Task 9

Seller View Products.

### Task 10

Buyer Product Grid.

### Task 11

Buyer Product Details.

### Task 12

Buy Now + NATRA payment information.

### Task 13

Receipt URL submission.

### Task 14

Admin login.

### Task 15

Admin product viewing.

### Task 16

Admin CBE/Telebirr settings.

### Task 17

Phase 1 integration testing.

Each item is a separate small task unless it is genuinely tiny enough to combine.

---

# 13. PROJECT MEMORY FILES

The GitHub repository MUST contain:

* `CLAUDE_MASTER_PROMPT.md`
* `PROJECT_ROADMAP.md`
* `CURRENT_STATUS.md`
* `ARCHITECTURE.md`
* `DATABASE_SCHEMA.md`
* `SETUP.md`

These files are part of the application project.

---

## CLAUDE_MASTER_PROMPT.md

Store this complete master prompt.

Do not shorten or remove the important rules.

---

## PROJECT_ROADMAP.md

Store the complete development roadmap:

### Phase 1

Basic marketplace foundation.

### Phase 2

Receipt verification + duplicate protection.

### Phase 3

Commission + seller earnings + settlements.

### Phase 4

Security + UI polish + production deployment.

---

## CURRENT_STATUS.md

After every completed task record:

* Current phase
* Completed task
* What works
* Files changed
* Database changes
* Errors encountered
* Fixes made
* Exact next small task

---

## ARCHITECTURE.md

Record:

* Current architecture
* Technologies
* Important technical decisions
* Data flow
* Storage architecture

---

## DATABASE_SCHEMA.md

Record:

* Current tables/models
* Fields
* Relationships
* Important constraints

Do not implement future database structures unnecessarily.

---

## SETUP.md

Record:

* Local setup
* Environment variables
* Oracle configuration
* Development commands
* Deployment instructions as they are developed

Never place real credentials in GitHub.

---

# 14. CONTINUATION RULE

NATRA will be developed across many Claude sessions.

At the beginning of every new session:

1. Read `CLAUDE_MASTER_PROMPT.md`
2. Read `PROJECT_ROADMAP.md`
3. Read `CURRENT_STATUS.md`
4. Inspect the existing code relevant to the current task
5. Continue from the existing project state

**DO NOT restart the project.**

**DO NOT rebuild completed features.**

**DO NOT unnecessarily replace working code.**

---

# 15. IF THE USER SAYS "CONTINUE"

If the user says:

**"Continue"**

read `CURRENT_STATUS.md` and perform ONLY the next ONE small task recorded there.

Then stop.

If the user says:

**"Continue Phase 1"**

still perform only ONE small task.

Do not build all remaining Phase 1 features.

---

# 16. PHASE CONTROL

Never automatically move to another phase.

If the user says:

**"Start Phase 2"**

begin Phase 2 one small task at a time.

If the user says:

**"Start Phase 3"**

begin Phase 3 one small task at a time.

Do not start future phases without explicit instruction.

---

# 17. TESTING RULE

Every task must be tested before being declared complete.

Do not claim that something works without testing it.

If a test fails:

* Fix the problem if it belongs to the current task.
* Do not start unrelated work.
* Record the problem and solution in `CURRENT_STATUS.md`.

---

# 18. CODE QUALITY

Prioritize:

1. Functionality
2. Correctness
3. Security
4. Maintainability
5. UI polish

Keep the codebase simple.

Avoid unnecessary:

* Libraries
* Abstraction
* Files
* Services
* APIs
* Features

Do not create future functionality prematurely.

---

# 19. GITHUB / PROJECT CONTINUITY

The project must remain portable.

The GitHub repository should contain all important project instructions and documentation needed to continue development.

The project must be understandable by another Claude session without relying on previous conversation history.

The combination of:

* `CLAUDE_MASTER_PROMPT.md`
* `PROJECT_ROADMAP.md`
* `CURRENT_STATUS.md`
* Existing source code

must provide enough context to continue development correctly.

---

# 20. FINAL PRODUCT ROADMAP

## PHASE 1 — BASIC MARKETPLACE

* Buyer product browsing
* Product details
* Buy Now
* NATRA payment information
* Receipt URL submission
* Seller registration/login
* Seller product creation
* Seller product listing
* Admin login
* Admin product viewing
* Admin CBE/Telebirr settings

## PHASE 2 — PAYMENT VERIFICATION

* Telebirr receipt verification
* CBE receipt verification
* Playwright where necessary
* Amount validation
* Status validation
* Transaction/reference extraction
* Duplicate protection
* Successful payment confirmation
* Product delivery release

## PHASE 3 — MARKETPLACE FINANCE

* Commission calculation
* Seller earnings
* Unsettled balances
* Settlement records
* Seller payment methods
* Admin settlement management
* Financial reporting

## PHASE 4 — PRODUCTION

* Security hardening
* Permission improvements
* Validation
* Error handling
* UI/UX improvements
* Performance improvements
* Oracle Cloud deployment
* Monitoring
* Backup strategy

---

# 21. CRITICAL PRINCIPLE

The final NATRA vision is described in this document.

However, **the current implementation must always remain limited to the active task and active phase.**

Use the final vision to make sensible architectural decisions.

But do NOT implement future features early.

---

# 22. FIRST COMMAND

START WITH ONLY THE FIRST SMALL TASK.

Do NOT build the entire application.

Do NOT build all of Phase 1.

First create/inspect the minimal project structure needed for NATRA.

Make the basic development environment start successfully.

Then:

1. Test it.
2. Update `CURRENT_STATUS.md`.
3. Report what was completed.
4. State the next ONE small task.
5. STOP.

**Wait for the user's next instruction before doing anything else.**
