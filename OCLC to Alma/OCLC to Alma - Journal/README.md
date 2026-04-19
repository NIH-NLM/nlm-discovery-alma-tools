# OCLC to Alma - Journal

A programmatic workflow that automatically searches the OCLC WorldCat Metadata API by **ISSN**, evaluates the records, and pushes the best matching journal record into your **Ex Libris Alma** catalog.

This tool is designed for **librarians and library staff**, not just developers. It reduces repetitive manual cataloging work by automating the search, evaluation, and import of high-quality OCLC records directly into Alma.

---

## 🌟 What This Tool Does

When you run this script and input an **ISSN**, it will automatically:
1. **Check Alma** to see if the journal already exists in your catalog (preventing duplicates).
2. **Search OCLC WorldCat** for the ISSN.
3. **Filter** for English-cataloged records.
4. **Score and Evaluate** the records based on cataloging quality (Encoding levels, major cataloging agencies, presence of 022 $a assignments, etc.).
5. **Select** the highest-scoring record.
6. **Normalize** the MARCXML data.
7. **Import** the selected record directly into Alma.

---

## 🔐 How Configuration Works (Important)

For security and clarity, **API keys are never hardcoded into the scripts**. 

In the project folder, you will see two files:
- `alma_api_keys_github.txt`
- `oclc_api_keys_github.txt`

These files contain placeholder text. You must replace the placeholders with your actual API keys for the script to work. **Do not share your real keys or upload them to a public GitHub repository.**

---

## 📋 What You Will Need

1. **Python 3.9 or newer** installed on your computer.
2. An **Alma API Key** with read/write permissions for bibliographic records (a Sandbox key is heavily recommended for testing).
3. An **OCLC WSKey and Secret** with access to the WorldCat Metadata API.
4. Basic ability to run a Python script from a terminal or command prompt. No prior programming experience is required!

---

## 🚀 Setup Instructions

### 1️⃣ Install Python
If you don't have Python installed, download it from [python.org](https://www.python.org/downloads/). 
*Important: During installation on Windows, make sure to check the box that says **"Add Python to PATH"**.*

### 2️⃣ Download This Tool
Download or clone this repository to your computer.

### 3️⃣ Install Required Packages
This script uses a few external Python libraries (like `requests` for making API calls). Open your terminal/command prompt, navigate to the folder where you saved this tool, and run:

```bash
pip install -r requirements.txt
```

### 4️⃣ Configure Your API Keys

Open the two text files in a text editor (like Notepad) and update them with your real credentials:

**`alma_api_keys_github.txt`**:
```text
Alma API keys
alma_sandbox_key = "INSERT_YOUR_ALMA_KEY_HERE"
alma_production_key = "INSERT_YOUR_PRODUCTION_KEY_HERE"
```

**`oclc_api_keys_github.txt`**:
```text
oclc_wskey=INSERT_YOUR_OCLC_WSKEY_HERE
oclc_secret=INSERT_YOUR_OCLC_SECRET_HERE
```
*Note: The script currently defaults to looking for `alma_sandbox_key`. If you want to use production, you can update the script to look for `alma_production_key` instead.*

### 5️⃣ Run the Tool!
Open your terminal or command prompt, navigate to the folder, and run:

```bash
python journal_workflow.py
```

The program will prompt you:
`Please enter the issn you want to search for:`

Type your ISSN (e.g., `2632-6663`) and press Enter. The script will handle the rest!

---

## 🛠️ Sandbox vs Production

Whenever possible:
- Test the script using your **Alma Sandbox API key** first.
- Only switch to your Production API key after you have verified the results look correct in your Sandbox environment.
- Review the output in Alma to ensure the normalization and importing meet your institution's standards.

---

## ❓ Troubleshooting

If something doesn't work:
- **401 Unauthorized Error**: Double-check your API keys in the `.txt` files. Make sure there are no accidental spaces or quotes inside the key itself.
- **Python not found**: Ensure Python is installed and added to your system's PATH.
- **ModuleNotFoundError**: Make sure you ran `pip install -r requirements.txt` to install the necessary libraries.
- **Can't find Alma Record**: Ensure your Alma API key has the correct read/write permissions for bibliographic data.