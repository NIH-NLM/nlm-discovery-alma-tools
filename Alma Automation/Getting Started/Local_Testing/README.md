# Alma API Local Testing Script

When developing scripts that modify bibliographic records in Ex Libris Alma, it can be tedious to constantly test your code. The typical workflow is to download the record (GET), modify it, and upload it back to Alma (PUT). 

**The Problem:** If you are iterating on your code, making tweaks, or fixing bugs, uploading bad data means you have to constantly go back into Alma and manually restore previous versions of the record just so you can run your script again.

**The Solution:** This project demonstrates a much safer and faster workflow. It separates the "downloading" step from the "modifying" step. By saving a copy of the live MARCXML to your computer and manipulating that local file instead, you can run, tweak, and re-run your Python script hundreds of times without ever touching (or breaking) the data in your Alma Sandbox or Production environments.

---

## 📖 For Librarians (Little or No Python Experience)

This script is a safe sandbox for you to see how Python interacts with Alma data. It acts as an automated "Export to XML" button, followed by an automated cataloging update.

### What does it do?
1. It asks you for an **MMS ID**.
2. It uses your Alma Sandbox API Key to retrieve the real MARC format of that record.
3. It saves the original record directly to your computer as an XML file (e.g., `991234567890123.xml`).
4. Instead of sending changes back to Alma, it opens that local file, adds a brand new cataloging field (a **246** alternate title with the text "test"), makes sure it is in correct numerical order among the other MARC tags, and saves it as a second file called `local_test.xml`.

You can then open both files side-by-side on your computer to see exactly what your code did, completely risk-free!

### How to use it:
1. Ensure you have Python installed on your computer.
2. Ensure you have your Alma Sandbox API key saved in a local text file and update the `api_key_file` path in the script.
	*(The file should contain a line like: `alma_sandbox_key="YOUR_KEY_HERE"`)*
3. Run the script from your terminal or command prompt:
	```bash
	python local_testing_github.py
	```
4. Follow the prompts!

---

## 💻 For Developers

This script serves as a foundational template for building your own Alma data-cleanup or cataloging automation scripts. 

### Key Concepts Demonstrated:
* **Workflow Separation**: The `get_bib_record()` function only handles the HTTP GET request. The `modify_marc_xml()` function only handles the local file I/O and XML manipulation. When you are ready to deploy to production, you simply swap the local file save with an HTTP PUT request.
* **Alma Namespace Handling**: Alma API exports include standard MARC21 slim namespaces. The script uses `ET.register_namespace('', 'http://www.loc.gov/MARC21/slim')` so when you rewrite the file, Python doesn't inject ugly prefixes (like `ns0:`) into every XML tag.
* **Finding the Payload**: The Alma API wraps the MARC record. The script targets the `<record>` element deeply nested inside the `<bib>` wrapper. 
* **Numerical Tag Insertion**: Instead of just `.append()`ing a new field to the end of the XML tree (which creates a sloppy MARC record), the script iterates through existing `tag` attributes to insert the new datafield in its proper numerical location.

### How to customize:
To test your own cataloging logic:
1. Find the `modify_marc_xml` function.
2. Remove the block of code that builds the "246" field.
3. Insert your own `xml.etree.ElementTree` logic to delete, modify, or add specific tags and subfields based on your project requirements.
4. Run the script, inspect the resulting `local_test.xml`, adjust your code, and run it again until the output is perfect!