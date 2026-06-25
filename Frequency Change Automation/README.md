# Alma Serial Frequency Change Automation

A Python script that automates MARC 21 bibliographic record updates for serial frequency changes in **Ex Libris Alma**. Given a spreadsheet of MMS IDs and their new publication frequencies, the script fetches each bib record, applies the correct MARC changes, and writes the record back to Alma via the REST API.

---

## What the script changes

| MARC field | Action |
|---|---|
| **310** (Current Publication Frequency) | Replaced with the new frequency and effective year (`$a`, `$b YYYY-`) |
| **321** (Former Publication Frequency) | Old 310 value is demoted here; existing 321 fields are kept and sorted chronologically |
| **008** positions 18–19 | Updated with the correct frequency (`008/18`) and regularity (`008/19`) codes per LOC |
| **515** (Note – Numbering Peculiarities) | Added or updated for continuously-published serials (optional column) |

---

## Requirements

- Python 3.9 or later
- The following packages (install with `pip`):

```bash
pip install requests pymarc pandas openpyxl
```

---

## API Key – security first

**Never hard-code your Alma API key in the script or commit it to version control.**

The script looks for your API key in this order:

| Priority | Method |
|---|---|
| 1 | `--api-key YOUR_KEY` command-line flag |
| 2 | `ALMA_API_KEY` environment variable |
| 3 | Plain-text key file (`alma_sandbox_key.txt` or `alma_production_key.txt`) in the working directory |
| 4 | Custom key file path via `--api-key-file /path/to/keyfile.txt` |

### Setting the environment variable

**macOS / Linux**
```bash
export ALMA_API_KEY="your_alma_api_key_here"
```

**Windows (PowerShell)**
```powershell
$env:ALMA_API_KEY = "your_alma_api_key_here"
```

**Windows (Command Prompt)**
```cmd
set ALMA_API_KEY=your_alma_api_key_here
```

### Using a key file

Create a plain-text file named `alma_sandbox_key.txt` (or `alma_production_key.txt`) with only the key on the first line:

```
your_alma_api_key_here
```

Add these files to `.gitignore` to prevent accidental commits:

```
# .gitignore
alma_sandbox_key.txt
alma_production_key.txt
*.key
```

---

## Generating an Alma API Key

1. Log in to the **Ex Libris Developer Network**: https://developers.exlibrisgroup.com
2. Register your application and request a key scoped to **Bibs → Read/Write**.
3. Use the **Sandbox** key for testing and the **Production** key only when you are ready to apply real changes.

> **Regional API base URLs** — the script defaults to the North America endpoint (`api-na`). Edit `AlmaClient.DEFAULT_BASE_URL` in the script if your institution uses a different region:
> - Europe: `https://api-eu.hosted.exlibrisgroup.com/almaws/v1`
> - Asia-Pacific: `https://api-ap.hosted.exlibrisgroup.com/almaws/v1`
> - Canada: `https://api-ca.hosted.exlibrisgroup.com/almaws/v1`

---

## Input spreadsheet format

Use the provided `frequency_changes_template.csv` as a starting point. Save as `.csv` or `.xlsx`.

| Column | Required | Description |
|---|---|---|
| `MMS ID` | **Yes** | Alma bibliographic MMS identifier |
| `New Frequency` | **Yes** | Human-readable frequency (see supported values below) |
| `Effective Year` | **Yes** | Year the new frequency begins (e.g. `2024`) |
| `Continuous Publication` | No | `yes` / `true` / `1` to add/update a 515 note |
| `Note Override` | No | Custom 515$a text; overrides the default note when provided |
| `Source URL` | No | URL for the journal or change reference (stored in the change plan and logs) |

### Supported frequency values

| Input value | 310$a text | 008/18 | 008/19 |
|---|---|---|---|
| `Annual` | Annual | a | r |
| `Semiannual` / `Semi-annual` / `Biannual` / `Twice a year` | Semiannual | f | r |
| `Quarterly` / `Four times a year` | Quarterly | q | r |
| `Bimonthly` | Bimonthly | b | r |
| `Six issues a year` | Six issues a year | b | x |
| `Monthly` / `12 issues per year` | Monthly / 12 issues/year | m | r/x |
| `Semimonthly` / `Twice a month` | Semimonthly | s | x |
| `Weekly` | Weekly | w | r |
| `Biweekly` | Biweekly | e | r |
| `Daily` | Daily | d | r |
| `Three times a year` / `Triannual` | Three times a year | t | r |
| `Three times a week` | Three times a week | i | r |
| `Three times a month` | Three times a month | j | r |
| `Biennial` | Biennial | g | r |
| `Triennial` | Triennial | h | r |
| `Continuously updated` | Continuously updated | k | r |
| `10 issues per year` / `11 issues per year` | 10/11 issues/year | m | x |
| `21 issues per year` | 21 issues per year | z | x |
| `Irregular` / `Completely irregular` | Irregular | x | x |

> Lookups are case-insensitive. Unsupported values are skipped and logged.

---

## Change plan (RecordUpdatePlan)

Before writing anything to Alma, the script builds a **change plan** for every record and logs it as a JSON object. This lets you inspect intent before committing changes.

Example log entry:

```json
{
  "mms_id": "991234567890123",
  "current_310": "Bimonthly",
  "new_310": "Monthly",
  "new_321_entries": [
    {"frequency": "Bimonthly", "date": "2016-2025"}
  ],
  "o008_frequency": "m",
  "o008_regularity": "r",
  "add_515": false,
  "note": null,
  "source_url": "https://example.org/journal"
}
```

The plan is always written to the log regardless of dry-run or execute mode.

---

## Usage

### Dry run (default – no changes written to Alma)

```bash
python alma_frequency_change_automation.py frequency_changes.csv
```

### Apply changes to Alma sandbox

```bash
python alma_frequency_change_automation.py frequency_changes.csv --execute
```

### Apply changes to Alma production

```bash
python alma_frequency_change_automation.py frequency_changes.csv --environment production --execute
```

### Save detailed output files

```bash
python alma_frequency_change_automation.py frequency_changes.csv \
    --execute \
    --save-output-files \
    --output-dir ./run_output_2024
```

This writes:
- `run_results_TIMESTAMP.csv` — per-row status (SUCCESS / SKIPPED / FAILED)
- `run_events_TIMESTAMP.jsonl` — machine-readable event log
- `automation_TIMESTAMP.log` — human-readable log

### Save BEFORE / AFTER XML snapshots for review

```bash
python alma_frequency_change_automation.py frequency_changes.csv \
    --updated-xml-dir ./xml_snapshots
```

Creates `BEFORE-<MMS_ID>.xml` and `AFTER-<MMS_ID>.xml` for each record — useful for cataloger review before committing changes.

### Interactive guided mode

```bash
python alma_frequency_change_automation.py --manual
```

Prompts for each setting; useful for staff running the script without a terminal.

### Test MARC transformation locally (no Alma connection)

Compare the script's output against a known-good AFTER XML without touching Alma:

```bash
python alma_frequency_change_automation.py \
    --test-before-xml BEFORE-9912345678901234.xml \
    --test-after-xml  AFTER-9912345678901234.xml  \
    --test-frequency  Monthly \
    --test-effective-year 2024 \
    --test-008-freq m \
    --test-008-reg  r
```

Exit codes: `0` = PASS, `1` = field mismatch, `2` = XML parse error.

---

## Full CLI reference

```
usage: alma_frequency_change_automation.py [-h] [--manual] [--execute]
       [--environment {sandbox,production}]
       [--api-key API_KEY] [--api-key-file API_KEY_FILE]
       [--output-dir OUTPUT_DIR] [--save-output-files]
       [--updated-xml-dir UPDATED_XML_DIR]
       [--test-before-xml TEST_BEFORE_XML] [--test-after-xml TEST_AFTER_XML]
       [--test-frequency TEST_FREQUENCY] [--test-effective-year YEAR]
       [--test-008-freq CODE] [--test-008-reg CODE]
       [--test-continuous] [--test-note-text TEXT]
       [--test-generated-xml-out PATH]
       [input_file]

positional arguments:
  input_file            Path to the input spreadsheet (.csv or .xlsx)

options:
  --manual              Guided interactive prompts
  --execute             Apply changes to Alma (default: dry run)
  --environment         sandbox | production (default: sandbox)
  --api-key             Alma API key (overrides ALMA_API_KEY env var)
  --api-key-file        Path to a plain-text file containing the API key
  --output-dir          Directory for output files (default: .)
  --save-output-files   Write CSV / JSONL / log output files
  --updated-xml-dir     Write BEFORE/AFTER XML snapshots to this directory
  --test-*              Local MARC comparison mode (see above)
```

---

## Workflow recommendation

1. **Prepare** your spreadsheet using `frequency_changes_template.csv`.
2. **Dry run** against the sandbox (`--environment sandbox`) to verify the script reads all rows correctly.
3. **Review snapshots** by adding `--updated-xml-dir ./xml_snapshots` and inspecting the generated AFTER XML files.
4. **Execute** in sandbox (`--execute --environment sandbox`) and confirm records look correct in the Alma UI.
5. **Execute** in production (`--execute --environment production`) once satisfied.

---

## Project structure

```
alma_frequency_change_automation.py   ← main script (this file)
frequency_changes_template.csv        ← sample input spreadsheet
README.md                             ← this file
alma_sandbox_key.txt                  ← your sandbox API key (do NOT commit)
alma_production_key.txt               ← your production API key (do NOT commit)
```

---

## Contributing

Pull requests are welcome. Please:
- Keep API keys out of all committed files.
- Add or update the template CSV if you extend the input format.
- Test changes locally using `--test-before-xml` / `--test-after-xml` before opening a PR.

---

## License

MIT — see `LICENSE` file for details.
