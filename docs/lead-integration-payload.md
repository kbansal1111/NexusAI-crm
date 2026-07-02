# Tutterfly CRM — Web-to-Lead Integration Payload (v1 draft)

Yeh JSON contract website/landing-page forms se Tutterfly CRM mein lead bhejne ke liye hai.
Endpoint abhi build hona baaki hai (`POST /api/v1/integrations/leads` — TBD); payload shape final
karke team ke saath share kiya ja raha hai taaki dono taraf ka kaam parallel chale.

## Full payload

```json
{
  "token": "<TUTTERFLY_INTEGRATION_TOKEN — Tutterfly team provide karegi, per-tenant>",
  "lead": {
    "salutation": "Mr.",
    "first_name": "Rahul",
    "last_name": "Sharma",

    "email": "rahul.sharma@example.com",
    "mobile": "+91 9876543210",
    "phone": "+91 1141234567",

    "company": "Acme Pvt Ltd",
    "website": "https://acme.example.com",

    "street": "12, MG Road",
    "city": "New Delhi",
    "state": "Delhi",
    "zip": "110001",
    "country": "India",

    "source": "Web",
    "campaign_name": "bali-summer-2026",
    "ip_address": "203.0.113.7",
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
      "description": "Customer wants beach-facing villa, flexible on dates by 2-3 days."
    }
  }
}
```

## Field rules

| Field | Required | Format / Notes |
|---|---|---|
| `token` | ✅ | Har request mein. Tutterfly per-tenant token dega. Leak hone par rotate hoga. |
| `last_name` | ✅ | Max 100 chars. Agar form mein ek hi "Name" field hai to pura naam yahan bhejo, `first_name` khali. |
| `first_name` | optional | Max 100. Khali string chalegi. |
| `salutation` | optional | `Mr.` / `Mrs.` / `Ms.` / `Dr.` / `Prof.` |
| `email` | optional* | Valid email. *Email ya mobile mein se kam-se-kam ek hona chahiye. |
| `mobile` | optional* | **`+<country code> <10 digits>`** — e.g. `+91 9876543210`. Sirf 10 digits bhejoge to hum `+91` maan lenge; country code ke saath bhejna best hai. |
| `phone` | optional | Same format as mobile. Landline/alternate ke liye. |
| `company` | optional | B2B enquiry ho to. Max 255. |
| `website` | optional | Customer ki company website (form ka URL nahi — wo `custom_fields.campaign_url` mein). |
| `street`/`city`/`state`/`zip`/`country` | optional | Customer ka address. Purana `region` ab `state` hai. |
| `source` | ✅ | Picklist **name** bhejo (e.g. `Web`, `Instagram`, `Google`, `Whatsapp`). ID resolve hum karenge. Naya source chahiye to pehle Tutterfly team ko bolo. |
| `campaign_name` | optional | Campaign identifier (purana `campaign_id` value). |
| `ip_address` | optional | Visitor IP (purana `ip`). |
| `segment` | optional | `B2C` (default) / `B2B` / `CORPORATE`. |
| `industry_data.travel_date` | ✅ | `YYYY-MM-DD`. Travel lead ke liye **mandatory** — form mein date field required rakho. |
| `industry_data.no_of_nights` | optional | Integer ≥ 0 (purana `no_of_nights`/`duration`). Number bhejo, string nahi. |
| `industry_data.no_of_pax` | optional | Integer ≥ 0 — total travellers (purana `no_of_pax`/`no_of_passengers`). |
| `industry_data.no_of_adults` / `no_of_childs` / `no_of_infants` | optional | Integer ≥ 0. Breakdown available ho to bhejo. |
| `industry_data.destinations` | optional | **Names ka array** (e.g. `["Bali"]`). Purane `destination_json`/`destinations_name`/`min_country_data` ki jagah sirf yeh. |
| `industry_data.experience` | optional | Experience **name**: `Budget` / `Standard` / `Luxury` / `Ultra-Luxury` / `Adventure` / `Honeymoon` / `Family`. |
| `industry_data.is_fixed` | optional | Boolean (purana `fixed_departure`). |
| `custom_fields.ref_id` | strongly recommended | Tumhare system ka unique reference — **dedupe isi par hoga**, duplicate submission par dobara lead nahi banegi. |
| `custom_fields.enquiry_id` | optional | Purana `dook_enquiry_id`. |
| `custom_fields.campaign_url` | optional | Landing page ka full URL (purana `url`). |
| `custom_fields.form_type` / `bnpl` / `description` | optional | Free-form; jaise pehle bhejte the. |

## Purane payload se kya HATA (mat bhejna)

| Purana field | Kyun |
|---|---|
| `source_medium` | Field system se remove ho chuki hai — sirf `source` hai. |
| `destination_json`, `destinations_name`, `min_country_data` | Ab sirf `industry_data.destinations` (names array). |
| `departure_id` | Lead par exist nahi karta. |
| `region` | Ab `state`. |
| `ip` | Ab `ip_address`. |
| `no_of_pax` (top-level), `travel_date` (top-level), `experience` (top-level), `fixed_departure`, `no_of_nights` (top-level) | Sab `industry_data` ke andar. |
| `custom_fields.segment`, `custom_fields.destination`, `custom_fields.no_of_passengers`, `custom_fields.date_of_travel`, `custom_fields.experience` | Duplicates the — canonical jagah upar define hai. |

## Minimal example (chhota enquiry form)

```json
{
  "token": "<TOKEN>",
  "lead": {
    "first_name": "",
    "last_name": "Priya Verma",
    "email": "priya@example.com",
    "mobile": "+91 9812345678",
    "city": "Mumbai",
    "state": "Maharashtra",
    "country": "India",
    "source": "Web",
    "industry_data": {
      "travel_date": "2026-10-05",
      "no_of_pax": 2,
      "destinations": ["Maldives"]
    },
    "custom_fields": {
      "ref_id": "WEB-2026-000124"
    }
  }
}
```

## Backend implementation notes (Tutterfly-internal, endpoint banate waqt)

1. **Auth**: per-tenant integration token, hashed store; tenant_id token se resolve — body se kabhi nahi.
2. **Owner assignment**: system user vs default user vs round-robin — DECISION PENDING. `creation_type="auto"` set hoga.
3. **Normalization**: phone → `+91 ` default prefix; ints cast; `source`/`experience`/`destinations` name→picklist-id resolve (`build_picklist_query`); unknown names ki policy decide karni hai.
4. **Dedupe**: `custom_fields.ref_id` (fallback `enquiry_id`) par idempotency — same ref dobara aaye to existing lead return, duplicate create nahi.
5. **travel_date policy**: travel tenants ke liye required (`require_for_travel=True`); missing par 422 ya default — decide karna hai (contract mein abhi mandatory bola hai).
6. **Security test**: tenant-isolation test `apps/backend/tests/security/` mein (CLAUDE.md rule).
