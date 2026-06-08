# Move Authority Record from Alma Production to Sandbox

## Overview
This standalone Python script copies one authority record from Alma Production into Alma Sandbox.

It is the shareable script version for collaboration and does not depend on Django `views.py` or `forms.py`.

## What the Script Does
1. Reads one authority MMS ID.
2. Fetches the full authority record XML from Alma Production.
3. Removes system-assigned identifiers (`mms_id`, `linked_record_id`, `nz_mms_id`, `cz_mms_id`).
4. Creates the authority record in Alma Sandbox.
5. Prints the new Sandbox MMS ID and heading text (if available).

## Important Behavior
- The Sandbox copy receives a newly assigned MMS ID.
- The Production MMS ID cannot be preserved when creating a new authority in Sandbox.

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
copy_authority_prod_to_sandbox_github.py
```

## How to Run
Interactive mode:

```bash
python copy_authority_prod_to_sandbox_github.py
```

Non-interactive mode:

```bash
python copy_authority_prod_to_sandbox_github.py --auth_id 9912345678901234 --api_key_file "C:/path/to/alma_api_keys.txt"
```

## Arguments
- `--auth_id`: Authority MMS ID to copy from Production to Sandbox.
- `--api_key_file`: Path to API key file containing both production and sandbox keys.

## Output Example
```text
--- Result ---
Source authority MMS ID: 9912345678901234
New sandbox MMS ID: 9919988776655443
Heading: Smith, John, 1970-
--------------
```
