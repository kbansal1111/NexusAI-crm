# Tutterfly CRM — Web-to-Lead Integration Payload (FINAL)

Website se Tutterfly CRM mein lead bhejne ka JSON contract — **structure exactly hamare Lead
schema ke according** (`app/models/lead.py` + `TravelLeadData`). Travel fields `industry_data`
ke andar, traceability `custom_fields` mein. Endpoint abhi build hona baaki hai
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
    "custom_fields": {
      "ref_id": "WEB-2026-000123",
      "enquiry_id": "98765",
      "campaign_url": "https://dooktravels.com/packages/bali?utm_campaign=bali-summer-2026",
      "form_type": "package_enquiry",
      "bnpl": "no",
      "description": "Customer wants beach-facing villa, flexible on dates."
    }
  }
}
```

> Sirf ek deviation schema se: `source` aur `industry_data.experience` mein team **name** bhejegi
> (`source_id`/`experience_id` ObjectIds unke paas nahi hote) — name→id resolve endpoint karega.
> Isi tarah `destinations` names hain; `destination_ids` hum resolve karenge.

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
| `campaign_name` | Campaign identifier. |
| `segment` | `B2C` (default) / `B2B` / `CORPORATE`. |
| `industry_data.no_of_nights/pax/adults/childs/infants` | Integers ≥ 0 — number bhejo, string nahi. |
| `industry_data.experience` | `Budget` / `Standard` / `Luxury` / `Ultra-Luxury` / `Adventure` / `Honeymoon` / `Family`. |
| `industry_data.is_fixed` | Boolean — fixed departure. |
| `custom_fields.ref_id` | **Strongly recommended** — unique per enquiry, dedupe key (retry-safe). |
| `custom_fields.enquiry_id` | Purana `dook_enquiry_id`; fallback dedupe key. |
| `custom_fields.campaign_url` | Landing page full URL (purana `url`). |
| `custom_fields.form_type` / `bnpl` / `description` | Free-form. |

## Purane (old CRM) payload se mapping — team ke reference ke liye

| Purana | Naya |
|---|---|
| `region` | `state` |
| `travel_date`, `no_of_nights`, `no_of_pax`, `fixed_departure`, `experience` (top-level) | `industry_data.*` (`fixed_departure` → `is_fixed`) |
| `destinations_name` / `destination_json` / `min_country_data` | `industry_data.destinations` (names array) |
| `url` | `custom_fields.campaign_url` |
| `ref_id` (top-level) | `custom_fields.ref_id` |
| `dook_enquiry_id` | `custom_fields.enquiry_id` |
| `source_medium` | ❌ mat bhejo — CRM se removed |
| `ip` | ❌ mat bhejo — CRM se removed |
| `departure_id` | ❌ drop |
| `custom_fields.segment` / `destination` / `date_of_travel` / `no_of_passengers` / `experience` | ❌ duplicates — canonical jagah upar |

## Backend implementation notes (Tutterfly-internal, endpoint banate waqt)

1. **Auth**: per-tenant integration token, hashed store; tenant_id token se resolve — body se kabhi nahi.
2. **Owner assignment**: system user vs default user vs round-robin — DECISION PENDING. `creation_type="auto"`.
3. **Resolution**: `source`/`experience`/`destinations` names → picklist ObjectIds (`build_picklist_query`, case-insensitive); phone normalize (`+91` default — `safe_phone_validator` invalid ko silently null karta hai, isliye pehle normalize); unknown-name policy decide karni hai.
4. **Required-field validation**: `validate_lead_record` (entity_required_fields.py).
5. **Dedupe**: `custom_fields.ref_id` (fallback `enquiry_id`) par idempotency.
6. **Security test**: tenant-isolation test `apps/backend/tests/security/` mein (CLAUDE.md rule).
7. Unknown/extra fields ignore karna, error mat dena.
