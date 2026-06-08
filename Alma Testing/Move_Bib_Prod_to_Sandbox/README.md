# Move Bib Record from Alma Production to Sandbox

## Overview
This standalone Python script copies one bibliographic record from Alma Production into Alma Sandbox, including attached inventory.

It is the shareable script version for collaboration and does not depend on Django `views.py` or `forms.py`.

## What the Script Does
1. Reads one bib MMS ID.
2. Fetches the bib XML from Alma Production.
3. Removes system-assigned identifiers and creates the bib in Alma Sandbox.
4. Copies all holdings and their items from Production to the new Sandbox bib.
5. Copies all electronic portfolios from Production to the new Sandbox bib.
6. Prints the new Sandbox MMS ID, title, inventory counts, and a detailed activity log.

## Important Behavior
- The Sandbox bib receives a newly assigned MMS ID.
- Original Production MMS ID and inventory IDs are not preserved.
- Script continues when individual holdings/items/portfolios fail and logs those errors.

## Prerequisites
- Python 3.10+
- `requests`

Install dependency:

```bash
pip install requests
```

## API Key Setup
Create a key file such as `alma_api_keys.txt` with the following keys:

```text
alma_sandbox_key = "your_sandbox_key"
alma_production_key = "your_production_key"
```

Then pass the path using `--api_key_file`, or set environment variable `ALMA_API_KEY_FILE`.

## Script File
Use:

```text
copy_prod_to_sandbox_github.py
```

## How to Run
Interactive mode:

```bash
python copy_prod_to_sandbox_github.py
```

Non-interactive mode:

```bash
python copy_prod_to_sandbox_github.py --mms_id 9912345678901234 --api_key_file "C:/path/to/alma_api_keys.txt"
```

## Arguments
- `--mms_id`: Bib MMS ID to copy from Production to Sandbox.
- `--api_key_file`: Path to API key file containing both production and sandbox keys.

## Output Example
```text
--- Result ---
Source MMS ID: 9912345678901234
New sandbox MMS ID: 9919988776655443
Title (245$a): Example journal title
Holdings copied: 2
Portfolios copied: 1

Log:
- Bib created in Sandbox - MMS ID: 9919988776655443
- Holding 22111111110006676 (MAIN) -> 22222222220006676
-   Item 23111111110006676 -> 23222222220006676
- Portfolio 53333333330006676 -> 54444444440006676
--------------
```
