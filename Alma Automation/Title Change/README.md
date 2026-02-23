# Title Change Updater for Alma (362 + 76X-78X Consolidated)

This script automates the process of updating catalog records in **Alma** when a serial title undergoes a **title change**. It reads a CSV file containing pairs of MMS IDs (one for the previous title and one for the new title), along with ceased-date and optional archive-begins information, then updates the relevant MARC fields on both records via the Alma Bib API.

---

## Table of Contents

1. [What the Script Does](#what-the-script-does)
2. [Prerequisites](#prerequisites)
3. [Setup](#setup)
4. [CSV Format](#csv-format)
5. [Configuration](#configuration)
6. [Running the Script](#running-the-script)
7. [MARC Fields Updated](#marc-fields-updated)
8. [Dry-Run Mode](#dry-run-mode)
9. [Troubleshooting](#troubleshooting)

---

## What the Script Does

For **each row** in the input CSV the script processes **two** bibliographic records:

### Previous (old) title
| MARC Field | What Changes |
|---|---|
| **008** | Position 06 set to `d` (ceased); positions 11-14 filled with the ceased year |
| **260/264 $3** | Open-ended date range closed with the ceased year |
| **362** | "Ceased with …" note added (or appended to existing text) |
| **785** | Succeeding-entry link created, pointing to the new title |
| **988** | Local field recording the new title's NLM UI and today's date |
| **995** | Review-date stamp updated to today |

### New (succeeding) title
| MARC Field | What Changes |
|---|---|
| **780** | Preceding-entry link created, pointing back to the previous title |
| **76X-78X** | Any linking field on the previous title that references the new title is copied/merged, with optional "Archive begins" coverage adjustments |

---

## Prerequisites

- **Python 3.10+** (tested with 3.12 and 3.13)
- The following Python packages (all included in the standard library or installable via pip):

```
requests
```

Install with:

```bash
pip install requests
```

> `csv`, `xml.etree.ElementTree`, `re`, and `datetime` are part of the Python standard library and do not need to be installed.

---

## Setup

### 1. API Key File

The script reads your Alma API key from a **separate text file** so the key is never hard-coded in the script itself. Create a plain-text file (e.g., `alma_api_keys.txt`) with a line like:

```
alma_sandbox_key = "your_key_here"
```

Then update this line near the top of `titlechange_consolidated.py`:

```python
with open(r"your_file_path_here.txt") as f:
```

Replace `your_file_path_here.txt` with the **full path** to your key file, for example:

```python
with open(r"C:\Users\YourName\Documents\alma_api_keys.txt") as f:
```

### 2. API Base URL

The default base URL points to the **North America** region:

```
https://api-na.hosted.exlibrisgroup.com/almaws/v1/bibs/
```

If your Alma instance is hosted in **Europe** or **Asia Pacific**, change `api-na` to `api-eu` or `api-ap` in the `ALMA_API_BASE_URL` variable.

---

## CSV Format

Prepare a CSV file with the following columns:

| Column | Required | Description |
|---|---|---|
| `Previous title MMS ID` | Yes | The Alma MMS ID of the old (ceased) title |
| `New title MMS ID` | Yes | The Alma MMS ID of the new (succeeding) title |
| `Ceased date` | No | When the old title ceased, e.g. `v.50 no.4 (2024)` or just `2024` |
| `Archive begins` | No | Start-of-coverage for the new title, used when merging 76X-78X linking fields |

**Example:**

```csv
Previous title MMS ID,New title MMS ID,Ceased date,Archive begins
9912345678901234,9987654321098765,v.50 no.4 (2024),v.51 no.1 (2025)
```

> The column header `Archive Begins` (capital B) is also accepted.

Then update the last line of the script with the path to your CSV:

```python
process_csv('your_file_path/TitleChange.csv')
```

---

## Configuration

Two settings near the top of the script control behavior:

```python
DRY_RUN = True
```

When `True`, the script fetches and modifies records in memory but **does not** write anything back to Alma. Set to `False` when you are ready to apply changes for real.

```python
COVERAGE_SUBFIELDS = ["g", "z"]
```

The subfield codes in 76X-78X linking fields that hold coverage / "archive begins" information. The script checks these codes (in order) when merging linking fields. Adjust if your records use different subfields.

---

## Running the Script

```bash
python titlechange_consolidated.py
```

The script will print progress to the console:

- CSV headers and each row as it's read
- Which 362 fields are being updated
- Coverage merge decisions for 76X-78X fields
- `DRY RUN: Would update …` messages (when `DRY_RUN = True`)
- `Successfully updated record …` (when `DRY_RUN = False`)

---

## MARC Fields Updated

### Ceased-title fields (previous title)

| Function | Field | Description |
|---|---|---|
| `update_008_field()` | 008 | Sets type-of-date to `d` and fills the end year |
| `update_260_264_field()` | 260/264 $3 | Closes the open-ended date range |
| `update_362_field()` | 362 | Adds or appends a "Ceased with …" note |
| `update_995_field()` | 995 | Stamps today's date as the review date |

### Linking-entry fields (both records)

| Function | Field | Description |
|---|---|---|
| `update_785_field()` | 785 | Adds a succeeding-entry link on the previous title |
| `update_780_field()` | 780 | Adds a preceding-entry link on the new title |
| `update_linking_fields_from()` | 76X-78X | Copies/merges linking fields from previous → new title |

### Local fields (previous title)

| Function | Field | Description |
|---|---|---|
| `update_988_field()` | 988 | Records the new title's NLM UI ($a) and today's date ($b) |
| `update_995_field()` | 995 | Updates the review date ($d) or creates $c + $d |

---

## Dry-Run Mode

By default `DRY_RUN = True`. In this mode:

- Records are **fetched** from Alma (GET requests still happen)
- All MARC modifications are computed in memory
- **No PUT requests** are sent — nothing is written back
- The console shows `DRY RUN: Would update previous record …` / `DRY RUN: Would update new record …`

Once you've verified the output looks correct, set `DRY_RUN = False` and run again to apply the changes.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `Alma sandbox API key not found` | Key file path is wrong, or the line doesn't start with `alma_sandbox_key` | Double-check the path in the `open()` call and the format of the key file |
| `Failed to fetch record for MMS ID …: 401` | Invalid or expired API key | Regenerate the key in the Alma Developer Network and update the key file |
| `Failed to fetch record for MMS ID …: 400` | Malformed MMS ID (extra spaces, non-numeric characters) | Check the CSV for stray whitespace |
| `Skipping row due to missing MMS ID` | CSV column header doesn't match exactly | Ensure headers are `Previous title MMS ID` and `New title MMS ID` (case-sensitive) |
| `Ceased date does not contain a valid year` | The "Ceased date" value has no 4-digit year | Provide a year in the CSV, e.g. `2024` or `v.10 (2024)` |
| `No $3 found in tag 260/264` | The record's 260/264 field has no $3 subfield | This is informational — no change is made to that field |
