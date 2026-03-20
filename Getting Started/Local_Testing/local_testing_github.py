"""
Alma API Local Testing Script (GitHub Template)

This script demonstrates a safe local-testing workflow:
1) Fetch a bibliographic record by MMS ID from Alma.
2) Save the original MARCXML locally.
3) Apply test XML changes locally (no PUT back to Alma).

Use this as a template before building production update scripts.
"""

import os
import requests
import xml.etree.ElementTree as ET


def load_alma_sandbox_key(api_key_file_path):
    """Load alma_sandbox_key from a local key file."""
    api_key = None
    with open(api_key_file_path, "r", encoding="utf-8") as key_file:
        for line in key_file:
            if line.strip().startswith("alma_sandbox_key"):
                api_key = line.split("=", 1)[1].strip().strip('"')
                break
    if not api_key:
        raise ValueError("Alma sandbox API key not found in key file.")
    return api_key


def get_bib_record(mms_id, api_key, alma_api_base_url):
    """Download a single Alma bib record as XML bytes."""
    url = f"{alma_api_base_url.rstrip('/')}/{mms_id}"
    headers = {
        "Authorization": f"apikey {api_key}",
        "Accept": "application/xml",
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.content


def modify_marc_xml(input_filename, output_filename):
    """Example local MARCXML edit: insert 246 $a test in numeric tag order."""
    ET.register_namespace("", "http://www.loc.gov/MARC21/slim")

    tree = ET.parse(input_filename)
    root = tree.getroot()

    record_elem = root.find(".//record")
    if record_elem is None:
        record_elem = root.find(".//{http://www.loc.gov/MARC21/slim}record")
    if record_elem is None:
        print("Warning: Could not find <record> tag. Appending to root.")
        record_elem = root

    new_datafield = ET.Element("datafield", {"tag": "246", "ind1": "1", "ind2": " "})
    new_subfield = ET.SubElement(new_datafield, "subfield", code="a")
    new_subfield.text = "test"

    insert_index = len(record_elem)
    for i, child in enumerate(record_elem):
        tag_attr = child.get("tag")
        if tag_attr and tag_attr.isdigit() and int(tag_attr) > 246:
            insert_index = i
            break

    record_elem.insert(insert_index, new_datafield)
    tree.write(output_filename, encoding="utf-8", xml_declaration=True)
    print(f"Added 246 $a 'test' and saved modified record to '{output_filename}'.")


def main():
    print("--- Alma API Local Testing Setup ---")

    # Update these defaults for your environment.
    api_key_file = r"your_file_path_here.txt"
    alma_api_base_url = "https://api-na.hosted.exlibrisgroup.com/almaws/v1/bibs"

    mms_id = input("Enter the MMS ID to retrieve: ").strip()
    if not mms_id:
        print("MMS ID is required. Exiting...")
        return

    try:
        api_key = load_alma_sandbox_key(api_key_file)
    except FileNotFoundError:
        print(f"ERROR: API key file not found at {api_key_file}")
        return
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return

    script_dir = os.path.dirname(os.path.abspath(__file__))
    original_filename = os.path.join(script_dir, f"{mms_id}.xml")
    modified_filename = os.path.join(script_dir, "local_test.xml")

    print(f"\nFetching record {mms_id} from Alma...")
    try:
        xml_content = get_bib_record(mms_id, api_key, alma_api_base_url)
    except requests.exceptions.HTTPError as exc:
        print(f"HTTP error while fetching record: {exc}")
        return
    except requests.exceptions.RequestException as exc:
        print(f"Request error while fetching record: {exc}")
        return

    with open(original_filename, "wb") as output_file:
        output_file.write(xml_content)
    print(f"Saved original record to '{original_filename}'.")

    print("\nRunning local XML test modifications...")
    modify_marc_xml(original_filename, modified_filename)

    print("\nLocal testing complete. Review both XML files before any Alma PUT workflow.")


if __name__ == "__main__":
    main()