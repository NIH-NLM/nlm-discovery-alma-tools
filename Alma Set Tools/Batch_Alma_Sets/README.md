# Batch Alma Sets Tool

## Overview
This standalone Python script takes one existing Alma itemized bibliographic set and splits it into multiple new itemized sets based on a batch size you choose.

It is designed as a shareable script version (like your other `_github.py` tools), so it does not require Django `views.py` or `forms.py`.

## What the Script Does
1. Reads the source Set ID and validates that the set exists.
2. Confirms the source set type is bibliographic (`BIB_MMS`).
3. Extracts all member MMS IDs from the source set.
4. Splits those MMS IDs into batches.
5. Creates one new itemized set per batch.
6. Adds each batch of MMS IDs into its new set.
7. Prints a per-batch success/failure summary.

## Prerequisites
- Python 3.10+
- `requests`

Install dependency:

```bash
pip install requests
```

## API Key Setup
Create a key file (for example `alma_api_keys.txt`) using this format:

```text
alma_sandbox_key = "your_sandbox_key"
alma_production_key = "your_production_key"
```

Then pass the file path with `--api_key_file`, or set the environment variable `ALMA_API_KEY_FILE`.

## Script File
Use:

```text
new_alma_set_for_batch_processing_github.py
```

## How to Run
Interactive mode:

```bash
python new_alma_set_for_batch_processing_github.py
```

Non-interactive example:

```bash
python new_alma_set_for_batch_processing_github.py --set_id 1234567890001234 --batch_size 500 --base_set_name "My Project" --environment sandbox --api_key_file "C:/path/to/alma_api_keys.txt" --yes
```

## Arguments
- `--set_id`: Source Alma Set ID to split.
- `--batch_size`: Number of records per new batch set.
- `--base_set_name`: Base name used for output sets (`<base> Batch 1`, `<base> Batch 2`, ...).
- `--environment`: `sandbox` or `production` (default: `sandbox`).
- `--api_key_file`: Path to API key file.
- `--yes`: Skip confirmation prompt.

## Notes
- This tool currently supports bibliographic sets only (`BIB_MMS`).
- Existing source set members are read in pages (100/page) and processed concurrently for performance.
- Member insertion uses chunked requests (up to 1000 IDs per request).
