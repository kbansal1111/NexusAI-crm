# Tutterfly CRM — System Handbook

**A standalone reference. You do not need access to the source code to read this.**

Every schema, rule, and code pattern that matters is reproduced inline. File paths are given so you
can find things once you *do* have the repository, but nothing here depends on opening them.

> Once you have the repo, `docs/SCHEMA_AND_DATA_FLOW.md` is the companion to this document: same
> material, but as a guided reading path with links into the actual source files.

---

## Table of contents

1. [What the system is](#1-what-the-system-is)
2. [Core concepts](#2-core-concepts)
3. [How the database is organised](#3-how-the-database-is-organised)
4. [Schema reference](#4-schema-reference)
   - [4.1 Identity & access](#41-identity--access)
   - [4.2 Core CRM objects](#42-core-crm-objects)
   - [4.3 Activity & attachments](#43-activity--attachments)
   - [4.4 Sales documents](#44-sales-documents)
   - [4.5 Opportunity financials](#45-opportunity-financials)
   - [4.6 Travel catalogue](#46-travel-catalogue)
   - [4.7 Territories](#47-territories)
   - [4.8 Configuration collections](#48-configuration-collections)
   - [4.9 Audit collections](#49-audit-collections)
5. [Where a field can live](#5-where-a-field-can-live)
6. [Relationship patterns](#6-relationship-patterns)
7. [Data flow: a request end to end](#7-data-flow-a-request-end-to-end)
8. [The visibility rules](#8-the-visibility-rules)
9. [Lifecycle: lead to cash](#9-lifecycle-lead-to-cash)
10. [Permissions catalogue](#10-permissions-catalogue)
11. [API surface](#11-api-surface)
12. [Frontend data flow](#12-frontend-data-flow)
13. [Rules you must follow when writing code](#13-rules-you-must-follow-when-writing-code)
14. [Glossary](#14-glossary)

---

## 1. What the system is

Tutterfly is a **multi-tenant, multi-industry CRM**. It is sold as SaaS: many customer companies
share one database and one deployment. The production customer is a travel agency, so the travel
vertical is the best-exercised, but the core objects are industry-neutral.

Two properties drive nearly every design decision:

| Property | Meaning | Consequence |
|---|---|---|
| **Multi-tenant** | Many customer companies ("tenants") share one MongoDB database | Every record carries `tenant_id`; every query filters on it |
| **Multi-industry** | A tenant is `travel`, `healthcare`, `education`, or `manufacturing` | Industry-specific fields live in a validated `industry_data` sub-document, not in separate models |

### Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Beanie ODM, MongoDB (Atlas) |
| Frontend | TypeScript, Next.js (App Router), React Query, Tailwind + shadcn/ui |
| Auth | NextAuth session on the frontend → JWT bearer token → FastAPI dependency |
| Cache | Redis (permission scope, directory lookups) |
| File storage | Amazon S3 |
| Deployment | Backend on EC2; frontend on Cloudflare Workers |

### Where the code lives

```
apps/backend/app/
  main.py         App assembly: middleware order + every router mount
  api/deps.py     Authentication + permission dependencies
  api/v1/         One route file per module (leads.py, opportunities.py, …)
  models/         Beanie documents — these ARE the MongoDB schema
  schemas/        Pydantic request/response contracts (not the DB shape)
  services/       Business logic; routes stay thin
  core/           Cross-cutting helpers (tenant scoping, picklists, search)
  middleware/     Request context, audit logging, industry gating
  db/mongodb.py   Beanie init; its document_models list is the collection registry
  scripts/        Migrations, index creation, seeding

apps/frontend/src/
  app/(dashboard)/  Route pages per module
  features/<name>/  components/ + api/ (React Query hooks) + types/
  lib/api/          axios client + one service file per backend module
  lib/rbac.ts       Permission gating in the UI
```

---

## 2. Core concepts

### Tenant

A customer company. Holds company details, branding, subscription plan, limits, and — critically —
`industry` and a `modules` map of feature flags.

### User, Role, Role Hierarchy

- A **User** belongs to exactly one tenant and holds a list of `role_ids`.
- A **Role** is a named bundle of permission strings (e.g. `create_lead`, `edit_opportunity`) plus an
  `is_admin` flag. Roles are per-tenant.
- A **Role Hierarchy** is a separate tree (`parent_id`, `user_ids`) describing who reports to whom.
  It controls *data visibility*, not permissions. A user's `role_hierarchy_id` places them in the tree.

Permissions answer **"may I perform this action at all?"**
Hierarchy answers **"whose records may I see?"** These are independent.

### Ownership

Every domain record has an `owner_id` pointing at a User. Ownership drives visibility (see §8) and can
be transferred ("change owner"), which immediately transfers visibility with it.

### Soft delete

Records are never physically removed. Deleting sets `deleted_at` to a timestamp. Every read filters
`deleted_at: None`. This applies to all domain collections.

---

## 3. How the database is organised

MongoDB, accessed through **Beanie** — an async ODM where a Python class defines both the document
shape and the collection. A model looks like this:

```python
class Lead(BaseDocument):
    first_name: str
    last_name: str
    email: Optional[EmailStr] = None
    tenant_id: PydanticObjectId
    owner_id: PydanticObjectId

    class Settings:
        name = "leads"          # ← the MongoDB collection name
```

There are roughly **150 collections**. Nearly all domain records inherit `BaseDocument`, which
contributes:

```python
created_at: datetime      # set on insert
updated_at: datetime      # auto-bumped by the overridden save()
deleted_at: datetime|None # soft-delete marker
```

and every domain model then adds the standard tenancy/ownership block:

```python
tenant_id: PydanticObjectId          # which customer company owns this row
owner_id: PydanticObjectId           # which user owns it → drives visibility
owner_name: str|None                 # DENORMALIZED copy of the owner's name
created_by: PydanticObjectId
last_modified_by_id: PydanticObjectId|None
custom_fields: dict                  # tenant-defined extra fields
industry_data: dict                  # industry-specific fields (validated)
```

### Two conventions that will confuse you otherwise

**Denormalized names.** `owner_name` and `account_name` are server-managed copies stored on the record
so list endpoints don't have to join the users/accounts collections on every row. They are populated by
a Beanie insert hook. They are **not** form fields — never let a client set them. Reads fall back to a
live lookup when the copy is missing.

**Consolidated collections.** MongoDB Atlas caps collections per cluster, so two families of small
tables were folded into one collection each with a discriminator field:

- All dropdown values → one `picklists` collection, discriminated by `picklist_type`
- All custom-field *definitions* → one `field_registry` collection, discriminated by `entity_type`

Both are covered in §4.8.

---

## 4. Schema reference

Field lists below are the real ones. `⚑` marks a field with non-obvious behaviour, explained beneath
the table.

### 4.1 Identity & access

#### `tenants`

| Field | Type | Notes |
|---|---|---|
| `company_name` | str | indexed |
| `subdomain` | str | unique |
| `email`, `phone` | str | |
| `address`, `city`, `state`, `country`, `zip_code` | str | |
| `logo_url`, `timezone`, `currency` | str | defaults `UTC` / `USD` |
| `plan` | str | `free` \| `basic` \| `premium` |
| `is_active` | bool | |
| `trial_ends_at` | datetime | |
| `max_users`, `max_storage_gb` | int | defaults 5 / 10 |
| `industry` ⚑ | enum | `travel` \| `healthcare` \| `education` \| `manufacturing` |
| `modules` ⚑ | dict | feature flags, e.g. `{"patients": true}` |

⚑ `industry` decides which validators run on `industry_data` everywhere in the system.
⚑ `modules` gates whole route families — a travel tenant calling `/api/v1/patients` gets 403. Defaults
are seeded per industry on tenant creation.

#### `users`

| Field | Type | Notes |
|---|---|---|
| `name`, `email` ⚑, `password` | str | email unique globally; password is a bcrypt hash |
| `tenant_id` | ObjectId | |
| `department_id`, `role_hierarchy_id` ⚑ | ObjectId | hierarchy placement |
| `phone`, `title`, `avatar_url` | str | |
| `is_active`, `is_verified` | bool | |
| `is_system` ⚑ | bool | service account owning the unassigned opportunity pool; cannot log in |
| `role_ids` | list[ObjectId] | → `roles` |
| `timezone`, `language` | str | |
| `smtp_host/port/username/password` | | per-user outbound email |
| `max_leads_per_day`, `max_opportunities`, `is_available_for_assignment` | | auto-assignment limits |
| `assigned_countries`, `assigned_destinations`, `not_assigned_countries` | list | auto-assignment routing |
| `is_bd_user` ⚑, `territory_ids` ⚑ | bool / list | **denormalized mirror only** |
| `monthly_revenue_target`, `monthly_deals_target` | number | |
| `last_assigned_at`, `last_login_at` | datetime | |
| `created_by`, `last_modified_by_id` | ObjectId | |

⚑ `email` is unique across the *whole platform*, not per tenant — one email cannot exist in two tenants.
⚑ `role_hierarchy_id` places the user in the reporting tree; this is what makes a manager see
subordinates' records.
⚑ `is_bd_user` / `territory_ids` are a **mirror** of "territories this user manages", kept only so the
user-edit form can pre-fill a control. **Visibility never reads them** — the authority is
`territories.manager_id`. This deliberate redundancy means the two admin screens can never drift into a
state where one grants access and the other denies it.

#### `roles`

| Field | Type | Notes |
|---|---|---|
| `name`, `display_name`, `description` | str | |
| `tenant_id` | ObjectId | roles are per-tenant |
| `permissions` | list[str] | e.g. `["view_lead", "create_lead"]` — see §10 |
| `is_admin` ⚑ | bool | |

⚑ `is_admin: true` means the holder sees every record in the tenant (visibility scoping returns "no
filter") and is auto-granted `unlock_opportunity`.

#### `role_hierarchies`

| Field | Type | Notes |
|---|---|---|
| `name` | str | |
| `tenant_id` | ObjectId | |
| `parent_id` | ObjectId | self-reference → forms the tree |
| `level` | int | depth |
| `user_ids` | list[ObjectId] | users sitting at this node |

#### `departments`

Organisational grouping, referenced by `users.department_id`.

---

### 4.2 Core CRM objects

#### `leads` — an unqualified prospect

| Group | Fields |
|---|---|
| Name | `salutation`, `first_name` (req), `middle_name`, `last_name` (req) |
| Contact | `email`, `phone`, `mobile` |
| Company | `company`, `title`, `no_employees`, `website` |
| Address | `street`, `city`, `state`, `zip`, `country` |
| Classification | `lead_status_id` → picklist, `industry_id` → picklist, `source_id` → picklist |
| Creation | `creation_type` (`manual` \| `auto`) |
| Conversion ⚑ | `is_converted`, `opportunity_id`, `converted_at` |
| Tenancy | `tenant_id`, `owner_id`, `owner_name`, `created_by`, `last_modified_by_id` |
| Extensible | `custom_fields`, `industry_data` |
| Flags | `is_favorite` |

⚑ A lead converts **once**. Attempting to convert an already-converted lead is rejected.

⚠️ **Travel fields are not on this model.** `travel_date`, `no_of_pax`, `destinations`,
`no_of_nights`, `experience_id` etc. live inside `industry_data`. See §5.

⚠️ **Three shipped fields live in `custom_fields`, not as columns**: `segment`, `campaign_name`,
`experience_id`. They render in the form's "Additional Information" section and are referenced in saved
views as `custom_fields.segment` etc. They're flagged `is_system` in the field registry so they cannot
be renamed or deleted.

#### `accounts` — the customer organisation *or* an individual

One collection serves both B2B and B2C, discriminated by `is_person_account`:

| | Company account (`false`) | Person account (`true`) |
|---|---|---|
| Identity | `name`, `website`, `category_id` | `salutation` + `first_name` + `last_name` |
| Phone | `phone` only | `phone` **and** `mobile` |
| UI route | `/accounts` | `/person-accounts` |
| Permission | `edit_account` | also `edit_account` — *not* a separate permission |

| Group | Fields |
|---|---|
| Basic | `name`, `email`, `phone`, `mobile`, `website`, `description`, `is_person_account`, `segment` (`B2C`\|`B2B`\|`CORPORATE`) |
| Person-only | `salutation`, `first_name`, `last_name` |
| Billing address ⚑ | `billing_street/city/state/zip/country` |
| Shipping address | `shipping_street/city/state/zip/country` |
| Classification | `acc_type_id`, `acc_parent_id` ⚑, `industry_id`, `category_id` |
| Tenancy | `tenant_id`, `owner_id`, `owner_name`, `created_by`, `last_modified_by_id` |
| Extensible | `custom_fields`, `industry_data` |

⚑ The **billing address** is what drives automatic territory assignment on opportunities.
⚑ `acc_parent_id` is a self-reference enabling parent/child account trees.

#### `contacts` — a person at an account

| Group | Fields |
|---|---|
| Name | `salutation`, `first_name` (req), `middle_name`, `last_name` (req) |
| Contact | `email`, `phone`, `mobile`, `fax` |
| Professional | `title`, `department` |
| Mailing address | `mailing_street/city/state/zip/country` |
| Other address | `other_street/city/state/zip/country` |
| Extra | `description`, `assistant`, `assistant_phone` |
| Link | `account_id` ⚑, `account_name` (denormalized) |
| Tenancy | `tenant_id`, `owner_id`, `owner_name`, `created_by`, `last_modified_by_id` |
| Extensible | `custom_fields`, `industry_data` |

⚑ `account_id` is the *primary* account. A many-to-many relationship also exists through the
`account_contact` pivot collection.

#### `opportunities` — the deal (the most complex model)

| Group | Fields |
|---|---|
| Basic | `name`, `amount`, `description`, `close_date` |
| Pipeline | `sales_stage_id` ⚑, `probability` (0–100) |
| Polymorphic link | `opportunitable_type` (`Account`\|`PersonalAccount`), `opportunitable_id` |
| Direct links | `account_id`, `account_name` (denorm), `contact_id`, `lead_id` ⚑ |
| Classification | `opportunity_type_id`, `source_id`, `source_url` |
| Loss | `close_lost_reason` |
| Team | `owner_id`, `owner_name`, `operation_user_id`, `team_member_ids` |
| Territory ⚑ | `territory_id`, `region_id`, `territory_match_source`, `territory_assigned_at` |
| Tenancy | `tenant_id`, `created_by`, `last_modified_by_id` |
| Flags | `is_queue`, `key_deal`, `verified_by_account`, `segment` (`B2B`\|`B2C`), `creation_type` |
| Finance | `fyear` |
| Locking ⚑ | `is_locked`, `locked_by`, `locked_at` |
| Display | `opportunity_number` ⚑ |
| Extensible | `custom_fields`, `industry_data` |

⚑ `sales_stage_id` points into the `picklists` collection at a row of type `sales_stage`, which carries
`probability`, `is_won`, and `is_lost`. Won/lost is therefore a property of the *stage*, not a separate
status field.
⚑ `lead_id` is set when the opportunity came from a lead conversion; the API then always reports
`creation_type` as `Auto`.
⚑ **Territory** is auto-resolved on create from the linked account's billing address.
`territory_match_source` records *how* it matched, in precedence order:
`postal_code` → `postal_code_pattern` → `state` → `country` → `manual`. The territory's manager is
looked up live from `territories.manager_id`; it is deliberately **not** copied onto the opportunity, so
reassigning a territory manager instantly changes who can see the deals.
⚑ Locking prevents concurrent edits; released by the `unlock_opportunity` permission, auto-granted to
admin roles.
⚑ `opportunity_number` is a per-tenant sequential integer (backed by the `tenant_counters`
collection), zero-padded to 10 digits for display.

---

### 4.3 Activity & attachments

These four use the same **polymorphic** pattern: a `<thing>able_type` string naming the parent model and
a `<thing>able_id` holding its id. That lets one collection attach to Accounts, Contacts, Leads, and
Opportunities alike.

#### `tasks`

| Field | Notes |
|---|---|
| `name`, `description`, `due_date` | |
| `status` | `Not Started` \| `In Progress` \| `Completed` \| `Deferred` |
| `priority` | `Low` \| `Normal` \| `High` \| `Urgent` |
| `taskable_type`, `taskable_id` | polymorphic parent |
| `contact_id`, `account_id` | direct convenience links |
| `assigned_user_id` ⚑, `owner_id` ⚑ | **dual ownership** |
| `completed_at`, `completed_by` | |
| `tenant_id`, `created_by`, `last_modified_by_id` | |

⚑ Tasks are the one object with two owners: the creator (`owner_id`) and the assignee
(`assigned_user_id`). A task is visible if **either** is in your visible set — which is why tasks have a
dedicated visibility helper.

#### `events`

| Field | Notes |
|---|---|
| `name`, `description`, `location` | |
| `start_datetime`, `end_datetime`, `all_day` | |
| `event_type` | `Meeting` \| `Call` \| `Email` \| `Task` \| `Other` |
| `eventable_type`, `eventable_id` | polymorphic parent |
| `assigned_user_ids`, `owner_id` | multiple participants |
| `reminder_minutes`, `reminder_sent` | |
| `status` | `Planned` \| `Held` \| `Not Held` \| `Cancelled` |
| `is_recurring`, `recurrence_pattern` | |

#### `notes`

`title`, `content` (req), `noteable_type`/`noteable_id`, `owner_id`, `is_private` ⚑, `is_pinned`.

⚑ Private notes are visible only to their owner regardless of hierarchy.

#### `files`

| Field | Notes |
|---|---|
| `filename`, `original_filename`, `file_path`, `file_size`, `mime_type` | |
| `storage_type` ⚑ | `s3` \| `local` |
| `fileable_type`, `fileable_id` | polymorphic parent |
| `category` | document / image / attachment |
| `owner_id`, `is_public`, `download_count` | |

⚑ Records whether a file went to S3 or to local disk. Download routing depends on it — a file written
to local disk on a server that later runs S3-only is unreachable, which was a production incident.

Supporting collections: `file_folders`, `file_shares`, `file_versions`, `file_public_links`,
`module_attachments`.

---

### 4.4 Sales documents

#### `quotes` and `quote_items`

| `quotes` | Notes |
|---|---|
| `quote_number` | auto-generated |
| `name` | |
| `opportunity_id`, `contact_id`, `account_id` | |
| `status` | `Draft` \| `Sent` \| `Accepted` \| `Rejected` \| `Expired` |
| `quote_date`, `valid_until` | |
| `subtotal`, `discount_percent`, `discount_amount`, `tax_percent`, `tax_amount`, `total`, `currency` | |
| `terms_and_conditions`, `notes` | |
| `industry_data` | e.g. travel: `travel_date`, `return_date`, `num_adults`, … |

`quote_items` rows hold `quote_id`, `name`, `description`, `product_id`, `quantity`, `unit_price`,
discount/tax fields, `total`, `sort_order`.

#### `invoices`, `invoice_items`, `payments`

| `invoices` | Notes |
|---|---|
| `invoice_number` | immutable ledger key |
| `quote_id`, `opportunity_id`, `contact_id`, `account_id` | |
| `status` | `Draft` \| `Sent` \| `Paid` \| `Partially Paid` \| `Overdue` \| `Cancelled` |
| `invoice_date`, `due_date` | |
| `subtotal` … `total`, `amount_paid` ⚑, `balance_due` ⚑, `currency` | |

⚑ `amount_paid` / `balance_due` are running totals maintained as `payments` rows are recorded.

`payments`: `invoice_id`, `amount`, `payment_date`, `payment_method` (Cash / Card / Bank Transfer /
Check), `reference_number`, `recorded_by`.

---

### 4.5 Opportunity financials

A separate, richer money model attached directly to opportunities — distinct from the quote/invoice
documents above.

#### `opportunity_costings`

Holds an embedded array of line items:

| Line item field | Meaning |
|---|---|
| `item_type` | Land Package / Visa / Tax / Miscellaneous / … |
| `supplier_id`, `supplier_name` | supplier + denormalized name |
| `destination_ids`, `destination_names` | |
| `amount` | **sell** price (what the customer pays) |
| `cost_amount` | **cost** (what we pay the supplier) |

Document-level rollups, recomputed on save: `total_amount`, `total_cost`, `profit`, `profit_percent`.

#### `payment_schedule_items`

Planned instalments: `description`, `due_date`, `amount`, `status` (`Pending` \| `Received`),
`payment_method`, `reference_number`, `paid_at`, and `transaction_id` linking to the transaction created
when it is marked received.

#### `opportunity_transactions` — note the approval workflow ⚑

| Field | Notes |
|---|---|
| `transaction_type` | `Receive` \| `Pay` \| `Refund` |
| `amount`, `transaction_date` | |
| `payment_mode`, `reference_id`, `supplier`, `service`, `destination`, `note` | |
| `payment_schedule_item_id` | back-link |
| `approval_status` ⚑ | `pending_verification` → `verified` → `approved`, plus `rejected` |
| `verified_by/at`, `approved_by/at`, `rejected_by/at`, `rejection_reason` | |

⚑ **Two-step approval.** Sales enters an amount; the accounts team *verifies* it, then gives final
*approval*. Rejected transactions are terminal until edited. The permissions are
`verify_opportunity_transaction` and `approve_opportunity_transaction`. Legacy rows created before this
field existed are treated as `approved` so historical ledgers aren't retroactively frozen.

#### Opportunity workflow collections

`vouchers` (draft → issued → redeemed → cancelled), `departures`, `ledger_accounts` (debit/credit
entries), `opportunity_claims`, `handover_requests` (transfer a deal between users, pending → accepted /
rejected), `opportunity_team_members`, `opportunity_payment_schedules`, `external_leads` (raw captures
from Facebook / webforms / API awaiting processing into real leads).

---

### 4.6 Travel catalogue

#### `suppliers`

Hotels, airlines, DMCs, transport operators.

| Group | Fields |
|---|---|
| Basic | `name`, `supplier_type` |
| Contact | `email`, `phone`, `mobile` |
| Address | `street`, `city`, `state`, `zip`, `country` |
| Service areas | `services`, `countries`, `states`, `service_cities`, `destinations` (all lists) |
| Business | `tax_id`, `registration_number`, `credit_limit` |
| Legacy contact ⚑ | `contact_person_name/email/phone` |
| Status | `is_active`, `is_preferred` |

⚑ Contact people used to be an embedded array. They now live in a **standalone `supplier_contacts`
collection** (one row per contact, with `supplier_id`, `name`, `designation`, `department`, `email`,
`phone`, `mobile`, `is_primary`) so they are globally searchable. The API still presents them nested
under `SupplierResponse.contacts`, so the external contract didn't change.

`opp_suppliers` is the pivot linking suppliers to opportunities, carrying a per-opportunity `cost`,
`notes`, and email subject/body.

#### `destinations`

`name`, `description`, `country_id` (ISO-3 code), `state_id`, `city_id`, `destination_type` (Beach /
Mountain / City / Historical), `best_time_to_visit`, `is_active`, `is_popular`, `tags`.

Pivots: `destination_opportunities`, `destination_leads` (each with an `is_primary` flag).

⚠️ Destinations *also* exist as picklist rows (`picklist_type: "destination"`), which is the live source
for dropdowns. The standalone `destinations` collection is the legacy path.

#### `itineraries`

`name`, `description`, `total_days`, `total_nights`, `start_date`, `end_date`, `destination_ids`,
`destination_names` ⚑, `tour_starts_from`, `tour_ends_same`, `pdf_file_id` ⚑, `inclusions`,
`feature_image`, `overview`, `is_active`, `is_template`.

⚑ `destination_names` preserves selection order — index `[0]` is the primary destination and drives the
S3 folder and display.
⚑ The day-by-day itinerary *builder* was replaced by a simple **PDF upload**: `pdf_file_id` points at a
`files` row holding the S3 key. Older builder fields remain optional for backward compatibility.

Pivot: `itinerary_opportunities`.

#### `packages`

`name`, `description`, `package_code`, `days`, `nights`, `destination_ids`, `base_price`, `currency`,
`valid_from`, `valid_to`, `inclusions`, `exclusions`, `itinerary_id`, `category` (Honeymoon / Family /
Adventure), `min_pax`, `max_pax`, `is_active`, `is_featured`.

Supporting: `package_pricing` (seasonal / group-size tiers), `package_opportunities` (pivot with
`custom_price`).

#### `products`

`name`, `description`, `product_code`, `category`, `product_type`, `price`, `currency`, `cost_price`,
`stock_quantity`, `duration`, `min_capacity`, `max_capacity`, `is_active`, `is_featured`, `tags`.

#### `departures`

Doubles as an opportunity-level departure and a standalone tour slot (`opportunity_id` null means
standalone): `name`, `destination`, `total_seats`, `booked_seats`, `held_seats`, `has_flight`,
`departure_date`, `return_date`, `pax_count`, `departure_city`, `return_city`, `status`, `hold_reason`,
`is_agent_departure`, `agent_id`.

---

### 4.7 Territories

#### `regions`

`name`, `code`, `description`, `currency`, `timezone`, `parent_id` (nesting), `manager_id`, `is_active`.

#### `territories` ⚑

| Field | Notes |
|---|---|
| `name`, `code`, `description` | |
| `region_id`, `parent_territory_id` | optional nesting |
| `assignment_type` | `manual` \| `geographic` \| `rule_based` |
| `countries`, `states`, `postal_codes` ⚑, `destinations` | geographic match criteria |
| `manager_id` ⚑ | **exactly one manager** |
| `is_active` | |

⚑ `postal_codes` supports wildcards, which is why the match-source enum distinguishes `postal_code`
from `postal_code_pattern`.
⚑ **`manager_id` is the single source of truth for territory-scoped visibility.** "Territory Manager"
and "BD owner" are the same role — there is no separate BD user pool. A user who manages a territory
sees exactly that territory's opportunities.

---

### 4.8 Configuration collections

#### `picklists` — every dropdown value in the product

One collection, discriminated by `picklist_type`. Known types include:

`account_type`, `account_source`, `account_category`, `industry`, `lead_status`, `source`,
`sales_stage`, `opportunity_type`, `opportunity_tag`, `experience`, `salutation`, `task_status`,
`task_priority`, `inclusion`, `itinerary_inclusion`, `supplier_type`, `supplier_service`, `destination`.

| Field | Notes |
|---|---|
| `name`, `description` | |
| `tenant_id` ⚑ | **nullable** |
| `picklist_type` | the discriminator |
| `industry` ⚑ | **nullable** |
| `sorting`, `is_active`, `is_default` | |
| `color` | |
| `probability`, `is_won`, `is_lost` | sales_stage only |
| `country` | destination only |

⚑ This implements a **platform-default + tenant-override** pattern:

```
tenant_id = null      → platform default, inherited by ALL tenants
tenant_id = <id>      → that tenant's own value (shadows a default with the same name)
industry  = null      → applies to all industries
industry  = "travel"  → travel tenants only
```

So querying with a bare `{"tenant_id": X}` **hides every platform default** — one of the most common
bugs in this codebase. The correct query is built centrally:

```python
def build_picklist_query(tenant_id, *, industry=None, active_only=True, picklist_type=None):
    tenant_or = {"$or": [{"tenant_id": tenant_id}, {"tenant_id": None}]}
    if industry:
        industry_or = {"$or": [
            {"industry": industry},
            {"industry": None},
            {"industry": {"$exists": False}},
        ]}
        query = {"$and": [tenant_or, industry_or]}
    else:
        query = {**tenant_or}
    if active_only:
        query["is_active"] = True
    if picklist_type:
        query["picklist_type"] = picklist_type   # prevents cross-type contamination
    return query
```

Results are then passed through `dedup_picklist_items()`, which drops a platform default when the tenant
has an override of the same name.

**Never hardcode a picklist value anywhere in the codebase.**

#### `field_registry` — custom-field *definitions*

One collection, discriminated by `entity_type` (`lead` / `opportunity` / `account` / `contact` /
`supplier` / `personal_account` / `task`).

| Field | Notes |
|---|---|
| `tenant_id` | nullable (platform-wide definitions) |
| `entity_type` | discriminator |
| `name`, `field_key`, `field_type` | text / number / date / boolean / select / multiselect / … |
| `label`, `description`, `placeholder`, `help_text` | |
| `is_required`, `is_mandatory`, `is_unique`, `validation_rules` | |
| `sorting`, `is_active`, `is_hidden`, `is_custom` | |
| `is_system` ⚑ | |
| `options` ⚑ | for select types |

⚑ `is_system: true` marks schema-bound fields that a hardcoded form section renders (Lead's `segment`,
`campaign_name`, `experience_id`; Opportunity's `starting_city`). The service layer **blocks**
delete/rename/deactivate on these, because saved-view filters reference them by exact key.
⚑ `options` accepts both plain strings (current API) and `{label, value}` dicts (legacy Laravel-era
rows).

The **values** are written into the owning document's `custom_fields` dict. A legacy
`custom_field_values` collection also exists for old rows.

#### `entity_views` — saved list views

Salesforce-style saved views, polymorphic over `entity_type` ∈ {account, personal_account, contact, lead,
opportunity, supplier, task}.

| Field | Notes |
|---|---|
| `entity_type`, `name`, `description` | |
| `filters` | legacy flat dict |
| `filter_rules` ⚑ | `[{field, operator, value}, …]` |
| `display_columns` ⚑ | ordered column keys |
| `scope` | `all` \| `mine` |
| `sort_by`, `sort_dir` | |
| `is_public` ⚑ | whole tenant vs creator-only |
| `is_default` | |
| `is_system`, `preset_key` ⚑ | |
| `created_by`, `tenant_id` | |

⚑ `filter_rules` are translated into a MongoDB query server-side.
⚑ Custom fields are encoded in `display_columns` as `additional:<field_id>`.
⚑ `is_public` must be honoured on **both** read and write.
⚑ System presets (Today / Yesterday / This Week) are lazily seeded per tenant+entity;
`preset_key` keeps seeding idempotent.

Companions: `entity_columns`, `entity_pin_views`, `entity_filters`.

*Legacy note:* Accounts and Person Accounts still use an older `account_views` model. Everything new
uses `entity_views`.

---

### 4.9 Audit collections

There are **two** audit trails and they serve different purposes. Do not confuse them.

| Collection | Written by | Purpose | Retention |
|---|---|---|---|
| `activity_logs` | Service layer, explicitly | The per-entity **History** timeline shown in the UI | Permanent |
| `api_audit_logs` | Middleware, automatically | "Who changed what, when, from where" for **every** mutating API call | TTL-expired |

`activity_logs` fields: `user_id`, `user_name`, `action` (create/update/delete/view/login/…),
`entity_type`, `entity_id`, `entity_name`, `description`, `changes` (`{field: {old, new}}`), `metadata`,
`ip_address`, `user_agent`, `tenant_id`.

`api_audit_logs` fields: `request_id` (matches the `X-Request-ID` response header and every log line for
that request), `method`, `path`, `route` (template, e.g. `/api/v1/leads/{lead_id}`), `query`, `body`
(sanitized, size-capped), `status_code`, `duration_ms`, `response_error`, actor fields, `ip_address`,
`user_agent`.

Because `api_audit_logs` is written by middleware, **no endpoint opts in or out** — coverage cannot
drift as new routes are added.

`login_logs` records login history: success/failure, reason, IP, device, browser, OS, session id.

---

## 5. Where a field can live

**This is the single most useful thing to internalise.** A new engineer's first bug is almost always
"I can't find this field on the model." There are four possible homes:

| Home | What it is | Example | How to query it |
|---|---|---|---|
| **Model field** | A real typed column on the document | `Lead.email` | `{"email": "x@y.com"}` |
| **`industry_data.*`** | Industry-specific, validated per industry | `industry_data.travel_date` | `{"industry_data.travel_date": …}` |
| **`custom_fields.*`** | Tenant-defined extras + some shipped fields | `custom_fields.segment` | `{"custom_fields.segment": "B2C"}` |
| **Picklist reference** | An ObjectId into the shared `picklists` collection | `Lead.lead_status_id` | join via `build_picklist_query` |

### The `industry_data` contract

Industry-specific fields live in `industry_data` on Lead, Opportunity, Account, Contact, and Quote, and
**must** pass a validator before reaching the database:

```python
from app.schemas.industry_data import validate_industry_data
validated = validate_industry_data(industry="travel", data=raw, mode="lead")
```

The dispatcher routes to a Pydantic model per `(industry, mode)` — 4 industries × 5 modes = **20
validators**. It raises on an unknown industry or mode, so a typo can't silently write unvalidated data.
It also strips empty strings before validating, because HTML forms submit untouched fields as `""` and
without that every blank numeric/date field would reject the whole request.

**What travel actually stores in `industry_data`:**

| Mode | Fields |
|---|---|
| Lead | `travel_date` (**required**), `no_of_nights`, `no_of_adults`, `no_of_pax`, `no_of_childs`, `no_of_infants`, `destinations`, `destination_ids`, `experience_id`, `is_fixed` |
| Opportunity | `travel_date` (**required**), `no_of_pax`, `no_of_nights`, `no_of_adults`, `no_of_childs`, `no_of_infants`, `destination_ids`, `origin_ids`, `inclusions`, `country_of_origin`, `starting_city`, `experience_id`, `departure_id`, `custom_departure` |
| Quote | `travel_date`, `return_date`, `num_adults`, `num_children`, `num_infants`, `destinations`, `destination_ids`, `no_of_nights`, `inclusions` |
| Account | `preferred_destinations`, `preferred_experience_types`, `travel_frequency`, `membership_tier`, `membership_number` |
| Contact | `passport_number`, `passport_expiry`, `nationality`, `date_of_birth`, `dietary_preferences`, `frequent_flyer_number` |

Healthcare, education, and manufacturing have equivalent field sets for all five modes.

---

## 6. Relationship patterns

Three patterns cover almost every relationship in the system.

### Direct foreign key

An ObjectId field pointing at another collection: `contacts.account_id`, `opportunities.account_id`.
Often paired with a denormalized name copy (`account_name`) to avoid joins on list pages.

### Polymorphic parent

A type string + an id, used where one collection attaches to several parents:

```
tasks.taskable_type = "Opportunity"    tasks.taskable_id  = <opportunity _id>
notes.noteable_type = "Lead"           notes.noteable_id  = <lead _id>
files.fileable_type = "Account"        files.fileable_id  = <account _id>
events.eventable_type = "Contact"      events.eventable_id = <contact _id>
```

Valid parent types are `Account`, `Contact`, `Lead`, `Opportunity`.

### Pivot collection (many-to-many)

A dedicated join collection, always carrying `tenant_id` of its own:

| Pivot | Links | Extra data on the link |
|---|---|---|
| `account_contact` | accounts ↔ contacts | — |
| `opp_suppliers` | opportunities ↔ suppliers | `cost`, `notes`, email subject/body |
| `destination_opportunities` | destinations ↔ opportunities | `is_primary` |
| `destination_leads` | destinations ↔ leads | `is_primary` |
| `itinerary_opportunities` | itineraries ↔ opportunities | `notes` |
| `package_opportunities` | packages ↔ opportunities | `custom_price` |

### The overall map

```
Tenant
 ├── User ──┬── role_ids ──> Role (permissions[])
 │          └── role_hierarchy_id ──> RoleHierarchy (tree)
 │
 ├── Lead ─────(convert)────> Opportunity
 │                              ├── account_id ──> Account ──> Contact
 │                              ├── sales_stage_id ──> picklists(sales_stage)
 │                              ├── territory_id ──> Territory ──> manager_id ──> User
 │                              ├── OpportunityCosting / PaymentScheduleItem / Transaction
 │                              ├── Quote ──> Invoice ──> Payment
 │                              └── pivots: suppliers, destinations, itineraries, packages
 │
 └── polymorphic attachments: Task / Event / Note / File  ──> any of the four core objects
```

---

## 7. Data flow: a request end to end

```
Browser
  │  React component (e.g. the Lead drawer form)
  ▼
React Query hook  ──  owns cache keys, staleTime, invalidation
  ▼
Service module    ──  one file per backend module, plain functions
  ▼
axios client      ──  attaches JWT, retries GETs, handles 401
  ▼
═══════════ network ═══════════
  ▼
CORS  →  GZip  →  ActivityContextMiddleware  →  Rate limiter
  │                        └── stamps X-Request-ID, writes api_audit_logs
  ▼
Route handler (api/v1/*.py)
  ▼
Depends(check_permission("create_lead"))
  └── get_current_user: decode JWT → load User → set activity context
  ▼
Pydantic schema validates the request body
  ▼
resolve_industry_data() validates the industry_data blob
  ▼
Service layer  ──  applies tenant + visibility scoping, business rules
  ▼
MongoDB (Beanie)   +   activity_logs row via ActivityMixin
  ▼
Response schema → JSON → back up the chain → React Query cache invalidation
```

### Step detail

**1. Middleware.** Registered in `main.py`. FastAPI runs middleware in *reverse* registration order, so
CORS — added last — is outermost. `ActivityContextMiddleware` stamps an `X-Request-ID` and writes an
`api_audit_logs` row for every mutating call.

**2. Authentication.** `get_current_user` decodes the JWT, rejects non-`access` token types (refresh and
password-reset tokens must never authenticate an API call), and loads the active, non-deleted user:

```python
payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
user_id = payload.get("sub")
if payload.get("type") not in (None, "access"):
    raise credentials_exception

user = await User.find_one(
    {"_id": ObjectId(user_id), "is_active": True, "deleted_at": None}
)
```

This is the **only** unscoped user query in the system — it is how tenant context gets established in
the first place. Everything downstream is scoped by `user.tenant_id`.

**3. Permission check.** `check_permission("create_lead")` loads the user's roles **scoped to their
tenant** and checks for the permission string:

```python
roles = await Role.find({
    "_id": {"$in": list(self.role_ids)},
    "tenant_id": self.tenant_id,      # ← a role id from another tenant grants nothing
    "deleted_at": None,
}).to_list()
```

Role loading is memoized per User instance because a single request checks permissions several times.
The memo lives exactly one request, so role edits apply on the next one.

**4. Body validation.** The route parses the body into a Pydantic schema from `app/schemas/`. These are
the **API contract** and deliberately are *not* the database models — an `Update` schema typically has
every field optional.

**5. Industry resolution.** The tenant's industry is fetched, then `industry_data` is validated against
the matching schema (§5).

**6. Service layer.** All business logic. Services receive `tenant_id` and `visible_owner_ids` from the
route and build scoped queries. Routes stay thin.

**7. Persistence.** Beanie writes the document. An insert hook fills the denormalized `owner_name` /
`account_name` fields.

**8. Audit.** A human-readable row goes to `activity_logs` with secrets redacted; the middleware's
`api_audit_logs` row is written independently.

### What a correct list endpoint looks like

```python
@router.get("/", response_model=LeadListResponse)
async def get_leads(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    view_id: Optional[str] = None,
    cursor: Optional[str] = None,
    current_user: User = Depends(check_permission("view_lead")),   # ← permission
    service: LeadService = Depends(get_lead_service),
):
    visible_owner_ids = await get_visible_owner_ids(current_user)   # ← visibility

    result = await service.get_leads_with_metadata(
        tenant_id=current_user.tenant_id,                           # ← tenancy
        visible_owner_ids=visible_owner_ids,
        view_id=view_id,      # optional saved view → filter_rules → Mongo query
        cursor=cursor,        # keyset pagination
        page=page, per_page=per_page,
    )

    # Resolve foreign ids for the whole page in ONE query — never per row
    await _bulk_resolve_destinations(result["leads"], current_user.tenant_id)
    return result
```

Three things to notice, because they are required everywhere:

- **Permission** gates the action; **tenant_id** gates the data; **visible_owner_ids** gates it again by
  ownership.
- Pagination is hybrid: page 1 returns an offset page plus a total; "load more" uses an opaque keyset
  cursor and skips the expensive COUNT.
- Foreign ids are resolved in **bulk after** the page is fetched, never with a lookup per row.

---

## 8. The visibility rules

Being in the right tenant is not enough. Within a tenant, what you can see is narrowed by ownership and
the role hierarchy.

```python
visible = await get_visible_owner_ids(current_user)
if visible is not None:                    # None means admin → no filter at all
    query["owner_id"] = {"$in": visible}
```

| User type | Sees |
|---|---|
| **Admin** (holds a role with `is_admin: true`) | Everything in the tenant — the helper returns `None`, meaning "apply no owner filter" |
| **Manager** (placed in a role hierarchy) | Own records **+ all subordinates'**, walking the tree downward |
| **Regular user** | Only records they own |
| **Territory Manager / BD user** | **Opportunities only:** strictly the opportunities in territories they manage — this *replaces* owner scope, it does not widen it |

### Worked examples

> **Priya** is a sales rep with no hierarchy node. `get_visible_owner_ids` returns `[priya_id]`. Her
> lead list shows only leads where `owner_id == priya_id`.

> **Raj** manages Priya and two others, and sits at a hierarchy node whose subtree contains all three.
> The helper returns `[raj_id, priya_id, dev_id, anita_id]`. Raj sees his own records plus all three
> reports'.

> **Meera** manages the "West India" territory. For **opportunities**, the helper returns her territory
> ids and the query becomes `{"territory_id": {"$in": [west_india_id]}}` — she sees every deal in that
> territory *regardless of who owns it*, and no deals outside it even if she happens to own one. For
> **leads and accounts**, ordinary owner scoping applies; territory scope is opportunity-only.

> **Arjun** holds an admin role. The helper returns `None` and no owner filter is applied. He sees the
> whole tenant — but still only his own tenant.

### Where it must be applied

On **list, detail, update, and delete** — not just list. Applying it only on list means a user can open
a colleague's record by pasting its URL.

| Situation | Helper |
|---|---|
| Building a list query | `apply_visibility_filter(query, visible)` |
| Checking one record | `is_record_visible(owner_id, visible)` |
| Checking one opportunity | `is_opportunity_visible(owner_id, territory_id, visible, bd_territory_ids)` |
| Checking one task | `is_task_visible(owner_id, assigned_user_id, visible)` — dual ownership |
| Dashboard aggregation | `opportunity_scope_match(user)` or `entity_scope_match(user)` |

**Dashboards must build their `$match` from those last two helpers**, never from a bare tenant query.
Otherwise a user is shown totals computed from records they cannot open.

### Performance note

The hierarchy walk is cached in Redis per `(tenant_id, user_id)` for about 90 seconds, and invalidated
on role, hierarchy, or territory changes. Redis is **required** in production: with multiple worker
processes an in-memory fallback would give each worker a different view of permissions.

---

## 9. Lifecycle: lead to cash

```
1. CAPTURE      Lead created — manually, by CSV import, or via the public
                web-to-lead API (authenticated by a per-tenant API key, not JWT).
                Optionally auto-assigned to a user by destination/country routing.

2. QUALIFY      lead_status_id moves through the status picklist.
                Tasks, events, notes, and files attach polymorphically.

3. CONVERT      One-way, once per lead:
                  a. Account first (avoids orphaned contacts) — reuse an
                     explicitly chosen account, or decide Person vs Company and
                     check for duplicates by name/email/phone, reusing a match
                     rather than failing.
                  b. Contact created or linked.
                  c. Opportunity created, carrying lead_id across.
                     Territory auto-assigns from the account's billing address.
                  d. Lead marked is_converted / opportunity_id / converted_at.

4. PIPELINE     Opportunity moves through sales_stage_id. The stage row carries
                probability, is_won, is_lost — won/lost is a property of the
                stage, not a separate field.

5. COST & QUOTE OpportunityCosting captures sell vs cost per line item and derives
                profit. Suppliers, destinations, itineraries, and packages attach
                via pivots. A Quote may be issued (Draft → Sent → Accepted).

6. COLLECT      PaymentScheduleItem plans instalments. Marking one received creates
                an OpportunityTransaction, which then runs the two-step approval:
                pending_verification → verified → approved.
                Alternatively an Invoice is raised and Payments recorded against it.

7. FULFIL       Vouchers issued, departures booked, ledger entries recorded,
                claims and handovers processed.
```

Every step writes an `activity_logs` row visible in the record's History tab, and an `api_audit_logs`
row for the underlying API call.

---

## 10. Permissions catalogue

110 permission strings are enforced across the API. They follow a consistent
`<action>_<module>` shape.

**Standard CRUD**, available for each module below as `view_`, `create_`, `edit_`, `delete_`:

`lead`, `contact`, `opportunity`, `task`, `event`, `note`, `supplier`, `product`, `quote`, `invoice`,
`itinerary`, `package`, `destination`, `department`, `report`, `role`, `user`, `email_template`,
`file_folder`, `patient`

**Accounts** are irregular — `view_account`, `edit_account`, plus `upload_account` / `download_account`.
There is **no** separate person-account permission: person accounts are gated by `edit_account` too.

**Files:** `view_file`, `edit_file`, `delete_file`, `download_file`, `share_file`, `public_link_file`

**Import/export:** `upload_lead`, `download_lead`, `upload_contact`, `download_contact`,
`upload_account`, `download_account`, `export_report`

**Email:** `view_email`, `create_email`, `send_email`

**Opportunity-specific:** `lock_opportunity`, `unlock_opportunity` ⚑, `owner_change_opportunity`,
`verify_opportunity_transaction`, `approve_opportunity_transaction`

**Administrative:** `manage_billing`, `manage_incentives`, `manage_sales_targets`, `manage_territory`,
`view_bd_panel`, `view_leaderboard`, `view_webhook`

⚑ `unlock_opportunity` is auto-granted to any role with `is_admin: true`.

**The frontend must gate every action button with the same permission string the backend enforces.**
Permissions are embedded in the session JWT, so the check is synchronous with no extra fetch. A mismatch
produces buttons that always 403.

---

## 11. API surface

All routes are under `/api/v1`. Interactive docs are served at `/api/docs`.

| Prefix | Module |
|---|---|
| `/auth` | login, token refresh, password reset |
| `/accounts`, `/contacts`, `/leads`, `/opportunities` | core CRM |
| `/tasks`, `/events`, `/notes`, `/emails`, `/comments`, `/reminders` | activity |
| `/files` | upload, folders, shares, versions, public links |
| `/suppliers`, `/itineraries`, `/packages`, `/departures`, `/destinations`, `/products` | travel catalogue |
| `/quotes`, `/invoices` | sales documents |
| `/opportunities/...` | costing, payment schedule, transactions, vouchers, ledger, claims, handover |
| `/users`, `/roles`, `/hierarchies`, `/departments` | identity |
| `/territories`, `/incentives` | territory & incentives |
| `/picklists`, `/custom_fields`, `/standard_fields` | field & picklist configuration |
| `/entity_views` | saved list views |
| `/admin`, `/settings` | admin settings hub |
| `/dashboards`, `/reports` | analytics |
| `/search`, `/search_extras` | global search |
| `/imports` | CSV import/export per entity |
| `/notifications`, `/fcm`, `/messaging` | notifications, push, Gmail/WhatsApp |
| `/webhooks`, `/billing`, `/subscription` | platform |
| `/integrations` ⚑ | **public** web-to-lead capture |
| `/assistant` | AI assistant |
| `/patients`, `/providers`, `/appointments`, `/care-plans`, `/referrals` | healthcare ⚑ |
| `/programs`, `/enrollments` | education ⚑ |
| `/boms`, `/production-orders`, `/inventory` | manufacturing ⚑ |

⚑ `/integrations` is the one **public** endpoint family. It authenticates with a per-tenant API key in
the `X-API-Key` header, **not** a JWT, and is rate-limited per route.
⚑ Vertical routers are gated by the tenant's `modules` flags — a travel tenant gets 403 from
`/patients`.

### Standard response shapes

A list endpoint returns the records under a **module-named key** — not a generic `items` — alongside
pagination and the picklists the UI needs to render its filter bar in the same round trip:

```jsonc
// GET /api/v1/leads/
{
  "leads": [ /* … */ ],
  "pagination": {
    "current_page": 1,
    "per_page": 10,
    "total": 243,
    "pages": 25,
    "next_cursor": "…",   // for "load more"
    "has_more": true
  },
  "lead_statuses": [], "sources": [], "users": [],
  "industries": [], "experiences": [], "sales_stages": []
}
```

Bundling the picklists into the list response is deliberate — it saves the frontend six extra requests
per page load.

Errors return `{"detail": …}`. Validation failures return **422** with a list of per-field errors.
Permission failures return **403** with `Permission denied: <permission> required`.

---

## 12. Frontend data flow

Four layers, each with one job:

| Layer | Location | Responsibility |
|---|---|---|
| Component | `features/<name>/components/` | Rendering and user interaction only |
| React Query hook | `features/<name>/api/use<Name>.ts` | Cache keys, `staleTime`, invalidation on mutation |
| Service | `lib/api/services/<name>.service.ts` | Plain async functions, one file per backend module, no React |
| HTTP client | `lib/api/client.ts` | The single axios instance |

The axios client handles three things you'd otherwise re-implement per call:

- **Token attachment** from an in-memory cache, avoiding a session round-trip on every request.
- **Transient retry** on idempotent GETs — up to 2 retries with backoff on 5xx or connection errors. Only
  GETs, so a retry can never double-submit a create.
- **401 handling** — re-fetch the session (which triggers a silent token refresh) and retry once. It
  logs the user out **only** if the refresh was definitively rejected, so a backend blip doesn't force a
  re-login.

**UI conventions that are enforced:**

- All create/edit happens in a **right-side drawer**. Full-page `/create` and `/[id]/edit` routes were
  deleted and must not be reintroduced.
- All forms use the shared `FormSectionHeader` + `FORM_SHELL_CLASS`. Never hand-roll section headings
  or labels.
- **Form fields are sacred** — do not remove, rename, or reorder fields or headings without an explicit
  request. They were aligned field-by-field against the client's previous CRM.
- Phone inputs use the shared `PhoneInput`; the format is `+<code> <10 digits>`. `mobile` is a
  person-account-only field.

---

## 13. Rules you must follow when writing code

These are enforced in code review. They are not stylistic.

### 1. Every query is tenant-scoped

```python
await Lead.find({"tenant_id": current_user.tenant_id, "deleted_at": None, ...})
```

Never query a domain collection without `tenant_id`. On writes, set
`tenant_id = current_user.tenant_id`. **Never trust a `tenant_id`, `owner_id`, or any foreign id from
the request body.** Cross-reference lookups are scoped too:

```python
await User.find({"_id": {"$in": ids}, "tenant_id": current_user.tenant_id})
```

A stale or forged foreign id must not leak another tenant's data. Reassigning ownership must validate
that the new owner is an active user **in the same tenant**.

### 2. Apply visibility scoping on list, detail, update, and delete

See §8. Tenant scoping alone is not access control.

### 3. Validate `industry_data`, always

Never store an unvalidated `industry_data` blob.

### 4. Soft-delete, never hard-delete

Set `deleted_at`; filter `deleted_at: None` on every read.

### 5. Query picklists through `build_picklist_query`

A bare `tenant_id` filter silently hides all platform defaults.

### 6. Search uses the shared prefix matcher

Use `word_prefix_regex` plus result caps for all search and autocomplete. No contains-regex, no raw
`$regex`. The frontend's `SearchableSelect` mirrors the same behaviour.

### 7. No N+1 lookups

Collect ids, fetch once with `{"_id": {"$in": ids}, "tenant_id": …}`, build a map, then attach.

### 8. Indexes go in the deploy script, not the model

Index creation at application startup crashed boot, so indexes are managed out of band by
`scripts/create_indexes.py`, run as a deploy step. A few older models still declare them inline; new
ones go in the script.

### 9. Every new endpoint gets a tenant-isolation test

Under `apps/backend/tests/security/`. The existing suite covers assistant isolation, audit logging, BD
territory visibility, entity-filter safety, import/export isolation, and upload isolation.

### 10. Verify before claiming done

```bash
# Backend
python -m py_compile <changed files>
python -c "from app.main import app"

# Frontend
npx tsc --noEmit
npm run build
```

### Ten traps, ranked by how often they bite

1. A field isn't on the model → check `industry_data`, then `custom_fields`, then the picklists.
2. Querying `picklists` with a bare `tenant_id` → hides every platform default.
3. Forgetting visibility scoping on detail/update/delete → users open colleagues' records by URL.
4. Trusting `tenant_id` / `owner_id` from the request body.
5. N+1 lookups in list endpoints.
6. Hard-deleting.
7. Adding an index to a model's `Settings` instead of the deploy script.
8. Frontend gate naming a different permission than the endpoint enforces.
9. Type-name collisions: `Contact`, `User`, and `Target` are both domain types **and** icon names —
   use `import type` and alias the icon.
10. Assuming a file is live — modules ending `_extra.py` and several legacy models exist; the router
    mount list in `main.py` is the authority.

---

## 14. Glossary

| Term | Meaning |
|---|---|
| **Tenant** | A customer company. The top-level isolation boundary. |
| **Industry** | `travel` / `healthcare` / `education` / `manufacturing`. Set per tenant; selects which validators and modules apply. |
| **`industry_data`** | Validated sub-document holding industry-specific fields on Lead / Opportunity / Account / Contact / Quote. |
| **`custom_fields`** | Free-form dict for tenant-defined fields — plus a handful of shipped fields that live here for historical reasons. |
| **Picklist** | A dropdown value. All of them live in one `picklists` collection, discriminated by `picklist_type`, with platform defaults plus tenant overrides. |
| **Platform default** | A picklist row with `tenant_id = null`, inherited by every tenant unless overridden. |
| **Person account** | An individual customer stored in `accounts` with `is_person_account = true`. B2C. |
| **Company account** | An organisation in `accounts` with `is_person_account = false`. B2B. |
| **Visibility scope** | The set of `owner_id`s whose records you may see, derived from your role hierarchy. `None` means admin — no filter. |
| **Territory Manager / BD user** | The same role. A user named in `territories.manager_id`; sees that territory's opportunities *instead of* owner-scoped ones. |
| **Polymorphic attachment** | Task / Event / Note / File attaching to any core object via a `*able_type` + `*able_id` pair. |
| **Pivot collection** | A join table for many-to-many links, e.g. `opp_suppliers`. |
| **Saved view** | A stored filter set + column selection per entity type, public (tenant-wide) or private (creator only). |
| **Denormalized name** | A server-managed copy such as `owner_name`, stored to avoid joins. Never a form field. |
| **Soft delete** | Setting `deleted_at` instead of removing the row. |
| **System user** | A non-loginable service account owning the pool of unassigned opportunities. |
| **Field registry** | The `field_registry` collection holding custom-field *definitions*; values live in the record's `custom_fields`. |
