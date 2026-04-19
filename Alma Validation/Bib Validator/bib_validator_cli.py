"""
Bib Validator CLI
-----------------
A terminal-based tool for validating MARCXML bibliographic records
via the Alma API. Fetches a bib record by MMS ID, runs validation,
and optionally pushes corrections back to Alma.

Usage:
    python bib_validator_cli.py
"""

import os
import sys
import requests
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# Import the existing validator – works whether the script is run directly
# from this folder or as part of the installed package.
# ---------------------------------------------------------------------------
try:
    from bib_validator import validate_marcxml_record
    from bib_marc_validator.bib_xml_corrections import route_marc_error
except ImportError:
    # When running from the same directory
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from bib_validator import validate_marcxml_record
    from bib_marc_validator.bib_xml_corrections import route_marc_error

# ---------------------------------------------------------------------------
# Load Alma sandbox API key so it isn't hardcoded in script
# ---------------------------------------------------------------------------
alma_api_key = None
with open(r"C:/Users/stockdalear/Desktop/alma_api_keys.txt") as f:
    for line in f:
        if line.strip().startswith("alma_sandbox_key"):
            alma_api_key = line.split("=", 1)[1].strip().strip('"')
            break

if not alma_api_key:
    raise ValueError("Alma sandbox API key not found in alma_api_keys.txt")

# ---------------------------------------------------------------------------
# Alma API base URL
# ---------------------------------------------------------------------------
ALMA_API_BASE_URL = "https://api-na.hosted.exlibrisgroup.com/almaws/v1/bibs/"

# ---------------------------------------------------------------------------
# Alma API helpers
# ---------------------------------------------------------------------------

def get_record(mms_id):
    """GET a bib record from Alma by MMS ID."""
    url = f"{ALMA_API_BASE_URL}{mms_id}"
    headers = {
        "Accept": "application/xml",
        "Authorization": f"apikey {alma_api_key}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.content
    else:
        print(f"Failed to fetch record for MMS ID {mms_id}: {response.status_code}")
        return None


def put_record(mms_id, xml_body):
    """PUT an updated bib record back to Alma."""
    url = f"{ALMA_API_BASE_URL}{mms_id}"
    headers = {
        "Content-Type": "application/xml",
        "Accept": "application/xml",
        "Authorization": f"apikey {alma_api_key}"
    }
    response = requests.put(url, headers=headers, data=xml_body)
    if response.status_code == 200:
        return response.content
    else:
        print(f"Failed to update record for MMS ID {mms_id}: {response.status_code}")
        return None

# ---------------------------------------------------------------------------
# MARCXML extraction helpers
# ---------------------------------------------------------------------------

def extract_marcxml_from_alma_response(response_xml) -> str:
    """
    Alma wraps the MARC record inside a <bib> envelope.  This function
    extracts the <record> element and returns it as a standalone XML string.
    Accepts bytes or str.
    """
    if isinstance(response_xml, bytes):
        root = ET.fromstring(response_xml)
    else:
        root = ET.fromstring(response_xml)

    # The MARC record lives at  <bib> -> <record> (namespace-aware)
    ns = {"marc": "http://www.loc.gov/MARC21/slim"}

    record = root.find(".//marc:record", ns)
    if record is None:
        # Try without namespace (some Alma responses vary)
        record = root.find(".//record")

    if record is None:
        return None

    xml_str = ET.tostring(record, encoding="unicode")

    # Alma often returns the <record> without the MARC namespace, but
    # bib_validator.py expects it.  Add the namespace if it's missing.
    if "http://www.loc.gov/MARC21/slim" not in xml_str:
        xml_str = xml_str.replace("<record", '<record xmlns="http://www.loc.gov/MARC21/slim"', 1)

    return xml_str

# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_banner():
    print()
    print("=" * 60)
    print("        NLM Bib Record Validator  (CLI Edition)")
    print("=" * 60)
    print()


def classify_errors(errors: list, marcxml: str):
    """
    Split errors into auto-correctable and manual-review lists.

    For each error, we try applying the correction logic.  If the XML
    changes, the error is auto-correctable; otherwise it needs manual review.

    Returns (auto_correctable, manual_review) – two lists of the original
    error objects.
    """
    auto_correctable = []
    manual_review = []

    for err in errors:
        try:
            corrected = route_marc_error(err, marcxml)
            if corrected != marcxml:
                auto_correctable.append(err)
            else:
                manual_review.append(err)
        except Exception:
            # If the correction logic blows up, treat it as manual
            manual_review.append(err)

    return auto_correctable, manual_review


def _format_error_line(number: int, err) -> str:
    """Return a single formatted error line."""
    if isinstance(err, dict):
        msg = err.get("error", str(err))
    else:
        msg = str(err)
    return f"  {number:3}. {msg}"


def print_errors(errors: list, marcxml: str):
    """Pretty-print validation errors in two sections."""
    if not errors:
        print("\n  ✓  No validation errors found!\n")
        return

    auto, manual = classify_errors(errors, marcxml)

    print(f"\n  Found {len(errors)} issue(s):\n")

    if auto:
        print(f"  ── Auto-correctable ({len(auto)}) ──────────────────────")
        for i, err in enumerate(auto, 1):
            print(_format_error_line(i, err))
        print()

    if manual:
        print(f"  ── Needs manual review ({len(manual)}) ─────────────────")
        for i, err in enumerate(manual, 1):
            print(_format_error_line(i, err))
        print()

    return auto, manual

# ---------------------------------------------------------------------------
# Main interactive loop
# ---------------------------------------------------------------------------

def main():
    print_banner()

    while True:
        # --- Prompt for MMS ID ---
        print("-" * 60)
        mms_id = input("Enter a MMS ID (or 'q' to quit): ").strip()
        if mms_id.lower() in ("q", "quit", "exit"):
            print("Goodbye!")
            break
        if not mms_id:
            print("No MMS ID entered. Try again.")
            continue

        # --- Fetch record from Alma ---
        print(f"\nFetching bib record for MMS ID: {mms_id} ...")
        response_content = get_record(mms_id)

        if response_content is None:
            continue

        print("  ✓  Record retrieved successfully.")

        # --- Extract MARCXML ---
        marcxml = extract_marcxml_from_alma_response(response_content)
        if marcxml is None:
            print("  ✗  Could not find a MARC record in the API response.")
            continue

        # --- Validate ---
        print("  Running validation …")
        should_validate, errors = validate_marcxml_record(marcxml, "regular")

        if not should_validate:
            print("\n  ⚠  Record was skipped for validation.")
            if errors:
                print_errors(errors, marcxml)
            continue

        result = print_errors(errors, marcxml)

        # --- Optionally apply corrections and PUT back ---
        if errors and result:
            auto, manual = result

            if auto:
                fix = input("Apply auto-corrections and push to Alma? (y/n): ").strip().lower()
                if fix == "y":
                    corrected_xml = marcxml
                    for err in auto:
                        corrected_xml = route_marc_error(err, corrected_xml)

                    # Swap the corrected <record> back into the full Alma envelope
                    import re as _re
                    if isinstance(response_content, bytes):
                        envelope = response_content.decode("utf-8")
                    else:
                        envelope = response_content

                    envelope = _re.sub(
                        r"<record[^>]*>.*?</record>",
                        corrected_xml,
                        envelope,
                        count=1,
                        flags=_re.DOTALL,
                    )

                    print(f"\n  Pushing corrected record for MMS ID: {mms_id} ...")
                    put_result = put_record(mms_id, envelope.encode("utf-8"))
                    if put_result is not None:
                        print("  ✓  Record updated successfully in Alma.")

                    if manual:
                        print(f"\n  ⚠  {len(manual)} issue(s) still require manual review.")
            else:
                print("  No auto-corrections available – all issues need manual review.")

        print()  # blank line before next prompt


if __name__ == "__main__":
    main()
