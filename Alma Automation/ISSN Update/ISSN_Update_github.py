# =============================================================================
# NLM UI → ISSN Updater for Alma
# =============================================================================
# This script automates the process of updating ISSN (022) fields in Alma
# bibliographic records. It reads a CSV file containing NLM Unique Identifiers
# and their associated ISSNs, looks up each record in Alma by NLM UI (stored
# in 035 $9), then rebuilds the 022 field(s) with the correct ISSNs.
#
# What the script does for each record:
#
#   - Looks up the bib record via the Alma API using the NLM UI as an
#     "other system ID" search, then confirms the match by checking 035 $9
#   - Detects whether the record represents an electronic resource (using
#     006 or 337 $a) to decide which ISSN should be the primary $a
#   - Rebuilds the 022 field(s):
#       • Primary 022: $a (main ISSN), $l (linking ISSN), optional $2, $9, $7
#       • Alternate 022: $a (other-format ISSN), $9, $7
#   - Cleans up 260 $b by removing any '[updated]' text
#   - 995 (local processing field): stamps today's date as a review date
# =============================================================================

# --- Python libraries used by this script ---
import csv                              # Reads the input CSV file
import requests                         # Makes HTTP calls to the Alma API
import xml.etree.ElementTree as ET      # Parses and edits the MARC XML records
from datetime import datetime           # Gets today's date for the 995 field

# =============================================================================
# API KEY SETUP
# =============================================================================
# Your API key is read from this variable. For better security, consider
# reading it from a separate text file so it is never exposed in the script
# itself (especially important for a public GitHub repository).
#
# Replace the value below with your own Alma API key, or refactor to read
# from a file as shown in the commented-out example.
#
# --- File-based alternative (recommended) ---
# alma_api_key = None
# with open(r"your_file_path_here.txt") as f:
#     for line in f:
#         if line.strip().startswith("alma_sandbox_key"):
#             alma_api_key = line.split("=", 1)[1].strip().strip('"')
#             break
# if not alma_api_key:
#     raise ValueError("Alma API key not found")
# API_KEY = alma_api_key
# ---
API_KEY = "your_api_key_here"

# Alma API base URL — change "api-na" to "api-eu" or "api-ap" if your
# Alma instance is hosted in Europe or Asia Pacific.
BASE_URL = "https://api-na.hosted.exlibrisgroup.com/almaws/v1/bibs"

# Path to the input CSV file (relative or absolute)
CSV_FILE = "ISSN.csv"

# Common HTTP headers for all Alma API requests
HEADERS = {'Accept': 'application/xml', 'Content-Type': 'application/xml'}

# =============================================================================
# ALMA API HELPERS
# =============================================================================

def get_exact_bib_by_nlm_ui(nlm_ui: str, api_key: str):
    """Look up a bib record in Alma by NLM Unique Identifier.

    Uses the Alma 'other_system_id' search parameter to find candidate
    records, then confirms the match by checking that one of the record's
    035 $9 subfields exactly equals the supplied NLM UI.

    Returns a tuple of (mms_id, record_element, title).
    Returns (None, None, None) if no exact match is found."""
    url = f"{BASE_URL}"
    params = {
        'other_system_id': nlm_ui,      # Search by "other system ID"
        'view': 'full',                  # Include the full MARC record
        'expand': 'None',               # No additional expansions
        'apikey': api_key
    }

    response = requests.get(url, headers=HEADERS, params=params)
    if response.status_code != 200:
        print(f"❌ API error for NLM UI {nlm_ui}: {response.status_code}")
        return None, None, None

    # Parse the response and look for an exact 035 $9 match
    root = ET.fromstring(response.content)
    for bib in root.findall('bib'):
        record = bib.find('record')
        if record is None:
            continue
        for df in record.findall('datafield[@tag="035"]'):
            for sf in df.findall('subfield[@code="9"]'):
                if sf.text == nlm_ui:
                    mms_id = bib.findtext('mms_id')
                    title = bib.findtext('title')
                    return mms_id, record, title

    print(f"⚠️ No exact match for 035 $9 == {nlm_ui}")
    return None, None, None

def put_record_back(mms_id: str, updated_record: ET.Element):
    """Save the updated record back to Alma.

    Before sending the PUT request this function:
      1. Calls remove_updated_from_260() to clean up any '[updated]' text
      2. Wraps the <record> element inside a <bib> envelope with the MMS ID

    The modified MARC XML is sent via PUT, overwriting the existing record."""
    # Clean up 260 $b before saving
    remove_updated_from_260(updated_record)

    # Wrap the record in a <bib> envelope (required by the Alma Bib API)
    bib = ET.Element('bib')
    ET.SubElement(bib, 'mms_id').text = mms_id
    bib.append(updated_record)

    updated_xml = ET.tostring(bib, encoding='utf-8').decode('utf-8')
    url = f"{BASE_URL}/{mms_id}"
    params = {'apikey': API_KEY}

    response = requests.put(url, headers=HEADERS, params=params,
                            data=updated_xml.encode('utf-8'))
    if response.status_code in [200, 204]:
        print(f"✅ Successfully updated MMS ID {mms_id}")
    else:
        print(f"❌ Failed to update: {response.status_code}\n{response.text}")

# =============================================================================
# FORMAT DETECTION
# =============================================================================

def detect_format(record):
    """Determine whether a record represents an electronic resource.

    Checks two places:
      1. 006 (Additional Material Characteristics): if the first character
         is 'm' the record is treated as a computer file → electronic.
      2. 337 $a (Media Type): if the value is 'computer' → electronic.

    Returns True for electronic, False for print."""
    # Check 006 — 'm' at position 0 means computer file
    for df in record.findall('controlfield[@tag="006"]'):
        if df.text and df.text.startswith('m'):
            return True

    # Check 337 $a — "computer" means electronic
    for df in record.findall('datafield[@tag="337"]'):
        sf = df.find('subfield[@code="a"]')
        if sf is not None and sf.text and sf.text.strip().lower() == 'computer':
            return True

    return False

# =============================================================================
# MARC FIELD UPDATE FUNCTIONS
# =============================================================================
# Each function below updates one specific MARC field or group of subfields.
# =============================================================================

def update_022_fields(record, print_issn, electronic_issn, linking_issn):
    """Rebuild the 022 (ISSN) field(s) based on the CSV data.

    The function first determines which format the record represents
    (electronic vs. print) via detect_format(), then decides which ISSN
    is the "primary" one (goes in the first 022 $a) and which is the
    "alternate" (goes in a second 022 $a).

    Logic summary:
      - Electronic record → primary = Electronic ISSN, alternate = Print ISSN
      - Print record      → primary = Print ISSN,      alternate = Electronic ISSN

    Subfields built on the PRIMARY 022:
      $a  The primary ISSN
      $l  Linking ISSN (preserved from the old 022 if it existed, otherwise
          falls back to the primary ISSN)
      $2  Preserved from the old 022 if it existed
      $9  Format code: 'EY' (electronic) or 'PY' (print) — only when an
          alternate ISSN also exists
      $7  Format label: '(Electronic)' or '(Print)' — only when an
          alternate ISSN also exists

    Subfields built on the ALTERNATE 022 (only if different from primary):
      $a  The alternate ISSN
      $9  Format code: 'PN' (print alternate) or 'EN' (electronic alternate)
      $7  Format label: '(Print)' or '(Electronic)'

    Special case: if no 022 existed before and only a Linking ISSN is
    provided, a single 022 with $a and $l set to the linking ISSN is created.
    """
    is_electronic = detect_format(record)

    # Collect existing 022 fields (we'll remove them and rebuild)
    old_022 = record.findall('datafield[@tag="022"]')

    # Values we may want to preserve from the existing first 022
    preserved_l = None      # Existing $l (linking ISSN)
    preserved_2 = None      # Existing $2 (ISSN center code)

    # Decide primary vs. alternate based on format
    primary   = (electronic_issn if is_electronic else print_issn or '').strip()
    alternate = (print_issn if is_electronic else electronic_issn or '').strip()

    # Preserve useful subfields from the old 022 before we delete it
    if old_022:
        a = old_022[0].find('subfield[@code="a"]')
        if a is not None and not primary:
            # If the CSV didn't supply a primary ISSN, keep the existing $a
            primary = a.text.strip() if a.text else ''

        l = old_022[0].find('subfield[@code="l"]')
        if l is not None:
            preserved_l = l.text.strip() if l.text else None

        sub2 = old_022[0].find('subfield[@code="2"]')
        if sub2 is not None:
            preserved_2 = sub2.text.strip() if sub2.text else None

    # Remove all old 022 fields — they will be rebuilt below
    for df in old_022:
        record.remove(df)

    # --- Special case: no previous 022 and only a linking ISSN is available ---
    if not old_022 and linking_issn:
        field = ET.Element('datafield', attrib={'tag': '022', 'ind1': ' ', 'ind2': ' '})
        ET.SubElement(field, 'subfield', attrib={'code': 'a'}).text = linking_issn
        ET.SubElement(field, 'subfield', attrib={'code': 'l'}).text = linking_issn
        record.append(field)
        return

    # --- Build the primary 022 field ---
    if primary:
        field1 = ET.Element('datafield', attrib={'tag': '022', 'ind1': ' ', 'ind2': ' '})

        # $a — Main ISSN
        ET.SubElement(field1, 'subfield', attrib={'code': 'a'}).text = primary

        # $l — Linking ISSN (preserve old value, or fall back to primary)
        ET.SubElement(field1, 'subfield', attrib={'code': 'l'}).text = (
            preserved_l if preserved_l else primary
        )

        # $2 — ISSN center code (preserved from old record if it existed)
        if preserved_2:
            ET.SubElement(field1, 'subfield', attrib={'code': '2'}).text = preserved_2

        # $9 and $7 — Format code and label (only when both formats exist)
        if alternate:
            ET.SubElement(field1, 'subfield', attrib={'code': '9'}).text = (
                'EY' if is_electronic else 'PY'
            )
            ET.SubElement(field1, 'subfield', attrib={'code': '7'}).text = (
                '(Electronic)' if is_electronic else '(Print)'
            )

        record.append(field1)

    # --- Build the alternate 022 field (other format) ---
    if alternate and alternate != primary:
        field2 = ET.Element('datafield', attrib={'tag': '022', 'ind1': ' ', 'ind2': ' '})

        # $a — Alternate-format ISSN
        ET.SubElement(field2, 'subfield', attrib={'code': 'a'}).text = alternate

        # $9 — Format code for the alternate
        ET.SubElement(field2, 'subfield', attrib={'code': '9'}).text = (
            'PN' if is_electronic else 'EN'
        )

        # $7 — Format label for the alternate
        ET.SubElement(field2, 'subfield', attrib={'code': '7'}).text = (
            '(Print)' if is_electronic else '(Electronic)'
        )

        record.append(field2)

def update_995_field(record):
    """Stamp the 995 local field with today's date as a review date.

    The 995 is a local field used to track when a record was last reviewed.
      - $a holds the review source (e.g., 'AUTH' for authority review)
      - $c holds the action code (e.g., 'REV' for reviewed)
      - $d holds the review date (YYYYMMDD format)

    Three cases:
      1. A 995 with $d already exists → update $d to today's date.
      2. A 995 exists but $d is missing → add $c ('REV') and $d (today).
      3. No 995 exists at all → create a new 995 with $a, $c, and $d.

    NOTE: The 995 is a local field specific to this institution. Other
    libraries may not use it or may use it differently."""
    today = datetime.today().strftime('%Y%m%d')
    updated = False

    for df in record.findall('datafield[@tag="995"]'):
        sf_d = df.find('subfield[@code="d"]')
        if sf_d is not None:
            # Case 1: $d exists — update it to today's date
            sf_d.text = today
            updated = True
        else:
            # Case 2: 995 exists but $d is missing — add $c and $d
            ET.SubElement(df, 'subfield', code='c').text = 'REV'
            ET.SubElement(df, 'subfield', code='d').text = today
            updated = True

    if not updated:
        # Case 3: No 995 at all — create one from scratch
        df = ET.Element('datafield', attrib={'tag': '995', 'ind1': ' ', 'ind2': ' '})
        ET.SubElement(df, 'subfield', attrib={'code': 'a'}).text = 'AUTH'
        ET.SubElement(df, 'subfield', attrib={'code': 'c'}).text = 'REV'
        ET.SubElement(df, 'subfield', attrib={'code': 'd'}).text = today
        record.append(df)

def remove_updated_from_260(record):
    """Strip '[updated]' from every 260 $b (publisher name) subfield.

    Some records may have had '[updated]' appended to the publisher name
    during a previous cataloging workflow. This function removes that text
    so the record is clean before it's saved back to Alma.

    Before: 260 $b Elsevier [updated]
    After:  260 $b Elsevier"""
    for df in record.findall('datafield[@tag="260"]'):
        for sf in df.findall('subfield[@code="b"]'):
            if sf.text and '[updated]' in sf.text:
                sf.text = sf.text.replace('[updated]', '').strip()

# =============================================================================
# MAIN WORKFLOW
# =============================================================================
# This function ties everything together: it reads the CSV, looks up each
# record by NLM UI, updates the 022/995 fields, and saves the changes back.
# =============================================================================

def main():
    """Process ISSN.csv and update ISSN fields in Alma records.

    Expected CSV columns:
      - 'NLM UI'          : The NLM Unique Identifier (stored in 035 $9)
      - 'Title'           : Title for display/logging purposes
      - 'Print ISSN'      : The print-format ISSN (optional)
      - 'Electronic ISSN' : The electronic-format ISSN (optional)
      - 'Linking ISSN'    : The linking ISSN (optional, used as fallback)
    """
    with open(CSV_FILE, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            # Read values from the CSV row
            nlm_ui     = str(row.get('NLM UI')).strip()
            title      = row.get('Title', '').strip()
            print_issn = row.get('Print ISSN', '').strip()
            e_issn     = row.get('Electronic ISSN', '').strip()
            linking    = row.get('Linking ISSN', '').strip()

            print(f"\n===== Processing {nlm_ui} - {title} =====")

            # Step 1: Look up the record by NLM UI
            mms_id, record, fetched_title = get_exact_bib_by_nlm_ui(nlm_ui, API_KEY)
            if record is None or mms_id is None:
                continue

            # Step 2: Rebuild the 022 ISSN fields
            update_022_fields(record, print_issn, e_issn, linking)

            # Step 3: Stamp the 995 review date
            update_995_field(record)

            # Step 4: Save the updated record back to Alma
            put_record_back(mms_id, record)

# =============================================================================
# RUN THE SCRIPT
# =============================================================================
if __name__ == "__main__":
    main()
