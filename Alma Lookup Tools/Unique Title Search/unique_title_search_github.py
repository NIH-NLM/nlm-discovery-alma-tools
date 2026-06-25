import argparse
import logging
import os
from pathlib import Path
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET

import requests


logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOG = logging.getLogger(__name__)


# =============================================================================
# API KEY SETUP (GitHub-safe)
# =============================================================================
def load_api_key(api_key=None, api_key_file=None, prefer_production=False):
    if api_key:
        return api_key.strip()

    env_key = os.getenv("ALMA_API_KEY")
    if env_key:
        return env_key.strip()

    if api_key_file:
        candidate_files = [api_key_file]
    else:
        default_repo_key_file = Path(__file__).resolve().parents[2] / "alma_api_keys_github.txt"
        env_key_file = os.getenv("ALMA_API_KEY_FILE")
        candidate_files = [p for p in [env_key_file, str(default_repo_key_file)] if p]

    for candidate in candidate_files:
        try:
            with open(candidate, encoding="utf-8") as f:
                content = f.read()
        except FileNotFoundError:
            continue

        parsed = {}
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            parsed[key.strip()] = value.strip().strip('"').strip("'")

        preferred_name = "alma_production_key" if prefer_production else "alma_sandbox_key"
        fallback_name = "alma_sandbox_key" if prefer_production else "alma_production_key"

        if parsed.get(preferred_name):
            return parsed[preferred_name]
        if parsed.get(fallback_name):
            return parsed[fallback_name]

        single_line = content.strip().strip('"').strip("'")
        if single_line and "\n" not in single_line and "=" not in single_line:
            return single_line

    raise ValueError(
        "Could not load Alma API key. Provide --api_key, set ALMA_API_KEY, "
        "or provide --api_key_file / ALMA_API_KEY_FILE with alma_sandbox_key/alma_production_key."
    )


ALMA_API_URL = "https://api-na.hosted.exlibrisgroup.com/almaws/v1"


def normalize_rda_title(title_str):
    if not title_str:
        return ""

    title_str = re.sub(r"(.+?(?:\s:|\s/|\s=|$)).*", r"\1", title_str)
    title_str = title_str.lower()

    replacements = {
        "ae_lig": ("\u00e6", "ae"),
        "ae_long": ("\u01e3", "ae"),
        "oe_lig": ("\u0153", "oe"),
        "thorn": ("\u00fe", "th"),
        "ia_tie": ("i\ufe20a\ufe21", "ia"),
        "ts_tie": ("t\ufe20s\ufe21", "ts"),
        "iu_tie": ("i\ufe20u\ufe21", "iu"),
        "zh_tie": ("z\ufe20h\ufe21", "zh"),
        "okina": ("\u02bb", ""),
        "apostrophe_mod": ("\u02bc", ""),
        "hamza_mod": ("\u02be", ""),
        "combining_left": ("\ufe20", ""),
        "combining_right": ("\ufe21", ""),
        "combining_double": ("\ufe23", ""),
    }
    title_str = unicodedata.normalize("NFC", title_str)
    for _, pair in replacements.items():
        old, new = pair
        title_str = title_str.replace(old, new)

    title_str = unicodedata.normalize("NFKD", title_str).encode("ASCII", "ignore").decode("utf-8")
    title_str = re.sub(r"<<.*?>>", "", title_str)
    title_str = re.sub(r"[^\w\s]", "", title_str)
    title_str = " ".join(title_str.split())
    return title_str


def get_alma_record(mms_id, api_url, api_key):
    if not isinstance(mms_id, str):
        raise TypeError("MMS ID must be a string")
    if not mms_id.isdigit():
        raise ValueError("MMS ID must contain only digits")

    headers = {
        "Authorization": f"apikey {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    url = f"{api_url.rstrip('/')}/bibs/{mms_id}"
    resp = requests.get(url, headers=headers, timeout=60)
    if resp.status_code != 200:
        LOG.error(f"Error from Alma API [{resp.status_code}]: {resp.text}")
        resp.raise_for_status()

    resp_json = resp.json()
    marcxml_data = resp_json.get("anies", [""])[0]
    if marcxml_data:
        marcxml_data = "<?xml version=\"1.0\" encoding=\"utf-8\"?>" + marcxml_data

    title = resp_json.get("title")
    if isinstance(title, str):
        title = unicodedata.normalize("NFC", title)
    return title, marcxml_data


def search_sru_catalog(query, sru_base_url, index=None, limit=100):
    cql_query = query if index is None else f'{index}="{query}"'
    results = []
    start_record = 1
    page_size = 50

    while len(results) < limit:
        current_limit = min(page_size, limit - len(results))
        params = {
            "version": "1.2",
            "operation": "searchRetrieve",
            "recordSchema": "marcxml",
            "maximumRecords": str(current_limit),
            "startRecord": str(start_record),
            "query": cql_query,
        }

        response = requests.get(sru_base_url, params=params, timeout=120)
        if response.status_code != 200:
            LOG.error(f"SRU Error: {response.status_code} - {response.text}")
            break

        root = ET.fromstring(response.content)
        namespaces = {
            "srw": "http://www.loc.gov/zing/srw/",
            "marc": "http://www.loc.gov/MARC21/slim",
        }
        records = root.findall(".//srw:recordData/marc:record", namespaces)
        if not records:
            break

        for rec in records:
            for elem in rec.iter():
                if "}" in elem.tag:
                    elem.tag = elem.tag.split("}", 1)[1]
            results.append(ET.tostring(rec, encoding="unicode"))

        start_record += len(records)
        if len(records) < current_limit:
            break

    return results


def extract_query_title_and_target(marcxml_data):
    marcxml_data = re.sub(r'\sxmlns="[^"]+"', "", marcxml_data, count=1)
    root = ET.fromstring(marcxml_data)

    f245 = root.find('.//datafield[@tag="245"]')
    title = None
    extracted_ind2 = None
    if f245 is not None:
        title = " ".join(
            [
                s.text
                for s in f245.findall("subfield")
                if s.attrib.get("code") in ["a", "n", "p"] and s.text
            ]
        )
        ind2 = f245.attrib.get("ind2")
        if ind2 and ind2.isdigit() and int(ind2) > 0 and len(title) >= int(ind2):
            extracted_ind2 = int(ind2)

    if not title:
        return None, None, None

    if extracted_ind2:
        query_base_title = title[extracted_ind2:]
        target_normalized = normalize_rda_title(query_base_title)
    else:
        query_base_title = title
        target_normalized = normalize_rda_title(title)

    return title, query_base_title, target_normalized


def build_cql_query(query_base_title):
    query_title = unicodedata.normalize("NFKD", query_base_title).encode("ASCII", "ignore").decode("utf-8")
    query_title = re.sub(r"[\s\W]+$", "", query_title)
    safe_query = query_title.replace('"', '\\"')

    isbd_suffixes = [" :", " /", " =", ","]
    words = safe_query.split()

    if len(words) > 2:
        return f'alma.title="{safe_query}"'

    articles = [
        "A", "An", "The",
        "Le", "La", "Les", "L'", "Un", "Une", "Des", "Du", "De la",
        "Der", "Die", "Das", "Den", "Dem", "Des", "Ein", "Eine", "Einer", "Eines", "Einem", "Einen",
        "El", "La", "Los", "Las", "Un", "Una", "Unos", "Unas",
        "Il", "Lo", "I", "Gli", "Le", "Uno", "Un'", "Del", "Dello", "Della", "Dei", "Degli", "Delle",
        "O", "Os", "As", "Um", "Uma", "Uns", "Umas",
        "Al", "De", "Na",
    ]

    def title_clauses(text):
        clauses = [f'alma.main_title="{text}"', f'alma.main_title=="{text}"']
        for suffix in isbd_suffixes:
            clauses.append(f'alma.main_title=="{text}{suffix}"')
        return clauses

    cql_clauses = title_clauses(safe_query)
    for article in articles:
        article_query = f"{article} {safe_query}" if not article.endswith("'") else f"{article}{safe_query}"
        cql_clauses.extend(title_clauses(article_query))

    return " or ".join(cql_clauses)


def format_field_with_codes(datafield):
    if datafield is None:
        return ""
    return " ".join(
        [
            f"${s.attrib.get('code', '')} {s.text}"
            for s in datafield.findall("subfield")
            if s.text
        ]
    )


def parse_sru_results(bib_xml_list, target_normalized):
    parsed_results = []

    for xml_string in bib_xml_list:
        if not xml_string:
            continue
        try:
            root = ET.fromstring(xml_string)

            f245 = root.find('.//datafield[@tag="245"]')
            main_title_raw = format_field_with_codes(f245)
            f245_anp = ""
            if f245 is not None:
                f245_anp = " ".join(
                    [
                        s.text
                        for s in f245.findall("subfield")
                        if s.attrib.get("code") in ["a", "n", "p"] and s.text
                    ]
                )
                ind2 = f245.attrib.get("ind2")
                if ind2 and ind2.isdigit() and int(ind2) > 0 and len(f245_anp) >= int(ind2):
                    f245_anp = f245_anp[int(ind2):]

            f130 = root.find('.//datafield[@tag="130"]')
            uniform_title_raw = format_field_with_codes(f130)
            f130_anp = ""
            if f130 is not None:
                f130_anp = " ".join(
                    [
                        s.text
                        for s in f130.findall("subfield")
                        if s.attrib.get("code") in ["a", "n", "p"] and s.text
                    ]
                )
                ind1 = f130.attrib.get("ind1")
                if ind1 and ind1.isdigit() and int(ind1) > 0 and len(f130_anp) >= int(ind1):
                    f130_anp = f130_anp[int(ind1):]

            norm_245 = normalize_rda_title(f245_anp) if f245_anp else ""
            norm_130 = normalize_rda_title(f130_anp) if f130_anp else ""

            if not (norm_245 == target_normalized or (norm_130 and norm_130 == target_normalized)):
                continue

            control001 = root.find('.//controlfield[@tag="001"]')
            hit_mms_id = control001.text if control001 is not None else ""

            nlmid = ""
            for f035 in root.findall('.//datafield[@tag="035"]'):
                sub9 = f035.find('subfield[@code="9"]')
                if sub9 is not None and sub9.text:
                    nlmid = sub9.text
                    break

            author = ""
            for tag in ["100", "110", "111"]:
                f_auth = root.find(f'.//datafield[@tag="{tag}"]')
                if f_auth is not None:
                    author = format_field_with_codes(f_auth)
                    break

            parsed_results.append(
                {
                    "mms_id": hit_mms_id,
                    "nlm_id": nlmid,
                    "author": author,
                    "title": main_title_raw,
                    "uniform_title": uniform_title_raw,
                    "norm_hit": norm_245 if norm_245 == target_normalized else norm_130,
                }
            )
        except Exception as e:
            LOG.error(f"An error occurred parsing unique title hit: {e}")

    return parsed_results


def build_fallback_entry(mms_id, marcxml_data, target_normalized):
    searched_root = ET.fromstring(re.sub(r'\sxmlns="[^"]+"', "", marcxml_data, count=1))

    s_f245 = searched_root.find('.//datafield[@tag="245"]')
    s_main_title_raw = format_field_with_codes(s_f245)

    s_f130 = searched_root.find('.//datafield[@tag="130"]')
    s_uniform_title_raw = format_field_with_codes(s_f130)

    s_nlmid = ""
    for f035 in searched_root.findall('.//datafield[@tag="035"]'):
        sub9 = f035.find('subfield[@code="9"]')
        if sub9 is not None and sub9.text:
            s_nlmid = sub9.text
            break

    s_author = ""
    for tag in ["100", "110", "111"]:
        f_auth = searched_root.find(f'.//datafield[@tag="{tag}"]')
        if f_auth is not None:
            s_author = format_field_with_codes(f_auth)
            break

    return {
        "mms_id": mms_id,
        "nlm_id": s_nlmid,
        "author": s_author,
        "title": s_main_title_raw,
        "uniform_title": s_uniform_title_raw,
        "norm_hit": target_normalized,
    }


def print_results(results):
    print("\n--- Validation Results ---")
    if not results:
        print("No matching records found. Title is unique!")
    else:
        print(f"Found {len(results)} potential duplicate(s) with matching titles:")
        for idx, res in enumerate(results, 1):
            print(f"\nResult #{idx}:")
            print(f"  MMS ID: {res['mms_id']}")
            if res.get("nlm_id"):
                print(f"  NLM ID: {res['nlm_id']}")
            if res.get("author"):
                print(f"  Author: {res['author']}")
            if res.get("uniform_title"):
                print(f"  130 field: {res['uniform_title']}")
            print(f"  245 field: {res['title']}")
            print(f"  Normalized Hit String: {res['norm_hit']}")
    print("-" * 26)


def main():
    parser = argparse.ArgumentParser(description="Alma Unique Title Search Tool (Updated GitHub Version)")
    parser.add_argument("--mms_id", required=False, help="The MMS ID of the record to check")
    parser.add_argument("--api_key", required=False, help="Alma API key (overrides file/env lookup)")
    parser.add_argument(
        "--api_key_file",
        required=False,
        help="Path to key file containing alma_sandbox_key/alma_production_key, or a plain key line",
    )
    parser.add_argument(
        "--use_production_key",
        action="store_true",
        help="Use alma_production_key when reading from key file",
    )
    parser.add_argument(
        "--sru_url",
        default="https://nlm.alma.exlibrisgroup.com/view/sru/01NLM_INST",
        help="The Alma institution SRU URL",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=4000,
        help="Maximum number of SRU records to retrieve (default: 4000)",
    )

    args = parser.parse_args()

    try:
        alma_api_key = load_api_key(
            api_key=args.api_key,
            api_key_file=args.api_key_file,
            prefer_production=args.use_production_key,
        )
    except ValueError as e:
        LOG.error(str(e))
        sys.exit(1)

    mms_id = args.mms_id
    if not mms_id:
        mms_id = input("Enter the MMS ID: ").strip()

    if not mms_id:
        LOG.error("An MMS ID is required to run the search.")
        sys.exit(1)
    if not mms_id.isdigit():
        LOG.error("MMS ID must contain digits only.")
        sys.exit(1)

    LOG.info(f"Fetching record for MMS ID: {mms_id}")

    try:
        _, marcxml_data = get_alma_record(mms_id, ALMA_API_URL, alma_api_key)
    except Exception as e:
        LOG.error(f"Could not fetch record from Alma: {e}")
        sys.exit(1)

    if not marcxml_data:
        LOG.error("Could not fetch valid MARCXML data for the given MMS ID.")
        sys.exit(1)

    source_title, query_base_title, target_normalized = extract_query_title_and_target(marcxml_data)
    if not query_base_title:
        LOG.error("Could not extract 245 $a, $n, $p from the provided MMS ID.")
        sys.exit(1)

    cql_query = build_cql_query(query_base_title)
    LOG.info(f"Searching Alma Catalog SRU for unique title matches: '{query_base_title}'")
    LOG.info(f"Source 245 title: '{source_title}'")
    LOG.info(f"Target Normalized Title: '{target_normalized}'")

    bib_xml_list = []
    try:
        bib_xml_list = search_sru_catalog(cql_query, args.sru_url, index=None, limit=args.limit)
    except Exception as e:
        LOG.error(f"SRU Search Error: {e}")

    LOG.info(f"Alma SRU returned {len(bib_xml_list)} strings for unique title search.")

    results = parse_sru_results(bib_xml_list, target_normalized)

    if not any(r["mms_id"] == mms_id for r in results):
        try:
            results.insert(0, build_fallback_entry(mms_id, marcxml_data, target_normalized))
        except Exception as e:
            LOG.error(f"Error building fallback entry for searched MMS ID {mms_id}: {e}")

    results.sort(
        key=lambda x: (
            0 if x["mms_id"] == mms_id else 1,
            1 if not x["uniform_title"] else 0,
            x["uniform_title"].lower() if x["uniform_title"] else "",
            x["title"].lower() if x["title"] else "",
        )
    )

    print_results(results)


if __name__ == "__main__":
    main()
