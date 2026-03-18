import argparse
import logging
import re
import requests
import sys
import unicodedata
import xml.etree.ElementTree as ET

# Configure simple logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
LOG = logging.getLogger(__name__)

alma_api_key = None
# Change the path below to match the location of your API key text file
api_key_file = r"C:/Users/{your_user_name}/Desktop/alma_api_keys.txt"

try:
    with open(api_key_file) as f:
        for line in f:
            if line.strip().startswith("alma_sandbox_key"):
                alma_api_key = line.split("=", 1)[1].strip().strip('"')
                break
except FileNotFoundError:
    LOG.error(f"API key file not found at {api_key_file}")
    sys.exit(1)

if not alma_api_key:
    raise ValueError("Alma sandbox API key not found in alma_api_keys.txt")

ALMA_API_URL = "https://api-na.hosted.exlibrisgroup.com/almaws/v1"

def normalize_rda_title(title_str):
    if not title_str:
        return ""
    
    # Truncate beyond first delimiter (/, :, =)
    title_str = re.sub(r'(.+?(?:\s:|\s/|\s=|$)).*', r'\1', title_str)
    
    # Lowercase
    title_str = title_str.lower()
    
    # Strip manual exceptions from Oracle BI script
    replacements = {
        'æ': 'ae', 'ǣ': 'ae', 'œ': 'oe', 'þ': 'th', 'i︠a︡': 'ia', 
        't︠s︡': 'ts', 'i︠u︡': 'iu', 'z︠h︡': 'zh',
        'ʻ': '', 'ʼ': '', 'ʾ': '', '︠': '', '︡': '', '︣': ''
    }
    title_str = unicodedata.normalize('NFC', title_str)
    for old, new in replacements.items():
        title_str = title_str.replace(old, new)
        
    # Translate diacritics to ASCII
    title_str = unicodedata.normalize('NFKD', title_str).encode('ASCII', 'ignore').decode('utf-8')
    
    # Strip generic bracket info
    title_str = re.sub(r'<<.*?>>', '', title_str)
    
    # Strip everything that isn't alphanumeric or whitespace
    title_str = re.sub(r'[^\w\s]', '', title_str)
    
    # Compress spaces
    title_str = ' '.join(title_str.split())
    
    return title_str

def get_alma_record(mms_id, api_url, api_key):
    """
    Retrieves a bibliographic record from Alma by MMS ID.
    Returns:
        tuple: (title, marcxml_data)
    """
    if not isinstance(mms_id, str):
        raise TypeError("MMS ID must be a string")
    if not mms_id.isdigit():
        raise ValueError("MMS ID must contain only digits")

    headers = {
        "Authorization": f"apikey {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    url = f"{api_url.rstrip('/')}/bibs/{mms_id}"
    try:
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            resp_json = resp.json()
            marcxml_data = resp_json.get('anies', [''])[0]
            if marcxml_data:
                marcxml_data = '<?xml version="1.0" encoding="utf-8"?>' + marcxml_data

            title = resp_json.get('title')
            if isinstance(title, str):
                title = unicodedata.normalize('NFC', title)
            return title, marcxml_data
        else:
            LOG.error(f"Error from Alma API [{resp.status_code}]: {resp.text}")
            resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        LOG.error(f"Error fetching record with MMS ID {mms_id}: {e}")
        return None, None

def search_sru_catalog(query, sru_base_url, index="alma.title", limit=100):
    """
    Perform a live SRU search against the Alma Catalog using a specified index.
    Returns a list of complete MARCXML strings for matching bib records.
    """
    cql_query = f'{index}="{query}"'
    results = []
    start_record = 1
    page_size = 50  # Alma SRU often silently caps responses to 50 records per page regardless of maximumRecords
    
    while len(results) < limit:
        current_limit = min(page_size, limit - len(results))
        params = {
            'version': '1.2',
            'operation': 'searchRetrieve',
            'recordSchema': 'marcxml',
            'maximumRecords': str(current_limit),
            'startRecord': str(start_record),
            'query': cql_query
        }
        
        try:
            response = requests.get(sru_base_url, params=params)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                namespaces = {
                    'srw': 'http://www.loc.gov/zing/srw/',
                    'marc': 'http://www.loc.gov/MARC21/slim'
                }
                records = root.findall('.//srw:recordData/marc:record', namespaces)
                if not records:
                    break  # No more records returned
                    
                for rec in records:
                    # Strip namespace prefixes for easier handling downstream
                    for elem in rec.iter():
                        if '}' in elem.tag:
                            elem.tag = elem.tag.split('}', 1)[1]
                    # We re-encode it to a string for parsing later to match how the original tool functions
                    results.append(ET.tostring(rec, encoding='unicode'))
                    
                start_record += len(records)
                
                # If we received fewer records than requested, we're likely at the end
                if len(records) < current_limit:
                    break
            else:
                LOG.error(f"SRU Error: {response.status_code} - {response.text}")
                break
        except requests.exceptions.RequestException as e:
            LOG.error(f"SRU Network Error: {e}")
            break
        except ET.ParseError as e:
            LOG.error(f"SRU XML Parse Error: {e}")
            break
            
    return results

def get_base_title_and_normalization(marcxml_data):
    """
    Extracts 245 $a, $n, $p and normalizes it. Supports non-filing characters.
    """
    # remove namespace to make element finding easier
    marcxml_data = re.sub(r'\sxmlns="[^"]+"', '', marcxml_data, count=1)
    root = ET.fromstring(marcxml_data)
    f245 = root.find('.//datafield[@tag="245"]')
    title = None
    extracted_ind2 = None
    
    if f245 is not None:
        title_parts = [s.text for s in f245.findall('subfield') if s.attrib.get('code') in ['a', 'n', 'p'] and s.text]
        title = ' '.join(title_parts)
        ind2 = f245.attrib.get('ind2')
        if ind2 and ind2.isdigit() and int(ind2) > 0 and len(title) >= int(ind2):
            extracted_ind2 = int(ind2)
            
    if not title:
        return None, None
        
    query_base_title = title[extracted_ind2:] if extracted_ind2 else title
    target_normalized = normalize_rda_title(title)
    if extracted_ind2:
        target_normalized = normalize_rda_title(query_base_title)
        
    return query_base_title, target_normalized

def parse_sru_results(bib_xml_list, target_normalized):
    """
    Parses SRU results list and checks for uniqueness against target target_normalized title.
    """
    parsed_results = []
    
    for xml_string in bib_xml_list:
        if not xml_string:
            continue
        try:
            root = ET.fromstring(xml_string)

            # Main Title (245)
            f245 = root.find('.//datafield[@tag="245"]')
            main_title_raw = ''
            f245_anp = ''
            if f245 is not None:
                main_title_raw = ' '.join([s.text for s in f245.findall('subfield') if s.text])
                f245_anp = ' '.join([s.text for s in f245.findall('subfield') if s.attrib.get('code') in ['a', 'n', 'p'] and s.text])
                ind2 = f245.attrib.get('ind2')
                if ind2 and ind2.isdigit() and int(ind2) > 0 and len(f245_anp) >= int(ind2):
                    f245_anp = f245_anp[int(ind2):]

            # Uniform Title (130)
            uniform_title_raw = ''
            f130_anp = ''
            f130 = root.find('.//datafield[@tag="130"]')
            if f130 is not None:
                uniform_title_raw = ' '.join([s.text for s in f130.findall('subfield') if s.text])
                f130_anp = ' '.join([s.text for s in f130.findall('subfield') if s.attrib.get('code') in ['a', 'n', 'p'] and s.text])
                ind1 = f130.attrib.get('ind1')
                if ind1 and ind1.isdigit() and int(ind1) > 0 and len(f130_anp) >= int(ind1):
                    f130_anp = f130_anp[int(ind1):]


            # Check for uniqueness: normalize anp titles and compare
            norm_245 = normalize_rda_title(f245_anp) if f245_anp else ""
            norm_130 = normalize_rda_title(f130_anp) if f130_anp else ""

            # LOG.info(f"Target: '{target_normalized}' | norm_245: '{norm_245}' | norm_130: '{norm_130}' | f245_anp raw: '{f245_anp}'")

            # Custom matching logic to correctly handle checking target_normalized against normalized returned value with non-filing logic taken into account
            match_found = False
            if norm_245 == target_normalized or (norm_130 and norm_130 == target_normalized):
                match_found = True
            
            if match_found:
                # MMS ID (001)
                control001 = root.find('.//controlfield[@tag="001"]')
                mmsid = control001.text if control001 is not None else ''

                parsed_results.append({
                    'mms_id': mmsid,
                    'title': main_title_raw,
                    'uniform_title': uniform_title_raw,
                    'norm_hit': norm_245 if norm_245 == target_normalized else norm_130
                })
        except Exception as e:
            LOG.error(f"An error occurred parsing unique title hit: {e}")  
            
    return parsed_results

def main():
    parser = argparse.ArgumentParser(description="Alma Unique Title Search Tool")
    parser.add_argument('--mms_id', required=False, help="The MMS ID of the record to check")
    # Change the domain and institution code (01NLM_INST) in the default URL below to match your own Alma institution's SRU endpoint
    parser.add_argument('--sru_url', default="https://nlm.alma.exlibrisgroup.com/view/sru/01NLM_INST", help="The Alma institution SRU URL")
    
    args = parser.parse_args()

    mms_id = args.mms_id
    if not mms_id:
        mms_id = input("Enter the MMS ID: ").strip()

    if not mms_id:
        LOG.error("An MMS ID is required to run the search.")
        sys.exit(1)

    LOG.info(f"Fetching record for MMS ID: {mms_id}")

    title, marcxml_data = get_alma_record(mms_id, ALMA_API_URL, alma_api_key)
    if not marcxml_data:
        LOG.error("Could not fetch valid MARCXML data for the given MMS ID.")
        sys.exit(1)
        
    query_base_title, target_normalized = get_base_title_and_normalization(marcxml_data)
    if not query_base_title:
        LOG.error("Could not extract 245 $a, $n, $p from the provided MMS ID.")
        sys.exit(1)
        
    # Remove diacritics for Alma search just like we do for normalization  
    query_title = unicodedata.normalize('NFKD', query_base_title).encode('ASCII', 'ignore').decode('utf-8')
    LOGO_MSG = f"Searching Alma Catalog SRU for unique title matches: '{query_title}'"
    LOG.info(LOGO_MSG)
    LOG.info(f"Target Normalized Title: '{target_normalized}'")
    
    bib_xml_list = search_sru_catalog(query_title, args.sru_url, limit=2000)
    
    LOG.info(f"Alma SRU returned {len(bib_xml_list)} strings for unique title search.")
    
    results = parse_sru_results(bib_xml_list, target_normalized)
    
    # Sort results so those with a uniform title appear at the top
    results.sort(key=lambda x: not bool(x.get('uniform_title')))

    print("\n--- Validation Results ---")
    if not results:
        print("No matching records found. Title is unique!")
    else:
        print(f"Found {len(results)} potential duplicate(s) with matching titles:")
        for idx, res in enumerate(results, 1):
            print(f"\nResult #{idx}:")
            print(f"  MMS ID: {res['mms_id']}")
            if res['uniform_title']:
                print(f"  130 field: {res['uniform_title']}")
            print(f"  245 field: {res['title']}")
            print(f"  Normalized Hit String: {res['norm_hit']}")
    print("-" * 26)

if __name__ == '__main__':
    main()
