# Alma Video URL Redirect Processor (XLSX Template)

This script supports Alma video record workflows where URL fields need to be normalized and validated by following redirects. It reads an XLSX file, creates converted URL values, follows redirect chains, and writes final destinations back to a new XLSX file.

It works in two modes:

- Generic mode (no API key) for normal web URLs.
- Alma-aware mode (optional API key) for Alma API endpoint URLs.

---

## Table of Contents

1. [What the Script Does](#what-the-script-does)
2. [What's in This Folder](#whats-in-this-folder)
3. [Prerequisites](#prerequisites)
4. [Setup](#setup)
5. [Spreadsheet Format](#spreadsheet-format)
6. [Running the Script](#running-the-script)
7. [URL Conversion and Redirect Logic](#url-conversion-and-redirect-logic)
8. [Alma API Key Options](#alma-api-key-options)
9. [Command-Line Arguments](#command-line-arguments)
10. [Troubleshooting](#troubleshooting)

---

## What the Script Does

This workflow is intended for Alma bibliographic records for video resources where URL patterns need cleanup before or during migration and validation work.

For each row in your spreadsheet the script:

1. Reads the source URL from a header column (default: `Uniform Resource Identifier`).
2. Writes a converted URL value in a new column.
3. Follows redirects for converted `watch=` URLs.
4. Writes the final destination URL to another new column.

The script supports cells containing multiple URLs separated by commas.

---

## What's in This Folder

| File | Purpose |
|---|---|
| `url_redirect_github.py` | Generic, reusable template script |
| `URL_Redirects_input.xlsx` | Sample input workbook |
| `URL_Redirects_output.xlsx` | Sample output workbook |
| `README.md` | This guide |

---

## Prerequisites

| Requirement | Details |
|---|---|
| Python 3.9+ | [Download Python](https://www.python.org/downloads/) |
| `openpyxl` | Read/write XLSX files |
| `requests` | Perform HTTP requests and follow redirects |

Install dependencies:

```bash
pip install openpyxl requests
```

---

## Setup

### 1. Place your input workbook

Prepare an `.xlsx` file with a header row containing your URL column.

### 2. Confirm the source header

The default source header is:

```text
Uniform Resource Identifier
```

If your library uses a different header, pass it with `--source-column`.

### 3. (Optional) Prepare an Alma API key file

If you need Alma API endpoint checks, create a small key file such as `alma_api_keys.txt`:

```text
alma_api_key = "YOUR_ALMA_API_KEY"
```

or simply:

```text
YOUR_ALMA_API_KEY
```

---

## Spreadsheet Format

### Input

| Column | Required | Description |
|---|---|---|
| Source URL header (default `Uniform Resource Identifier`) | Yes | URL(s) to process |

### Output columns added by script

| Column | Description |
|---|---|
| `Converted URL` | URL copied or normalized to `watch=` format, else `manual cleanup` |
| `Redirected URL` | Final redirected URL, else `no redirect` |

---

## Running the Script

Basic usage:

```bash
python url_redirect_github.py URL_Redirects_input.xlsx
```

By default, output is written to:

```text
<input_stem>_output.xlsx
```

Common examples:

```bash
python url_redirect_github.py input.xlsx -o output.xlsx
python url_redirect_github.py input.xlsx --source-column "URL"
python url_redirect_github.py input.xlsx --timeout 20 --delay 0.25 --save-every 25
python url_redirect_github.py input.xlsx --alma-api-key "YOUR_ALMA_KEY"
python url_redirect_github.py input.xlsx --alma-api-key-file alma_api_keys.txt
```

---

## URL Conversion and Redirect Logic

### Conversion rules (`Converted URL`)

| Condition | Result |
|---|---|
| URL contains `watch=` | Copy as-is |
| URL contains `launch.asp?` | Convert `launch.asp?` to `watch=` |
| URL is empty or unmatched | `manual cleanup` |

### Redirect rules (`Redirected URL`)

| Condition | Result |
|---|---|
| Converted value contains `watch=` | Request URL and store final redirected destination |
| Redirect result equals original URL | `no redirect` |
| Request error or timeout | `no redirect` |
| Converted value is `manual cleanup` | `no redirect` |

---

## Alma API Key Options

The API key is optional and mainly useful for Alma-specific URL checks.

- If provided, the script appends `apikey` only to Alma API URLs (`hosted.exlibrisgroup.com` with `/almaws/` in the path).
- The key is never appended to non-Alma external URLs.
- You can pass the key by argument, key file, or environment variable.

Environment variable option:

```bash
set ALMA_API_KEY=YOUR_ALMA_API_KEY
python url_redirect_github.py input.xlsx
```

---

## Command-Line Arguments

| Argument | Default | Description |
|---|---|---|
| `input_xlsx` | (required) | Input workbook path |
| `-o, --output-xlsx` | `<input>_output.xlsx` | Output workbook path |
| `--source-column` | `Uniform Resource Identifier` | Header containing source URLs |
| `--converted-column` | `Converted URL` | Header for normalized URLs |
| `--redirected-column` | `Redirected URL` | Header for final redirected URLs |
| `--timeout` | `15` | Per-request timeout in seconds |
| `--delay` | `0.5` | Delay between requests in seconds |
| `--save-every` | `50` | Save workbook every N rows |
| `--alma-api-key` | none | Alma API key (optional) |
| `--alma-api-key-file` | none | File containing `alma_api_key = "..."` or plain key (optional) |

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `source column ... not found` | Header in row 1 does not match | Use `--source-column` with exact header text |
| Many `manual cleanup` values | URLs do not match current conversion patterns | Extend `convert_url_value()` in the script |
| Many `no redirect` values | Timeout, blocked host, or no redirect exists | Increase `--timeout`, test URLs in browser, verify network access |
| Script runs slowly | Large sheet with delay between requests | Lower `--delay` carefully and keep request pacing polite |
| Alma API URL checks fail | Missing/invalid API key | Provide `--alma-api-key`, `--alma-api-key-file`, or `ALMA_API_KEY` |
