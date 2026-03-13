# URL Redirect Processor (XLSX Template)

This script is a generic template for libraries that need to normalize Alma video record URLs in a spreadsheet, follow redirects, and capture the final destination URL.

It can run without an API key for regular web URLs, and it can optionally use an Alma API key when URLs point to Alma API endpoints.

## What's in This Folder

| File | Purpose |
|---|---|
| `url_redirect.py` | Original local version used for initial processing |
| `url_redirect_github.py` | Generic, reusable template script |
| `URL_Redirects_input.xlsx` | Sample input workbook |
| `URL_Redirects_output.xlsx` | Sample output workbook |
| `README.md` | This guide |

## What the Script Does

This workflow is intended for Alma bibliographic records for video resources where URL patterns need cleanup before or during migration and validation work.

For each row in your spreadsheet:

1. Reads the source URL from a specified header (default: `Uniform Resource Identifier`).
2. Writes a `Converted URL` value:
   - If URL contains `watch=`, copy as-is.
   - If URL contains `launch.asp?`, convert it to `watch=`.
   - Otherwise write `manual cleanup`.
3. Requests each `watch=` URL and follows redirects.
4. Writes the final destination URL to `Redirected URL`.
   - If no redirect or request failure: `no redirect`.

The script supports cells with multiple URLs separated by commas.

## Prerequisites

| Requirement | Details |
|---|---|
| Python 3.9+ | [Download Python](https://www.python.org/downloads/) |
| `openpyxl` | Read/write XLSX files |
| `requests` | Follow web redirects |

Install dependencies:

```bash
pip install openpyxl requests
```

## Usage

Run from this folder or provide full paths:

```bash
python url_redirect_github.py URL_Redirects_input.xlsx
```

By default, output is written to `<input_stem>_output.xlsx`.

### Common options

```bash
python url_redirect_github.py input.xlsx -o output.xlsx
python url_redirect_github.py input.xlsx --source-column "URL"
python url_redirect_github.py input.xlsx --timeout 20 --delay 0.25 --save-every 25
python url_redirect_github.py input.xlsx --alma-api-key "YOUR_ALMA_KEY"
python url_redirect_github.py input.xlsx --alma-api-key-file alma_api_keys.txt
```

## Command-Line Arguments

| Argument | Default | Description |
|---|---|---|
| `input_xlsx` | (required) | Input workbook path |
| `-o, --output-xlsx` | `<input>_output.xlsx` | Output workbook path |
| `--source-column` | `Uniform Resource Identifier` | Header containing source URLs |
| `--converted-column` | `Converted URL` | Header for normalized URLs |
| `--redirected-column` | `Redirected URL` | Header for final redirected URLs |
| `--timeout` | `15` | Per-request timeout (seconds) |
| `--delay` | `0.5` | Delay between requests (seconds) |
| `--save-every` | `50` | Save workbook every N rows |
| `--alma-api-key` | none | Alma API key (optional) |
| `--alma-api-key-file` | none | File containing `alma_api_key = "..."` (optional) |

## Alma API Key Behavior

- The API key is optional and mainly useful for Alma-specific URL checks.
- If provided, the script appends `apikey` only to Alma API URLs (`hosted.exlibrisgroup.com` with `/almaws/` in the path).
- The key is not added to non-Alma external URLs.
- You can also set `ALMA_API_KEY` as an environment variable instead of passing it on the command line.

### Tiny sample key file

Create a text file such as `alma_api_keys.txt` with one of these formats:

```text
alma_api_key = "YOUR_ALMA_API_KEY"
```

or simply:

```text
YOUR_ALMA_API_KEY
```

Then run:

```bash
python url_redirect_github.py input.xlsx --alma-api-key-file alma_api_keys.txt
```

## Notes for Adapting at Another Library

- You can keep your existing spreadsheet format and point `--source-column` to the correct header.
- You can rename output columns using `--converted-column` and `--redirected-column`.
- If your URLs need different conversion rules, edit `convert_url_value()` in `url_redirect_github.py`.

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `source column ... not found` | Header in row 1 does not match | Use `--source-column` with exact header text |
| Many `manual cleanup` values | URLs do not match current patterns | Extend `convert_url_value()` for local URL patterns |
| Many `no redirect` values | Request timeout, blocked host, or no redirect exists | Increase `--timeout`, test URLs in browser, verify network access |
| Script is slow | Large file plus delay between requests | Lower `--delay` carefully and keep polite request pacing |
