# Tutterfly CRM — Web-to-Lead Integration Payload (FINAL — endpoint LIVE)

Website se Tutterfly CRM mein lead bhejne ka JSON contract — **structure exactly hamare lead form
ke according**: contact/address fields top-level par, travel fields `industry_data` mein, aur form
ke **Additional Information** section ke fields (Segment / Campaign / Experience) `custom_fields`
mein.

## Endpoint

```
POST https://<backend-domain>/api/v1/integrations/leads
Content-Type: application/json
X-API-Key: <API_KEY>          # key SIRF is header mein — body mein token nahi
```

- API key Tutterfly team degi (`scripts/manage_integration_tokens.py create --tenant <sub> --label Website`).
  Key sirf creation par ek baar dikhti hai; rotate karne ke liye nayi banao → website par lagao → purani revoke.
- **Har web lead ka `source` automatically "Website" set hota hai** — payload mein `source` bhejne
  ki zaroorat nahi (bheja to ignore hoga). Yahi flag web-origin leads ko identify karta hai.
- **Auto-conversion**: web lead create hote hi Opportunity mein convert ho jaati hai —
  lead ka owner tenant **Admin**, opportunity **System** pool mein (pre-sales assign karegi).
- **Duplicates**: har submission NAYI lead banati hai (same email/mobile par bhi).

### Response codes

| Code | Matlab | Website team action |
|---|---|---|
| 201 | `{"success":true,"lead_id":"...","opportunity_id":"...","converted":true}` | Done |
| 401 | Invalid/revoked API key | Key check karo |
| 422 | Required field missing (readable message in `detail`) | Payload fix karo |
| 429 | Rate limit (60/min) | Retry with backoff |
| 5xx | Server error | Retry with backoff |

## Payload

```json
{
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
    "ip": "203.0.113.7",
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
> - `custom_fields.experience` / `industry_data.destinations` mein team **name** bhejegi —
>   name→picklist-id resolve endpoint karega.
> - **Duplicate handling**: same email/mobile wali lead dobara aaye to CRM duplicate create nahi
>   karta — existing lead se match hota hai.

## Required (CRM enforce karta hai — `validate_lead_record`)

| Field | Rule |
|---|---|
| `X-API-Key` header | Har request. Server-to-server only, browser mein expose nahi. |
| `last_name` | Max 100. Single "Name" field ho to pura naam yahan, `first_name` = `""`. |
| `city`, `state`, `country` | Teeno mandatory. |
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
| `ip` | Visitor ka IP address — CRM mein lead ke "IP Address" field mein dikhega (isi se team enquirer ka country nikalti hai). Zaroor bhejo. |
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
| `source` | ❌ bhejne ki zaroorat nahi — har web lead automatically "Website" |
| `token` (body mein) | ❌ removed — key ab sirf `X-API-Key` header mein |
| `source_medium` | ❌ mat bhejo — CRM se removed |
| `ip` | ✅ wapas aa gaya (2026-07-04) — `ip` bhejo, CRM mein `custom_fields.ip_address` mein store hota hai |
| `ref_id`, `url`, `dook_enquiry_id`, `departure_id`, `form_type`, `bnpl` | ❌ drop — CRM lead mein koi field nahi |
| `custom_fields.destination` / `description` / `date_of_travel` / `no_of_passengers` | ❌ drop — canonical fields upar cover karte hain |

## PHP integration example (team ke reference ke liye)

```php
<?php
define('TUTTERFLY_LEAD_API', 'https://tutterfly-backend.bigfat.ai/api/v1/integrations/leads');
define('TUTTERFLY_API_KEY', '<API_KEY>');   // config/env mein rakho

$payload = json_encode(array(
    "lead" => array(
        "first_name"  => "",
        "last_name"   => $name,
        "email"       => $email,
        "mobile"      => $mob_no,                // 10 digit chalega, +91 hum laga denge
        "phone"       => $mob_no,
        "company"     => $company,
        "city"        => $city,
        "state"       => $region,                // purana 'region'
        "country"     => $country,
        "ip"          => $ip,                    // visitor IP — ZAROOR bhejo
        "industry_data" => array(
            "travel_date"  => $travel_date,      // YYYY-MM-DD — REQUIRED
            "no_of_nights" => $duration,
            "no_of_pax"    => $no_of_traveler,
            "destinations" => $destinations_name // "Bali, Singapore" chalega
        ),
        "custom_fields" => array(
            "campaign_name" => $campaign_id,
            "experience"    => $experience
        )
    )
));

$ch = curl_init(TUTTERFLY_LEAD_API);
curl_setopt_array($ch, array(
    CURLOPT_POST           => true,
    CURLOPT_POSTFIELDS     => $payload,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT        => 15,
    CURLOPT_HTTPHEADER     => array(
        'Content-Type: application/json',
        'X-API-Key: ' . TUTTERFLY_API_KEY    // key SIRF header mein
    )
));
$response  = curl_exec($ch);
$http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

if ($http_code == 201) {
    $result = json_decode($response, true);  // lead_id, opportunity_id, converted
} else {
    // 401 = key galat | 422 = field missing | 429/5xx = retry
    error_log("Tutterfly lead API failed [HTTP $http_code] :: $response");
}
?>
```

> **Note (wire format vs storage):** payload mein `ip` top-level hai (website ke liye simple),
> par CRM isse lead ke **`custom_fields.ip_address`** mein store karta hai — wahi jagah jahan
> form ka Additional Information → IP Address field save hota hai. Dono align hain.

## Backend implementation notes (Tutterfly-internal — SHIPPED 2026-07-04)

Endpoint: `app/api/v1/integrations.py`. Keys: `integration_tokens` collection (sha256 hash + prefix,
scopes `leads:write`, multi-key rotation) — manage via `scripts/manage_integration_tokens.py`.
- Auth: X-API-Key header ONLY (body token support user ke bolne par remove kiya) → hash lookup → tenant. 401 fail-closed.
- Owner: tenant Admin (is_admin role, oldest active; fallback System user). `creation_type="auto"`.
- Source: hamesha "Website" (resolve ya tenant-scoped auto-create) — web-origin flag.
- Auto-convert: `convert_lead(lead, LeadConvert())` → Account/Contact/Opportunity; opp owner System pool.
  Conversion failure lead ko kabhi nahi girati (201 + `converted:false` + error log).
- Duplicates: `skip_duplicate_check=True` — hamesha nayi lead.
- Normalization: `normalize_loose_phone` (+91 default), string→int/bool casts, comma-string destinations,
  invalid email/phone drop (reject nahi), unknown fields ignore (`extra="ignore"` — hostile tenant_id/owner_id bhi).
- Mapping: `custom_fields.segment/campaign_name` → Lead.custom_fields; `experience` name → `experience_id`;
  destinations names → `destination_ids` (unknown names skip, names phir bhi save).
- Validation: `validate_lead_record` — last_name, city, state, country + travel: travel_date, destinations.
- Tests: `tests/security/test_lead_integration.py` (33 hermetic tests, tenant isolation included).
- Rate limit: 60/min per IP.
