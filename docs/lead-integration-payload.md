# Tutterfly CRM — Web-to-Lead Integration Payload (FINAL)

Website se Tutterfly CRM mein lead bhejne ka JSON contract — **structure exactly hamare lead form
ke according**: contact/address fields top-level par, travel fields `industry_data` mein, aur form
ke **Additional Information** section ke fields (Segment / Campaign / Experience) `custom_fields`
mein. Endpoint abhi build hona baaki hai (`POST /api/v1/integrations/leads` — TBD); URL + token
go-live se pehle milega.

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
    "industry_data": {
      "travel_date": "2026-09-15",
      "no_of_nights": 5,
      "no_of_pax": 4,
      "no_of_adults": 2,
      "no_of_childs": 1,
      "no_of_infants": 1,
      "destinations": ["Bali", "Singapore"],
      "is_fixed": false
    },
    "custom_fields": {
      "segment": "B2C",
      "campaign_name": "bali-summer-2026",
      "experience": "Honeymoon"
    }
  }
}
```

> **Notes:**
> - `source` / `custom_fields.experience` / `industry_data.destinations` mein team **name** bhejegi —
>   name→picklist-id resolve endpoint karega.
> - **Duplicate handling**: same email/mobile wali lead dobara aaye to CRM duplicate create nahi
>   karta — existing lead se match hota hai.

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
| `industry_data.no_of_nights/pax/adults/childs/infants` | Integers ≥ 0 — number bhejo, string nahi. |
| `industry_data.is_fixed` | Boolean — fixed departure. |
| `custom_fields.segment` | `B2C` (default) / `B2B` / `CORPORATE` — form ke Additional Information ka Segment. |
| `custom_fields.campaign_name` | Campaign identifier — form ka Campaign field. |
| `custom_fields.experience` | `Budget` / `Standard` / `Luxury` / `Ultra-Luxury` / `Adventure` / `Honeymoon` / `Family` — form ka Experience field. |

## Purane (old CRM) payload se mapping — team ke reference ke liye

| Purana | Naya |
|---|---|
| `region` | `state` |
| `travel_date`, `no_of_nights`, `no_of_pax`, `fixed_departure` (top-level) | `industry_data.*` (`fixed_departure` → `is_fixed`) |
| `destinations_name` / `destination_json` / `min_country_data` | `industry_data.destinations` (names array) |
| `no_of_traveler` / `no_of_passengers` | `industry_data.no_of_pax` |
| `campaign_name` (top-level) | `custom_fields.campaign_name` |
| `experience` (top-level) / `custom_fields.experience` | `custom_fields.experience` |
| `custom_fields.segment` | `custom_fields.segment` (same) |
| `source_medium` | ❌ mat bhejo — CRM se removed |
| `ip` | ❌ mat bhejo — CRM se removed |
| `ref_id`, `url`, `dook_enquiry_id`, `departure_id`, `form_type`, `bnpl` | ❌ drop — CRM lead mein koi field nahi |
| `custom_fields.destination` / `description` / `date_of_travel` / `no_of_passengers` | ❌ drop — canonical fields upar cover karte hain |

## Backend implementation notes (Tutterfly-internal, endpoint banate waqt)

1. **Auth**: per-tenant integration token, hashed store; tenant_id token se resolve — body se kabhi nahi.
2. **Owner assignment**: system user vs default user vs round-robin — DECISION PENDING. `creation_type="auto"`.
3. **Payload mapping**: backend ab Additional Information ko `Lead.custom_fields` dict mein hi
   store karta hai (2026-07-03 refactor, `scripts/migrate_lead_additional_to_custom_fields.py`) —
   payload ka `custom_fields` block 1:1 map hota hai:
   - `custom_fields.segment` → `Lead.custom_fields["segment"]` (default `B2C`)
   - `custom_fields.campaign_name` → `Lead.custom_fields["campaign_name"]`
   - `custom_fields.experience` (name) → Experience picklist id → `Lead.custom_fields["experience_id"]`
   - `source` → `source_id`; `industry_data.destinations` names → `destinations` + `destination_ids`
4. **Required-field validation**: `validate_lead_record` (entity_required_fields.py) — last_name, city, state, country, source_id + travel: travel_date, destinations.
5. **Dedupe**: built-in `_check_duplicate_lead` (email+mobile) create par chalta hai — integration ke liye policy decide karni hai (same person, nayi enquiry?).
6. **Security test**: tenant-isolation test `apps/backend/tests/security/` mein (CLAUDE.md rule).
7. Unknown/extra fields ignore karna, error mat dena.
