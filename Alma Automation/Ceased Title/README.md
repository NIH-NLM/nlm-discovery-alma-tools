# Ceased Title Updater for Alma

This script automates the process of updating catalog records in [Ex Libris Alma](https://exlibrisgroup.com/products/alma-library-services-platform/) when a serial title has ceased publication. Instead of manually editing each record, you provide a CSV of MMS IDs and ceased dates, and the script updates the appropriate MARC fields for you.

## What's in This Folder

| File | Purpose |
|---|---|
| `ceasedtitle2_github.py` | The Python script that does the work |
| `ceasedtitle.csv` | A sample CSV file showing the expected format |
| `alma_api_keys_github.txt` | A template for your Alma API key file |
| `README.md` | This guide |

## What the Script Changes

For each record in the CSV, the script updates these MARC fields:

| MARC Field | What Changes | Example |
|---|---|---|
| **008** (fixed-length) | Position 06 set to `d` (ceased); positions 11–14 filled with the end year | `......c20109999...` → `......d20102024...` |
| **260/264 $c** | Closes the open-ended publication date | `2010-` → `2010-2024` or `[2010]-` → `[2010]-[2024]` |
| **260/264 $3** | Closes the open-ended date range if present | `v.1 (2010)- :` → `v.1 (2010)-2024 :` |
| **362** (ind1=1) | Adds a "Ceased with..." note | `Began with v.1 (2010).` → `Began with v.1 (2010); ceased with v.14 no.4 (2024).` |
| **995 $d** | Stamps today's date as a review date | `$d 20260218` |

> **Note:** Records with a 510 field indicating current MEDLINE or PubMed indexing are automatically skipped because those titles require a different ceased-title workflow.

## Prerequisites

| Requirement | Details |
|---|---|
| **Python 3.6 or later** | [Download Python](https://www.python.org/downloads/) — during installation, check **"Add Python to PATH"** |
| **`requests` library** | A Python library for making web requests (installed in Step 1 below) |
| **Alma API key** | A key with **Bibs – Read/Write** permissions from the [Ex Libris Developer Network](https://developers.exlibrisgroup.com/) |

> **New to Python?** After installing, confirm it's working by opening a terminal (Command Prompt on Windows, Terminal on Mac) and typing `python --version`. You should see something like `Python 3.x.x`.

---

## Setup (One-Time)

### Step 1 — Install the required Python library

Open a terminal and run:

```
pip install requests
```

### Step 2 — Add your API key

1. Open the `alma_api_keys_github.txt` file included in this folder.
2. You'll see a placeholder line like:

   ```
   alma_sandbox_key = "your_actual_api_key_here"
   ```

3. Replace `your_actual_api_key_here` with your real Alma API key and save the file.

> ⚠️ **Important:** If you fork or clone this repository, **never commit your real API key to GitHub**. Add the key file to your `.gitignore` or only edit it locally.

### Step 3 — Update the script with your file paths

Open `ceasedtitle2_github.py` and make two small edits:

**Edit 1 — Point to your API key file (near the top of the script):**

Find this line:
```python
with open(r"your_file_path_here.txt") as f:
```

Replace it with the path to your copy of the key file. Since it's in the same folder, you can use:
```python
with open(r"alma_api_keys_github.txt") as f:
```

Or use a full path if you prefer to keep it elsewhere:
```python
with open(r"C:\Users\YourName\Documents\alma_api_keys_github.txt") as f:
```

**Edit 2 — Point to your CSV file (at the very bottom of the script):**

Find this line:
```python
process_csv('your_file_path/ceasedtitle.csv')
```

Replace it with the path to your CSV. Since it's in the same folder, you can use:
```python
process_csv('ceasedtitle.csv')
```

### Step 4 — Check your region

The script defaults to the **North America** API gateway. If your Alma instance is in a different region, update this line near the top:

```python
ALMA_API_BASE_URL = "https://api-na.hosted.exlibrisgroup.com/almaws/v1/bibs/"
```

| Region | Change `api-na` to |
|---|---|
| North America | `api-na` (default) |
| Europe | `api-eu` |
| Asia Pacific | `api-ap` |

---

## Preparing Your CSV

Open `ceasedtitle.csv` to see the expected format. The file needs two columns:

| MMS ID | Ceased date |
|---|---|
| 991234563456789 | v.50 no.4 (2024) |
| 997654321098765 | v.12 (2023) |

- **MMS ID** — The Alma MMS ID for the bibliographic record. You can find this in Alma on the record's details page.
- **Ceased date** — The last volume/issue/year published. The script extracts the 4-digit year from this text for the 008 and 260/264 fields, and uses the full text for the 362 note.

> **Tip:** You can export a list of MMS IDs from an Alma set or analytics report and add the "Ceased date" column manually.

---

## Running the Script

1. Open a terminal and navigate to this folder:

   ```
   cd "path\to\ceased title"
   ```

2. Run the script:

   ```
   python ceasedtitle2_github.py
   ```

3. The script will print progress as it works through your CSV:
   - Each row it processes
   - Whether a record was updated or skipped
   - Any errors (e.g., invalid MMS ID, API issues)

---

## What to Expect

**Successful update:**
```
CSV headers: ['MMS ID', 'Ceased date']
{'MMS ID': '991234563456789', 'Ceased date': 'v.50 no.4 (2024)'}
Starting to update 362 field with ceased date: v.50 no.4 (2024)
Successfully updated record for MMS ID 991234563456789
```

**Skipped record (MEDLINE/PubMed):**
```
Skipping MMS ID 997654321098765: Can't cease MEDLINE or PMC titles programmatically
```

**Common errors:**

| Message | Likely Cause |
|---|---|
| `Alma sandbox API key not found` | The key file is missing the `alma_sandbox_key = "..."` line, or the file path is wrong |
| `FileNotFoundError` | The file path to the key file or CSV doesn't match the actual location |
| `Failed to fetch record: 401` | Your API key is incorrect or expired |
| `Failed to fetch record: 403` | Your API key doesn't have **Bibs – Read/Write** permissions |
| `Failed to update record: 400` | Something in the modified XML is invalid — check the MMS ID and record in Alma |
| `Ceased date does not contain a valid year` | The "Ceased date" column doesn't include a 4-digit year |

---

## A Note About the 995 Field

The 995 is a **local field** used at this institution to track when a record was reviewed. Your library may not use the 995, or may use it differently. You can:

- **Remove** the `update_995_field` function and its call in `process_csv` if you don't need it.
- **Modify** it to match your local field and subfield codes.

---

## Testing Safely

We strongly recommend testing with your **Alma Sandbox** before running against production:

1. Generate a Sandbox API key from the [Developer Network](https://developers.exlibrisgroup.com/).
2. Use that key in `alma_api_keys_github.txt`.
3. Run the script against a small CSV (1–2 records) and verify the results in your Sandbox.
4. Once you're confident, switch to your Production API key.

---

## Questions or Issues?

If you run into problems or have questions about adapting this script for your library, feel free to open an issue on this GitHub repository.
