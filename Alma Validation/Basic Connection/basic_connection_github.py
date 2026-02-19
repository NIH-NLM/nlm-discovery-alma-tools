import requests
from xml.etree import ElementTree as ET

# This is a basic Alma python script that proves you are connected to your Alma instance. It prompts you for a MMS ID, then makes a request to the Alma API to retrieve the MARC record for that MMS ID and prints the title (245 $a) to the console. You can expand on this script to retrieve other fields or perform other actions as needed.

# Load Alma sandbox API key so it isn't hardcoded in script. Make sure to replace "your_file_path_here.txt" with the actual path to your alma_api_keys.txt file. The script looks for a line that starts with "alma_sandbox_key" and extracts the API key from that line. If the key is not found, it raises an error.
alma_api_key = None
with open(r"your_file_path_here.txt") as f:
    for line in f:
        if line.strip().startswith("alma_sandbox_key"):
            alma_api_key = line.split("=", 1)[1].strip().strip('"')
            break

if not alma_api_key:
    raise ValueError("Alma sandbox API key not found in alma_api_keys.txt")

# Alma API base URL. Change "na" to "eu" or "ap" if your Alma instance is in a different region. The endpoint used here is for retrieving a bibliographic record by MMS ID. You can change the endpoint to access other resources as needed.
ALMA_API_BASE_URL = "https://api-na.hosted.exlibrisgroup.com/almaws/v1/bibs/"

mms_id = input("Enter a MMS ID: ").strip()

url = f"{ALMA_API_BASE_URL}{mms_id}"
headers = {
    "Accept": "application/xml",
    "Authorization": f"apikey {alma_api_key}"
}

response = requests.get(url, headers=headers)

if response.status_code == 200:
    bib = ET.fromstring(response.content)
    record = bib.find(".//record")
    if record is not None:
        for datafield in record.findall("datafield[@tag='245']"):
            subfield_a = datafield.find("subfield[@code='a']")
            if subfield_a is not None and subfield_a.text:
                print(f"245 $a: {subfield_a.text}")
                break
        else:
            print("No 245 field found in the record.")
    else:
        print("No MARC record found in the response.")
else:
    print(f"Failed to fetch record: {response.status_code} - {response.text}")
