import argparse
import logging
import math
import os
import sys
import threading

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure simple logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOG = logging.getLogger(__name__)

ALMA_API_URL = "https://api-na.hosted.exlibrisgroup.com/almaws/v1"
ALMA_MEMBERS_PAGE_LIMIT = 100
SUPPORTED_CONTENT_TYPES = {"BIB_MMS"}


def get_session():
    """Create a requests session with retries for transient network/server errors."""
    session = requests.Session()
    retry = Retry(
        total=5,
        connect=3,
        read=3,
        backoff_factor=2,
        status_forcelist=[500, 502, 503, 504],
    )
    adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def load_api_key(api_key_file, environment):
    """Load an Alma API key from a local text file using the repo's key names."""
    key_name = "alma_production_key" if environment == "production" else "alma_sandbox_key"
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
        "Expected keys: alma_sandbox_key and alma_production_key."
    )


def get_set_info(set_id, api_key):
    """Fetch metadata for an Alma set via GET /conf/sets/{set_id}."""
    headers = {
        "Authorization": f"apikey {api_key}",
        "Accept": "application/json",
    }
    url = f"{ALMA_API_URL}/conf/sets/{set_id}"
    try:
        response = get_session().get(url, headers=headers, timeout=30)
        if response.status_code == 400:
            return None, None, 0, (
                f"Set ID {set_id!r} was not found. "
                "Please check that you entered a Set ID, not an MMS ID."
            )
        response.raise_for_status()
        data = response.json()
        set_name = data.get("name", set_id)
        content_type = data.get("content", {}).get("value", "")
        total_records = data.get("number_of_members", {}).get("value", 0)
        return set_name, content_type, total_records, None
    except requests.exceptions.RequestException as exc:
        return None, None, 0, f"Error fetching set info: {exc}"


def extract_set_members(set_id, api_key, total_records):
    """Retrieve all member MMS IDs from a source set using parallel page requests."""
    headers = {
        "Authorization": f"apikey {api_key}",
        "Accept": "application/json",
    }

    if total_records == 0:
        return []

    offsets = list(range(0, total_records, ALMA_MEMBERS_PAGE_LIMIT))
    results = {}
    lock = threading.Lock()
    semaphore = threading.Semaphore(10)
    session = get_session()

    LOG.info("Starting extraction of %s records...", total_records)

    def fetch_chunk(offset):
        with semaphore:
            try:
                url = (
                    f"{ALMA_API_URL}/conf/sets/{set_id}/members"
                    f"?limit={ALMA_MEMBERS_PAGE_LIMIT}&offset={offset}"
                )
                response = session.get(url, headers=headers, timeout=60)
                response.raise_for_status()
                data = response.json()
                members = data.get("member", [])
                chunk_ids = [member.get("id") for member in members if member.get("id")]
                with lock:
                    results[offset] = chunk_ids
            except Exception as exc:  # noqa: BLE001
                LOG.error("Error fetching chunk at offset %s: %s", offset, exc)
                with lock:
                    results[offset] = []

    threads = [threading.Thread(target=fetch_chunk, args=(offset,)) for offset in offsets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    mms_ids = []
    for offset in offsets:
        mms_ids.extend(results.get(offset, []))

    LOG.info("Extracted %s record IDs.", len(mms_ids))
    return mms_ids


def create_itemized_set(set_name, description, content_type, api_key):
    """Create an empty itemized Alma set and return the new set ID."""
    url = f"{ALMA_API_URL}/conf/sets"
    headers = {
        "Authorization": f"apikey {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "name": set_name,
        "description": description,
        "type": {"value": "ITEMIZED"},
        "content": {"value": content_type},
        "private": {"value": "false"},
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.status_code != 200:
        alma_error = response.text
        try:
            errors = response.json().get("errorList", {}).get("error", [])
            if errors:
                alma_error = "; ".join(err.get("errorMessage", "") for err in errors)
        except Exception:  # noqa: BLE001
            pass
        msg = f"{response.status_code} Client Error: {alma_error}"
        raise requests.exceptions.HTTPError(msg, response=response)

    new_set_id = response.json().get("id")
    LOG.info("Set '%s' created successfully. Set ID: %s", set_name, new_set_id)
    return new_set_id


def add_members_to_set(set_id, mms_ids, api_key):
    """Populate an itemized set with MMS IDs using chunked, parallel add_members calls."""
    url = f"{ALMA_API_URL}/conf/sets/{set_id}?op=add_members"
    headers = {
        "Authorization": f"apikey {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    session = get_session()

    chunk_size = 1000
    chunks = [mms_ids[i : i + chunk_size] for i in range(0, len(mms_ids), chunk_size)]

    LOG.info(
        "Adding %s members to Set %s in %s batch(es) of up to %s...",
        len(mms_ids),
        set_id,
        len(chunks),
        chunk_size,
    )

    push_lock = threading.Lock()
    push_semaphore = threading.Semaphore(5)
    chunk_errors = []

    def extract_alma_error(response):
        try:
            errors = response.json().get("errorList", {}).get("error", [])
            if errors:
                return "; ".join(err.get("errorMessage", "") for err in errors)
        except Exception:  # noqa: BLE001
            pass
        return response.text

    def push_chunk(chunk):
        with push_semaphore:
            payload = {
                "members": {
                    "member": [{"id": str(record_id)} for record_id in chunk],
                },
            }
            try:
                response = session.post(url, headers=headers, json=payload, timeout=60)
                if response.status_code not in (200, 204):
                    alma_error = extract_alma_error(response)
                    err = f"{response.status_code} error adding members: {alma_error}"
                    with push_lock:
                        chunk_errors.append(err)
                else:
                    LOG.info("Chunk of %s added to set %s.", len(chunk), set_id)
            except Exception as exc:  # noqa: BLE001
                with push_lock:
                    chunk_errors.append(f"Error pushing chunk: {exc}")

    threads = [threading.Thread(target=push_chunk, args=(chunk,)) for chunk in chunks]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    if chunk_errors:
        raise RuntimeError(" | ".join(chunk_errors))

    LOG.info("Finished adding members to Set %s.", set_id)


def run_batch(set_id, batch_size, base_set_name, api_key):
    """Split source-set members into batches and create new itemized sets."""
    set_name, content_type, total_records, set_error = get_set_info(set_id, api_key)
    if set_error:
        return False, set_error, 0, []

    if total_records == 0:
        return False, "The source set is empty.", 0, []

    if content_type not in SUPPORTED_CONTENT_TYPES:
        return False, (
            f"Set content type '{content_type}' is not supported. "
            "This tool only works with Bibliographic (BIB_MMS) sets."
        ), total_records, []

    LOG.info("Source set '%s' has %s records.", set_name, total_records)

    mms_ids = extract_set_members(set_id, api_key, total_records)
    if not mms_ids:
        return False, "No MMS IDs were found to process.", total_records, []

    batches = [mms_ids[i : i + batch_size] for i in range(0, len(mms_ids), batch_size)]
    batch_results = []

    for index, batch in enumerate(batches, start=1):
        new_name = f"{base_set_name} Batch {index}"
        LOG.info("Processing batch %s of %s: %s records", index, len(batches), len(batch))
        try:
            new_set_id = create_itemized_set(
                set_name=new_name,
                description=f"Batch {index} auto-generated from source set {set_id}",
                content_type=content_type,
                api_key=api_key,
            )
            add_members_to_set(new_set_id, batch, api_key)
            batch_results.append(
                {
                    "batch_num": index,
                    "set_name": new_name,
                    "new_set_id": new_set_id,
                    "count": len(batch),
                    "error": None,
                }
            )
        except Exception as exc:  # noqa: BLE001
            batch_results.append(
                {
                    "batch_num": index,
                    "set_name": new_name,
                    "new_set_id": None,
                    "count": len(batch),
                    "error": str(exc),
                }
            )

    successful = sum(1 for batch in batch_results if not batch["error"])
    summary = f"Done. Created {successful} of {len(batches)} batch set(s) from {total_records} records."
    return successful == len(batches), summary, total_records, batch_results


def print_preview(set_id, batch_size, base_set_name, environment, set_name, total_records):
    """Print a quick run preview before creating sets."""
    batches = math.ceil(total_records / batch_size)
    print("\n--- Preview ---")
    print(f"Environment: {environment}")
    print(f"Source Set ID: {set_id}")
    print(f"Source Set Name: {set_name}")
    print(f"Source Records: {total_records}")
    print(f"Batch Size: {batch_size}")
    print(f"Expected Batch Sets: {batches}")
    print(f"Base Set Name: {base_set_name}")
    print("----------------\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create Alma batch itemized sets from an existing source set.",
    )
    parser.add_argument("--set_id", help="Source Alma Set ID to split")
    parser.add_argument("--batch_size", type=int, help="Records per output set")
    parser.add_argument("--base_set_name", help="Base name for output sets")
    parser.add_argument(
        "--environment",
        choices=["sandbox", "production"],
        default="sandbox",
        help="Alma environment for API key selection",
    )
    parser.add_argument(
        "--api_key_file",
        default=os.environ.get("ALMA_API_KEY_FILE", r"your_file_path_here.txt"),
        help="Path to alma_api_keys.txt",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt and run immediately",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    set_id = args.set_id or input("Enter source Set ID: ").strip()
    if not set_id:
        LOG.error("A source Set ID is required.")
        sys.exit(1)

    if args.batch_size is None:
        batch_size_text = input("Enter batch size (records per set): ").strip()
        try:
            batch_size = int(batch_size_text)
        except ValueError:
            LOG.error("Batch size must be an integer.")
            sys.exit(1)
    else:
        batch_size = args.batch_size

    if batch_size <= 0:
        LOG.error("Batch size must be greater than 0.")
        sys.exit(1)

    base_set_name = args.base_set_name or input("Enter base set name: ").strip()
    if not base_set_name:
        LOG.error("A base set name is required.")
        sys.exit(1)

    api_key = load_api_key(args.api_key_file, args.environment)

    set_name, content_type, total_records, set_error = get_set_info(set_id, api_key)
    if set_error:
        LOG.error(set_error)
        sys.exit(1)

    if content_type not in SUPPORTED_CONTENT_TYPES:
        LOG.error(
            "Set content type '%s' is not supported. This tool only supports BIB_MMS sets.",
            content_type,
        )
        sys.exit(1)

    print_preview(set_id, batch_size, base_set_name, args.environment, set_name, total_records)

    if not args.yes:
        confirm = input("Proceed and create batch sets? (y/n): ").strip().lower()
        if confirm not in {"y", "yes"}:
            print("Cancelled.")
            return

    success, message, _, batch_results = run_batch(set_id, batch_size, base_set_name, api_key)

    print("\n--- Results ---")
    print(message)
    for result in batch_results:
        if result["error"]:
            print(
                f"Batch {result['batch_num']}: FAILED | {result['set_name']} | "
                f"records={result['count']} | error={result['error']}"
            )
        else:
            print(
                f"Batch {result['batch_num']}: OK | {result['set_name']} | "
                f"new_set_id={result['new_set_id']} | records={result['count']}"
            )

    if not success:
        sys.exit(2)


if __name__ == "__main__":
    main()
