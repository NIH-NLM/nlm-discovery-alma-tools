# Serials Maintenance

Tools in this area support serials cataloging maintenance workflows in Ex Libris Alma.

## Available Tools

- [Frequency Change Automation](Frequency%20Change%20Automation/) - Updates serial publication frequency data in MARC records using spreadsheet-driven input.

## Recommended Workflow

1. Read the tool-specific documentation in [Frequency Change Automation](Frequency%20Change%20Automation/README.md).
2. Prepare your input data using the provided template file in that folder.
3. Run in dry-run mode first, then execute in sandbox, then production.

## Security Notes

- Never commit Alma API keys to this repository.
- Store keys in environment variables or local untracked key files.
- Follow the key-handling instructions in the tool README.

## Scope

This folder is intended for serials-focused maintenance scripts. Add new serials workflows here with:

- a script file,
- an input template (if needed), and
- a local README documenting usage and safeguards.
