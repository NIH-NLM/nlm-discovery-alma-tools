# NLM Bib Record Validator

A command-line tool for validating and correcting MARCXML bibliographic records in Alma. Built for NLM catalogers to quickly check individual bib records against cataloging rules and automatically fix common errors.

---

## What does it do?

1. **You enter an MMS ID** and the tool fetches the full bib record from the Alma sandbox API.
2. **It checks the record** against hundreds of cataloging rules — 008 byte values, indicator settings, required subfields, IndexCat-specific conventions, and more.
3. **It sorts the results** into two groups:
   - **Auto-correctable** — issues the tool knows how to fix (e.g., wrong 245 first indicator, missing 008 genre code, date corrections from 260/264).
   - **Needs manual review** — issues that require a cataloger's judgment (e.g., ambiguous location codes, missing fields with no obvious default).
4. **You choose** whether to apply the auto-corrections and push the updated record back to Alma.

---

## Quick start

### Prerequisites

- **Python 3.9+** installed on your computer.
- The **requests** library (`pip install requests`).
- An **Alma API key** saved in a file on your Desktop called `alma_api_keys.txt`. The file should contain a line like:
  ```
  alma_sandbox_key = "your-api-key-here"
  ```

### Running the tool

1. Open a terminal (Command Prompt, PowerShell, or VS Code terminal).
2. Navigate to the `Bib validator` folder:
   ```
   cd "C:\...\Bib validator"
   ```
3. Run the CLI:
   ```
   python bib_validator_cli.py
   ```
4. When prompted, type an MMS ID and press Enter. Type `q` to quit.

> **Which script do I run?**  Always run **`bib_validator_cli.py`**. It is the only file you interact with directly. The other files are supporting code that it calls behind the scenes.

---

## What each file does

| File | Purpose |
|------|---------|
| **`bib_validator_cli.py`** | **← Run this one.** The interactive command-line tool. Handles prompting for MMS IDs, talking to the Alma API, displaying results, and pushing corrections. |
| `bib_validator.py` | The validation engine. Contains all the cataloging rules that check the record for errors. You never need to open or run this file directly. |
| `bib_marc_validator/` | A support package (folder) used by the validator. It contains the correction logic and helper functions for reading and editing MARCXML. |
| `bib_marc_validator/bib_xml_corrections.py` | The auto-correction logic. For each known error, this file contains the code that fixes it in the XML. |
| `bib_marc_validator/xml_helpers.py` | Low-level functions for reading specific parts of a MARC record (control fields, indicators, subfields). |
| `bib_marc_validator/xml_formatters.py` | Formatting utilities for MARCXML output. |
| `bib_marc_validator/resources/validation/marc_validation_resources.py` | Reference data used during validation (valid language codes, country codes, Unicode characters to remove, etc.). |

Files like `__init__.py` are standard Python boilerplate that allow the folders to be treated as packages. You can ignore them.

---

## Example session

```
============================================================
        NLM Bib Record Validator  (CLI Edition)
============================================================

------------------------------------------------------------
Enter a MMS ID (or 'q' to quit): 9910892303406676

Fetching bib record for MMS ID: 9910892303406676 ...
  ✓  Record retrieved successfully.
  Running validation …

  Found 8 issue(s):

  ── Auto-correctable (1) ──────────────────────
    1. 245 first indicator should be '0' when fields 100, 110, 111, or 130 are not present.

  ── Needs manual review (7) ─────────────────
    1. 008/15-17 = xxu, does a more specific location exist?
    2. 040 missing subfield(s): $b.
    3. Both 260 and 264 fields are missing.
    4. 008 Date 1 is empty.
    5. 008/18-21 contains a value other than blank or fill character (|) and 300 $b not present
    6. 008/7-14 are all 'blank'.
    7. CATALOGER: 336 $a is 'still image' but is missing required 655 $a values.

Apply auto-corrections and push to Alma? (y/n): y

  Pushing corrected record for MMS ID: 9910892303406676 ...
  ✓  Record updated successfully in Alma.

  ⚠  7 issue(s) still require manual review.
```

---

## Types of checks

The validator covers a wide range of cataloging rules, including:

- **008 fixed-field bytes** — dates, country codes, language, illustration codes, genre codes, biography, festschrift, conference, index indicators, encoding level, and more.
- **Leader values** — record type, bibliographic level, encoding level.
- **Required fields & subfields** — 040 $b, 041, 044, 245 indicators, 264/260 presence, 300, 336, 504, 655, and others.
- **Field consistency** — e.g., 655 genre terms matching 008 byte values, 504 bibliography notes matching 008/24-27, 300 $b matching 008/18-21.
- **IndexCat-specific rules** — punctuation in 245, 264, 300; Academic Dissertation checks; 590 bracket removal; illustration code ordering.
- **Indicator validation** — 041, 245, 264, 510, 856 indicators checked against record context.
- **Duplicate / conflicting fields** — multiple 362 fields, both 260 and 264 present, etc.

---

## Adapting for your library

This tool was built for the National Library of Medicine, so some checks are NLM-specific and won't apply to other libraries. You'll want to review `bib_validator.py` and comment out or delete any rules that aren't relevant to your cataloging practice. A few examples:

- **035 $9 checks** — NLM uses 035 $9 for local identifiers (e.g., NLM Unique IDs). Most libraries don't use this subfield and can remove these checks.
- **510 checks** — Some 510 validation (e.g., PMC-related rules) is specific to NLM's serials workflow.
- **655 $a checks** — These validate Medical Subject Heading (MeSH) publication types like "Academic Dissertation," "Bibliography," "Congress," etc. The 655 genre term checks are only relevant for medical libraries that assign MeSH terms. Non-medical libraries can safely remove or replace these with their own genre/form vocabulary rules.
- **999 / 950 / 992 / 994 fields** — These are local fields used internally at NLM. Any checks referencing them can be removed.

To disable a check, find it in `bib_validator.py` and either delete the block or comment it out by adding `#` at the start of each line.

---

## Customizing the API key location

By default the tool reads your API key from:

```
C:/Users/<your-username>/Desktop/alma_api_keys.txt
```

If your file is in a different location, open `bib_validator_cli.py` and change the path on the line that starts with `with open(...)`.

---

## Contributing

To add a new validation rule, edit `bib_validator.py` and add your check inside the `validate_marcxml_record()` function. If the new rule is auto-correctable, add the corresponding fix in `bib_marc_validator/bib_xml_corrections.py` inside the `correct_marc_error()` function. The CLI will automatically detect whether the new rule is fixable — no changes to `bib_validator_cli.py` are needed.
