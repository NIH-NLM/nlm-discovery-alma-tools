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
    """Remove named child elements from an XML root before POSTing."""
    for tag in tag_names:
        element = root.find(tag)
        if element is not None:
            root.remove(element)


# ---------------------------------------------------------------------------
# BIB
# ---------------------------------------------------------------------------
def get_bib(mms_id, prod_key):
    url = f"{ALMA_API_BASE}/bibs/{mms_id}"
    response = requests.get(url, headers=prod_headers(prod_key), timeout=60)
    response.raise_for_status()
    return response.content


def create_bib_sandbox(bib_xml, sandbox_key):
    root = ET.fromstring(bib_xml)
    remove_elements(root, "mms_id", "linked_record_id", "nz_mms_id", "cz_mms_id")
    xml_body = ET.tostring(root, encoding="utf-8")
    url = f"{ALMA_API_BASE}/bibs"
    response = requests.post(url, headers=sandbox_headers(sandbox_key), data=xml_body, timeout=60)
    response.raise_for_status()
    new_root = ET.fromstring(response.content)
    return new_root.findtext("mms_id")


def extract_bib_title(bib_xml):
    root = ET.fromstring(bib_xml)
    for datafield in root.findall(".//datafield[@tag='245']"):
        subfield_a = datafield.find("subfield[@code='a']")
        if subfield_a is not None and subfield_a.text:
            return subfield_a.text.strip()
    return None


# ---------------------------------------------------------------------------
# HOLDINGS
# ---------------------------------------------------------------------------
def get_holdings_list(mms_id, prod_key):
    """Return a list of (holding_id, location_label) tuples from Production."""
    url = f"{ALMA_API_BASE}/bibs/{mms_id}/holdings"
    response = requests.get(url, headers=prod_headers(prod_key), timeout=60)
    response.raise_for_status()

    root = ET.fromstring(response.content)
    results = []
    for holding in root.findall(".//holding"):
        holding_id = holding.findtext("holding_id")
        location = holding.findtext("location") or "unknown location"
        if holding_id:
            results.append((holding_id, location))
    return results


def get_holding(mms_id, holding_id, prod_key):
    url = f"{ALMA_API_BASE}/bibs/{mms_id}/holdings/{holding_id}"
    response = requests.get(url, headers=prod_headers(prod_key), timeout=60)
    response.raise_for_status()
    return response.content


def create_holding_sandbox(new_mms_id, holding_xml, sandbox_key):
    root = ET.fromstring(holding_xml)
    remove_elements(root, "holding_id", "bib_data")
    xml_body = ET.tostring(root, encoding="utf-8")
    url = f"{ALMA_API_BASE}/bibs/{new_mms_id}/holdings"
    response = requests.post(url, headers=sandbox_headers(sandbox_key), data=xml_body, timeout=60)
    response.raise_for_status()
    new_root = ET.fromstring(response.content)
    return new_root.findtext("holding_id")


# ---------------------------------------------------------------------------
# ITEMS
# ---------------------------------------------------------------------------
def get_item_pids(mms_id, holding_id, prod_key):
    """Return all item PIDs for a holding, handling pagination."""
    pids = []
    offset = 0
    limit = 100

    while True:
        url = (
            f"{ALMA_API_BASE}/bibs/{mms_id}/holdings/{holding_id}/items"
            f"?offset={offset}&limit={limit}"
        )
        response = requests.get(url, headers=prod_headers(prod_key), timeout=60)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        total = int(root.get("total_record_count", 0))
        for item in root.findall(".//item"):
            pid = item.findtext("item_data/pid")
            if pid:
                pids.append(pid)

        offset += limit
        if offset >= total:
            break

    return pids


def get_item(mms_id, holding_id, pid, prod_key):
    url = f"{ALMA_API_BASE}/bibs/{mms_id}/holdings/{holding_id}/items/{pid}"
    response = requests.get(url, headers=prod_headers(prod_key), timeout=60)
    response.raise_for_status()
    return response.content


def create_item_sandbox(new_mms_id, new_holding_id, item_xml, sandbox_key):
    root = ET.fromstring(item_xml)
    remove_elements(root, "bib_data", "holding_data")
    item_data = root.find("item_data")
    if item_data is not None:
        remove_elements(item_data, "pid")

    xml_body = ET.tostring(root, encoding="utf-8")
    url = f"{ALMA_API_BASE}/bibs/{new_mms_id}/holdings/{new_holding_id}/items"
    response = requests.post(url, headers=sandbox_headers(sandbox_key), data=xml_body, timeout=60)
    response.raise_for_status()
    new_root = ET.fromstring(response.content)
    return new_root.findtext("item_data/pid")


# ---------------------------------------------------------------------------
# PORTFOLIOS
# ---------------------------------------------------------------------------
def get_portfolio_ids(mms_id, prod_key):
    """Return all portfolio IDs for a bib, handling pagination."""
    portfolio_ids = []
    offset = 0
    limit = 100

    while True:
        url = f"{ALMA_API_BASE}/bibs/{mms_id}/portfolios?offset={offset}&limit={limit}"
        response = requests.get(url, headers=prod_headers(prod_key), timeout=60)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        total = int(root.get("total_record_count", 0))
        for portfolio in root.findall(".//portfolio"):
            portfolio_id = portfolio.findtext("id")
            if portfolio_id:
                portfolio_ids.append(portfolio_id)

        offset += limit
        if offset >= total:
            break

    return portfolio_ids


def get_portfolio(mms_id, portfolio_id, prod_key):
    url = f"{ALMA_API_BASE}/bibs/{mms_id}/portfolios/{portfolio_id}"
    response = requests.get(url, headers=prod_headers(prod_key), timeout=60)
    response.raise_for_status()
    return response.content


def create_portfolio_sandbox(new_mms_id, portfolio_xml, sandbox_key):
    root = ET.fromstring(portfolio_xml)
    remove_elements(root, "id")
    xml_body = ET.tostring(root, encoding="utf-8")
    url = f"{ALMA_API_BASE}/bibs/{new_mms_id}/portfolios"
    response = requests.post(url, headers=sandbox_headers(sandbox_key), data=xml_body, timeout=60)
    response.raise_for_status()
    new_root = ET.fromstring(response.content)
    return new_root.findtext("id")


def move_bib_prod_to_sandbox(mms_id, prod_key, sandbox_key):
    """Copy one bib and attached inventory from Production to Sandbox."""
    log = []

    LOG.info("Fetching bib %s from Production...", mms_id)
    bib_xml = get_bib(mms_id, prod_key)
    title_245 = extract_bib_title(bib_xml)

    LOG.info("Creating bib in Sandbox...")
    new_mms_id = create_bib_sandbox(bib_xml, sandbox_key)
    log.append(f"Bib created in Sandbox - MMS ID: {new_mms_id}")

    holdings_count = 0
    try:
        holdings = get_holdings_list(mms_id, prod_key)
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        log.append(f"Could not retrieve holdings: {status}")
        holdings = []

    for holding_id, location in holdings:
        try:
            holding_xml = get_holding(mms_id, holding_id, prod_key)
            new_holding_id = create_holding_sandbox(new_mms_id, holding_xml, sandbox_key)
            log.append(f"Holding {holding_id} ({location}) -> {new_holding_id}")
            holdings_count += 1
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            body = exc.response.text[:200] if exc.response is not None else str(exc)
            log.append(f"ERROR copying holding {holding_id}: {status} - {body}")
            continue

        try:
            pids = get_item_pids(mms_id, holding_id, prod_key)
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            log.append(f"  ERROR retrieving items for holding {holding_id}: {status}")
            pids = []

        for pid in pids:
            try:
                item_xml = get_item(mms_id, holding_id, pid, prod_key)
                new_pid = create_item_sandbox(new_mms_id, new_holding_id, item_xml, sandbox_key)
                log.append(f"  Item {pid} -> {new_pid}")
            except requests.exceptions.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else "unknown"
                body = exc.response.text[:200] if exc.response is not None else str(exc)
                log.append(f"  ERROR copying item {pid}: {status} - {body}")

    portfolios_count = 0
    try:
        portfolio_ids = get_portfolio_ids(mms_id, prod_key)
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        log.append(f"Could not retrieve portfolios: {status}")
        portfolio_ids = []

    for portfolio_id in portfolio_ids:
        try:
            portfolio_xml = get_portfolio(mms_id, portfolio_id, prod_key)
            new_portfolio_id = create_portfolio_sandbox(new_mms_id, portfolio_xml, sandbox_key)
            log.append(f"Portfolio {portfolio_id} -> {new_portfolio_id}")
            portfolios_count += 1
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            body = exc.response.text[:200] if exc.response is not None else str(exc)
            log.append(f"ERROR copying portfolio {portfolio_id}: {status} - {body}")

    return {
        "source_mms_id": mms_id,
        "new_mms_id": new_mms_id,
        "title": title_245,
        "holdings_count": holdings_count,
        "portfolios_count": portfolios_count,
        "log": log,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Copy one bib record and inventory from Alma Production to Alma Sandbox.",
    )
    parser.add_argument("--mms_id", help="Bib MMS ID to copy")
    parser.add_argument(
        "--api_key_file",
        default=os.environ.get("ALMA_API_KEY_FILE", r"your_file_path_here.txt"),
        help="Path to alma_api_keys.txt",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    mms_id = args.mms_id or input("Enter bib MMS ID: ").strip()
    if not mms_id:
        LOG.error("Bib MMS ID is required.")
        sys.exit(1)
    if not mms_id.isdigit():
        LOG.error("Bib MMS ID must contain only digits.")
        sys.exit(1)

    prod_key = load_api_key(args.api_key_file, "alma_production_key")
    sandbox_key = load_api_key(args.api_key_file, "alma_sandbox_key")

    try:
        result = move_bib_prod_to_sandbox(mms_id, prod_key, sandbox_key)
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        body = exc.response.text if exc.response is not None else str(exc)
        LOG.error("Alma API request failed (%s): %s", status, body)
        sys.exit(2)
    except Exception as exc:  # noqa: BLE001
        LOG.error("Unexpected error: %s", exc)
        sys.exit(3)

    print("\n--- Result ---")
    print(f"Source MMS ID: {result['source_mms_id']}")
    print(f"New sandbox MMS ID: {result['new_mms_id']}")
    if result["title"]:
        print(f"Title (245$a): {result['title']}")
    else:
        print("Title (245$a): (not found)")
    print(f"Holdings copied: {result['holdings_count']}")
    print(f"Portfolios copied: {result['portfolios_count']}")

    print("\nLog:")
    for line in result["log"]:
        print(f"- {line}")
    print("--------------")


if __name__ == "__main__":
    main()
