# Alma Unique Title Search Tool

## Overview
This Python script checks an Alma bibliographic record against an institution's Alma catalog to determine if its title is truly "unique" according to Resource Description and Access (RDA) guidelines. If the title is not unique (i.e., another record shares the exact same base title), the script will surface the other matching records, allowing catalogers to see conflicts and apply the appropriate uniform title (130 field) or qualifiers to differentiate them.

## Why is this tool needed?
Under RDA rules, titles for serials, integrating resources, and certain monographs must be unique. When a new resource has the exact same title as an existing resource, catalogers must break the conflict by adding a uniform title (MARC 130) with qualifiers (such as place of publication or corporate body). 

**The Challenge with Alma:**
Searching natively in Alma to determine title uniqueness is notoriously difficult:
1. **Over-Indexing:** Alma's default "Title" search index brings in too many extraneous MARC fields (like alternative titles, added entries, and series titles), returning a flood of false positives.
2. **Subfield Clutter:** Even with Alma's new custom index functionality—which allows institutions to index the MARC 245 field specifically—the search results are still skewed because subfields `$b` (remainder of title) and `$c` (statement of responsibility) are included. 
3. **Punctuation and Diacritics:** Direct string matches often fail when one record has diacritics, trailing brackets, or specific RDA punctuation, making it hard to find true conflicts.

**The Solution:**
This tool programmatically strips out the noise. It fetches a specific record, isolates the core unique title elements (245 `$a`, `$n`, and `$p`), normalizes the string by stripping out punctuation, brackets, and diacritics, and then runs an automated Search/Retrieve via URL (SRU) query against the Alma catalog. It returns only true conflicts, sorted so that existing uniform titles (130 fields) appear at the top, immediately showing the cataloger what qualifiers have already been used.

## How it Works
1. **Retrieve:** The script connects to the Alma API using a system MMS ID and fetches the full MARCXML of the target bibliographic record.
2. **Isolate and Normalize:** It extracts the base title (MARC 245 subfields `$a`, `$n`, and `$p`), truncates it at the first RDA delimiter (like `/`, `:`, or `=`), strips all punctuation and diacritics, and normalizes it to a basic lowercase string. 
3. **Query:** It formulates an SRU search query and bounces it against the institution's Alma catalog.
4. **Compare:** For every record returned by the SRU search, the script runs the exact same normalization logic on its 245 and 130 fields, comparing them directly against the target string. 
5. **Output:** True matches are printed to the terminal, highlighting the MMS ID, the 130 field (if present), and the 245 field. 

## Setup & Configuration for Developers

### Prerequisites
* Python 3.x
* `requests` module (`pip install requests`)
* An Alma API Key with Read/Write access to Bibliographic Records
* Your Institution's Alma SRU URL

### Configuring the API Key
By default, the script looks for a text file located at `C:/Users/{your_user_name}/Desktop/alma_api_keys.txt` containing a line like:
```text
alma_sandbox_key = "YOUR_API_KEY_HERE"
```
*(You must modify the `api_key_file` variable in `unique_title_search.py` to match the actual path to your key file or supply the key via environment variables if preferred).*

### Configuring the SRU Endpoint
Open `unique_title_search.py` and modify the default `--sru_url` argument in the `main()` function to point to your institution's specific endpoint. For example, change the domain (`nlm.alma.exlibrisgroup.com`) and institution code (`01NLM_INST`) to your specific organization's values:

```python
# Change the domain and institution code (01NLM_INST) in the default URL below to match your own Alma institution's SRU endpoint
parser.add_argument('--sru_url', default="https://nlm.alma.exlibrisgroup.com/view/sru/01NLM_INST", help="The Alma institution SRU URL")
```

## How to Run (For Catalogers / Librarians)
From your terminal or command prompt, run the script:

```bash
python unique_title_search.py
```

The terminal will prompt you to enter the MMS ID of the record you are cataloging:
```bash
Enter the MMS ID: 9918237498127391
```

*(Alternatively, you can skip the prompt by passing the MMS ID directly):*
```bash
python unique_title_search.py --mms_id 9918237498127391
```

### Understanding the Output
If no matching records exist, the terminal will confirm the title is unique:
```text
--- Validation Results ---
No matching records found. Title is unique!
```

If conflicts *do* exist in the catalog, it will populate a list of matching records, heavily prioritizing existing Uniform Titles (130 fields) so you know how to qualify the new record:

```text
--- Validation Results ---
Found 2 potential duplicate(s) with matching titles:

Result #1:
  MMS ID: 9916535703406676
  130 field: Nanomedicine (Ge)
  245 field: Nanomedicine / Yi Ge, Songjun Li, Shenqi Wang, Richard Moore, editors.
  Normalized Hit String: nanomedicine

Result #2:
  MMS ID: 9916535702131234
  245 field: Nanomedicine.
  Normalized Hit String: nanomedicine
--------------------------
```