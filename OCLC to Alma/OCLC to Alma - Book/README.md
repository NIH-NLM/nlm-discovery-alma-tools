# OCLC to Alma Integration Workflow

Welcome! This tool streamlines the process of importing book records from OCLC directly into your Alma institution. It is designed to be librarian-friendly and reduces manual data entry so you can catalog items much faster.

---

## 🚀 What Does This Program Do?

When you run this script and input an ISBN, it performs the following steps in the background:

1. **Checks Alma to Prevent Duplicates**:
   It immediately uses the Alma SRU connection (Search/Retrieve via URL) to query your local Alma catalog for the requested ISBN. If an existing record is found, it will warn you so you don't accidentally create a duplicate.
2. **Searches OCLC WorldCat**:
   If no local match is found, it queries the OCLC WorldCat Metadata API to find all records associated with that ISBN.
3. **Filters for English Cataloging**:
   It automatically filters out non-English cataloging records (usually indicated by MARC field 040 language codes) to ensure you import standard records.
4. **Scores the Remaining Records**:
   To find the "best" and most complete record from OCLC, it uses a scoring algorithm based on MARC cataloging standards (details below).
5. **Prepares the Import**:
   The highest-scoring OCLC record is then grabbed, and the tool can push it into Alma, linking it into your catalog seamlessly.

---

## 🏆 How Are OCLC Records Scored?

Sometimes there are many records for the same ISBN. To pick the best one, the program scores them automatically using these rules:

1. **Full-Level Cataloging (+100 points)**:
   It checks the Encoding Level (Leader/17). If the level indicates full completeness (such as blank `' '`, `'I'`, `'L'`, `'M'`, or `'1'`), the record earns 100 points.
2. **Pre-Publication / CIP (+80 points)**:
   If the record is Level `8` (Cataloging in Publication/Pre-publication), it gets 80 points because it's still an excellent source of metadata.
3. **Major Cataloging Agency (+50 points)**:
   If the record was created by a major trusted agency (MARC field 040 $a)—like the Library of Congress (`DLC`), National Library of Medicine (`NLM`), British Library (`BL`), or Library and Archives Canada (`NLC`)—it gets a 50-point bonus.
4. **Tie-Breaker (Oldest OCLC Number Wins)**:
   If multiple records have the exact same score, the system selects the one with the smallest OCLC number, assuming the original/older master record is usually best.

---

## 🛠️ How to Connect This Tool to Your Institution

If you are setting this up for a new library or a new librarian's workstation, you will need to modify two things: **Authentication Keys** and the **Alma URL settings**. 

### 1. Set Up Your API Keys (No Code Changes Needed!)
For security, the script looks for text files on the user's **Desktop**. This ensures you never accidentally share passwords if you share the code.

1. **Create an Alma Key File:**
   - Create a text file directly on your desktop named: `alma_api_keys.txt`
   - Paste in your Alma Sandbox (or Production) key like this:
     ```text
     alma_sandbox_key="l7xx1234567890abcdefg"
     ```
2. **Create an OCLC Key File:**
   - Create another text file on your desktop named: `oclc_api_keys.txt`
   - Paste in your OCLC Web Service Key and Secret:
     ```text
     oclc_wskey="your_oclc_wskey_here"
     oclc_secret="your_oclc_secret_here"
     ```

*(The program automatically reads these files every time it runs.)*

### 2. Update the Alma SRU URL in the Code

Currently, the script is configured to talk to the **NLM Premium Sandbox** (`01NLM_INST`). To connect to your specific institution's catalog, you need to open `book_workflow.py` and modify standard URLs:

1. Open `book_workflow.py`.
2. Locate the line that defines `alma_sru_url`. It currently looks like this:
   ```python
   alma_sru_url = "https://nlm-psb.alma.exlibrisgroup.com/view/sru/01NLM_INST"
   ```
3. Change it to match your institution's SRU endpoint. 
   - **For Sandbox**: Usually formatted as `https://<YOUR-PREFIX>-psb.alma.exlibrisgroup.com/view/sru/<YOUR_INST_CODE>`
   - **For Production**: Usually formatted as `https://<YOUR-PREFIX>.alma.exlibrisgroup.com/view/sru/<YOUR_INST_CODE>`

*Note on the Alma API Base URL: As long as you provide the correct API key, the standard base URL (`https://api-na.hosted.exlibrisgroup.com/almaws/v1/bibs`) will automatically detect whether to route your request to your Production or Sandbox environment!*

---

**That's it!** With the text files on your desktop and your institution's SRU URL updated, you are ready to start importing items effortlessly.

---

## 🙏 Acknowledgements & Inspiration

This project was inspired by the excellent work done on **[Snapicat](https://github.com/boston-library/snapicat)** by the Boston Public Library. While this codebase was written independently, Snapicat provided the foundational inspiration for the concept of connecting to the OCLC API to programmatically evaluate, score, and automatically select the highest-quality MARC records to bring into Alma.