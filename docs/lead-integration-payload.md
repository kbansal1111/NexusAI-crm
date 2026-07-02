# Tutterfly CRM — Web-to-Lead Integration Payload (FINAL)

Website se Tutterfly CRM mein lead bhejne ka JSON contract — **structure exactly hamare Lead
schema + Lead form ke according** (`app/models/lead.py` + `TravelLeadData`). Har field jo yahan
hai wo CRM ke lead form mein dikhti hai. Endpoint abhi build hona baaki hai
(`POST /api/v1/integrations/leads` — TBD); URL + token go-live se pehle milega.

## Payload

```json
{
  "token": "<TUTTERFLY_INTEGRATION_TOKEN — hum denge>",
  "lead": {
    "salutation": "Mr.",
    "first_name": "Rahul",
    "last_name": "Sharma",
    "email": "rahul.sharma@example.com",
    "mobile": "+91 9876543210",
    "phone": "+91 1141234567",
    "company": "Acme Pvt Ltd",
    "title": "Manager",
    "no_employees": 10,
    "website": "https://acme.example.com",
    "street": "12, MG Road",
    "city": "New Delhi",
    "state": "Delhi",
    "zip": "110001",
    "country": "India",
    "source": "Web",
    "campaign_name": "bali-summer-2026",
    "segment": "B2C",
    "industry_data": {
      "travel_date": "2026-09-15",
      "no_of_nights": 5,
      "no_of_pax": 4,
      "no_of_adults": 2,
      "no_of_childs": 1,
      "no_of_infants": 1,
      "destinations": ["Bali", "Singapore"],
      "experience": "Honeymoon",
      "is_fixed": false
    },
    "ref_id": "WEB-2026-000123"
  }
}
```

> **Notes:**
> - `source` / `industry_data.experience` / `industry_data.destinations` mein team **name** bhejegi —
>   name→picklist-id resolve endpoint karega (`source_id`, `experience_id`, `destination_ids`).
> - `ref_id` CRM ka lead field **nahi** hai — sirf **dedupe/idempotency** ke liye hai (retry ya
>   double-submit par duplicate lead nahi banegi). Endpoint isse internally store karega, lead form
>   mein nahi dikhega.
> - Custom fields system (admin-defined additional fields) humne use nahi kiya hai, isliye contract
>   mein koi `custom_fields` block **nahi** hai.

## Required (CRM enforce karta hai — `validate_lead_record`)

| Field | Rule |
|---|---|
| `token` | Har request. Server-to-server only, browser mein expose nahi. |
| `last_name` | Max 100. Single "Name" field ho to pura naam yahan, `first_name` = `""`. |
| `city`, `state`, `country` | Teeno mandatory. |
| `source` | Picklist name — `Web`, `Instagram`, `Google`, `Whatsapp`… Naya value pehle humein batao. |
| `industry_data.travel_date` | `YYYY-MM-DD`. Form par required rakho. |
| `industry_data.destinations` | Names ka array, kam-se-kam ek. |

## Optional

| Field | Note |
|---|---|
| `email` / `mobile` | Kam-se-kam ek bhejo. Phone format `+91 9876543210`; sirf 10 digits → `+91` maan lenge. |
| `phone` | Alternate/landline, same format. |
| `salutation` | `Mr.` / `Mrs.` / `Ms.` / `Dr.` / `Prof.` |
| `company`, `title`, `no_employees`, `website` | B2B info. `no_employees` integer ≥ 1. |
| `street`, `zip` | Address extras. |
| `campaign_name` | Campaign identifier — CRM form ke "Campaign" field mein dikhta hai. |
| `segment` | `B2C` (default) / `B2B` / `CORPORATE`. |
| `industry_data.no_of_nights/pax/adults/childs/infants` | Integers ≥ 0 — number bhejo, string nahi. |
| `industry_data.experience` | `Budget` / `Standard` / `Luxury` / `Ultra-Luxury` / `Adventure` / `Honeymoon` / `Family`. |
| `industry_data.is_fixed` | Boolean — fixed departure. |
| `ref_id` | **Strongly recommended** — unique per enquiry, dedupe key (retry-safe). CRM field nahi, sirf integration ke liye. |

## Purane (old CRM) payload se mapping — team ke reference ke liye

| Purana | Naya |
|---|---|
| `region` | `state` |
| `travel_date`, `no_of_nights`, `no_of_pax`, `fixed_departure`, `experience` (top-level) | `industry_data.*` (`fixed_departure` → `is_fixed`) |
| `destinations_name` / `destination_json` / `min_country_data` | `industry_data.destinations` (names array) |
| `no_of_traveler` / `no_of_passengers` | `industry_data.no_of_pax` |
| `ref_id` | `ref_id` (dedupe ke liye, CRM field nahi) |
| `source_medium` | ❌ mat bhejo — CRM se removed |
| `ip` | ❌ mat bhejo — CRM se removed |
| `url`, `dook_enquiry_id`, `departure_id`, `form_type`, `bnpl` | ❌ drop — CRM lead mein koi field nahi |
| `custom_fields` block (segment/destination/description/…) | ❌ drop — custom fields system use nahi ho raha; `segment` top-level bhejo |

## Backend implementation notes (Tutterfly-internal, endpoint banate waqt)

1. **Auth**: per-tenant integration token, hashed store; tenant_id token se resolve — body se kabhi nahi.
2. **Owner assignment**: system user vs default user vs round-robin — DECISION PENDING. `creation_type="auto"`.
3. **Resolution**: `source`/`experience`/`destinations` names → picklist ObjectIds (`build_picklist_query`, case-insensitive); phone normalize (`+91` default — `safe_phone_validator` invalid ko silently null karta hai, isliye pehle normalize).
4. **Required-field validation**: `validate_lead_record` (entity_required_fields.py) — last_name, city, state, country, source_id + travel: travel_date, destinations.
5. **Dedupe**: `ref_id` par idempotency. Storage: Lead doc ke `custom_fields` dict mein internally rakh sakte hain (`{"ref_id": ...}`) — UI join isse overwrite karta hai to display mein nahi aayega, sirf query ke kaam aayega. NOTE: built-in `_check_duplicate_lead` (email+mobile) bhi create par chalta hai — integration ke liye iski policy decide karni hai (same person, nayi enquiry?).
6. **Security test**: tenant-isolation test `apps/backend/tests/security/` mein (CLAUDE.md rule).
7. Unknown/extra fields ignore karna, error mat dena (old site extras bhej sakti hai).
