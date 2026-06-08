# NLM Discovery Alma Tools

A collection of practical Python tools for Ex Libris Alma workflows.

This repository is designed for librarians, catalogers, metadata staff, and systems staff who want clear, documented scripts for validation, automation, lookup, set processing, and controlled testing.

## Repository Areas

- [Getting Started](Getting%20Started/) - Starter scripts and safe local testing workflows for Alma API work
- [Alma Validation](Alma%20Validation/) - Validation and correction tools for bibliographic records
- [Alma Lookup Tools](Alma%20Lookup%20Tools/) - Lookup and discovery utilities
- [Alma Automation](Alma%20Automation/) - Workflow automation scripts for cataloging and metadata operations
- [Alma Set Tools](Alma%20Set%20Tools/) - Set creation and batch set splitting workflows
- [Alma Testing](Alma%20Testing/) - Controlled record movement tools between Production and Sandbox

## Tool Index

### Getting Started
- [Basic Connection](Getting%20Started/Basic%20Connection/) - Confirm API key permissions and Alma connectivity
- [Local Testing](Getting%20Started/Local_Testing/) - Download and test XML changes locally before update workflows

### Alma Validation
- [Bib Validator](Alma%20Validation/Bib%20Validator/) - MARCXML validation with rule checks and optional corrections

### Alma Lookup Tools
- [Unique Title Search](Alma%20Lookup%20Tools/Unique%20Title%20Search/) - Checks title uniqueness by comparing normalized 245/130 data against SRU results

### Alma Automation
- [Ceased Title](Alma%20Automation/Ceased%20Title/) - Automates ceased title processing
- [ISSN Update](Alma%20Automation/ISSN%20Update/) - Updates ISSN fields in Alma bibliographic records
- [Title Change](Alma%20Automation/Title%20Change/) - Updates linked records when serial titles change
- [URL Redirect](Alma%20Automation/URL%20Redirect/) - Resolves redirected URLs and records final destinations

### Alma Set Tools
- [Batch Alma Sets](Alma%20Set%20Tools/Batch_Alma_Sets/) - Splits one source itemized bib set into multiple batch sets

### Alma Testing
- [Move Authority Prod to Sandbox](Alma%20Testing/Move_Authority_Prod_to_Sandbox/) - Copies an authority record from Production to Sandbox
- [Move Authority Sandbox to Prod](Alma%20Testing/Move_Authority_Sandbox_to_Prod/) - Copies an authority record from Sandbox to Production
- [Move Bib Prod to Sandbox](Alma%20Testing/Move_Bib_Prod_to_Sandbox/) - Copies a bib record and related inventory from Production to Sandbox

## Configuration and Security

- Keep API keys out of source control.
- Use a local key file that follows the included example format in [alma_api_keys_github.txt](alma_api_keys_github.txt).
- Recommended key names used by public-share scripts:
  - alma_sandbox_key
  - alma_production_key
- Add real key files to .gitignore.

## Recommended Usage Order

1. Start with [Getting Started/Basic Connection](Getting%20Started/Basic%20Connection/).
2. Continue with [Getting Started/Local_Testing](Getting%20Started/Local_Testing/).
3. Run testing and movement workflows in Sandbox-first patterns before production-impact workflows.
4. For any folder, review its local README before running the script.

## Notes

- Many tools now include standalone public-share scripts named with a _github.py suffix.
- These standalone scripts are designed for collaboration outside of Django form/view integrations.
