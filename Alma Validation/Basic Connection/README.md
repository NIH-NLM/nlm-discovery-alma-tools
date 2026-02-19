# Alma API Connection Test

A simple Python script that verifies your library can connect to its [Ex Libris Alma](https://exlibrisgroup.com/products/alma-library-services-platform/) instance through the Alma API. You provide a MMS ID (the unique identifier for a bibliographic record in Alma), and the script retrieves and displays the title (MARC field 245 $a) from that record.

## Prerequisites

| Requirement | Details |
|---|---|
| **Python 3.6+** | [Download Python](https://www.python.org/downloads/) — during installation, check **"Add Python to PATH"** |
| **`requests` library** | Installed in the setup steps below |
| **Alma API key** | A read-only Production or Sandbox key with **Bibs - Read** permissions, generated from the [Ex Libris Developer Network](https://developers.exlibrisgroup.com/) |

> **New to Python?** After installing, you can confirm it's working by opening a terminal (Command Prompt on Windows, Terminal on Mac) and typing `python --version`. You should see a version number like `Python 3.x.x`.

## Setup

### 1. Install the required library

Open a terminal and run:

```
pip install requests
```

### 2. Create your API key file

The script reads your Alma API key from a plain text file so the key is never hardcoded in the script itself. **Do not commit this file to GitHub.**

1. Create a new text file anywhere on your computer (e.g., `alma_api_keys.txt`).
2. Add the following line, replacing the placeholder with your actual API key:

```
alma_sandbox_key = "your_actual_api_key_here"
```

3. Save the file and note the full file path (e.g., `C:\Users\YourName\Documents\alma_api_keys.txt`).

### 3. Update the script with your file path

Open `basic_connection_github.py` and find this line near the top:

```python
with open(r"your_file_path_here.txt") as f:
```

Replace `your_file_path_here.txt` with the full path to your API key file. For example:

```python
with open(r"C:\Users\YourName\Documents\alma_api_keys.txt") as f:
```

> **Tip:** The `r` before the quotes means "raw string" — it ensures backslashes in Windows file paths are read correctly.

### 4. Check your region

The script defaults to the **North America** API gateway (`api-na`). If your Alma instance is hosted in a different region, update this line:

```python
ALMA_API_BASE_URL = "https://api-na.hosted.exlibrisgroup.com/almaws/v1/bibs/"
```

| Region | URL prefix |
|---|---|
| North America | `api-na` |
| Europe | `api-eu` |
| Asia Pacific | `api-ap` |

## Running the Script

1. Open a terminal and navigate to the folder containing the script:

   ```
   cd path\to\your\folder
   ```

2. Run the script:

   ```
   python basic_connection_github.py
   ```

3. When prompted, enter an MMS ID from your Alma instance (e.g., `991234563456789`).

## What to Expect

**Successful connection:**

```
Enter a MMS ID: 991234563456789
245 $a: The title of the record.
```

**Common errors:**

| Message | Likely cause |
|---|---|
| `Failed to fetch record: 400` | The MMS ID is invalid or doesn't exist in your Alma instance |
| `Failed to fetch record: 401` | Your API key is incorrect or lacks the required permissions |
| `Failed to fetch record: 403` | Your API key doesn't have access to the Bibs API |
| `Alma sandbox API key not found` | The key file is missing the `alma_sandbox_key = "..."` line |
| `FileNotFoundError` | The file path in the script doesn't match where your key file is saved |

## Security Reminder

**Never commit your API key to GitHub.** If you plan to push this repository, add your key file to `.gitignore`:

```
alma_api_keys.txt
```

## Next Steps

Once you've confirmed a successful connection, you can expand the script to:

- Retrieve other MARC fields (e.g., 100 $a for author, 020 $a for ISBN)
- Loop through a list of MMS IDs from a spreadsheet
- Update or create records using Alma's PUT and POST endpoints

For more on the Alma API, see the [Ex Libris Alma REST API documentation](https://developers.exlibrisgroup.com/alma/apis/).
