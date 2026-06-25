"""
Alma Serial Frequency Change Automation
========================================
Automates MARC record updates for serial frequency changes in Ex Libris Alma.

For each row in the input spreadsheet this script:
  1. Fetches the bib record from Alma via the REST API.
  2. Demotes the current 310 field to a historical 321 field.
  3. Creates a new 310 with the updated frequency and effective year.
  4. Updates positions 18-19 in the 008 fixed field.
  5. Optionally adds/updates a 515 note for continuously-published serials.
  6. Writes the record back to Alma (unless running in dry-run mode).

API Key security
----------------
NEVER hard-code your Alma API key in this script or commit it to version control.
Supply it through one of the following methods (evaluated in order):

  1. Command-line flag:   --api-key YOUR_KEY
  2. Environment variable: export ALMA_API_KEY=YOUR_KEY
  3. Key file (plain text, one line):
       - sandbox:    alma_sandbox_key.txt    (or --api-key-file path)
       - production: alma_production_key.txt (or --api-key-file path)

Add any key files to your .gitignore so they are never committed.

Dependencies
------------
  pip install requests pymarc pandas openpyxl

Usage examples
--------------
  # Dry run (no changes written to Alma) – sandbox environment
  python alma_frequency_change_automation.py frequency_changes.csv

  # Dry run with explicit API key
  python alma_frequency_change_automation.py frequency_changes.csv --api-key YOUR_SANDBOX_KEY

  # Apply changes to Alma sandbox
  python alma_frequency_change_automation.py frequency_changes.csv --execute

  # Apply changes to Alma production
  python alma_frequency_change_automation.py frequency_changes.csv --environment production --execute

  # Save detailed output files (CSV, JSONL, log)
  python alma_frequency_change_automation.py frequency_changes.csv --save-output-files --output-dir ./run_output

  # Interactive guided mode (useful when running manually without CLI experience)
  python alma_frequency_change_automation.py --manual

  # Test MARC transformation locally without calling Alma
  python alma_frequency_change_automation.py \\
      --test-before-xml BEFORE.xml \\
      --test-after-xml  AFTER.xml  \\
      --test-frequency  Monthly    \\
      --test-effective-year 2024   \\
      --test-008-freq m            \\
      --test-008-reg  r
"""

import argparse
import copy
import csv
import io
import json
import logging
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, cast

import pandas as pd
import requests
from pymarc import Field, Record, Subfield, parse_xml_to_array
from pymarc.marcxml import record_to_xml as pymarc_record_to_xml


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class InputRow:
    row_index: int
    mms_id: str
    new_frequency: str
    effective_year: int
    continuous_publication: bool = False
    note_text_override: Optional[str] = None
    source_url: Optional[str] = None


@dataclass
class RecordUpdatePlan:
    """Change plan built from the live Alma record before any writes are made.

    Inspect this object (or its JSON log entry) to verify what the script
    intends to do before committing changes to Alma.
    """

    mms_id: str
    current_310: str
    new_310: str
    new_321_entries: List[Dict[str, str]]  # [{"frequency": "...", "date": "..."}]
    o008_frequency: str
    o008_regularity: str
    add_515: bool
    note: Optional[str]
    source_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Input file discovery
# ---------------------------------------------------------------------------

def _discover_input_file() -> Optional[str]:
    """Look for a spreadsheet in the script directory and cwd."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_dirs = list(dict.fromkeys([script_dir, os.getcwd()]))

    preferred_names = ["frequency_changes.csv", "frequency_changes.xlsx"]
    for directory in search_dirs:
        for name in preferred_names:
            candidate = os.path.join(directory, name)
            if os.path.exists(candidate):
                return candidate

    candidates: List[str] = []
    for directory in search_dirs:
        for name in sorted(os.listdir(directory)):
            if name.lower().endswith((".csv", ".xlsx", ".xls")):
                full = os.path.join(directory, name)
                if full not in candidates:
                    candidates.append(full)

    return candidates[0] if candidates else None


# ---------------------------------------------------------------------------
# Interactive/manual mode
# ---------------------------------------------------------------------------

def _prompt_for_manual_args(args: argparse.Namespace) -> argparse.Namespace:
    """Walk the user through required arguments interactively."""
    print("Manual mode: press Enter to accept the default shown in brackets.")

    discovered_input = _discover_input_file()
    default_input = args.input_file or discovered_input or ""
    while not args.input_file:
        entered = input(f"Input spreadsheet path [{default_input}]: ").strip()
        chosen = entered or default_input
        if not chosen:
            print("Please provide a .csv or .xlsx file path.")
            continue
        if not os.path.exists(chosen):
            print(f"File not found: {chosen}")
            continue
        args.input_file = chosen

    if args.environment not in ("sandbox", "production"):
        args.environment = "sandbox"

    env_entered = (
        input(f"Environment (sandbox/production) [{args.environment}]: ").strip().lower()
    )
    if env_entered in ("sandbox", "production"):
        args.environment = env_entered

    execute_default = "y" if args.execute else "n"
    execute_entered = (
        input(f"Apply updates to Alma? (y/N) [{execute_default}]: ").strip().lower()
    )
    if execute_entered in ("y", "yes"):
        args.execute = True
    elif execute_entered in ("n", "no", ""):
        args.execute = False

    output_entered = input(f"Output directory [{args.output_dir}]: ").strip()
    if output_entered:
        args.output_dir = output_entered

    return args


# ---------------------------------------------------------------------------
# Spreadsheet loading
# ---------------------------------------------------------------------------

def load_spreadsheet(file_path: str) -> Tuple[List[InputRow], "pd.DataFrame"]:
    """Read a .csv or .xlsx file and return parsed InputRow objects."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".csv":
        csv_encodings = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
        last_exc: Optional[Exception] = None
        df = None
        for enc in csv_encodings:
            try:
                df = pd.read_csv(file_path, dtype={"MMS ID": str}, encoding=enc)
                break
            except UnicodeDecodeError as exc:
                last_exc = exc

        if df is None:
            if last_exc:
                raise last_exc
            raise ValueError(f"Could not decode CSV file: {file_path}")
    else:
        df = pd.read_excel(file_path, dtype={"MMS ID": str})

    # Normalize headers: strip whitespace, replace non-breaking spaces, collapse runs.
    normalized_columns = []
    for col in df.columns:
        name = str(col).replace("\u00a0", " ").strip()
        name = " ".join(name.split())
        normalized_columns.append(name)
    df.columns = normalized_columns

    required_cols = ["MMS ID", "New Frequency", "Effective Year"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        raise ValueError(
            "Input file is missing required columns: "
            f"{', '.join(missing_cols)}. "
            f"Found columns: {', '.join(str(c) for c in df.columns)}"
        )

    rows: List[InputRow] = []
    for row_index, (_, row) in enumerate(df.iterrows()):
        mms_id_raw = row.get("MMS ID", "")
        mms_id = "" if pd.isna(mms_id_raw) else str(mms_id_raw).strip()

        new_frequency_raw = row.get("New Frequency", "")
        new_frequency = (
            "" if pd.isna(new_frequency_raw) else str(new_frequency_raw).strip()
        )

        effective_year_raw = row.get("Effective Year", None)
        effective_year = 0
        if effective_year_raw is not None and not pd.isna(effective_year_raw):
            try:
                effective_year = int(str(effective_year_raw).strip())
            except ValueError:
                effective_year = 0

        cp_val = str(row.get("Continuous Publication", "")).strip().lower()
        is_cp = cp_val in ["yes", "true", "1", "y"]

        note_override_raw = row.get("Note Override", None)
        note_override: Optional[str] = None
        if note_override_raw is not None and not pd.isna(note_override_raw):
            candidate_note = str(note_override_raw).strip()
            note_override = candidate_note if candidate_note else None

        source_url_raw = row.get("Source URL", None)
        source_url: Optional[str] = None
        if source_url_raw is not None and not pd.isna(source_url_raw):
            candidate_url = str(source_url_raw).strip()
            source_url = candidate_url if candidate_url else None

        rows.append(
            InputRow(
                row_index=row_index,
                mms_id=mms_id,
                new_frequency=new_frequency,
                effective_year=effective_year,
                continuous_publication=is_cp,
                note_text_override=note_override,
                source_url=source_url,
            )
        )

    return rows, df


# ---------------------------------------------------------------------------
# Frequency mapping  (MARC 21 / LOC codes)
# ---------------------------------------------------------------------------

FREQUENCY_MAP: Dict[str, Dict[str, str]] = {
    # --- Standard regular frequencies ---
    "annual":                {"310_text": "Annual",                "008_freq": "a", "008_reg": "r"},
    "semiannual":            {"310_text": "Semiannual",            "008_freq": "f", "008_reg": "r"},
    "quarterly":             {"310_text": "Quarterly",             "008_freq": "q", "008_reg": "r"},
    "bimonthly":             {"310_text": "Bimonthly",             "008_freq": "b", "008_reg": "r"},
    "six issues a year":     {"310_text": "Six issues a year",     "008_freq": "b", "008_reg": "x"},
    "six times a year":      {"310_text": "Six times a year",      "008_freq": "b", "008_reg": "x"},
    "monthly":               {"310_text": "Monthly",               "008_freq": "m", "008_reg": "r"},
    "semimonthly":           {"310_text": "Semimonthly",           "008_freq": "s", "008_reg": "x"},
    "twice a month":         {"310_text": "Semimonthly",           "008_freq": "s", "008_reg": "x"},
    "twice per month":       {"310_text": "Semimonthly",           "008_freq": "s", "008_reg": "x"},
    "weekly":                {"310_text": "Weekly",                "008_freq": "w", "008_reg": "r"},
    "biweekly":              {"310_text": "Biweekly",              "008_freq": "e", "008_reg": "r"},
    "daily":                 {"310_text": "Daily",                 "008_freq": "d", "008_reg": "r"},
    "three times a year":    {"310_text": "Three times a year",    "008_freq": "t", "008_reg": "r"},
    "triannual":             {"310_text": "Three times a year",    "008_freq": "t", "008_reg": "r"},
    "biennial":              {"310_text": "Biennial",              "008_freq": "g", "008_reg": "r"},
    "triennial":             {"310_text": "Triennial",             "008_freq": "h", "008_reg": "r"},
    "three times a week":    {"310_text": "Three times a week",    "008_freq": "i", "008_reg": "r"},
    "three times a month":   {"310_text": "Three times a month",   "008_freq": "j", "008_reg": "r"},
    "continuously updated":  {"310_text": "Continuously updated",  "008_freq": "k", "008_reg": "r"},
    # --- Near-monthly irregular counts ---
    "10 issues/year":        {"310_text": "10 issues/year",        "008_freq": "m", "008_reg": "x"},
    "10 issues per year":    {"310_text": "10 issues/year",        "008_freq": "m", "008_reg": "x"},
    "11 issues/year":        {"310_text": "11 issues/year",        "008_freq": "m", "008_reg": "x"},
    "11 issues per year":    {"310_text": "11 issues/year",        "008_freq": "m", "008_reg": "x"},
    "12 issues/year":        {"310_text": "12 issues/year",        "008_freq": "m", "008_reg": "x"},
    "12 issues per year":    {"310_text": "12 issues/year",        "008_freq": "m", "008_reg": "x"},
    "21 issues per year":    {"310_text": "21 issues per year",    "008_freq": "z", "008_reg": "x"},
    # --- Irregular / other ---
    "irregular":             {"310_text": "Irregular",             "008_freq": "x", "008_reg": "x"},
    "completely irregular":  {"310_text": "Irregular",             "008_freq": "x", "008_reg": "x"},
    # --- Common aliases ---
    "semi-annual":           {"310_text": "Semiannual",            "008_freq": "f", "008_reg": "r"},
    "biannual":              {"310_text": "Semiannual",            "008_freq": "f", "008_reg": "r"},
    "twice a year":          {"310_text": "Semiannual",            "008_freq": "f", "008_reg": "r"},
    "twice yearly":          {"310_text": "Semiannual",            "008_freq": "f", "008_reg": "r"},
    "four issues a year":    {"310_text": "Quarterly",             "008_freq": "q", "008_reg": "r"},
    "four times a year":     {"310_text": "Quarterly",             "008_freq": "q", "008_reg": "r"},
}


# ---------------------------------------------------------------------------
# API key helpers
# ---------------------------------------------------------------------------

def load_api_key_from_file(file_path: str) -> Optional[str]:
    """Read a plain-text API key file (one key per file, on the first line)."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            key = f.read().strip()
            return key or None
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Frequency helpers
# ---------------------------------------------------------------------------

def get_frequency_rules(frequency_name: str) -> Optional[Dict[str, str]]:
    return FREQUENCY_MAP.get(frequency_name.lower())


def _derive_cp_note_text(frequency: str) -> str:
    """Return the appropriate 515 continuous-publication note based on frequency."""
    if frequency.lower().strip() == "annual":
        return "Articles published as they become available and compiled into annual volumes."
    return "Articles published as they become available and compiled into volumes or issues."


def validate_row(row: InputRow, default_note_text: str) -> Tuple[bool, str]:
    if not row.mms_id:
        return False, "Missing MMS ID"
    rules = get_frequency_rules(row.new_frequency)
    if not rules:
        return False, f"Unsupported frequency: '{row.new_frequency}'"
    if not row.effective_year:
        return False, "Missing or invalid Effective Year"
    return True, "Valid"


# ---------------------------------------------------------------------------
# Change-plan builder
# ---------------------------------------------------------------------------

def build_update_plan(
    row: InputRow,
    record: Record,
    freq_rules: Dict[str, str],
    note_text: Optional[str],
) -> RecordUpdatePlan:
    """Derive the full change plan from the live record without mutating it.

    Call this before ``update_record_for_frequency`` so the intent of every
    update is logged and reviewable prior to any write back to Alma.
    """
    # Current 310
    current_310_fields = record.get_fields("310")
    current_310_text = (
        current_310_fields[0].get_subfields("a")[0]
        if current_310_fields and current_310_fields[0].get_subfields("a")
        else ""
    )

    # Compute what the closed date range will look like on the demoted 321.
    new_321_entries: List[Dict[str, str]] = []
    if current_310_fields:
        old_b = (
            current_310_fields[0].get_subfields("b")[0]
            if current_310_fields[0].get_subfields("b")
            else ""
        ).strip()

        if not old_b:
            date_range = f"-{row.effective_year - 1}"
        elif old_b.endswith("-") and len(old_b) >= 5:
            old_start = old_b[:-1].strip()
            if old_start.isdigit():
                end_year = row.effective_year - 1
                date_range = (
                    old_start
                    if int(old_start) == end_year
                    else f"{old_start}-{end_year}"
                )
            else:
                date_range = old_b
        else:
            date_range = old_b

        new_321_entries.append(
            {"frequency": current_310_text, "date": date_range}
        )

    return RecordUpdatePlan(
        mms_id=row.mms_id,
        current_310=current_310_text,
        new_310=freq_rules["310_text"],
        new_321_entries=new_321_entries,
        o008_frequency=freq_rules["008_freq"],
        o008_regularity=freq_rules["008_reg"],
        add_515=row.continuous_publication,
        note=note_text if row.continuous_publication else None,
        source_url=row.source_url,
    )


# ---------------------------------------------------------------------------
# MARC field helpers
# ---------------------------------------------------------------------------

def _first_year_from_range(range_text: str) -> int:
    txt = (range_text or "").strip()
    if not txt:
        return 999999
    if txt.startswith("-"):
        return 0
    first = txt.split("-")[0].strip()
    if first.isdigit():
        return int(first)
    return 999999


def _reorder_321_fields(record: Record) -> None:
    fields_321 = record.get_fields("321")
    if len(fields_321) <= 1:
        return
    sorted_fields = sorted(
        fields_321,
        key=lambda f: _first_year_from_range((f.get_subfields("b") or [""])[0]),
    )
    for f in fields_321:
        record.remove_field(f)
    for f in sorted_fields:
        record.add_ordered_field(f)


# ---------------------------------------------------------------------------
# Alma REST client
# ---------------------------------------------------------------------------

class AlmaClient:
    """Thin wrapper around the Alma Bibs REST API."""

    # Override base_url to point at a different region, e.g.:
    #   https://api-eu.hosted.exlibrisgroup.com/almaws/v1  (Europe)
    #   https://api-ap.hosted.exlibrisgroup.com/almaws/v1  (Asia-Pacific)
    DEFAULT_BASE_URL = "https://api-na.hosted.exlibrisgroup.com/almaws/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
    ):
        self.api_key = api_key or os.environ.get("ALMA_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"apikey {self.api_key}",
            "Accept": "application/xml",
            "Content-Type": "application/xml",
        }

    def get_bib_record(self, mms_id: str) -> bytes:
        url = f"{self.base_url}/bibs/{mms_id}"
        resp = requests.get(url, headers=self.headers)
        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            body = (resp.text or "").strip()
            detail = f"{resp.status_code} for GET {url}"
            if body:
                detail += f" | {body[:500]}"
            raise requests.HTTPError(detail) from exc
        return resp.content

    def update_bib_record(self, mms_id: str, marc_xml: bytes) -> bytes:
        url = f"{self.base_url}/bibs/{mms_id}"
        resp = requests.put(url, headers=self.headers, data=marc_xml)
        try:
            resp.raise_for_status()
        except requests.HTTPError as exc:
            body = (resp.text or "").strip()
            detail = f"{resp.status_code} for PUT {url}"
            if body:
                detail += f" | {body[:500]}"
            raise requests.HTTPError(detail) from exc
        return resp.content


# ---------------------------------------------------------------------------
# MARC XML helpers
# ---------------------------------------------------------------------------

def parse_marc_xml(xml_content: bytes) -> Optional[Record]:
    records = parse_xml_to_array(io.BytesIO(xml_content))
    return records[0] if records else None


def record_to_xml(record: Record) -> bytes:
    return pymarc_record_to_xml(record)


def _inject_record_into_bib_xml(original_bib_xml: bytes, updated_record: Record) -> bytes:
    """Replace the <record> element inside the Alma <bib> XML envelope.

    Alma's PUT /bibs/{mms_id} requires the full <bib>…</bib> wrapper.
    pymarc's record_to_xml() emits only the bare <record> element, so we
    splice the updated record back into the original GET response body.
    """
    updated_record_xml = record_to_xml(updated_record)
    result = re.sub(
        rb"<record[^>]*>.*?</record>",
        updated_record_xml,
        original_bib_xml,
        count=1,
        flags=re.DOTALL,
    )
    return result


def _field_subfields(record: Record, tag: str) -> List[Dict[str, str]]:
    values: List[Dict[str, str]] = []
    for field in record.get_fields(tag):
        field_map: Dict[str, str] = {}
        for code in ["a", "b"]:
            subs = field.get_subfields(code)
            if subs:
                field_map[code] = subs[0]
        values.append(field_map)
    return values


# ---------------------------------------------------------------------------
# Core MARC transformation
# ---------------------------------------------------------------------------

def update_record_for_frequency(
    record: Record,
    new_freq_text: str,
    effective_year: int,
    o008_freq: str,
    o008_reg: str,
    is_continuous: bool,
    note_text: str = "Articles published as they become available and compiled into annual volumes.",
) -> Record:
    """Return a deep copy of *record* with frequency fields updated."""
    updated = copy.deepcopy(record)

    def _build_old_range(old_b_value: str, new_start_year: int) -> str:
        old_b = (old_b_value or "").strip()
        if not old_b:
            return f"-{new_start_year - 1}"
        if old_b.endswith("-") and len(old_b) >= 5:
            old_start = old_b[:-1].strip()
            if old_start.isdigit():
                end_year = new_start_year - 1
                if int(old_start) == end_year:
                    return old_start
                return f"{old_start}-{end_year}"
        return old_b

    # Demote existing 310 → 321 (former frequency).
    current_310s = updated.get_fields("310")
    created_321 = False
    if current_310s:
        old_310 = current_310s[0]
        old_freq = (
            old_310.get_subfields("a")[0]
            if old_310.get_subfields("a")
            else "Unknown"
        )
        old_range_raw = (
            old_310.get_subfields("b")[0]
            if old_310.get_subfields("b")
            else ""
        )
        updated.remove_field(old_310)

        new_321 = Field(
            tag="321",
            indicators=cast(Any, [" ", " "]),
            subfields=[
                Subfield(code="a", value=old_freq),
                Subfield(code="b", value=_build_old_range(old_range_raw, effective_year)),
            ],
        )
        updated.add_ordered_field(new_321)
        created_321 = True

    if created_321:
        _reorder_321_fields(updated)

    # Add new 310 (current frequency).
    new_310 = Field(
        tag="310",
        indicators=cast(Any, [" ", " "]),
        subfields=[
            Subfield(code="a", value=new_freq_text),
            Subfield(code="b", value=f"{effective_year}-"),
        ],
    )
    updated.add_ordered_field(new_310)

    # Update 008 positions 18-19.
    f008 = updated.get_fields("008")
    if f008:
        val = cast(str, f008[0].data or "")
        if len(val) >= 20:
            f008[0].data = val[:18] + o008_freq + o008_reg + val[20:]

    # Add/update 515 note for continuously-published serials.
    if is_continuous:
        existing_515s = updated.get_fields("515")
        if existing_515s:
            target_515 = existing_515s[0]
            had_a = False
            new_subs: List[Subfield] = []
            for sub in target_515.subfields:
                if sub.code == "a" and not had_a:
                    new_subs.append(Subfield(code="a", value=note_text))
                    had_a = True
                else:
                    new_subs.append(Subfield(code=sub.code, value=sub.value))
            if not had_a:
                new_subs.append(Subfield(code="a", value=note_text))
            target_515.subfields = new_subs
        else:
            note_field = Field(
                tag="515",
                indicators=cast(Any, [" ", " "]),
                subfields=[Subfield(code="a", value=note_text)],
            )
            updated.add_ordered_field(note_field)

    if created_321:
        latest_321 = updated.get_fields("321")[-1]
        if not latest_321.get_subfields("b"):
            raise ValueError("Generated 321 is missing required $b date range")

    return updated


# ---------------------------------------------------------------------------
# Local XML comparison (test/QA mode)
# ---------------------------------------------------------------------------

def compare_with_expected_after(
    before_xml_path: str,
    after_xml_path: str,
    new_frequency_text: str,
    effective_year: int,
    o008_freq: str,
    o008_reg: str,
    is_continuous: bool,
    note_text: str = "Articles published as they become available and compiled into annual volumes.",
    generated_xml_out: Optional[str] = None,
) -> int:
    """Compare the script's output against an expected AFTER XML file.

    Returns 0 (PASS), 1 (FAIL – field mismatch), or 2 (parse error).
    """
    with open(before_xml_path, "rb") as _f:
        before_record = parse_marc_xml(_f.read())
    with open(after_xml_path, "rb") as _f:
        expected_after_record = parse_marc_xml(_f.read())

    if before_record is None:
        print(f"FAIL: Could not parse BEFORE XML: {before_xml_path}")
        return 2
    if expected_after_record is None:
        print(f"FAIL: Could not parse AFTER XML: {after_xml_path}")
        return 2

    generated = update_record_for_frequency(
        record=before_record,
        new_freq_text=new_frequency_text,
        effective_year=effective_year,
        o008_freq=o008_freq,
        o008_reg=o008_reg,
        is_continuous=is_continuous,
        note_text=note_text,
    )

    if generated_xml_out:
        with open(generated_xml_out, "wb") as f:
            f.write(record_to_xml(generated))
        print(f"Wrote generated XML to: {generated_xml_out}")

    checks = [
        ("310", _field_subfields(generated, "310"), _field_subfields(expected_after_record, "310")),
        ("321", _field_subfields(generated, "321"), _field_subfields(expected_after_record, "321")),
        (
            "008",
            [generated.get_fields("008")[0].data if generated.get_fields("008") else ""],
            [expected_after_record.get_fields("008")[0].data if expected_after_record.get_fields("008") else ""],
        ),
        ("515", _field_subfields(generated, "515"), _field_subfields(expected_after_record, "515")),
    ]

    failed = False
    for tag, actual, expected in checks:
        if actual == expected:
            print(f"PASS {tag}: {actual}")
        else:
            failed = True
            print(f"FAIL {tag}:")
            print(f"  expected: {expected}")
            print(f"  actual:   {actual}")

    if failed:
        print("RESULT: FAIL")
        return 1

    print("RESULT: PASS")
    return 0


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

class Reporter:
    def __init__(self, output_dir: str = ".", save_output_files: bool = False):
        self.save_output_files = save_output_files
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_path: Optional[str] = None
        self.jsonl_path: Optional[str] = None
        self.updated_spreadsheet_path: Optional[str] = None

        if self.save_output_files:
            os.makedirs(output_dir, exist_ok=True)
            self.csv_path = f"{output_dir}/run_results_{timestamp}.csv"
            self.jsonl_path = f"{output_dir}/run_events_{timestamp}.jsonl"
            self.updated_spreadsheet_path = f"{output_dir}/updated_frequency_changes_{timestamp}.csv"

        self.processed = 0
        self.skipped = 0
        self.failed = 0

        logging_kwargs: Dict[str, Any] = {
            "level": logging.INFO,
            "format": "%(asctime)s - %(levelname)s - %(message)s",
        }
        if self.save_output_files:
            logging_kwargs["filename"] = f"{output_dir}/automation_{timestamp}.log"
        logging.basicConfig(**logging_kwargs)
        self.logger = logging.getLogger(__name__)

        if self.save_output_files and self.csv_path:
            with open(self.csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["MMS ID", "Status", "Message", "Original 310", "New 310"])

    def _write_json_event(self, payload: Dict[str, Any]) -> None:
        if self.save_output_files and self.jsonl_path:
            with open(self.jsonl_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=True) + "\n")

    def log_result(
        self,
        mms_id: str,
        status: str,
        message: str,
        old_310: str = "",
        new_310: str = "",
    ) -> None:
        self.logger.info(
            f"MMS_ID: {mms_id} | Status: {status} | Msg: {message}"
        )
        if self.save_output_files and self.csv_path:
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([mms_id, status, message, old_310, new_310])
        self._write_json_event(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "mms_id": mms_id,
                "status": status,
                "message": message,
                "old_310": old_310,
                "new_310": new_310,
            }
        )
        if status == "SUCCESS":
            self.processed += 1
        elif status == "SKIPPED":
            self.skipped += 1
        else:
            self.failed += 1


# ---------------------------------------------------------------------------
# Main processor
# ---------------------------------------------------------------------------

class FrequencyProcessor:
    def __init__(
        self,
        api_key: Optional[str],
        output_dir: str = ".",
        save_output_files: bool = False,
        updated_xml_dir: Optional[str] = None,
    ):
        self.alma = AlmaClient(api_key=api_key)
        self.reporter = Reporter(output_dir=output_dir, save_output_files=save_output_files)
        self.updated_xml_dir = updated_xml_dir
        if self.updated_xml_dir:
            os.makedirs(self.updated_xml_dir, exist_ok=True)

    def _write_original_xml(self, mms_id: str, xml_content: bytes) -> Optional[str]:
        if not self.updated_xml_dir:
            return None
        out_path = os.path.join(self.updated_xml_dir, f"BEFORE-{mms_id}.xml")
        with open(out_path, "wb") as f:
            f.write(xml_content)
        return out_path

    def _write_updated_xml(self, mms_id: str, record: Record) -> Optional[str]:
        if not self.updated_xml_dir:
            return None
        out_path = os.path.join(self.updated_xml_dir, f"AFTER-{mms_id}.xml")
        with open(out_path, "wb") as f:
            f.write(record_to_xml(record))
        return out_path

    def process_file(self, file_path: str, dry_run: bool = True) -> None:
        self.reporter.logger.info(
            f"Starting processing for {file_path}. Dry run: {dry_run}"
        )
        rows, source_df = load_spreadsheet(file_path)
        status_df = source_df.copy()
        for col in ["Processing Status", "Message", "Original 310", "New 310"]:
            if col not in status_df.columns:
                status_df[col] = ""

        for row in rows:
            is_valid, msg = validate_row(row, "")
            if not is_valid:
                self.reporter.log_result(row.mms_id, "SKIPPED", msg)
                status_df.at[row.row_index, "Processing Status"] = "SKIPPED"
                status_df.at[row.row_index, "Message"] = msg
                continue

            rules = get_frequency_rules(row.new_frequency)
            if rules is None:
                reason = f"Unsupported frequency: {row.new_frequency}"
                self.reporter.log_result(row.mms_id, "SKIPPED", reason)
                status_df.at[row.row_index, "Processing Status"] = "SKIPPED"
                status_df.at[row.row_index, "Message"] = reason
                continue

            freq_rules: Dict[str, str] = rules

            if not freq_rules.get("008_freq") or not freq_rules.get("008_reg"):
                reason = f"Missing 008 mapping for frequency: {row.new_frequency}"
                self.reporter.log_result(row.mms_id, "SKIPPED", reason)
                status_df.at[row.row_index, "Processing Status"] = "SKIPPED"
                status_df.at[row.row_index, "Message"] = reason
                continue

            try:
                xml_content = self.alma.get_bib_record(row.mms_id)
                self._write_original_xml(row.mms_id, xml_content)
                record = parse_marc_xml(xml_content)
                if not record:
                    reason = "Could not parse MARC XML from Alma response."
                    self.reporter.log_result(row.mms_id, "FAILED", reason)
                    status_df.at[row.row_index, "Processing Status"] = "FAILED"
                    status_df.at[row.row_index, "Message"] = reason
                    continue

                old_310s = record.get_fields("310")
                old_310_text = (
                    old_310s[0].get_subfields("a")[0]
                    if old_310s and old_310s[0].get_subfields("a")
                    else ""
                )

                note_text = row.note_text_override or _derive_cp_note_text(row.new_frequency)

                plan = build_update_plan(row, record, freq_rules, note_text)
                self.reporter.logger.info(
                    f"Update plan: {json.dumps(asdict(plan), ensure_ascii=True)}"
                )

                updated_record = update_record_for_frequency(
                    record=record,
                    new_freq_text=freq_rules["310_text"],
                    effective_year=row.effective_year,
                    o008_freq=freq_rules["008_freq"],
                    o008_reg=freq_rules["008_reg"],
                    is_continuous=row.continuous_publication,
                    note_text=note_text,
                )

                written_xml_path = self._write_updated_xml(row.mms_id, updated_record)

                if not dry_run:
                    updated_xml = _inject_record_into_bib_xml(xml_content, updated_record)
                    self.alma.update_bib_record(row.mms_id, updated_xml)

                result_msg = (
                    "Update completed successfully."
                    if not dry_run
                    else "DRY RUN - Update planned successfully."
                )
                if written_xml_path:
                    result_msg += f" Generated XML: {written_xml_path}"

                self.reporter.log_result(
                    row.mms_id,
                    "SUCCESS",
                    result_msg,
                    old_310=old_310_text,
                    new_310=freq_rules["310_text"],
                )
                status_df.at[row.row_index, "Processing Status"] = "SUCCESS"
                status_df.at[row.row_index, "Message"] = (
                    "Update completed successfully."
                    if not dry_run
                    else "DRY RUN - Update planned successfully."
                )
                status_df.at[row.row_index, "Original 310"] = old_310_text
                status_df.at[row.row_index, "New 310"] = freq_rules["310_text"]

            except Exception as exc:
                self.reporter.log_result(row.mms_id, "ERROR", str(exc))
                self.reporter.logger.error(
                    f"Error processing {row.mms_id}: {exc}", exc_info=True
                )
                status_df.at[row.row_index, "Processing Status"] = "FAILED"
                status_df.at[row.row_index, "Message"] = str(exc)

        if self.reporter.save_output_files and self.reporter.updated_spreadsheet_path:
            status_df.to_csv(
                self.reporter.updated_spreadsheet_path, index=False, encoding="utf-8"
            )

        self.reporter.logger.info("Processing complete.")
        self.reporter.logger.info(
            f"Summary: processed={self.reporter.processed}, "
            f"skipped={self.reporter.skipped}, "
            f"failed={self.reporter.failed}"
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

DEFAULT_CONTINUOUS_NOTE = (
    "Articles published as they become available and compiled into annual volumes."
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Alma Serial Frequency Change Automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Positional
    parser.add_argument(
        "input_file",
        nargs="?",
        help="Path to the input spreadsheet (.csv or .xlsx).",
    )

    # Run-mode
    parser.add_argument(
        "--manual",
        action="store_true",
        help="Guided interactive prompts (useful when running from a GUI / double-click).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply changes to Alma. Default is a dry run (read-only).",
    )
    parser.add_argument(
        "--environment",
        choices=["sandbox", "production"],
        default="sandbox",
        help="Which Alma environment to target (default: sandbox).",
    )

    # API key
    parser.add_argument(
        "--api-key",
        help="Alma API key. Overrides ALMA_API_KEY environment variable.",
        default=os.environ.get("ALMA_API_KEY"),
    )
    parser.add_argument(
        "--api-key-file",
        help=(
            "Path to a plain-text file containing the Alma API key (one key per file). "
            "Falls back to alma_sandbox_key.txt or alma_production_key.txt in the "
            "current directory when not specified."
        ),
    )

    # Output
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory for log and report files (default: current directory).",
    )
    parser.add_argument(
        "--save-output-files",
        action="store_true",
        help="Write CSV, JSONL, and log files to --output-dir.",
    )
    parser.add_argument(
        "--updated-xml-dir",
        help=(
            "Directory to write BEFORE-<MMS_ID>.xml and AFTER-<MMS_ID>.xml snapshots. "
            "Useful for review before committing changes."
        ),
    )

    # Test / QA mode (no Alma connection required)
    parser.add_argument("--test-before-xml", help="BEFORE MARC XML file for local comparison.")
    parser.add_argument("--test-after-xml",  help="Expected AFTER MARC XML file for local comparison.")
    parser.add_argument("--test-frequency",       help="New 310$a text to apply in test mode.")
    parser.add_argument("--test-effective-year",  type=int, help="Effective start year for test mode.")
    parser.add_argument("--test-008-freq",         help="008 position 18 frequency code for test mode.")
    parser.add_argument("--test-008-reg",          help="008 position 19 regularity code for test mode.")
    parser.add_argument(
        "--test-continuous",
        action="store_true",
        help="Include 515 continuous-publication note in test mode.",
    )
    parser.add_argument(
        "--test-note-text",
        default=DEFAULT_CONTINUOUS_NOTE,
        help="515$a note text used in test mode.",
    )
    parser.add_argument(
        "--test-generated-xml-out",
        help="Write the generated XML to this path in test mode.",
    )

    args = parser.parse_args()

    # ---- Test / QA mode ---------------------------------------------------
    if args.test_before_xml or args.test_after_xml:
        required = {
            "--test-before-xml":      args.test_before_xml,
            "--test-after-xml":       args.test_after_xml,
            "--test-frequency":       args.test_frequency,
            "--test-effective-year":  args.test_effective_year,
            "--test-008-freq":        args.test_008_freq,
            "--test-008-reg":         args.test_008_reg,
        }
        missing = [flag for flag, val in required.items() if val in (None, "")]
        if missing:
            print(f"Error: missing required test-mode arguments: {', '.join(missing)}")
            return

        exit_code = compare_with_expected_after(
            before_xml_path=args.test_before_xml,
            after_xml_path=args.test_after_xml,
            new_frequency_text=args.test_frequency,
            effective_year=args.test_effective_year,
            o008_freq=args.test_008_freq,
            o008_reg=args.test_008_reg,
            is_continuous=args.test_continuous,
            note_text=args.test_note_text,
            generated_xml_out=args.test_generated_xml_out,
        )
        raise SystemExit(exit_code)

    # ---- Interactive mode -------------------------------------------------
    if args.manual:
        args = _prompt_for_manual_args(args)

    # ---- Resolve input file -----------------------------------------------
    if not args.input_file:
        discovered_input = _discover_input_file()
        if discovered_input:
            args.input_file = discovered_input
            print(f"No input_file provided. Using: {discovered_input}")
        else:
            parser.print_usage()
            print(
                "\nError: input_file is required unless using "
                "--test-before-xml / --test-after-xml mode."
            )
            return

    # ---- Resolve API key --------------------------------------------------
    api_key = args.api_key
    if not api_key:
        key_file = args.api_key_file or (
            "alma_sandbox_key.txt"
            if args.environment == "sandbox"
            else "alma_production_key.txt"
        )
        api_key = load_api_key_from_file(key_file)

    if not api_key and args.execute:
        print(
            "Error: An Alma API key is required when --execute is set.\n"
            "Supply it via --api-key, the ALMA_API_KEY environment variable, "
            "or a key file (alma_sandbox_key.txt / alma_production_key.txt)."
        )
        return

    # ---- Run processor ----------------------------------------------------
    processor = FrequencyProcessor(
        api_key=api_key,
        output_dir=args.output_dir,
        save_output_files=args.save_output_files,
        updated_xml_dir=args.updated_xml_dir,
    )
    dry_run = not args.execute

    print(f"Starting in {'DRY RUN' if dry_run else 'EXECUTE'} mode ...")
    processor.process_file(args.input_file, dry_run=dry_run)
    print("Finished.")
    print(
        f"Summary: processed={processor.reporter.processed}, "
        f"skipped={processor.reporter.skipped}, "
        f"failed={processor.reporter.failed}"
    )

    if args.save_output_files:
        print(f"Updated spreadsheet : {processor.reporter.updated_spreadsheet_path}")
        print(f"Result CSV          : {processor.reporter.csv_path}")
        print(f"Machine log (JSONL) : {processor.reporter.jsonl_path}")
    else:
        print("Output files are disabled. Pass --save-output-files to enable them.")

    if args.updated_xml_dir:
        print(f"BEFORE/AFTER XML snapshots written to: {args.updated_xml_dir}")


if __name__ == "__main__":
    main()
