"""Unit tests for company name standardization and alias mapping."""

from src.transform import normalize_company_name


def test_alias_lookup():
    alias_map = {
        "google": "Google",
        "google llc": "Google",
        "google inc": "Google",
        "jpmc": "JPMorgan Chase",
        "aws": "Amazon",
    }

    name, mapped = normalize_company_name("google llc", alias_map)
    assert name == "Google"
    assert mapped is True

    name, mapped = normalize_company_name("JPMC", alias_map)
    assert name == "JPMorgan Chase"
    assert mapped is True

    name, mapped = normalize_company_name("  AWS  ", alias_map)
    assert name == "Amazon"
    assert mapped is True


def test_legal_suffix_stripping():
    alias_map = {"microsoft": "Microsoft", "apple": "Apple"}

    # Stripping 'inc' or 'corp'
    name, mapped = normalize_company_name("Apple Inc.", alias_map)
    assert name == "Apple"
    assert mapped is True

    name, mapped = normalize_company_name("Microsoft Corporation", alias_map)
    assert name == "Microsoft"
    assert mapped is True


def test_unmapped_company_name():
    alias_map = {"google": "Google"}

    # Unmapped names should be cleaned and title-cased
    name, mapped = normalize_company_name("  random  robotics  pvt  ltd  ", alias_map)
    assert name == "Random Robotics"
    assert mapped is False
