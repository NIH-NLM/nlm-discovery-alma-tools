# NLM UI → ISSN Updater for Alma

This script automates the process of updating **ISSN (022)** fields in Alma bibliographic records. It reads a CSV file containing NLM Unique Identifiers and their associated ISSNs, looks up each record in Alma by NLM UI (stored in 035 $9), then rebuilds the 022 field(s) with the correct print and/or electronic ISSNs.

---

## Table of Contents

1. [What the Script Does](#what-the-script-does)
2. [Prerequisites](#prerequisites)
3. [Setup](#setup)
4. [CSV Format](#csv-format)
5. [Running the Script](#running-the-script)
6. [MARC Fields Updated](#marc-fields-updated)
7. [022 Rebuild Logic](#022-rebuild-logic)
8. [Troubleshooting](#troubleshooting)

---

## What the Script Does

For **each row** in the input CSV the script:

1. **Looks up** the bib record in Alma using the NLM UI as an "other system ID" search, then confirms the match by verifying that 035 $9 exactly equals the NLM UI.
2. **Detects the format** (electronic vs. print) by checking 006 and 337 $a.
3. **Rebuilds the 022 field(s)** with the correct primary and alternate ISSNs, preserving $l (linking ISSN) and $2 (ISSN center code) from the existing record.
4. **Cleans up 260 $b** by removing any `[updated]` text.
5. **Stamps the 995** local field with today's date as a review date.
6. **Saves** the updated record back to Alma via PUT.

---

## Prerequisites

- **Python 3.10+** (tested with 3.12 and 3.13)
- The `requests` library:

```bash
pip install requests
```

> `csv`, `xml.etree.ElementTree`, and `datetime` are part of the Python standard library.

---

## Setup

### 1. API Key

The script stores the API key in a variable near the top of `NLM_UI_UpdateISSN.py`:

```python
API_KEY = "your_api_key_here"
```

Replace it with your actual Alma API key. For better security, consider reading the key from a separate file — a commented-out example is included in the script.

### 2. API Base URL

The default base URL points to the **North America** region:

```
https://api-na.hosted.exlibrisgroup.com/almaws/v1/bibs
```

Change `api-na` to `api-eu` or `api-ap` if your Alma instance is in Europe or Asia Pacific.

### 3. CSV File Path

The default CSV path is:

```python
CSV_FILE = "ISSN.csv"
```

Update this to the actual path of your input CSV file (relative or absolute).

---

## CSV Format

Prepare a CSV file with the following columns:

| Column | Required | Description |
|---|---|---|
| `NLM UI` | Yes | The NLM Unique Identifier (matches 035 $9 in the MARC record) |
| `Title` | No | Title for display/logging purposes only |
| `Print ISSN` | No | The print-format ISSN |
| `Electronic ISSN` | No | The electronic-format ISSN |
| `Linking ISSN` | No | The linking ISSN (used as fallback when no 022 exists) |

**Example:**

```csv
NLM UI,Title,Print ISSN,Electronic ISSN,Linking ISSN
101234567,Journal of Example Studies,1234-5678,2345-6789,3456-7890
```

> At least one of `Print ISSN`, `Electronic ISSN`, or `Linking ISSN` should be provided for the script to make meaningful changes.

---

## Running the Script

```bash
python NLM_UI_UpdateISSN.py
```

The script prints progress to the console for each row:

```
===== Processing 101234567 - Journal of Example Studies =====
✅ Successfully updated MMS ID 9912345678901234
```

Or, if something goes wrong:

```
❌ API error for NLM UI 101234567: 401
⚠️ No exact match for 035 $9 == 101234567
❌ Failed to update: 400
```

---

## MARC Fields Updated

| Function | Field | Description |
|---|---|---|
| `get_exact_bib_by_nlm_ui()` | 035 $9 | Used to look up and confirm the record (read-only) |
| `detect_format()` | 006, 337 $a | Determines electronic vs. print format (read-only) |
| `update_022_fields()` | 022 | Rebuilds $a, $l, $2, $9, $7 with correct ISSNs |
| `remove_updated_from_260()` | 260 $b | Strips `[updated]` text from publisher name |
| `update_995_field()` | 995 | Stamps review date ($d) and action code ($c) |

---

## 022 Rebuild Logic

The script picks the **primary** and **alternate** ISSNs based on the record's format:

| Record Format | Primary ISSN ($a) | Alternate ISSN ($a) |
|---|---|---|
| Electronic | Electronic ISSN | Print ISSN |
| Print | Print ISSN | Electronic ISSN |

### Primary 022 subfields

| Subfield | Value | Notes |
|---|---|---|
| `$a` | Primary ISSN | |
| `$l` | Linking ISSN | Preserved from old 022, or falls back to primary |
| `$2` | ISSN center code | Preserved from old 022 if it existed |
| `$9` | `EY` or `PY` | Only present when an alternate ISSN also exists |
| `$7` | `(Electronic)` or `(Print)` | Only present when an alternate ISSN also exists |

### Alternate 022 subfields (only if different from primary)

| Subfield | Value | Notes |
|---|---|---|
| `$a` | Alternate ISSN | |
| `$9` | `PN` or `EN` | Format code for the alternate |
| `$7` | `(Print)` or `(Electronic)` | Format label for the alternate |

### Special case

If no 022 existed before and only a **Linking ISSN** is provided, a single 022 is created with `$a` and `$l` both set to the linking ISSN.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `❌ API error … 401` | Invalid or expired API key | Regenerate the key in the Alma Developer Network |
| `❌ API error … 400` | Malformed NLM UI (extra spaces, non-numeric) | Check the CSV for stray whitespace |
| `⚠️ No exact match for 035 $9` | NLM UI not found in any record's 035 $9 | Verify the NLM UI is correct and present in Alma |
| `❌ Failed to update: 400` | Record XML is malformed after editing | Inspect the record in Alma and check for data issues |
| No 022 changes visible | Both Print and Electronic ISSN columns are empty, and no Linking ISSN | Provide at least one ISSN in the CSV |
| `No $3 found in tag 260/264` | Not an error — informational only | No action needed |
