# =============================================================================
# Title Change Updater for Alma  (362 + 76X-78X consolidated)
# =============================================================================
# This script automates the process of updating catalog records in Alma when a
# serial title undergoes a title change. It reads a CSV file containing a pair
# of MMS IDs (the previous title and the new title) along with the ceased date
# and an optional "Archive begins" value, then updates the relevant MARC fields.
#
# On the PREVIOUS title's record:
#   - 008 (fixed-length data): sets the publication status to 'd' (dead/ceased)
#     and fills in the end date
#   - 260/264 $3 (materials specified): closes the open-ended date range
#   - 362 (dates of publication): adds a "Ceased with..." note
#   - 785 (succeeding entry): adds a link to the new title's record, pulling
#     the title (245 $a), ISSN (022 $a), LCCN (010 $a), OCLC number (035 $a),
#     and NLM UI (035 $9) from the new title
#   - 988 (local field): records the NLM UI of the new title and today's date
#   - 995 (local processing field): stamps today's date as a review date
#
# On the NEW title's record:
#   - 780 (preceding entry): adds a link back to the previous title's record,
#     pulling the title (245 $a), ISSN (022 $a), LCCN (010 $a), OCLC number
#     (035 $a/$w), and NLM UI (035 $9) from the previous title
#   - 76X-78X (linking fields): any linking field on the previous title that
#     references the new title's 245 $a is copied/merged into the new record,
#     with optional "Archive begins" coverage adjustments
#
# A DRY_RUN flag (below) lets you preview what would be changed without
# actually writing anything back to Alma.
# =============================================================================

# --- Python libraries used by this script ---
import csv                              # Reads the input CSV file
import requests                         # Makes HTTP calls to the Alma API
from xml.etree import ElementTree as ET # Parses and edits the MARC XML records
import re                               # Pattern matching for dates in MARC fields
from datetime import datetime           # Gets today's date for the 988/995 fields

# =============================================================================
# API KEY SETUP
# =============================================================================
# Your API key is read from a separate text file so it is never exposed in the
# script itself. This is especially important for a public GitHub repository.
# See the README for instructions on creating your key file.
alma_api_key = None
# Replace "your_file_path_here.txt" with the full path to your API key file.
# Example: r"C:\Users\YourName\Documents\alma_api_keys.txt"
with open(r"your_file_path_here.txt") as f:
    for line in f:
        # The file should contain a line like:  alma_sandbox_key = "your_key_here"
        if line.strip().startswith("alma_sandbox_key"):
            alma_api_key = line.split("=", 1)[1].strip().strip('"')
            break

# Stop immediately if no key was found — the script can't run without it
if not alma_api_key:
    raise ValueError("Alma sandbox API key not found in alma_api_keys.txt")

# Alma API base URL — change "api-na" to "api-eu" or "api-ap" if your
# Alma instance is hosted in Europe or Asia Pacific.
ALMA_API_BASE_URL = "https://api-na.hosted.exlibrisgroup.com/almaws/v1/bibs/"

# =============================================================================
# CONFIGURATION
# =============================================================================

# Set to True to preview changes without writing to Alma.
# Set to False when you are ready to apply updates for real.
DRY_RUN = True

# Subfield codes in 76X-78X linking fields that hold coverage / "archive
# begins" information. The script checks these codes (in order) when merging
# linking fields from the previous record into the new record.
COVERAGE_SUBFIELDS = ["g", "z"]

# =============================================================================
# ALMA API HELPERS
# =============================================================================

def get_record(mms_id):
    """Retrieve a single bibliographic record from Alma by its MMS ID.
    Returns the full MARC XML so we can read and edit it."""
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

def put_record(mms_id, marcxml):
    """Save the updated record back to Alma.

    This sends the modified MARC XML back to Alma using a PUT request,
    which overwrites the existing record with our changes."""
    url = f"{ALMA_API_BASE_URL}{mms_id}"
    headers = {
        "Content-Type": "application/xml",
        "Authorization": f"apikey {alma_api_key}"
    }
    response = requests.put(url, headers=headers, data=marcxml)
    if response.status_code in [200, 204]:
        print(f"Successfully updated record for MMS ID {mms_id}")
    else:
        print(f"Failed to update record for MMS ID {mms_id}: "
              f"{response.status_code} - {response.content}")

# =============================================================================
# MARC FIELD UPDATE FUNCTIONS — CEASED-TITLE FIELDS (Previous Title)
# =============================================================================
# These functions update the previous title's record to reflect that the
# title has ceased publication and changed to a new title.
# =============================================================================

def extract_year(ceased_date):
    """Pull a 4-digit year from a ceased date string.

    The ceased date in the CSV might look like 'v.50 no.4 (2024)' or just
    '2024'. This function finds the first 4-digit year in the string."""
    match = re.search(r"\b(\d{4})\b", ceased_date)
    return match.group(1) if match else None

def update_008_field(record, ceased_date):
    """Update the 008 fixed-length field to mark the title as ceased.

    The 008 is a 40-character fixed field. This function changes:
      - Position 06 (Type of date): set to 'd' (meaning the item has ceased)
      - Positions 11-14 (Date 2 / ending date): filled with the ceased year
    The start date (positions 07-10) is left as-is.

    Before: 008  ......c20109999...
    After:  008  ......d20102024..."""
    ceased_year = extract_year(ceased_date)
    if ceased_year is None:
        print(f"Ceased date does not contain a valid year: {ceased_date}")
        return

    for controlfield in record.findall("controlfield[@tag='008']"):
        if controlfield is not None:
            if len(controlfield.text) >= 40:
                controlfield.text = (
                    controlfield.text[:6]       # Positions 00-05: keep as-is
                    + 'd'                       # Position 06:    'd' = ceased
                    + controlfield.text[7:11]   # Positions 07-10: keep start date
                    + ceased_year               # Positions 11-14: insert end year
                    + controlfield.text[15:]    # Positions 15-39: keep as-is
                )
            break

def update_260_264_field(record, ceased_date):
    """Close the open date range in the 260/264 $3 (materials specified).

    For an ongoing serial the 260/264 $3 typically has an open-ended date
    that we need to close with the ceased year.

    Examples:
      Before: $3 v.1 (2015)- :     After: $3 v.1 (2015)-2024 :
      Before: $3 v.1 (2015)        After: $3 v.1 (2015)-2024 :

    If $3 already contains a hyphen and ends with a colon, the ceased year
    is inserted before the colon. Otherwise a hyphen, the year, and a colon
    are appended."""
    ceased_year = extract_year(ceased_date)
    if ceased_year is None:
        print(f"Ceased date does not contain a valid year: {ceased_date}")
        return

    # Check both 260 and 264 fields (different cataloging conventions)
    for datafield in (
        record.findall("datafield[@tag='260']")
        + record.findall("datafield[@tag='264']")
    ):
        subfield_3 = datafield.find("subfield[@code='3']")

        if subfield_3 is not None and subfield_3.text:
            current_value = subfield_3.text.strip()

            if '-' in current_value:
                # Already contains a hyphen (open-ended range)
                if current_value.endswith(':'):
                    # Strip the colon, add the year, put the colon back
                    new_value = current_value.rstrip(':').strip() + ceased_year
                else:
                    new_value = current_value.strip() + '-' + ceased_year
                new_value += " :"
                subfield_3.text = new_value
            else:
                # No hyphen yet — append a range
                new_value = current_value.strip() + '-' + ceased_year + " :"
                subfield_3.text = new_value
        else:
            print(f"No $3 found in tag {datafield.attrib['tag']}.")

def update_362_field(record, ceased_date):
    """Add or update the 362 field (dates of publication note).

    The 362 with first indicator '1' is an unformatted note about when the
    serial started and/or stopped. This function handles three cases:

    1. A 362 exists with $a already populated → append the ceased info:
       Before: 362 1_ $a Began with v.1 (2010).
       After:  362 1_ $a Began with v.1 (2010); ceased with v.50 no.4 (2024)

    2. A 362 exists but $a is missing → create $a with the ceased note.

    3. No 362 field exists at all → create the entire field and subfield."""
    print(f"Starting to update 362 field with ceased date: {ceased_date}")

    # Look for existing 362 fields with indicator 1 (unformatted note)
    existing_362_fields = record.findall("datafield[@tag='362'][@ind1='1']")

    if existing_362_fields:
        for datafield in existing_362_fields:
            subfield_a = datafield.find("subfield[@code='a']")
            if subfield_a is None:
                # Case 2: 362 exists but has no $a — add one
                subfield_a = ET.SubElement(datafield, 'subfield', attrib={'code': 'a'})
                subfield_a.text = f"Ceased with {ceased_date}"
            else:
                # Case 1: 362 $a exists — append ceased info after existing text
                updated_text = subfield_a.text.rstrip('.')
                subfield_a.text = f"{updated_text}; ceased with {ceased_date}"
    else:
        # Case 3: No 362 at all — create a new one from scratch
        new_362 = ET.Element('datafield', attrib={'tag': '362', 'ind1': '1', 'ind2': ' '})
        subfield_a = ET.SubElement(new_362, 'subfield', attrib={'code': 'a'})
        subfield_a.text = f"Ceased with {ceased_date}"
        record.append(new_362)

# =============================================================================
# MARC FIELD UPDATE FUNCTIONS — LINKING ENTRY FIELDS (780 / 785)
# =============================================================================
# These functions create the linking entries between the old and new titles.
#   - 780 (Preceding Entry) goes on the NEW title, pointing back to the old one
#   - 785 (Succeeding Entry) goes on the OLD title, pointing to the new one
#
# Each linking field pulls identifiers from the linked record:
#   $t  Title (from 245 $a)
#   $x  ISSN (from 022 $a)
#   $w  Control numbers: LCCN (010 $a), OCLC (035 $a/$w), NLM UI (035 $9)
# =============================================================================

def update_780_field(new_record, previous_id):
    """Add a 780 (preceding entry) field to the new title's record.

    The 780 links the new title back to the previous (old) title. It fetches
    the previous title's record from Alma and pulls:
      $t  Previous title (245 $a, trailing period stripped)
      $x  Previous ISSN (022 $a)
      $w  LCCN prefixed with (DLC)   — from 010 $a
      $w  OCLC number                — from 035 $a containing (OCoLC)
      $w  Any existing 035 $w values — carried over as-is
      $w  NLM UI prefixed with (DNLM) — from 035 $9

    Indicators are set to '0' '0' (Continues / Main series).
    If a 780 already exists on the new record, the function returns without
    making changes to avoid creating duplicate links."""
    # Skip if a 780 already exists on this record
    existing_780 = new_record.findall(".//datafield[@tag='780']")
    if existing_780:
        return

    # Fetch the previous title's record to extract its identifiers
    previous_record_xml = get_record(previous_id)
    if previous_record_xml is None:
        return

    previous_tree = ET.fromstring(previous_record_xml)
    previous_record = previous_tree.find('record')
    if previous_record is None:
        return

    # Gather identifiers from the previous title's record
    previous_title_245_a = previous_record.find(".//datafield[@tag='245']/subfield[@code='a']")
    previous_title_022_a = previous_record.find(".//datafield[@tag='022']/subfield[@code='a']")
    previous_title_010_a = previous_record.find(".//datafield[@tag='010']/subfield[@code='a']")
    previous_title_035_a = previous_record.find(".//datafield[@tag='035']/subfield[@code='a']")
    previous_title_035_w = previous_record.findall(".//datafield[@tag='035']/subfield[@code='w']")
    previous_title_035_9 = previous_record.find(".//datafield[@tag='035']/subfield[@code='9']")

    # Build the new 780 field
    new_780 = ET.Element('datafield', attrib={'tag': '780', 'ind1': '0', 'ind2': '0'})

    # $t — Title of the previous serial (strip trailing period)
    subfield_t = ET.SubElement(new_780, 'subfield', attrib={'code': 't'})
    if previous_title_245_a is not None and previous_title_245_a.text:
        subfield_t.text = previous_title_245_a.text.rstrip('.')

    # $x — ISSN of the previous serial
    if previous_title_022_a is not None:
        subfield_x = ET.SubElement(new_780, 'subfield', attrib={'code': 'x'})
        subfield_x.text = previous_title_022_a.text

    # $w — LCCN (Library of Congress Control Number), prefixed with (DLC)
    if previous_title_010_a is not None and previous_title_010_a.text:
        subfield_w = ET.SubElement(new_780, 'subfield', attrib={'code': 'w'})
        subfield_w.text = "(DLC)" + previous_title_010_a.text

    # $w — OCLC number from 035 $a (only if it contains the (OCoLC) prefix)
    if previous_title_035_a is not None and previous_title_035_a.text and "(OCoLC)" in previous_title_035_a.text:
        subfield_w = ET.SubElement(new_780, 'subfield', attrib={'code': 'w'})
        subfield_w.text = previous_title_035_a.text

    # $w — Any existing 035 $w values (carried over directly)
    for w_value in previous_title_035_w:
        subfield_w = ET.SubElement(new_780, 'subfield', attrib={'code': 'w'})
        subfield_w.text = w_value.text

    # $w — NLM Unique Identifier from 035 $9, prefixed with (DNLM)
    if previous_title_035_9 is not None and previous_title_035_9.text:
        subfield_w = ET.SubElement(new_780, 'subfield', attrib={'code': 'w'})
        subfield_w.text = "(DNLM)" + previous_title_035_9.text

    new_record.append(new_780)

def update_785_field(record, new_id):
    """Add a 785 (succeeding entry) field to the previous title's record.

    The 785 links the old title forward to the new (succeeding) title. It
    fetches the new title's record from Alma and pulls:
      $t  New title (245 $a, trailing period stripped)
      $x  New ISSN (022 $a)
      $w  LCCN prefixed with (DLC)    — from 010 $a
      $w  OCLC number                 — from 035 $a containing (OCoLC)
      $w  NLM UI prefixed with (DNLM) — from 035 $9

    Indicators are set to '0' '0' (Continued by / Main series)."""
    # Fetch the new title's record to extract its identifiers
    new_record_xml = get_record(new_id)
    if new_record_xml is None:
        return

    new_tree = ET.fromstring(new_record_xml)
    new_record = new_tree.find('record')
    if new_record is None:
        return

    # Gather identifiers from the new title's record
    new_title_245_a = new_record.find(".//datafield[@tag='245']/subfield[@code='a']")
    new_title_022_a = new_record.find(".//datafield[@tag='022']/subfield[@code='a']")
    new_title_010_a = new_record.find(".//datafield[@tag='010']/subfield[@code='a']")
    new_title_035_a = new_record.find(".//datafield[@tag='035']/subfield[@code='a']")
    new_title_035_9 = new_record.find(".//datafield[@tag='035']/subfield[@code='9']")

    # Build the new 785 field
    new_785 = ET.Element('datafield', attrib={'tag': '785', 'ind1': '0', 'ind2': '0'})

    # $t — Title of the new serial (strip trailing period)
    subfield_t = ET.SubElement(new_785, 'subfield', attrib={'code': 't'})
    if new_title_245_a is not None and new_title_245_a.text:
        subfield_t.text = new_title_245_a.text.rstrip('.')

    # $x — ISSN of the new serial
    if new_title_022_a is not None:
        subfield_x = ET.SubElement(new_785, 'subfield', attrib={'code': 'x'})
        subfield_x.text = new_title_022_a.text

    # $w — LCCN prefixed with (DLC)
    if new_title_010_a is not None and new_title_010_a.text:
        subfield_w = ET.SubElement(new_785, 'subfield', attrib={'code': 'w'})
        subfield_w.text = "(DLC)" + new_title_010_a.text

    # $w — OCLC number from 035 $a (only if it contains (OCoLC))
    if new_title_035_a is not None and new_title_035_a.text and "(OCoLC)" in new_title_035_a.text:
        subfield_w = ET.SubElement(new_785, 'subfield', attrib={'code': 'w'})
        subfield_w.text = new_title_035_a.text

    # $w — NLM Unique Identifier from 035 $9, prefixed with (DNLM)
    if new_title_035_9 is not None and new_title_035_9.text:
        subfield_w = ET.SubElement(new_785, 'subfield', attrib={'code': 'w'})
        subfield_w.text = "(DNLM)" + new_title_035_9.text

    record.append(new_785)

# =============================================================================
# MARC FIELD UPDATE FUNCTIONS — LOCAL FIELDS (988 / 995)
# =============================================================================
# These local fields are specific to this institution. Other libraries may not
# use them or may use them differently. Modify or remove as needed.
# =============================================================================

def update_988_field(record, new_id):
    """Add a 988 local field to the previous title's record.

    The 988 records the NLM Unique Identifier of the succeeding (new) title
    and the date the change was processed. It fetches the new title's 035 $9
    (which holds the NLM UI) and creates:
      $a  NLM UI of the new title (with any '(DNLM)' prefix stripped)
      $b  Today's date in YYYYMMDD format

    If the new title's record has no 035 $9, no 988 is added."""
    # Fetch the new title's record to extract its NLM UI
    new_record_xml = get_record(new_id)
    if new_record_xml is None:
        return

    new_tree = ET.fromstring(new_record_xml)
    new_record = new_tree.find('record')
    if new_record is None:
        return

    new_title_035_9 = new_record.find(".//datafield[@tag='035']/subfield[@code='9']")

    if new_title_035_9 is not None and new_title_035_9.text:
        new_988 = ET.Element('datafield', attrib={'tag': '988', 'ind1': ' ', 'ind2': ' '})

        # $a — NLM UI of the new title (strip the (DNLM) prefix if present)
        subfield_a = ET.SubElement(new_988, 'subfield', attrib={'code': 'a'})
        subfield_a.text = new_title_035_9.text.replace("(DNLM)", "").strip()

        # $b — Date the title change was processed
        subfield_b = ET.SubElement(new_988, 'subfield', attrib={'code': 'b'})
        subfield_b.text = datetime.now().strftime("%Y%m%d")

        record.append(new_988)

def update_995_field(record):
    """Stamp the 995 local field with today's date as a review date.

    The 995 is a local field used to track when a record was last reviewed.
      - $d holds the review date (YYYYMMDD format)
      - $c holds the action code (e.g., 'REV' for reviewed)

    If $d already exists, it's updated to today. If it doesn't exist,
    both $c (set to 'REV') and $d (set to today) are added.

    NOTE: The 995 is a local field specific to this institution. Other
    libraries may not use it or may use it differently. You can remove or
    modify this function to match your local practices."""
    today_date = datetime.now().strftime("%Y%m%d")

    for datafield in record.findall('.//datafield[@tag="995"]'):
        subfield_d = datafield.find('subfield[@code="d"]')

        if subfield_d is not None:
            # $d exists — just update it to today's date
            subfield_d.text = today_date
        else:
            # $d doesn't exist — add both the action code and date
            subfield_c = ET.SubElement(datafield, 'subfield', attrib={'code': 'c'})
            subfield_c.text = "REV"

            subfield_d = ET.SubElement(datafield, 'subfield', attrib={'code': 'd'})
            subfield_d.text = today_date

# =============================================================================
# 76X-78X LINKING-FIELD COPIER  (New Title)
# =============================================================================
# When a title changes, the previous record may carry 76X-78X linking fields
# (e.g., 773 Host Item, 776 Additional Physical Form, etc.) that reference
# the new title. This section copies or merges those fields into the new
# record so the links are preserved.
#
# An optional "Archive begins" value from the CSV can override the coverage
# date stored in the linking field's $g or $z subfield.
# =============================================================================

def _parse_first_year(text):
    """Return the first 4-digit year found in *text* (as an int), or None."""
    if not text:
        return None
    m = re.search(r"(\d{4})", text)
    return int(m.group(1)) if m else None

def _parse_last_year(text):
    """Return the last 4-digit year found in *text* (as an int), or None."""
    if not text:
        return None
    m = re.findall(r"(\d{4})", text)
    return int(m[-1]) if m else None

def _ends_with_open_range(text):
    """True if *text* ends with an open-ended date range like '2015-'."""
    if not text:
        return False
    return bool(re.search(r"\d{4}-\s*$", text))

def update_linking_fields_from(target_record, source_id, archive_begins=None):
    """Copy 76X-78X linking fields from a source record into the target.

    This function fetches the record identified by *source_id* and iterates
    through every MARC datafield in the 760-789 range. For each field whose
    title subfield ($t or $a) matches the target record's 245 $a (case-
    insensitive, trailing punctuation stripped), it either:

      A) Copies the field into the target (if no field with that tag exists)
      B) Merges missing subfields into the target's existing field

    Coverage / "Archive begins" handling
    -------------------------------------
    If *archive_begins* is provided (from the CSV), the coverage subfield
    ($g or $z — see COVERAGE_SUBFIELDS) is adjusted on the target:

      1. If the target already has coverage that ends with an open range
         (e.g. "2015-"), the trailing open-ended portion is removed.
      2. If the target has a definite end year and *archive_begins* starts
         after it, the new coverage is appended with a semicolon:
           Before: $g v.1-v.10 (2015-2020)
           After:  $g v.1-v.10 (2015-2020); v.11 (2021)
      3. If neither condition applies, no coverage change is made.
      4. If the target field has no coverage subfield at all, one is created
         with the *archive_begins* value.

    When *archive_begins* is not provided the source field is copied or
    merged verbatim."""
    # Fetch the source (previous title) record
    source_xml = get_record(source_id)
    if source_xml is None:
        return

    try:
        source_tree = ET.fromstring(source_xml)
    except Exception as e:
        print(f"Failed parsing source record {source_id}: {e}")
        return

    source_record = source_tree.find('record')
    if source_record is None:
        return

    # --- Helper: get a cleaned 245 $a from a record --------------------------
    def get_245_a(rec):
        sf = rec.find(".//datafield[@tag='245']/subfield[@code='a']")
        if sf is None or sf.text is None:
            return None
        return re.sub(r"[\s\.:;,/]+$", "", sf.text.strip())

    target_245 = get_245_a(target_record)
    if not target_245:
        return

    # --- Helper: build a signature string for duplicate detection -------------
    def df_signature(df):
        """Create a comparable fingerprint for a datafield + all subfields."""
        parts = [df.attrib.get('tag', '')]
        for sf in df.findall('subfield'):
            parts.append(f"{sf.attrib.get('code', '')}:${sf.text}")
        return '|'.join(parts)

    # --- Iterate through every tag in the 760-789 range ----------------------
    for tag_num in range(760, 790):
        tag = str(tag_num)
        for src_df in source_record.findall(f".//datafield[@tag='{tag}']"):

            # Find a title-like subfield on the source linking field
            src_title_sf = (
                src_df.find("subfield[@code='t']")
                or src_df.find("subfield[@code='a']")
            )
            if src_title_sf is None or src_title_sf.text is None:
                continue

            src_title = re.sub(r"[\s\.:;,/]+$", "", src_title_sf.text.strip())

            # Only process if the source linking field points to this target's title
            if src_title.lower() != target_245.lower():
                continue

            # Skip exact duplicates already present on the target record
            src_sig = df_signature(src_df)
            already_exists = any(
                df_signature(tgt_df) == src_sig
                for tgt_df in target_record.findall(f".//datafield[@tag='{tag}']")
            )
            if already_exists:
                continue

            # ---- Locate coverage subfield on the source (if any) ----
            src_cov_sf = None
            for code in COVERAGE_SUBFIELDS:
                src_cov_sf = src_df.find(f"subfield[@code='{code}']")
                if src_cov_sf is not None and src_cov_sf.text:
                    break

            # =============================================================
            # PATH A: "Archive begins" was supplied in the CSV
            # =============================================================
            if archive_begins:
                new_start_year = _parse_first_year(archive_begins)

                tgt_same_tag = target_record.find(f".//datafield[@tag='{tag}']")

                if tgt_same_tag is not None:
                    # Find the coverage subfield already on the target
                    tgt_cov_sf = None
                    for code in COVERAGE_SUBFIELDS:
                        tgt_cov_sf = tgt_same_tag.find(f"subfield[@code='{code}']")
                        if tgt_cov_sf is not None:
                            break

                    if tgt_cov_sf is not None and tgt_cov_sf.text:
                        tgt_text = tgt_cov_sf.text.strip()

                        if _ends_with_open_range(tgt_text):
                            # Open-ended "YYYY-" → remove the trailing open range
                            print(f"Removing open-ended suffix from target {tag} "
                                  f"subfield before adding new coverage: '{tgt_text}'")
                            new_tgt_text = re.sub(
                                r"\d{4}-\s*$", "", tgt_text
                            ).rstrip(' ,;:')
                            tgt_cov_sf.text = new_tgt_text
                            print(f"Updated target coverage to: '{tgt_cov_sf.text}'")

                        else:
                            # Existing end year — check for a gap
                            existing_end = _parse_last_year(tgt_text)
                            if (existing_end is not None
                                    and new_start_year is not None
                                    and new_start_year > existing_end):
                                # Gap exists → append with semicolon
                                print(f"Gap detected (existing end {existing_end} < "
                                      f"new start {new_start_year}). Appending "
                                      f"archive_begins '{archive_begins}' to target {tag}.")
                                tgt_cov_sf.text = tgt_text + "; " + archive_begins
                                print(f"Updated target coverage to: '{tgt_cov_sf.text}'")
                            else:
                                print(f"No coverage change needed for target {tag}; "
                                      f"existing='{tgt_text}', "
                                      f"archive_begins='{archive_begins}'")
                    else:
                        # No coverage subfield on target — add one
                        add_code = COVERAGE_SUBFIELDS[0]
                        new_sf = ET.SubElement(
                            tgt_same_tag, 'subfield', attrib={'code': add_code}
                        )
                        new_sf.text = archive_begins
                        print(f"Added coverage subfield ${add_code}='{archive_begins}' "
                              f"to existing target {tag} field")
                else:
                    # No existing target field with this tag — create a copy
                    # of the source but use archive_begins for coverage
                    new_df = ET.Element('datafield', attrib={
                        'tag':  src_df.attrib.get('tag', ''),
                        'ind1': src_df.attrib.get('ind1', ' '),
                        'ind2': src_df.attrib.get('ind2', ' '),
                    })
                    for src_sf in src_df.findall('subfield'):
                        code = src_sf.attrib.get('code', '')
                        new_sf = ET.SubElement(new_df, 'subfield', attrib={'code': code})
                        # Override coverage subfields with archive_begins
                        if code in COVERAGE_SUBFIELDS:
                            new_sf.text = archive_begins
                        else:
                            new_sf.text = src_sf.text
                    target_record.append(new_df)
                    print(f"Appended new {tag} field with coverage "
                          f"'{archive_begins}' to target record")

            # =============================================================
            # PATH B: No "Archive begins" — copy / merge verbatim
            # =============================================================
            else:
                tgt_same_tag = target_record.find(f".//datafield[@tag='{tag}']")

                if tgt_same_tag is not None:
                    # Field already exists — add any missing subfields
                    for src_sf in src_df.findall('subfield'):
                        code = src_sf.attrib.get('code', '')
                        if tgt_same_tag.find(f"subfield[@code='{code}']") is None:
                            new_sf = ET.SubElement(
                                tgt_same_tag, 'subfield', attrib={'code': code}
                            )
                            new_sf.text = src_sf.text
                            print(f"Added missing subfield ${code} to existing "
                                  f"target {tag}")
                else:
                    # Field doesn't exist on target — copy the whole thing
                    new_df = ET.Element('datafield', attrib={
                        'tag':  src_df.attrib.get('tag', ''),
                        'ind1': src_df.attrib.get('ind1', ' '),
                        'ind2': src_df.attrib.get('ind2', ' '),
                    })
                    for src_sf in src_df.findall('subfield'):
                        new_sf = ET.SubElement(
                            new_df, 'subfield',
                            attrib={'code': src_sf.attrib.get('code', '')}
                        )
                        new_sf.text = src_sf.text
                    target_record.append(new_df)
                    print(f"Appended new {tag} field to target record")

# =============================================================================
# MAIN WORKFLOW
# =============================================================================
# This function ties everything together: it reads your CSV, fetches each
# pair of records from Alma, updates the MARC fields, and saves the changes
# back. For each row in the CSV it processes TWO records:
#   1. The previous (old) title — ceased fields + 785 link + 988 + 995
#   2. The new (succeeding) title — 780 link + 76X-78X linking field merge
#
# When DRY_RUN is True the script shows what it *would* do but does not
# write anything to Alma. Set DRY_RUN = False (near the top of this file)
# when you are ready to apply changes for real.
# =============================================================================

def process_csv(csv_filename):
    """Process a CSV of title changes and update their records in Alma.

    Expected CSV columns:
      - 'Previous title MMS ID' : The Alma MMS ID for the old title  (required)
      - 'New title MMS ID'      : The Alma MMS ID for the new title  (required)
      - 'Ceased date'           : When the old title ceased, e.g. 'v.50 no.4 (2024)'
      - 'Archive begins'        : Optional start-of-coverage for the new title
                                   (used when merging 76X-78X linking fields)
    """
    with open(csv_filename, newline='', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        print("CSV headers:", reader.fieldnames)
        for row in reader:
            print(row)

            # Read the MMS IDs and dates from the CSV row
            previous_mms_id = row.get('Previous title MMS ID')
            new_mms_id      = row.get('New title MMS ID')
            ceased_date      = row.get('Ceased date')
            archive_begins   = row.get('Archive begins') or row.get('Archive Begins')

            # Skip rows that are missing either MMS ID
            if previous_mms_id is None or new_mms_id is None:
                print("Skipping row due to missing MMS ID:", row)
                continue

            # =================================================================
            # PART 1: Update the PREVIOUS title's record
            # =================================================================

            # Step 1: Fetch the previous title's record from Alma
            previous_record_xml = get_record(previous_mms_id)
            if previous_record_xml is None:
                continue
            previous_tree   = ET.fromstring(previous_record_xml)
            previous_record = previous_tree.find('record')

            # Step 2: Update ceased-title MARC fields (only if we have a date)
            if ceased_date:
                update_008_field(previous_record, ceased_date)       # Fixed field: publication status
                update_260_264_field(previous_record, ceased_date)   # Publication statement $3 dates
                update_362_field(previous_record, ceased_date)       # Dates of publication note

            # Step 3: Add linking / local fields
            update_785_field(previous_record, new_mms_id)   # 785: link to the new (succeeding) title
            update_988_field(previous_record, new_mms_id)   # 988: NLM UI of the new title + date
            update_995_field(previous_record)                # 995: stamp today's review date

            # Step 4: Save the updated previous title record back to Alma
            if DRY_RUN:
                print(f"DRY RUN: Would update previous record {previous_mms_id}")
            else:
                put_record(previous_mms_id,
                           ET.tostring(previous_tree, encoding='utf-8').decode('utf-8'))

            # =================================================================
            # PART 2: Update the NEW title's record
            # =================================================================

            # Step 5: Fetch the new title's record from Alma
            new_record_xml = get_record(new_mms_id)
            if new_record_xml is None:
                continue
            new_tree   = ET.fromstring(new_record_xml)
            new_record = new_tree.find('record')

            # Step 6: Copy / merge any relevant 76X-78X linking fields from the
            #         previous record, applying "Archive begins" if provided
            update_linking_fields_from(new_record, previous_mms_id,
                                       archive_begins=archive_begins)

            # Step 7: Add a 780 linking back to the previous (old) title
            update_780_field(new_record, previous_mms_id)

            # Step 8: Save the updated new title record back to Alma
            if DRY_RUN:
                print(f"DRY RUN: Would update new record {new_mms_id}")
            else:
                put_record(new_mms_id,
                           ET.tostring(new_tree, encoding='utf-8').decode('utf-8'))

# =============================================================================
# RUN THE SCRIPT
# =============================================================================
# Replace the path below with the path to your CSV file.
# The CSV should have columns: 'Previous title MMS ID', 'New title MMS ID',
# 'Ceased date', and optionally 'Archive begins'
process_csv('your_file_path/TitleChange.csv')
