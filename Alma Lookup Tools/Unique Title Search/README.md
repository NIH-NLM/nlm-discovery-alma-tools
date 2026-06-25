# Alma Unique Title Search Tool

## Overview
This folder contains a standalone public-share script:

- `unique_title_search_github.py`

The script checks whether a title in Alma is truly unique under RDA-style comparison rules by normalizing and comparing MARC 245/130 title data across SRU results.

## What This Updated Script Does
1. Fetches a bib record from Alma using an MMS ID.
2. Extracts 245 subfields `$a`, `$n`, and `$p`.
3. Applies non-filing logic from 245 indicator 2 when present.
4. Normalizes titles (diacritics, punctuation, transliteration exceptions, whitespace).
5. Runs SRU CQL queries with additional clauses for short titles to improve recall.
6. Compares normalized candidate 245/130 values against the target normalized title.
7. Returns matching records with MMS ID, NLM ID (035$9 when available), author, 245, and 130.
8. Ensures the searched MMS ID is included in results even when SRU indexing misses it.

## Why This Tool Is Useful
Alma title searching can over-return due to indexing breadth and punctuation differences. This script narrows results to practical duplicate candidates for cataloging decisions about qualifiers and uniform titles.

## Prerequisites
- Python 3.x
- `requests` (`pip install requests`)
- Alma API key with permission to read bibliographic records
- Institution-specific Alma SRU endpoint

## Configuration

### API key file
In `unique_title_search_github.py`, update:

```python
api_key_file = r"your_file_path_here.txt"
```

Your key file should include:

```text
alma_sandbox_key = "YOUR_API_KEY_HERE"
```

### SRU endpoint
Set your institution endpoint with `--sru_url` when running, or update the default in the script:

```python
parser.add_argument(
    "--sru_url",
    default="https://nlm.alma.exlibrisgroup.com/view/sru/01NLM_INST",
    help="The Alma institution SRU URL",
)
```

## Run

Interactive MMS ID prompt:

```bash
python unique_title_search_github.py
```

Direct MMS ID:

```bash
python unique_title_search_github.py --mms_id 9918237498127391
```

Optional SRU URL and result cap:

```bash
python unique_title_search_github.py --mms_id 9918237498127391 --sru_url "https://your-domain.alma.exlibrisgroup.com/view/sru/01YOUR_INST" --limit 4000
```

## Output
If no duplicate candidates are found:

```text
--- Validation Results ---
No matching records found. Title is unique!
--------------------------
```

If matches are found, results are sorted with the searched MMS first, then records with 130 values.