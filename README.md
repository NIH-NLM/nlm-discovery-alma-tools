# Alma Validation & Automation Toolkit (Python + Alma API)

A collection of Python scripts for validating data, improving metadata
quality, and automating workflows in **Ex Libris Alma** using the Alma
API.

This repository is designed for **librarians and library staff**, not
just developers.

All scripts include extensive comments explaining what they do and how
to modify them safely.

------------------------------------------------------------------------

## Purpose of This Repository

This toolkit exists to:

-   Reduce repetitive manual work in Alma\
-   Improve data consistency and quality\
-   Support validation workflows\
-   Provide transparent, well-documented automation\
-   Make the Alma API approachable for librarians

You do not need to be a programmer to use these scripts.

If you can follow step-by-step instructions and edit a file path, you
can use this toolkit.

------------------------------------------------------------------------

## How Configuration Works (Important)

For security and clarity:

-   API keys are **never hardcoded** into scripts.
-   API keys are stored in a separate `.txt` file.
-   Scripts contain placeholders that you update once.
-   An anonymized example key file is included to show the required
    structure.

This keeps your credentials safe and prevents accidental uploads to
GitHub.

Each script contains clear comments explaining:

-   Where to edit the file path
-   How to confirm your Alma region (NA, EU, AP)
-   Which API key is being used (sandbox vs production)

------------------------------------------------------------------------

## What You Will Need

-   Python 3.9 or newer
-   An Alma API key (sandbox recommended for testing)
-   Access to your institution's Alma API
-   Basic ability to run a Python script from a terminal

No prior programming experience is required.

------------------------------------------------------------------------

## Recommended First Path

Start in this order:

1. Use [Getting Started/Basic Connection](Getting%20Started/Basic%20Connection/) to confirm API connectivity and key permissions.
2. Then use [Getting Started/Local_Testing](Getting%20Started/Local_Testing/) to safely test XML changes locally before any update workflow.

------------------------------------------------------------------------

## General Setup (Applies to All Scripts)

### 1️⃣ Install Python

Download from: https://www.python.org/downloads/

During installation, select:

✔ Add Python to PATH

Verify installation:

    python --version

------------------------------------------------------------------------

### 2️⃣ Download This Repository

Option A (recommended):

    git clone https://github.com/YOUR-USERNAME/YOUR-REPO-NAME.git

Option B:

-   Click **Code**
-   Download ZIP
-   Extract the folder

------------------------------------------------------------------------

### 3️⃣ Create Your API Key File

Create a text file on your computer:

    alma_api_keys.txt

Follow the structure shown in the included example file.

Do not change the variable names.

Do not upload your real key file to GitHub.

------------------------------------------------------------------------

### 4️⃣ Update Script Placeholders

In each script, you will see:

-   A placeholder file path for your API key file
-   A base URL containing `api-na`, `api-eu`, or `api-ap`

You must:

-   Replace the file path with the location of your key file
-   Confirm the correct Alma region

Each script explains this clearly in comments at the top.

------------------------------------------------------------------------

## 🛠️ Included Tools & Modules

### [OCLC to Alma - Book](OCLC_to_Alma_README.md)
A programmatic workflow that automatically prevents duplicates, searches the OCLC WorldCat Metadata API by ISBN, filters for English cataloging, and uses a built-in MARC scoring algorithm (Encoding level, major cataloging agencies, etc.) to evaluate and select the best possible WorldCat record to bring into your Alma institution's catalog.

---

## Repository Structure

Example structure:

    alma-automation/
    │
    ├── example_scripts/
    ├── validation/
    ├── automation/
    ├── utils/
    ├── output/
    ├── alma_api_keys_example.txt
    └── README.md

As this repository grows, scripts may be grouped by function:

-   Validation
-   Reporting
-   Metadata cleanup
-   Batch updates
-   API exploration tools

------------------------------------------------------------------------

## Script Design Philosophy

Each script in this repository:

-   Has a clear description at the top
-   Explains what it does in plain language
-   Uses comments generously
-   Avoids hardcoded credentials
-   Favors readability over cleverness
-   Is designed to be modified safely

The goal is clarity, not complexity.

------------------------------------------------------------------------

## Sandbox vs Production

Whenever possible:

-   Test scripts in Alma Sandbox first
-   Use production keys only after verifying results
-   Start with small batches
-   Review outputs before scaling

Automation is powerful --- use it carefully.

------------------------------------------------------------------------

## Troubleshooting (General Guidance)

If something doesn't work:

-   Read the error message carefully
-   Confirm your file path is correct
-   Confirm your API key file matches the example format
-   Confirm your Alma region is correct
-   Confirm your API key has the proper permissions

Most issues are configuration-related.

------------------------------------------------------------------------

## Security Best Practices

-   Never upload your real API key file
-   Add `alma_api_keys.txt` to your `.gitignore`
-   Use sandbox keys when developing
-   Rotate keys periodically according to your institution's policy

------------------------------------------------------------------------

## Who This Is For

This repository is especially useful for:

-   Metadata librarians
-   Catalogers
-   E-resources staff
-   Systems librarians
-   Anyone interested in responsible automation in Alma

If you are new to APIs, start with a basic connection script and build
from there.

------------------------------------------------------------------------

## Contributions

Improvements are welcome.

If you are:

-   A librarian with workflow ideas
-   A systems librarian with scripting experience
-   A developer interested in improving clarity

Feel free to contribute or suggest enhancements.

------------------------------------------------------------------------

## Guiding Principle

Automation should:

-   Reduce repetitive labor
-   Improve data quality
-   Increase confidence in workflows
-   Empower library staff

It should never feel opaque or risky.

Transparency and documentation are core values of this repository.
