"""
ebook_batch_workflow.py

Standalone batch workflow for importing eBook records from OCLC WorldCat into
Ex Libris Alma, with electronic portfolio creation.

This is a self-contained version: all shared OCLC helper modules (token
manager, search/retrieve service, and MARC country-code map) are inlined
below so the script has no local package dependencies beyond the third-party
libraries listed in requirements.txt.

Steps for each eISBN in the input spreadsheet:
  1. Check Alma via SRU — if already present, record "Already in Alma" + MMS ID.
  2. If not in Alma, search OCLC for the best English-cataloged record whose
     020 $a matches the eISBN.
  3. Normalize the MARCXML and push the bib to Alma via the REST API.
  4. Create an electronic portfolio linked to the new bib.
  5. Write all results (MMS ID, portfolio ID) to an output Excel file.

Configuration is provided entirely through environment variables (see
.env.example / README.md) — no institution-specific values or credentials
are hardcoded in this file.
"""

import datetime
import os
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Optional

import requests
import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

# ---------------------------------------------------------------------------
# Optional .env loader (avoids a python-dotenv dependency). If a .env file
# exists next to this script, load KEY=VALUE pairs into os.environ for any
# keys not already set in the real environment.
# ---------------------------------------------------------------------------
def _load_dotenv() -> None:
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
    except Exception as e:
        print(f"Warning: could not read .env file: {e}")


_load_dotenv()

# ===========================================================================
# Shared constants (originally src/shared/constants.py)
# ===========================================================================
OCLC_API_BASE_URL = "https://metadata.api.oclc.org/worldcat"
OCLC_OAUTH_URL = "https://oauth.oclc.org/token"
OCLC_OAUTH_SCOPE = "WorldCatMetadataAPI"
BATCH_SIZE = 100

SEARCH_FIELD_MAPPING = {
    "ti": "ti",
    "au": "au",
    "se": "se",
    "pu": "pu",
    "pb": "pb",
    "yr": "yr",
    "su": "su",
    "is": "is",
    "bn": "bn",
    "kw": "kw",
}

DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}

# ===========================================================================
# Shared MARC country-code map (originally src/shared/marc_country_mapping.py)
# ===========================================================================
MARC_COUNTRY_MAP = {
    "af": "Afghanistan", "alu": "United States", "aku": "United States",
    "aa": "Albania", "abc": "Canada", "ae": "Algeria", "as": "American Samoa",
    "an": "Andorra", "ao": "Angola", "am": "Anguilla", "ay": "Antarctica",
    "aq": "Antigua and Barbuda", "ag": "Argentina", "azu": "United States",
    "aru": "United States", "ai": "Armenia (Republic)", "aw": "Aruba",
    "at": "Australia", "aca": "Australia", "au": "Austria", "aj": "Azerbaijan",
    "bf": "Bahamas", "ba": "Bahrain", "bg": "Bangladesh", "bb": "Barbados",
    "bw": "Belarus", "be": "Belgium", "bh": "Belize", "dm": "Benin",
    "bm": "Bermuda Islands", "bt": "Bhutan", "bo": "Bolivia",
    "bn": "Bosnia and Herzegovina", "bs": "Botswana", "bv": "Bouvet Island",
    "bl": "Brazil", "bcc": "Canada", "bi": "British Indian Ocean Territory",
    "vb": "British Virgin Islands", "bx": "Brunei", "bu": "Bulgaria",
    "uv": "Burkina Faso", "br": "Burma", "bd": "Burundi",
    "cau": "United States", "cb": "Cambodia", "cm": "Cameroon",
    "xxc": "Canada", "cv": "Cabo Verde", "ca": "Caribbean Netherlands",
    "cj": "Cayman Islands", "cx": "Central African Republic", "cd": "Chad",
    "cl": "Chile", "cc": "China", "ch": "China (Republic : 1949- )",
    "xa": "Christmas Island (Indian Ocean)", "xb": "Cocos (Keeling) Islands",
    "ck": "Colombia", "cou": "United States", "cq": "Comoros",
    "cf": "Congo (Brazzaville)", "cg": "Congo (Democratic Republic)",
    "ctu": "United States", "cw": "Cook Islands", "xga": "Australia",
    "cr": "Costa Rica", "iv": "Côte d'Ivoire", "ci": "Croatia", "cu": "Cuba",
    "co": "Curaçao", "cy": "Cyprus", "xr": "Czech Republic",
    "deu": "United States", "dk": "Denmark", "dcu": "United States",
    "ft": "Djibouti", "dq": "Dominica", "dr": "Dominican Republic",
    "ec": "Ecuador", "ua": "Egypt", "es": "El Salvador", "enk": "England",
    "eg": "Equatorial Guinea", "ea": "Eritrea", "er": "Estonia",
    "sq": "Eswatini", "et": "Ethiopia", "fk": "Falkland Islands",
    "fa": "Faroe Islands", "fj": "Fiji", "fi": "Finland",
    "flu": "United States", "fr": "France", "fg": "French Guiana",
    "fp": "French Polynesia", "go": "Gabon", "gm": "Gambia", "gz": "Gaza Strip",
    "gau": "United States", "gs": "Georgia (Republic)", "gw": "Germany",
    "gh": "Ghana", "gi": "Gibraltar", "gr": "Greece", "gl": "Greenland",
    "gd": "Grenada", "gp": "Guadeloupe", "gu": "Guam", "gt": "Guatemala",
    "gg": "Guernsey", "gv": "Guinea", "pg": "Guinea-Bissau", "gy": "Guyana",
    "ht": "Haiti", "hiu": "United States",
    "hm": "Heard and McDonald Islands", "ho": "Honduras", "hu": "Hungary",
    "ic": "Iceland", "idu": "United States", "ilu": "United States",
    "ii": "India", "inu": "United States", "io": "Indonesia",
    "iau": "United States", "ir": "Iran", "iq": "Iraq",
    "iy": "Iraq-Saudi Arabia Neutral Zone", "ie": "Ireland",
    "im": "Isle of Man", "is": "Israel", "it": "Italy", "jm": "Jamaica",
    "ja": "Japan", "je": "Jersey", "ji": "Johnston Atoll", "jo": "Jordan",
    "ksu": "United States", "kz": "Kazakhstan", "kyu": "United States",
    "ke": "Kenya", "gb": "Kiribati", "kn": "Korea (North)",
    "ko": "Korea (South)", "kv": "Kosovo", "ku": "Kuwait", "kg": "Kyrgyzstan",
    "ls": "Laos", "lv": "Latvia", "le": "Lebanon", "lo": "Lesotho",
    "lb": "Liberia", "ly": "Libya", "lh": "Liechtenstein", "li": "Lithuania",
    "lau": "United States", "lu": "Luxembourg", "mg": "Madagascar",
    "meu": "United States", "mw": "Malawi", "my": "Malaysia",
    "xc": "Maldives", "ml": "Mali", "mm": "Malta", "mbc": "Canada",
    "xe": "Marshall Islands", "mq": "Martinique", "mdu": "United States",
    "mau": "United States", "mu": "Mauritania", "mf": "Mauritius",
    "ot": "Mayotte", "mx": "Mexico", "miu": "United States",
    "fm": "Micronesia (Federated States)", "xf": "Midway Islands",
    "mnu": "United States", "msu": "United States", "mou": "United States",
    "mv": "Moldova", "mc": "Monaco", "mp": "Mongolia", "mtu": "United States",
    "mo": "Montenegro", "mj": "Montserrat", "mr": "Morocco", "mz": "Mozambique",
    "sx": "Namibia", "nu": "Nauru", "nbu": "United States", "np": "Nepal",
    "ne": "Netherlands", "nvu": "United States", "nkc": "Canada",
    "nl": "New Caledonia", "nhu": "United States", "nju": "United States",
    "nmu": "United States", "xna": "Australia", "nyu": "United States",
    "nz": "New Zealand", "nfc": "Canada", "nq": "Nicaragua", "ng": "Niger",
    "nr": "Nigeria", "xh": "Niue",
    "xx": "No place, unknown, or undetermined", "nx": "Norfolk Island",
    "ncu": "United States", "ndu": "United States", "xn": "North Macedonia",
    "nik": "Northern Ireland", "nw": "Northern Mariana Islands",
    "xoa": "Australia", "ntc": "Canada", "no": "Norway", "nsc": "Canada",
    "nuc": "Canada", "ohu": "United States", "oku": "United States",
    "mk": "Oman", "onc": "Canada", "oru": "United States", "pk": "Pakistan",
    "pw": "Palau", "pn": "Panama", "pp": "Papua New Guinea",
    "pf": "Paracel Islands]", "py": "Paraguay", "pau": "United States",
    "pe": "Peru", "ph": "Philippines", "pc": "Pitcairn Island", "pl": "Poland",
    "po": "Portugal", "pic": "Canada", "pr": "Puerto Rico", "qa": "Qatar",
    "quc": "Canada", "qea": "Australia", "re": "Réunion",
    "riu": "United States", "rm": "Romania", "ru": "Russia (Federation)",
    "rw": "Rwanda", "sc": "Saint-Barthélemy", "xj": "Saint Helena",
    "xd": "Saint Kitts-Nevis", "xk": "Saint Lucia", "st": "Saint-Martin",
    "xl": "Saint Pierre and Miquelon",
    "xm": "Saint Vincent and the Grenadines", "ws": "Samoa", "sm": "San Marino",
    "sf": "Sao Tome and Principe", "snc": "Canada", "su": "Saudi Arabia",
    "stk": "Scotland", "sg": "Senegal", "rb": "Serbia", "se": "Seychelles",
    "sl": "Sierra Leone", "si": "Singapore", "sn": "Sint Maarten",
    "xo": "Slovakia", "xv": "Slovenia", "bp": "Solomon Islands",
    "so": "Somalia", "sa": "South Africa", "xra": "Australia",
    "scu": "United States", "sdu": "United States",
    "xs": "South Georgia and the South Sandwich Islands", "sd": "South Sudan",
    "sp": "Spain", "sh": "Spanish North Africa", "xp": "Spratly Island",
    "ce": "Sri Lanka", "sj": "Sudan", "sr": "Surinam", "sw": "Sweden",
    "sz": "Switzerland", "sy": "Syria", "ta": "Tajikistan", "tz": "Tanzania",
    "tma": "Australia", "tnu": "United States",
    "fs": "Terres australes et antarctiques françaises",
    "txu": "United States", "th": "Thailand", "em": "Timor-Leste",
    "tg": "Togo", "tl": "Tokelau", "to": "Tonga",
    "tr": "Trinidad and Tobago", "ti": "Tunisia", "tu": "Turkey",
    "tk": "Turkmenistan", "tc": "Turks and Caicos Islands", "tv": "Tuvalu",
    "ug": "Uganda", "un": "Ukraine", "ts": "United Arab Emirates",
    "xxk": "United Kingdom", "xxu": "United States",
    "uc": "United States Misc. Caribbean Islands",
    "up": "United States Misc. Pacific Islands", "uy": "Uruguay",
    "utu": "United States", "uz": "Uzbekistan", "nn": "Vanuatu",
    "vp": "Various places", "vc": "Vatican City", "ve": "Venezuela",
    "vtu": "United States", "vra": "Australia", "vm": "Vietnam",
    "vi": "Virgin Islands of the United States", "vau": "United States",
    "wk": "Wake Island", "wlk": "Wales", "wf": "Wallis and Futuna",
    "wau": "United States", "wj": "West Bank of the Jordan River",
    "wvu": "United States", "wea": "Australia", "ss": "Western Sahara",
    "wiu": "United States", "wyu": "United States", "ye": "Yemen",
    "ykc": "Canada", "za": "Zambia", "rh": "Zimbabwe",
}

# ===========================================================================
# OCLC OAuth2 token manager (originally src/shared/oclc_token_manager.py)
# ===========================================================================
_TOKEN_CACHE: Optional[tuple[str, float]] = None
_BUFFER_SECONDS = 5 * 60  # refresh 5 minutes before expiry


class OCLCTokenManager:
    """Manages an OCLC OAuth2 client_credentials token with caching and retries.

    Credentials are read from the OCLC_WSKEY / OCLC_SECRET environment
    variables. As a fallback, set OCLC_KEY_FILE to a text file containing
    lines like:
        oclc_wskey=your_key
        oclc_secret=your_secret
    """

    def __init__(self) -> None:
        self._wskey = os.environ.get("OCLC_WSKEY", "")
        self._secret = os.environ.get("OCLC_SECRET", "")
        self._max_retries = 3
        self._backoff_base = 1.0

        if not (self._wskey and self._secret):
            key_file = os.environ.get("OCLC_KEY_FILE", "")
            if key_file and os.path.exists(key_file):
                self._load_from_file(key_file)

    def _load_from_file(self, path: str) -> None:
        for encoding in ("utf-8", "utf-16"):
            try:
                with open(path, encoding=encoding) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("oclc_wskey"):
                            parts = line.split("=", 1)
                            if len(parts) == 2:
                                self._wskey = parts[1].strip().strip("\"'+")
                        elif line.startswith("oclc_secret"):
                            parts = line.split("=", 1)
                            if len(parts) == 2:
                                self._secret = parts[1].strip().strip("\"'+")
                if self._wskey and self._secret:
                    return
            except UnicodeError:
                continue
            except Exception as e:
                print(f"Could not read OCLC credentials file {path}: {e}")
                return

    def can_make_request(self) -> bool:
        """Return True if credentials are configured."""
        return bool(self._wskey and self._secret)

    def get_shared_token(self) -> Optional[str]:
        """Obtain a shared client_credentials token, caching it with a 5-minute
        refresh buffer, and retrying with backoff on transient failures."""
        global _TOKEN_CACHE
        now = time.time()
        if _TOKEN_CACHE is not None:
            token, expires_at = _TOKEN_CACHE
            if expires_at > now + _BUFFER_SECONDS:
                return token
            _TOKEN_CACHE = None

        data = {"grant_type": "client_credentials", "scope": OCLC_OAUTH_SCOPE}
        auth = (self._wskey, self._secret)
        last_error: Optional[Exception] = None
        for attempt in range(self._max_retries):
            try:
                resp = requests.post(
                    OCLC_OAUTH_URL,
                    data=data,
                    auth=auth,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=15,
                )
                resp.raise_for_status()
                body = resp.json()
                access_token = body.get("access_token")
                expires_in = int(body.get("expires_in", 3600))
                if not access_token:
                    return None
                expires_at = now + expires_in
                _TOKEN_CACHE = (access_token, expires_at)
                return access_token
            except requests.RequestException as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    time.sleep(self._backoff_base * (2 ** attempt))
        raise last_error or RuntimeError("Failed to obtain OCLC token")


# ===========================================================================
# OCLC WorldCat Metadata API service (originally src/shared/oclc_service.py)
# ===========================================================================
class OCLCService:
    """Service for WorldCat Metadata API search and bib retrieval."""

    def __init__(self, oclc_token_manager: "OCLCTokenManager") -> None:
        self._token_manager = oclc_token_manager
        self._session = requests.Session()

    def _auth_headers(self) -> dict[str, str]:
        token = self._token_manager.get_shared_token()
        h = dict(DEFAULT_HEADERS)
        h["Authorization"] = f"Bearer {token}"
        return h

    def batch_search(
        self,
        books: list[dict[str, Any]],
        append_query: Optional[str] = None,
        sorting_order: Optional[str] = None,
        is_refining: Optional[bool] = None,
    ) -> tuple[list[dict[str, Any]], Optional[int]]:
        """Call the WorldCat Metadata API search/brief-bibs endpoint."""
        base = OCLC_API_BASE_URL.rstrip("/")
        url = f"{base}/search/brief-bibs"
        all_results: list[dict[str, Any]] = []
        usage_remaining: Optional[int] = None

        for i in range(0, len(books), BATCH_SIZE):
            chunk = books[i : i + BATCH_SIZE]
            q_parts = []
            for book in chunk:
                for field, mapped in SEARCH_FIELD_MAPPING.items():
                    val = book.get(field) or book.get(mapped)
                    if val:
                        q_parts.append(f"{mapped}:{val}")
                        break
            q = " OR ".join(q_parts) if q_parts else ""
            if append_query:
                q = f"({q}) AND ({append_query})" if q else append_query
            params: dict[str, Any] = {"q": q} if q else {}
            if sorting_order is not None:
                params["orderBy"] = sorting_order
            if is_refining is not None:
                params["isRefining"] = str(is_refining).lower()

            resp = self._session.get(
                url, params=params, headers=self._auth_headers(), timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            brief_records = data.get("briefRecords") or data.get("briefBibs") or []
            if isinstance(brief_records, list):
                all_results.extend(brief_records)
            else:
                all_results.append(brief_records)
            rem = resp.headers.get("X-Usage-Remaining") or resp.headers.get("Usage-Remaining")
            if rem is not None:
                try:
                    usage_remaining = int(rem)
                except ValueError:
                    pass

        return all_results, usage_remaining

    def generate_xml(self, oclc_numbers: list[str], format_type: str = "marcxml") -> str:
        """Call manage/bibs/{oclc_number} and return MARC/MARCXML text."""
        base = OCLC_API_BASE_URL.rstrip("/")
        accept = "application/marcxml+xml" if format_type == "marcxml" else "application/marc"
        headers = self._auth_headers()
        headers["Accept"] = accept
        parts: list[str] = []
        for oclc_number in oclc_numbers:
            url = f"{base}/manage/bibs/{oclc_number}"
            try:
                resp = self._session.get(url, headers=headers, timeout=30)
                resp.raise_for_status()
                ct = resp.headers.get("Content-Type", "")
                if "xml" in ct or "marc" in ct:
                    text = resp.text if hasattr(resp, "text") else resp.content.decode("utf-8", errors="replace")
                    parts.append(text)
            except requests.RequestException:
                continue
        return "\n".join(parts)


# ===========================================================================
# Configuration — everything institution/credential-specific comes from the
# environment (see .env.example / README.md). Nothing personal is hardcoded.
# ===========================================================================
INPUT_XLSX = os.environ.get(
    "INPUT_XLSX",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "input.xlsx"),
)

ALMA_API_KEY = os.environ.get("ALMA_API_KEY", "")
ALMA_API_KEY_FILE = os.environ.get("ALMA_API_KEY_FILE", "")
ALMA_KEY_NAME = os.environ.get("ALMA_KEY_NAME", "alma_api_key")

# Alma REST API (bibs) and SRU base URLs — these are institution-specific.
ALMA_API_BASE = os.environ.get("ALMA_API_BASE", "")
ALMA_SRU_URL = os.environ.get("ALMA_SRU_URL", "")
ALMA_ECOLLECTIONS_BASE = os.environ.get(
    "ALMA_ECOLLECTIONS_BASE",
    "https://api-na.hosted.exlibrisgroup.com/almaws/v1/electronic/e-collections",
)

# Electronic portfolio settings — set these to the e-collection/e-service you
# want new portfolios attached to.
PORTFOLIO_ECOLL_ID = os.environ.get("PORTFOLIO_ECOLL_ID", "")
PORTFOLIO_ESVC_ID = os.environ.get("PORTFOLIO_ESVC_ID", "")
PORTFOLIO_LICENSE = os.environ.get("PORTFOLIO_LICENSE", "")
PORTFOLIO_ACTIVATION_DATE = os.environ.get("PORTFOLIO_ACTIVATION_DATE", "")
PORTFOLIO_LIBRARY = os.environ.get("PORTFOLIO_LIBRARY", "")

# Number of rows to process per run (unset / empty = process all)
_process_limit_env = os.environ.get("PROCESS_LIMIT", "")
PROCESS_LIMIT = int(_process_limit_env) if _process_limit_env.strip() else None

# Delay (seconds) between OCLC API calls to stay within rate limits
OCLC_REQUEST_DELAY = float(os.environ.get("OCLC_REQUEST_DELAY", "0.5"))


def _require_config(name: str, value: str) -> None:
    if not value:
        raise SystemExit(
            f"ERROR: required configuration '{name}' is not set. "
            f"Set it as an environment variable or in a .env file — see .env.example."
        )


# ---------------------------------------------------------------------------
# Helper: load Alma API key
# ---------------------------------------------------------------------------
def load_alma_key() -> str:
    if ALMA_API_KEY:
        return ALMA_API_KEY
    if ALMA_API_KEY_FILE and os.path.exists(ALMA_API_KEY_FILE):
        try:
            with open(ALMA_API_KEY_FILE) as f:
                for line in f:
                    if line.strip().startswith(ALMA_KEY_NAME):
                        parts = line.split("=", 1)
                        if len(parts) > 1:
                            return parts[1].strip().strip("\"'+")
        except Exception as e:
            print(f"Could not read Alma API key file: {e}")
    return ""


# ---------------------------------------------------------------------------
# Helper: check Alma via SRU for an ISBN
# Returns (found: bool, mms_id: str, record_count: int, url_856: str)
# ---------------------------------------------------------------------------
def check_alma_sru(isbn: str) -> tuple[bool, str, int, str]:
    params = {
        "version": "1.2",
        "operation": "searchRetrieve",
        "recordSchema": "marcxml",
        "query": f'alma.isbn="{isbn}"',
    }
    try:
        resp = requests.get(ALMA_SRU_URL, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"  Alma SRU returned HTTP {resp.status_code} for ISBN {isbn}")
            return False, "", 0, ""

        root = ET.fromstring(resp.content)
        ns = {"srw": "http://www.loc.gov/zing/srw/"}
        num_elem = root.find(".//srw:numberOfRecords", ns)
        if num_elem is None or not (num_elem.text or "").isdigit():
            return False, "", 0, ""

        count = int(num_elem.text)
        if count == 0:
            return False, "", 0, ""

        # Extract MMS ID from the first record's srw:recordIdentifier (Alma
        # puts the MMS ID there), or fall back to the MARC 001 control field.
        mms_id = ""
        rec_id_elem = root.find(".//srw:recordIdentifier", ns)
        if rec_id_elem is not None and rec_id_elem.text:
            mms_id = rec_id_elem.text.strip()

        if not mms_id:
            cf001 = root.find(".//{http://www.loc.gov/MARC21/slim}controlfield[@tag='001']")
            if cf001 is not None and cf001.text:
                mms_id = cf001.text.strip()

        # Extract 856 $u from the first MARCXML record in the SRU response
        url_856 = ""
        marc_ns = "http://www.loc.gov/MARC21/slim"
        for df in root.findall(f".//{{{marc_ns}}}datafield[@tag='856']"):
            sf_u = df.find(f"{{{marc_ns}}}subfield[@code='u']")
            if sf_u is not None and sf_u.text:
                url_856 = sf_u.text.strip()
                break

        return True, mms_id, count, url_856

    except Exception as e:
        print(f"  Error querying Alma SRU for ISBN {isbn}: {e}")
        return False, "", 0, ""


# ---------------------------------------------------------------------------
# Helper: score an OCLC brief-bib record
# ---------------------------------------------------------------------------
def score_record(rec: dict) -> int:
    score = 0
    cat_info = rec.get("catalogingInfo", {})
    lvl = cat_info.get("levelOfCataloging", "")
    agency = cat_info.get("catalogingAgency", "")

    if lvl in [" ", "I", "L", "M", "1"]:
        score += 100
    elif lvl == "8":
        score += 80

    if agency in ["DLC", "NLC", "NLM", "BL"]:
        score += 50

    return score


def sort_key(rec: dict) -> tuple[int, int]:
    s = score_record(rec)
    try:
        n = int(rec.get("oclcNumber", "999999999999999"))
    except ValueError:
        n = 999999999999999
    return (s, -n)


# ---------------------------------------------------------------------------
# Helper: search OCLC and return the best record dict, or None
# Returns dict with keys: oclc_number, title, author, score, encoding_level,
#                         agency, field_count, marcxml
# ---------------------------------------------------------------------------
def find_best_oclc_record(isbn: str, service: OCLCService) -> Optional[dict]:
    try:
        results, _ = service.batch_search([{}], append_query=f"bn:{isbn}")
    except Exception as e:
        print(f"  OCLC search error for ISBN {isbn}: {e}")
        return None

    # Filter for English-cataloged records only
    eng_results = [
        r for r in results
        if r.get("catalogingInfo", {}).get("catalogingLanguage") == "eng"
    ]

    if not eng_results:
        return None

    eng_results.sort(key=sort_key, reverse=True)

    found_matches = []
    best_score_found = -1

    for rec in eng_results:
        candidate_oclc = rec.get("oclcNumber")
        if not candidate_oclc:
            continue

        current_score = score_record(rec)

        # Stop pulling XMLs once we have a valid match and score drops
        if found_matches and current_score < best_score_found:
            break

        time.sleep(OCLC_REQUEST_DELAY)
        candidate_xml = service.generate_xml([candidate_oclc], format_type="marcxml")
        if not candidate_xml:
            continue

        try:
            temp_root = ET.fromstring(candidate_xml)
            temp_record = temp_root.find(".//{http://www.loc.gov/MARC21/slim}record")
            if temp_record is None:
                temp_record = temp_root.find(".//record")
            if temp_record is None:
                temp_record = temp_root

            match_found = False
            for f in list(temp_record):
                if f.tag.endswith("datafield") and f.get("tag") == "020":
                    for s in list(f):
                        if s.tag.endswith("subfield") and s.get("code") == "a" and s.text:
                            clean_val = s.text.split(" ")[0].strip()
                            if clean_val == isbn:
                                match_found = True
                                break
                if match_found:
                    break

            if match_found:
                best_score_found = current_score
                marc_field_count = len(list(temp_record))
                found_matches.append(
                    {
                        "rec": rec,
                        "xml": candidate_xml,
                        "field_count": marc_field_count,
                        "score": current_score,
                    }
                )
                if current_score >= 80:
                    break
                if len(found_matches) >= 5:
                    break
            else:
                print(f"    Skipping OCLC {candidate_oclc} — ISBN not in 020 $a")
        except Exception as e:
            print(f"    Error parsing XML for OCLC {candidate_oclc}: {e}")
            continue

    if not found_matches:
        return None

    # Sort valid matches by field count descending
    found_matches.sort(key=lambda x: x["field_count"], reverse=True)
    best = found_matches[0]
    best_rec = best["rec"]

    cat_info = best_rec.get("catalogingInfo", {})
    encoding_level = cat_info.get("levelOfCataloging", "")
    if encoding_level == " ":
        encoding_level = "Full"

    return {
        "oclc_number": best_rec.get("oclcNumber", ""),
        "title": best_rec.get("title", ""),
        "author": best_rec.get("author", ""),
        "score": best["score"],
        "encoding_level": encoding_level,
        "agency": cat_info.get("catalogingAgency", ""),
        "field_count": best["field_count"],
        "marcxml": best["xml"],
    }


# ---------------------------------------------------------------------------
# Helpers: MARC normalization, DOI extraction, Alma bib + portfolio creation
# ---------------------------------------------------------------------------
def extract_doi_from_marc(record_elem) -> str:
    """Extract a DOI (10.xxxx/...) from an 856 $u field in a MARC record.
    Returns empty string if not found."""
    for field in record_elem:
        if field.get("tag") == "856":
            for sf in field:
                if sf.get("code") == "u" and sf.text:
                    m = re.search(r"10\.\d{4,9}/[^\s\"'<>]+", sf.text)
                    if m:
                        return m.group(0)
    return ""


def extract_856_url_from_marc(record_elem) -> str:
    """Return the full URL from the first 856 $u in a MARC record."""
    for field in record_elem:
        if field.get("tag") == "856":
            for sf in field:
                if sf.get("code") == "u" and sf.text:
                    return sf.text.strip()
    return ""


def normalize_marcxml(marcxml_str: str, isbn: str) -> str:
    """Apply local Alma normalization rules to a raw MARCXML string.
    Returns the wrapped <bib>...</bib> XML string ready to POST to Alma.

    The specific tags removed/relocated below reflect one institution's
    cataloging conventions — adjust tags_to_remove / tags_to_950 and the
    locally-defined fields (911/992/993-999) to match your own conventions.
    """
    tags_to_remove = [
        "012", "016", "029", "037", "049", "051", "060", "096",
        "265", "380", "386", "541", "561", "562", "563",
        "752", "758", "776", "850", "886", "887",
        "891", "938", "948", "994",
    ]
    tags_to_950 = [
        "600", "610", "611", "630", "647", "648",
        "650", "651", "653", "654", "655", "656",
        "657", "658", "662", "688",
    ]
    seen_035 = set()

    ET.register_namespace("", "http://www.loc.gov/MARC21/slim")
    root = ET.fromstring(marcxml_str)
    record = root.find(".//{http://www.loc.gov/MARC21/slim}record")
    if record is None:
        record = root.find(".//record")
    if record is None:
        record = root

    for field in list(record):
        tag = field.get("tag")
        if not tag:
            continue

        # Normalize 001 — strip ocm/ocn/on prefix so Alma doesn't create a duplicate 035
        if tag == "001" and field.text:
            text = field.text.strip()
            for prefix in ("ocm", "ocn", "on"):
                if text.startswith(prefix):
                    text = text[len(prefix):]
                    break
            field.text = text

        if tag in tags_to_remove:
            record.remove(field)
            continue

        if tag in tags_to_950:
            field.set("tag", "950")
            continue

        if tag == "035":
            # Remove 035 with (OCoLC)ocn / (OCoLC)ocm / (OCoLC)on prefix in $a
            remove_flag = False
            for sf in list(field):
                if sf.get("code") == "a" and sf.text:
                    t = sf.text.strip()
                    if t.startswith("(OCoLC)ocn") or t.startswith("(OCoLC)ocm") or t.startswith("(OCoLC)on"):
                        remove_flag = True
                        break
            if remove_flag:
                record.remove(field)
                continue

            # Reorder subfields: 9, a, z, others
            subfields = list(field)
            for sf in subfields:
                field.remove(sf)
            sf9, sfa, sfz, sfo = [], [], [], []
            for sf in subfields:
                c = sf.get("code")
                if c == "9":
                    sf9.append(sf)
                elif c == "a":
                    sfa.append(sf)
                elif c == "z":
                    sfz.append(sf)
                else:
                    sfo.append(sf)
            for sf in sf9 + sfa + sfz + sfo:
                field.append(sf)

            # Deduplicate
            field_str = ET.tostring(field, encoding="unicode")
            if field_str in seen_035:
                record.remove(field)
            else:
                seen_035.add(field_str)

    # Build 041 / 044 from 008
    lang_code = country_code = None
    for elem in record:
        if elem.get("tag") == "008" and elem.text and len(elem.text) >= 38:
            country_code = elem.text[15:18].strip().lower()
            lang_code = elem.text[35:38].strip().lower()
            break

    if lang_code and not any(f.get("tag") == "041" for f in record):
        new_041 = ET.Element("datafield", {"ind1": "0", "ind2": " ", "tag": "041"})
        ET.SubElement(new_041, "subfield", {"code": "a"}).text = lang_code
        record.append(new_041)

    if country_code and not any(f.get("tag") == "044" for f in record):
        full_country = MARC_COUNTRY_MAP.get(country_code, "")
        if not full_country and len(country_code) == 3:
            if country_code.endswith("u"):
                full_country = "United States"
            elif country_code.endswith("c"):
                full_country = "Canada"
            elif country_code.endswith("a"):
                full_country = "Australia"
        if full_country:
            new_044 = ET.Element("datafield", {"ind1": " ", "ind2": " ", "tag": "044"})
            ET.SubElement(new_044, "subfield", {"code": "9"}).text = full_country
            record.append(new_044)

    date_str = datetime.datetime.now().strftime("%Y%m%d")

    new_911 = ET.Element("datafield", {"ind1": " ", "ind2": " ", "tag": "911"})
    ET.SubElement(new_911, "subfield", {"code": "a"}).text = "Electronic only"
    record.append(new_911)

    new_992 = ET.Element("datafield", {"ind1": " ", "ind2": " ", "tag": "992"})
    ET.SubElement(new_992, "subfield", {"code": "p"}).text = "Px"
    ET.SubElement(new_992, "subfield", {"code": "e"}).text = "EF"
    ET.SubElement(new_992, "subfield", {"code": "a"}).text = date_str
    record.append(new_992)

    for tag in ["993", "994", "995", "996"]:
        el = ET.Element("datafield", {"ind1": " ", "ind2": " ", "tag": tag})
        ET.SubElement(el, "subfield", {"code": "a"}).text = "[CAT ONLY]"
        ET.SubElement(el, "subfield", {"code": "b"}).text = date_str
        record.append(el)

    new_997 = ET.Element("datafield", {"ind1": " ", "ind2": " ", "tag": "997"})
    ET.SubElement(new_997, "subfield", {"code": "a"}).text = "[CAT ONLY]"
    record.append(new_997)

    new_998 = ET.Element("datafield", {"ind1": " ", "ind2": " ", "tag": "998"})
    ET.SubElement(new_998, "subfield", {"code": "a"}).text = f"ERMSLC {PORTFOLIO_LICENSE}".strip()
    ET.SubElement(new_998, "subfield", {"code": "b"}).text = date_str
    record.append(new_998)

    new_999 = ET.Element("datafield", {"ind1": " ", "ind2": " ", "tag": "999"})
    ET.SubElement(new_999, "subfield", {"code": "a"}).text = "WTC"
    record.append(new_999)

    # Sort fields numerically by tag (leader sorts first)
    def _sort_key(elem):
        return "0000" if "leader" in elem.tag.lower() else elem.get("tag", "ZZZZ")

    sorted_elems = sorted(list(record), key=_sort_key)
    for elem in list(record):
        record.remove(elem)
    for elem in sorted_elems:
        record.append(elem)

    return (
        "<bib>"
        "<suppress_from_publishing>false</suppress_from_publishing>"
        "<suppress_from_external_search>false</suppress_from_external_search>"
        + ET.tostring(record, encoding="unicode")
        + "</bib>"
    )


def create_alma_bib(normalized_xml: str, alma_key: str) -> tuple[str, str]:
    """POST normalized MARCXML to Alma. Returns (mms_id, error_message)."""
    headers = {
        "Accept": "application/xml",
        "Content-Type": "application/xml",
        "Authorization": f"apikey {alma_key}",
    }
    try:
        resp = requests.post(
            ALMA_API_BASE, headers=headers, data=normalized_xml.encode("utf-8"), timeout=30
        )
        if resp.status_code in (200, 201):
            resp_xml = ET.fromstring(resp.content)
            mms_id = resp_xml.findtext(".//mms_id") or ""
            return mms_id, ""
        return "", f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return "", str(e)


def create_alma_portfolio(mms_id: str, title: str, doi: str, alma_key: str) -> tuple[str, str]:
    """Create an electronic portfolio for the bib. Returns (portfolio_id, error_message)."""
    bkey_val = f"bkey={doi}" if doi else ""

    portfolio_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<portfolio>
    <is_local>true</is_local>
    <is_standalone>false</is_standalone>
    <material_type>BOOK</material_type>
    <library>{PORTFOLIO_LIBRARY}</library>
    <resource_metadata>
        <title>{title}</title>
        <mms_id>{mms_id}</mms_id>
    </resource_metadata>
    <electronic_collection>
        <id>{PORTFOLIO_ECOLL_ID}</id>
        <service>{PORTFOLIO_ESVC_ID}</service>
    </electronic_collection>
    <availability>11</availability>
    <linking_details>
        <url_type_override>param</url_type_override>
        <parser_parameters_override>{bkey_val}</parser_parameters_override>
        <proxy_enabled>false</proxy_enabled>
    </linking_details>
    <license>{PORTFOLIO_LICENSE}</license>
    <activation_date>{PORTFOLIO_ACTIVATION_DATE}</activation_date>
</portfolio>"""

    headers = {
        "Content-Type": "application/xml",
        "Authorization": f"apikey {alma_key}",
    }
    url = f"{ALMA_API_BASE}/{mms_id}/portfolios"

    try:
        resp = requests.post(url, data=portfolio_xml.encode("utf-8"), headers=headers, timeout=30)
        if resp.status_code in (200, 201):
            try:
                root = ET.fromstring(resp.text)
                id_elem = root.find(".//id")
                if id_elem is not None and id_elem.text:
                    return id_elem.text.strip(), ""
                link_elem = root.find(".//link")
                if link_elem is not None and link_elem.text:
                    return link_elem.text.strip().split("/")[-1], ""
            except Exception:
                pass
            return "created", ""
        return "", f"HTTP {resp.status_code}: {resp.text[:300]}"
    except Exception as e:
        return "", str(e)


def ensure_service_parser(alma_key: str, parser_name: str, parser_url: str) -> None:
    """Ensure the target e-service has the expected parser/parser_parameters.
    Safe to call on every run — only PUTs if a change is needed.
    Set PARSER_NAME / PARSER_URL env vars to control the desired values, or
    leave them unset to skip this step entirely."""
    if not parser_name or not parser_url:
        return

    url = f"{ALMA_ECOLLECTIONS_BASE}/{PORTFOLIO_ECOLL_ID}/e-services/{PORTFOLIO_ESVC_ID}"
    headers_xml = {
        "Accept": "application/xml",
        "Content-Type": "application/xml",
        "Authorization": f"apikey {alma_key}",
    }

    try:
        r = requests.get(
            url, headers={"Accept": "application/xml", "Authorization": f"apikey {alma_key}"}, timeout=30
        )
        if not r.ok:
            print(f"  Warning: could not verify service parser (HTTP {r.status_code})")
            return

        root = ET.fromstring(r.content)
        parser_elem = root.find("parser")
        params_elem = root.find("parser_parameters")
        current_parser = (parser_elem.text or "").strip() if parser_elem is not None else ""
        current_params = (params_elem.text or "").strip() if params_elem is not None else ""

        if current_parser == parser_name and current_params == parser_url:
            print("  Service parser already configured.")
            return

        desired = {
            "parser": parser_name,
            "parser_override": parser_name,
            "parser_parameters": parser_url,
            "parser_parameters_override": parser_url,
        }
        for tag, value in desired.items():
            elem = root.find(tag)
            if elem is not None:
                elem.text = value
            else:
                ET.SubElement(root, tag).text = value

        put_body = ET.tostring(root, encoding="unicode")
        r2 = requests.put(url, data=put_body.encode("utf-8"), headers=headers_xml, timeout=30)
        if r2.ok:
            print(f"  Service parser set to {parser_name} with {parser_url}")
        else:
            print(f"  Warning: service parser update failed (HTTP {r2.status_code}): {r2.text[:200]}")

    except Exception as e:
        print(f"  Warning: could not update service parser: {e}")


# ---------------------------------------------------------------------------
# Write results spreadsheet
# ---------------------------------------------------------------------------
HEADER = [
    "No.",
    "Book Title",
    "Series",
    "Edition",
    "eISBN",
    "Status",
    "Alma MMS ID",
    "Alma Portfolio ID",
    "Alma 856 URL",
    "OCLC Number",
    "OCLC Title",
    "Score",
    "Encoding Level",
    "Cataloging Agency",
    "Notes",
]

STATUS_COLORS = {
    "Already in Alma": "FFF2CC",  # yellow
    "Created in Alma": "D9EAD3",  # green
    "Bib Created, No Portfolio": "C9DAF8",  # blue
    "Not Found in OCLC": "FCE5CD",  # orange
    "OCLC Error": "F4CCCC",  # red
}


def write_results(rows: list[dict], output_path: str) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Results"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="4472C4")
    for col, h in enumerate(HEADER, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    for row_idx, row in enumerate(rows, 2):
        status = row.get("status", "")
        fill_color = STATUS_COLORS.get(status, "FFFFFF")
        row_fill = PatternFill("solid", fgColor=fill_color)

        values = [
            row.get("no", ""),
            row.get("book_title", ""),
            row.get("series", ""),
            row.get("edition", ""),
            row.get("eisbn", ""),
            status,
            row.get("alma_mms_id", ""),
            row.get("alma_portfolio_id", ""),
            row.get("alma_856_url", ""),
            row.get("oclc_number", ""),
            row.get("oclc_title", ""),
            row.get("score", ""),
            row.get("encoding_level", ""),
            row.get("agency", ""),
            row.get("notes", ""),
        ]
        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col, value=val)
            cell.fill = row_fill

    col_widths = [6, 40, 30, 10, 18, 20, 20, 20, 50, 14, 40, 8, 16, 18, 40]
    for col, width in enumerate(col_widths, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = width

    ws.freeze_panes = "A2"
    wb.save(output_path)
    print(f"\nResults written to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 60)
    print("eBook Batch Workflow — OCLC to Alma")
    print(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # --- Validate required configuration up front ---
    _require_config("ALMA_API_BASE", ALMA_API_BASE)
    _require_config("ALMA_SRU_URL", ALMA_SRU_URL)
    _require_config("PORTFOLIO_ECOLL_ID", PORTFOLIO_ECOLL_ID)
    _require_config("PORTFOLIO_ESVC_ID", PORTFOLIO_ESVC_ID)
    _require_config("PORTFOLIO_LIBRARY", PORTFOLIO_LIBRARY)

    # --- Load Alma key ---
    alma_key = load_alma_key()
    if not alma_key:
        print("ERROR: Could not load Alma API key. Set ALMA_API_KEY or ALMA_API_KEY_FILE. Exiting.")
        return

    # --- Optionally ensure the e-service has the expected parser settings ---
    parser_name = os.environ.get("PARSER_NAME", "")
    parser_url = os.environ.get("PARSER_URL", "")
    if parser_name and parser_url:
        print("Checking e-service parser configuration...")
        ensure_service_parser(alma_key, parser_name, parser_url)

    # --- Load OCLC service ---
    try:
        token_mgr = OCLCTokenManager()
        if not token_mgr.can_make_request():
            print("ERROR: OCLC credentials not configured. Set OCLC_WSKEY/OCLC_SECRET or OCLC_KEY_FILE. Exiting.")
            return
        service = OCLCService(token_mgr)
    except Exception as e:
        print(f"ERROR initializing OCLC service: {e}")
        return

    # --- Read input spreadsheet ---
    if not os.path.exists(INPUT_XLSX):
        print(f"ERROR: Input file not found: {INPUT_XLSX}")
        return

    wb_in = openpyxl.load_workbook(INPUT_XLSX)
    ws_in = wb_in.active

    # Expected columns: No. | Book Title | Series Titles | Edition | eISBN | ...
    rows_to_process = []
    for row in ws_in.iter_rows(min_row=2, values_only=True):
        no, book_title, series, edition, eisbn, *_ = list(row) + [None] * 9
        if eisbn is None:
            continue
        rows_to_process.append(
            {
                "no": str(no) if no is not None else "",
                "book_title": str(book_title) if book_title else "",
                "series": str(series) if series else "",
                "edition": str(edition) if edition else "",
                "eisbn": str(int(eisbn)) if isinstance(eisbn, float) else str(eisbn),
            }
        )

    total = len(rows_to_process)
    if PROCESS_LIMIT is not None:
        rows_to_process = rows_to_process[:PROCESS_LIMIT]
        print(f"Loaded {total} eISBNs; processing first {len(rows_to_process)} (PROCESS_LIMIT={PROCESS_LIMIT}).\n")
    else:
        print(f"\nLoaded {total} eISBNs from spreadsheet.\n")

    results = []

    for i, book in enumerate(rows_to_process, 1):
        isbn = book["eisbn"]
        run_total = len(rows_to_process)
        print(f"[{i}/{run_total}] ISBN {isbn}  —  {book['book_title'][:50]}")

        result_row = dict(book)

        # --- Step 1: Check Alma ---
        found, mms_id, count, url_856 = check_alma_sru(isbn)

        if found:
            print(f"  → Already in Alma ({count} record(s), MMS ID: {mms_id or 'N/A'})")
            result_row.update(
                {
                    "status": "Already in Alma",
                    "alma_mms_id": mms_id,
                    "alma_portfolio_id": "",
                    "alma_856_url": url_856,
                    "oclc_number": "",
                    "oclc_title": "",
                    "score": "",
                    "encoding_level": "",
                    "agency": "",
                    "notes": f"{count} Alma record(s) found",
                }
            )
            results.append(result_row)
            continue

        print("  → Not in Alma. Searching OCLC...")
        time.sleep(OCLC_REQUEST_DELAY)

        # --- Step 2: Search OCLC ---
        best = find_best_oclc_record(isbn, service)

        if not best:
            print("  → No suitable OCLC record found.")
            result_row.update(
                {
                    "status": "Not Found in OCLC",
                    "alma_mms_id": "",
                    "alma_portfolio_id": "",
                    "alma_856_url": "",
                    "oclc_number": "",
                    "oclc_title": "",
                    "score": "",
                    "encoding_level": "",
                    "agency": "",
                    "notes": "No English-cataloged record with matching 020 $a found in OCLC",
                }
            )
            results.append(result_row)
            continue

        print(
            f"  → OCLC {best['oclc_number']} | Score {best['score']} | "
            f"Level: {best['encoding_level']} | Agency: {best['agency']}"
        )

        # --- Step 3: Extract DOI and 856 URL before normalization removes 856 ---
        try:
            raw_root = ET.fromstring(best["marcxml"])
            raw_record = raw_root.find(".//{http://www.loc.gov/MARC21/slim}record")
            if raw_record is None:
                raw_record = raw_root.find(".//record")
            if raw_record is None:
                raw_record = raw_root
            doi = extract_doi_from_marc(raw_record)
            url_856 = extract_856_url_from_marc(raw_record)
        except Exception:
            doi = ""
            url_856 = ""

        if doi:
            print(f"    DOI from MARC 856: {doi}")

        # --- Step 4: Normalize MARCXML ---
        try:
            normalized_xml = normalize_marcxml(best["marcxml"], isbn)
        except Exception as norm_err:
            print(f"  ! Normalization error: {norm_err}")
            result_row.update(
                {
                    "status": "OCLC Error",
                    "alma_mms_id": "",
                    "alma_portfolio_id": "",
                    "alma_856_url": url_856,
                    "oclc_number": best["oclc_number"],
                    "oclc_title": best["title"],
                    "score": best["score"],
                    "encoding_level": best["encoding_level"],
                    "agency": best["agency"],
                    "notes": f"Normalization failed: {norm_err}",
                }
            )
            results.append(result_row)
            continue

        # --- Step 5: Push bib to Alma ---
        print("  → Pushing bib to Alma...")
        new_mms_id, bib_err = create_alma_bib(normalized_xml, alma_key)

        if not new_mms_id:
            print(f"  ! Alma bib creation failed: {bib_err}")
            result_row.update(
                {
                    "status": "OCLC Error",
                    "alma_mms_id": "",
                    "alma_portfolio_id": "",
                    "alma_856_url": url_856,
                    "oclc_number": best["oclc_number"],
                    "oclc_title": best["title"],
                    "score": best["score"],
                    "encoding_level": best["encoding_level"],
                    "agency": best["agency"],
                    "notes": f"Alma bib creation failed: {bib_err}",
                }
            )
            results.append(result_row)
            continue

        print(f"  → Bib created. MMS ID: {new_mms_id}")

        # --- Step 6: Create portfolio ---
        print(f"  → Creating portfolio (DOI: {doi or 'N/A'})...")
        port_id, port_err = create_alma_portfolio(new_mms_id, best["title"], doi, alma_key)

        if port_id:
            print(f"  → Portfolio created: {port_id}")
            result_row.update(
                {
                    "status": "Created in Alma",
                    "alma_mms_id": new_mms_id,
                    "alma_portfolio_id": port_id,
                    "alma_856_url": url_856,
                    "oclc_number": best["oclc_number"],
                    "oclc_title": best["title"],
                    "score": best["score"],
                    "encoding_level": best["encoding_level"],
                    "agency": best["agency"],
                    "notes": f"{best['field_count']} MARC fields; DOI: {doi}",
                }
            )
        else:
            print(f"  ! Portfolio creation failed: {port_err}")
            result_row.update(
                {
                    "status": "Bib Created, No Portfolio",
                    "alma_mms_id": new_mms_id,
                    "alma_portfolio_id": "",
                    "alma_856_url": url_856,
                    "oclc_number": best["oclc_number"],
                    "oclc_title": best["title"],
                    "score": best["score"],
                    "encoding_level": best["encoding_level"],
                    "agency": best["agency"],
                    "notes": f"Portfolio error: {port_err}",
                }
            )

        results.append(result_row)

    # --- Write output ---
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    output_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), f"results_{date_str}.xlsx"
    )
    write_results(results, output_path)

    # Summary
    already = sum(1 for r in results if r["status"] == "Already in Alma")
    created = sum(1 for r in results if r["status"] == "Created in Alma")
    bib_only = sum(1 for r in results if r["status"] == "Bib Created, No Portfolio")
    notfound = sum(1 for r in results if r["status"] == "Not Found in OCLC")
    errors = sum(1 for r in results if r["status"] == "OCLC Error")
    processed = len(results)
    print("\nSummary:")
    print(f"  Already in Alma          : {already}")
    print(f"  Created in Alma          : {created}")
    print(f"  Bib Created, No Portfolio: {bib_only}")
    print(f"  Not Found in OCLC        : {notfound}")
    print(f"  Errors                   : {errors}")
    print(f"  Total processed          : {processed}")


if __name__ == "__main__":
    main()
