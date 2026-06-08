import argparse
import logging
import os
import sys

import requests
from xml.etree import ElementTree as ET

# Configure simple logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOG = logging.getLogger(__name__)

ALMA_API_BASE = "https://api-na.hosted.exlibrisgroup.com/almaws/v1"


def prod_headers(prod_key):
    return {
        "Accept": "application/xml",
        "Content-Type": "application/xml",
        "Authorization": f"apikey {prod_key}",
    }


def sandbox_headers(sandbox_key):
    return {
        "Accept": "application/xml",
        "Content-Type": "application/xml",
        "Authorization": f"apikey {sandbox_key}",
    }


def load_api_key(api_key_file, key_name):
    """Load one API key from a text file using expected key names."""
    try:
        with open(api_key_file, encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped.startswith(key_name):
                    return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        LOG.error("API key file not found at %s", api_key_file)
        sys.exit(1)

    raise ValueError(
        f"Could not find {key_name!r} in key file. "
        "Expected keys include alma_production_key and alma_sandbox_key."
    )


def remove_elements(root, *tag_names):
    """Remove named child elements from XML root before creating in sandbox."""
    for tag in tag_names:
        element = root.find(tag)
        if element is not None:
            root.remove(element)


def get_authority(auth_id, prod_key):
    """Fetch full authority XML from Alma Production."""
    url = f"{ALMA_API_BASE}/bibs/authorities/{auth_id}?view=full"
    response = requests.get(url, headers=prod_headers(prod_key), timeout=60)
    response.raise_for_status()
    return response.content


def extract_heading(authority_xml):
    """Extract 1xx authorized heading text for output display."""
    root = ET.fromstring(authority_xml)
    for tag in ("100", "110", "111", "130", "150", "151", "155"):
        for field in root.findall(f".//datafield[@tag='{tag}']"):
            parts = [subfield.text for subfield in field.findall("subfield") if subfield.text]
            if parts:
                return " ".join(parts)
    return None


def create_authority_sandbox(authority_xml, sandbox_key):
    """Create authority in Sandbox and return newly assigned MMS ID."""
    root = ET.fromstring(authority_xml)
    remove_elements(root, "mms_id", "linked_record_id", "nz_mms_id", "cz_mms_id")

    xml_body = ET.tostring(root, encoding="utf-8")
    url = f"{ALMA_API_BASE}/bibs/authorities"
    response = requests.post(url, headers=sandbox_headers(sandbox_key), data=xml_body, timeout=60)
    response.raise_for_status()

    new_root = ET.fromstring(response.content)
    return new_root.findtext("mms_id")


def move_authority_prod_to_sandbox(auth_id, prod_key, sandbox_key):
    """Copy one authority record from Alma Production to Alma Sandbox."""
    LOG.info("Fetching authority %s from Production...", auth_id)
    authority_xml = get_authority(auth_id, prod_key)

    heading = extract_heading(authority_xml)

    LOG.info("Creating authority in Sandbox...")
    new_auth_id = create_authority_sandbox(authority_xml, sandbox_key)

    return {
        "source_auth_id": auth_id,
        "new_auth_id": new_auth_id,
        "heading": heading,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Copy one authority record from Alma Production to Alma Sandbox.",
    )
    parser.add_argument("--auth_id", help="Authority MMS ID to copy")
    parser.add_argument(
        "--api_key_file",
        default=os.environ.get("ALMA_API_KEY_FILE", r"your_file_path_here.txt"),
        help="Path to alma_api_keys.txt",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    auth_id = args.auth_id or input("Enter authority MMS ID: ").strip()
    if not auth_id:
        LOG.error("Authority MMS ID is required.")
        sys.exit(1)
    if not auth_id.isdigit():
        LOG.error("Authority MMS ID must contain only digits.")
        sys.exit(1)

    prod_key = load_api_key(args.api_key_file, "alma_production_key")
    sandbox_key = load_api_key(args.api_key_file, "alma_sandbox_key")

    try:
        result = move_authority_prod_to_sandbox(auth_id, prod_key, sandbox_key)
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        body = exc.response.text if exc.response is not None else str(exc)
        LOG.error("Alma API request failed (%s): %s", status, body)
        sys.exit(2)
    except Exception as exc:  # noqa: BLE001
        LOG.error("Unexpected error: %s", exc)
        sys.exit(3)

    print("\n--- Result ---")
    print(f"Source authority MMS ID: {result['source_auth_id']}")
    print(f"New sandbox MMS ID: {result['new_auth_id']}")
    if result["heading"]:
        print(f"Heading: {result['heading']}")
    else:
        print("Heading: (not found in 1xx)")
    print("--------------")


if __name__ == "__main__":
    main()
