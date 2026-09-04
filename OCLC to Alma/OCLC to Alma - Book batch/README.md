# eBook Batch Workflow — OCLC to Alma

Standalone, single-file batch workflow that imports eBook records from OCLC
WorldCat into Ex Libris Alma and creates electronic portfolios. No local
package dependencies beyond `requests` and `openpyxl` — all OCLC helper code
(token manager, search service, MARC country-code map) is inlined in
[ebook_batch_workflow.py](ebook_batch_workflow.py). You do **not** need to
download or set up the single-record `OCLC to Alma - Book` tool to use this
— it's fully self-contained.

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in your credentials and
   institution-specific Alma endpoints/portfolio target. `.env` is
   gitignored — never commit it. As an alternative to `OCLC_WSKEY`/
   `OCLC_SECRET`, you can point `OCLC_KEY_FILE` at a local key file (e.g.
   `oclc_api_keys.txt`) — this filename is also gitignored, but double check
   with `git status` before committing and delete any real key file from
   this folder before pushing.
3. Prepare an input spreadsheet (default name `input.xlsx`, override with
   `INPUT_XLSX`) with a header row followed by data starting at row 2, in
   this column order: `No. | Book Title | Series | Edition | eISBN`.
4. Run:
   ```
   python ebook_batch_workflow.py
   ```

## What it does

For each eISBN in the input spreadsheet:

1. Checks Alma via SRU — if already present, records "Already in Alma" + MMS ID.
2. If not present, searches OCLC for the best English-cataloged record whose
   020 $a matches the eISBN.
3. Normalizes the MARCXML (see `normalize_marcxml` — adjust the tag lists and
   locally-defined fields to match your own cataloging conventions) and
   pushes the bib to Alma.
4. Creates an electronic portfolio linked to the new bib, attached to the
   e-collection/e-service configured via `PORTFOLIO_ECOLL_ID` / `PORTFOLIO_ESVC_ID`.
5. Writes all results (MMS ID, portfolio ID, status) to a timestamped
   `results_YYYYMMDD.xlsx` file.

## Configuration

All configuration is via environment variables (or a `.env` file next to the
script) — see `.env.example` for the full list. Required values:
`ALMA_API_BASE`, `ALMA_SRU_URL`, `PORTFOLIO_ECOLL_ID`, `PORTFOLIO_ESVC_ID`,
`PORTFOLIO_LIBRARY`, plus OCLC and Alma credentials.

## Notes

- MARC normalization rules in `normalize_marcxml` reflect one institution's
  cataloging conventions (which tags to drop, which to move to 950, and the
  locally-defined 911/992/993-999 fields). Review and adjust for your own
  Alma configuration before using in production.
- Rate limiting: `OCLC_REQUEST_DELAY` (seconds) controls the delay between
  OCLC API calls.
