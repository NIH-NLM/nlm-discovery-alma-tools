# Getting Started

Tools and starter examples for safely learning and testing Alma API workflows.

## Tools

- [Local Testing](Local_Testing/) - Download a bib record, apply local XML changes, and verify output without writing changes back to Alma

## Folder Contents

| Folder | Purpose |
|---|---|
| `Local_Testing` | Download a live Alma bib record, apply local XML changes, and validate results without writing back to Alma |

## Recommended First Steps

1. Install Python 3.6+.
2. Install required Python packages for each script folder.
3. Create a local API key file (do not commit keys to GitHub).
4. Run scripts in a sandbox environment first.

## Local Testing Workflow

The `Local_Testing` folder demonstrates a safe development pattern:

1. Fetch a bibliographic record using an MMS ID and API key.
2. Save the original MARCXML locally.
3. Apply your Python XML logic to the local copy.
4. Review output before any PUT/update workflow.

This helps you iterate quickly without risking accidental record changes in Alma.

## Security Notes

- Keep API keys in local files outside source control when possible.
- Add key files to `.gitignore`.
- Use least-privilege API permissions for testing.

## Related Project Areas

After completing local testing, you can move on to:

- `Alma Validation` for record checks and correction workflows
- `Alma Automation` for scripted update processes
- `Alma Lookup Tools` for targeted search/lookup utilities
