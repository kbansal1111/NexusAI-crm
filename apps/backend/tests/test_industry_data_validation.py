"""
Regression tests for industry_data validation across non-travel industries.

These pin the two failure modes that broke healthcare/education/manufacturing
create & edit forms:

1. Multi-value fields (diagnosis codes, submitted documents, certifications,
   ...) are plain text inputs in the UI, so the API receives a comma-separated
   STRING where the schema declares List[str]. That must coerce, not 422.

2. Untouched numeric/datetime inputs submit as "" — an empty string must be
   treated as "not provided", not fed to int/float/datetime parsing.
"""
import pytest
from pydantic import ValidationError

from app.schemas.industry_data import validate_industry_data


# ---------------------------------------------------------------------------
# 1. Comma-separated string → List[str] coercion
# ---------------------------------------------------------------------------

def test_healthcare_opportunity_diagnosis_codes_accepts_csv_string():
    result = validate_industry_data(
        industry="healthcare",
        data={"treatment_type": "Physio", "diagnosis_codes": "E11.9, I10"},
        mode="opportunity",
    )
    assert result["diagnosis_codes"] == ["E11.9", "I10"]


def test_healthcare_opportunity_diagnosis_codes_accepts_real_list():
    result = validate_industry_data(
        industry="healthcare",
        data={"diagnosis_codes": ["E11.9", "I10"]},
        mode="opportunity",
    )
    assert result["diagnosis_codes"] == ["E11.9", "I10"]


def test_education_opportunity_documents_submitted_accepts_csv_string():
    result = validate_industry_data(
        industry="education",
        data={"admission_status": "applied", "documents_submitted": "Transcript, Passport"},
        mode="opportunity",
    )
    assert result["documents_submitted"] == ["Transcript", "Passport"]


def test_manufacturing_contact_certifications_accepts_csv_string():
    result = validate_industry_data(
        industry="manufacturing",
        data={"certifications": "Six Sigma, AWS D1.1"},
        mode="contact",
    )
    assert result["certifications"] == ["Six Sigma", "AWS D1.1"]


def test_healthcare_account_specialties_accepts_csv_string():
    result = validate_industry_data(
        industry="healthcare",
        data={"facility_type": "Clinic", "specialties": "Cardiology,Orthopedics"},
        mode="account",
    )
    assert result["specialties"] == ["Cardiology", "Orthopedics"]


# ---------------------------------------------------------------------------
# 2. Empty strings from untouched form inputs are dropped, not rejected
# ---------------------------------------------------------------------------

def test_empty_string_numeric_fields_are_dropped_not_422():
    result = validate_industry_data(
        industry="healthcare",
        data={
            "treatment_type": "Consult",
            "estimated_treatment_cost": "",  # untouched number input
            "appointment_date": "",          # untouched datetime input
        },
        mode="opportunity",
    )
    assert result == {"diagnosis_codes": [], "procedure_codes": [], "treatment_type": "Consult"}


def test_manufacturing_empty_quantity_is_dropped():
    result = validate_industry_data(
        industry="manufacturing",
        data={"quantity_ordered": "", "plant_location": "Pune"},
        mode="opportunity",
    )
    assert "quantity_ordered" not in result
    assert result["plant_location"] == "Pune"


def test_numeric_strings_still_coerce():
    result = validate_industry_data(
        industry="manufacturing",
        data={"quantity_ordered": "25", "unit_of_measure": "kg"},
        mode="opportunity",
    )
    assert result["quantity_ordered"] == 25


# ---------------------------------------------------------------------------
# 3. Real validation errors still fire (cleanup must not swallow them)
# ---------------------------------------------------------------------------

def test_invalid_enum_still_rejected():
    with pytest.raises(ValidationError):
        validate_industry_data(
            industry="healthcare",
            data={"urgency": "asap"},  # not in routine|urgent|emergent
            mode="lead",
        )


def test_travel_opportunity_still_requires_travel_date():
    with pytest.raises(ValidationError):
        validate_industry_data(
            industry="travel",
            data={"no_of_pax": 2, "travel_date": ""},  # blank required field
            mode="opportunity",
        )


def test_unknown_industry_still_rejected():
    with pytest.raises(ValueError):
        validate_industry_data(industry="healtcare", data={"x": 1}, mode="lead")
