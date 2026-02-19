# =============================================================================
# Ceased Title Updater for Alma
# =============================================================================
# This script automates the process of updating catalog records in Alma when a
# serial title has ceased publication. It reads a CSV file containing MMS IDs
# and ceased dates, then updates the relevant MARC fields in each record:
#
#   - 008 (fixed-length data): sets the publication status to 'd' (dead/ceased)
#     and fills in the end date
#   - 260/264 $c (publication date): closes the open-ended date range
#   - 260/264 $3 (materials specified): closes the open-ended date range
#   - 362 (dates of publication): adds a "Ceased with..." note
#   - 995 (local processing field): stamps today's date as a review date
#
# Records that are indexed in MEDLINE or PubMed (identified by a 510 field)
# are skipped because those titles require a different workflow.
# =============================================================================

# --- Python libraries used by this script ---
import csv                              # Reads the input CSV file
import requests                         # Makes HTTP calls to the Alma API
from xml.etree import ElementTree as ET # Parses and edits the MARC XML records
import re                               # Pattern matching for dates in MARC fields
from datetime import datetime           # Gets today's date for the 995 field

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
    
def should_skip_record(record):
    """Check if a record should be skipped.
    
    Titles indexed in MEDLINE or PubMed (indicated by a 510 field with
    $a = 'MEDLINE' or 'PubMed' and $9 = '1' meaning currently indexed)
    need to go through a separate ceased-title workflow, so this script
    leaves them alone."""
    for datafield in record.findall("datafield[@tag='510']"):
        subfield_9 = datafield.find("subfield[@code='9']")
        subfield_a = datafield.find("subfield[@code='a']")
        
        # $9 = "1" means the title is currently indexed in the source named in $a
        if subfield_9 is not None and subfield_9.text == "1" and subfield_a is not None:
            if subfield_a.text in ["MEDLINE", "PubMed"]:
                return True
    return False

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
        print(f"Failed to update record for MMS ID {mms_id}: {response.status_code} - {response.content}")

# =============================================================================
# MARC FIELD UPDATE FUNCTIONS
# =============================================================================
# Each function below updates one specific MARC field to reflect that the
# title has ceased publication.
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
    """Close the open date range in the 260/264 publication statement.
    
    For an ongoing serial, the 260/264 $c typically has an open-ended date:
      $c 2015-         (not in brackets)
      $c [2015]-       (in brackets)
    This function fills in the end year to close the range:
      $c 2015-2024
      $c [2015]-[2024]
    
    It also updates $3 (materials specified) if it contains an open date
    range ending with a colon, e.g.:
      Before: $3 v.1 (2015)- :
      After:  $3 v.1 (2015)-2024 :"""
    ceased_year = extract_year(ceased_date)
    if ceased_year is None:
        print(f"Ceased date does not contain a valid year: {ceased_date}")
        return

    # Check both 260 and 264 fields (different cataloging conventions)
    for datafield in record.findall("datafield[@tag='260']") + record.findall("datafield[@tag='264']"):

        # ---- Update subfield $c (date of publication) ----
        subfield_c = datafield.find("subfield[@code='c']")
        if subfield_c is not None and subfield_c.text:
            current_value = subfield_c.text.strip()

            # Case 1: Bracketed start year ending with hyphen → [2015]-[2024]
            match = re.match(r"(\[\d{4}\])\s*-\s*$", current_value)
            if match:
                subfield_c.text = f"{match.group(1)}-[{ceased_year}]"

            # Case 2: Non-bracketed year ending with hyphen → 2015-2024
            elif current_value.endswith('-'):
                subfield_c.text = current_value + ceased_year

        # ---- Update subfield $3 (materials specified) ----
        subfield_3 = datafield.find("subfield[@code='3']")
        if subfield_3 is not None and subfield_3.text:
            current_value = subfield_3.text.strip()
            # If $3 ends with "- :" (open range followed by colon), close it
            if re.search(r"-\s*:$", current_value):
                subfield_3.text = current_value[:-2] + ceased_year + " :"


def update_362_field(record, ceased_date):
    """Add or update the 362 field (dates of publication note).
    
    The 362 with first indicator '1' is an unformatted note about when the
    serial started and/or stopped. This function handles three cases:
    
    1. A 362 exists with $a already populated → append the ceased info:
       Before: 362 1_ $a Began with v.1 (2010).
       After:  362 1_ $a Began with v.1 (2010); ceased with v.50 no.4 (2024).
    
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
                subfield_a.text = f"Ceased with {ceased_date}."
            else:
                # Case 1: 362 $a exists — append ceased info after existing text
                updated_text = subfield_a.text.rstrip('.')
                subfield_a.text = f"{updated_text}; ceased with {ceased_date}."
    else:
        # Case 3: No 362 at all — create a new one from scratch
        new_362 = ET.Element('datafield', attrib={'tag': '362', 'ind1': '1', 'ind2': ' '})
        subfield_a = ET.SubElement(new_362, 'subfield', attrib={'code': 'a'})
        subfield_a.text = f"Ceased with {ceased_date}."
        record.append(new_362)


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
# MAIN WORKFLOW
# =============================================================================
# This function ties everything together: it reads your CSV, fetches each
# record from Alma, updates the MARC fields, and saves the changes back.
# =============================================================================

def process_csv(csv_filename):
    """Process a CSV of ceased titles and update their records in Alma.
    
    Expected CSV columns:
      - 'MMS ID'      : The Alma MMS ID for each title (required)
      - 'Ceased date'  : When the title ceased, e.g. 'v.50 no.4 (2024)'
    """
    with open(csv_filename, newline='', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        print("CSV headers:", reader.fieldnames)
        for row in reader:
            print(row)

            mms_id = row.get('MMS ID')
            ceased_date = row.get('Ceased date')

            # Skip rows that don't have an MMS ID
            if mms_id is None:
                print("Skipping row due to missing MMS ID:", row)
                continue

            # Step 1: Fetch the current record from Alma
            record_xml = get_record(mms_id)
            if record_xml is None:
                continue
            tree = ET.fromstring(record_xml)
            record = tree.find('record')

            # Step 2: Skip MEDLINE/PubMed titles (they need a different workflow)
            if should_skip_record(record):
                print(f"Skipping MMS ID {mms_id}: Can't cease MEDLINE or PMC titles programmatically")
                continue

            # Step 3: Update MARC fields if we have a ceased date
            if ceased_date:
                update_008_field(record, ceased_date)       # Fixed field: publication status
                update_260_264_field(record, ceased_date)   # Publication statement dates
                update_362_field(record, ceased_date)       # Dates of publication note
            
            # Step 4: Always stamp the 995 review date
            update_995_field(record)

            # Step 5: Save the updated record back to Alma
            put_record(mms_id, ET.tostring(tree, encoding='utf-8').decode('utf-8'))

# =============================================================================
# RUN THE SCRIPT
# =============================================================================
# Replace the path below with the path to your CSV file.
# The CSV should have columns: 'MMS ID' and 'Ceased date'
process_csv('your_file_path/ceasedtitle.csv')
