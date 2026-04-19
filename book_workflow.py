import os
import sys
import requests
import xml.etree.ElementTree as ET
import re
import datetime

# Add the current directory and TA tool directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'TA tool'))

from src.shared.oclc_token_manager import OCLCTokenManager
from src.shared.oclc_service import OCLCService
try:
    from src.shared.marc_country_mapping import MARC_COUNTRY_MAP
except Exception as e:
    MARC_COUNTRY_MAP = {}
    print(f"Warning could not load country mapping: {e}")

import time

def fast_update_excel_and_read(title):
    # Dummy, unused fallback method 
    pass

def main():
    print("Welcome to the OCLC to Alma Workflow (Python Edition) - BOOKS WORKFLOW")
    isbn = input("Please enter the ISBN you want to search for: ").strip()
    
    if not isbn:
        print("No ISBN entered. Exiting.")
        return

    # Load Alma API key early so we can check Alma
    alma_api_key = None
    try:
        with open(r"C:/Users/stockdalear/Desktop/alma_api_keys.txt") as f:
            for line in f:
                if line.strip().startswith("alma_sandbox_key"):
                    parts = line.split("=", 1)
                    if len(parts) > 1:
                        alma_api_key = parts[1].strip().strip('"\'+')
                    break
    except Exception as e:
        print(f"Could not read alma API key: {e}")

    if not alma_api_key:
        print("Error: Alma sandbox API key not found in C:/Users/stockdalear/Desktop/alma_api_keys.txt")
        return

    # For API, ExLibris uses the standard endpoint; the sandbox/prod routing is handled by the API key
    alma_api_base_url = "https://api-na.hosted.exlibrisgroup.com/almaws/v1/bibs"

    print(f"\nChecking Alma via SRU to see if ISBN {isbn} already exists...")
    # Premium sandbox domains usually contain -psb
    alma_sru_url = "https://nlm-psb.alma.exlibrisgroup.com/view/sru/01NLM_INST"
    sru_params = {
        'version': '1.2',
        'operation': 'searchRetrieve',
        'recordSchema': 'marcxml',
        'query': f'alma.isbn="{isbn}"'
    }
    
    try:
        check_response = requests.get(alma_sru_url, params=sru_params)
        if check_response.status_code == 200:
            root = ET.fromstring(check_response.content)
            namespaces = {'srw': 'http://www.loc.gov/zing/srw/'}
            num_recs_elem = root.find('.//srw:numberOfRecords', namespaces)
            
            if num_recs_elem is not None and num_recs_elem.text and num_recs_elem.text.isdigit():
                total_records = int(num_recs_elem.text)
                if total_records > 0:
                    print(f"Found {total_records} existing record(s) in Alma with ISBN {isbn}.")
                    proceed = input("Do you still want to proceed with searching OCLC and adding a new record? (y/n): ").strip().lower()
                    if proceed != 'y':
                        print("Operation cancelled.")
                        return
        else:
            print(f"Could not check Alma via SRU. API responded with status {check_response.status_code}")
            print(f"Response: {check_response.text}")
    except Exception as e:
        print(f"Error checking Alma SRU: {e}")

    print(f"\nSearching OCLC for ISBN: {isbn}...")
    
    try:
        # Initialize token manager and service
        token_mgr = OCLCTokenManager()
        service = OCLCService(token_mgr)
        
        # OCLC uses 'in' for ISBN queries
        books = [{}]
        results, remaining = service.batch_search(books, append_query=f"bn:{isbn}")
        
        # Manually filter results for records cataloged in English (040 $b)
        eng_results = []
        for r in results:
            if r.get('catalogingInfo', {}).get('catalogingLanguage') == 'eng':
                eng_results.append(r)

        if not eng_results:
            print("No English-cataloged records found in OCLC for that ISBN.")
            return
            
        # Score the English records to find the best match
        def score_record(rec):
            score = 0
            cat_info = rec.get('catalogingInfo', {})
            lvl = cat_info.get('levelOfCataloging', '')
            agency = cat_info.get('catalogingAgency', '')

            # 1. Encoding Level (Leader/17)
            # Blank (' ') represents Full-level cataloging. 'I', 'L', 'M', '1' are also standard full levels.
            if lvl in [' ', 'I', 'L', 'M', '1']:
                score += 100
            elif lvl == '8': # Level 8 (Pre-publication)
                score += 80
                
            # 2. Major Cataloging Agency (040 $a)
            # DLC = Library of Congress, NLC = Library and Archives Canada, NLM = National Library of Medicine
            if agency in ['DLC', 'NLC', 'NLM', 'BL']:
                score += 50
                
            return score
            
        def sort_key(rec):
            score = score_record(rec)
            try:
                # Smaller OCLC number = older record
                oclc_num = int(rec.get('oclcNumber', '999999999999999'))
            except ValueError:
                oclc_num = 999999999999999
            # Return tuple: (score, negative oclc_num) 
            # With reverse=True, higher scores win. For ties, a smaller original OCLC number (less negative) wins.
            return (score, -oclc_num)

        # Sort by best score descending
        eng_results.sort(key=sort_key, reverse=True)
        
        print(f"Found {len(eng_results)} English-cataloged records. Validating 020 $a assignments...")
        
        found_matches = []
        best_score_found = -1

        for rec in eng_results:
            candidate_oclc = rec.get('oclcNumber')
            if not candidate_oclc:
                continue

            current_score = score_record(rec)

            # If we already found a valid match and the next records score lower algorithmically, stop pulling XMLs
            if found_matches and current_score < best_score_found:
                break

            candidate_xml = service.generate_xml([candidate_oclc], format_type="marcxml")
            if not candidate_xml:
                continue

            try:
                temp_root = ET.fromstring(candidate_xml)
                temp_record = temp_root.find('.//{http://www.loc.gov/MARC21/slim}record')
                if temp_record is None:
                    temp_record = temp_root.find('.//record')
                if temp_record is None:
                    temp_record = temp_root

                match_found = False
                for f in list(temp_record):
                    if f.tag.endswith('datafield') and f.get('tag') == '020':
                        for s in list(f):
                            if s.tag.endswith('subfield') and s.get('code') == 'a' and s.text:
                                # Sometimes it has qualifiers like '2048-4070 (online)'
                                clean_val = s.text.split(' ')[0].strip()
                                if clean_val == isbn:
                                    match_found = True
                                    break
                    if match_found:
                        break

                if match_found:
                    best_score_found = current_score
                    marc_field_count = len(list(temp_record))
                    found_matches.append({
                        'rec': rec,
                        'xml': candidate_xml,
                        'field_count': marc_field_count,
                        'score': current_score
                    })
                    
                    if current_score >= 80:
                        # Excellent record format, take it immediately!
                        break
                    
                    # If we've gathered up to 5 ties for a sub-80 score, that's enough to compare.
                    if len(found_matches) >= 5:
                        break
                else:
                    print(f"  Skipping {candidate_oclc} - Searched ISBN {isbn} is not in 020 $a.")
            except Exception as e:
                print(f"  Error parsing XML for {candidate_oclc}: {e}")
                continue

        if not found_matches:
            print("No English-cataloged records had the requested ISBN explicitly assigned to 020 $a.")
            return

        # Sort the valid matches by field count descending
        # (It intrinsically preserves the OCLC age tie-breaker because they were sorted before we appended)
        found_matches.sort(key=lambda x: x['field_count'], reverse=True)
        
        best_match = found_matches[0]
        best_record = best_match['rec']
        marcxml_str = best_match['xml']

        if best_match['score'] < 80 and len(found_matches) > 1:
            print(f"\nScore was < 80. Compared {len(found_matches)} valid records and selected the one with the most MARC tags ({best_match['field_count']} tags).")

        oclc_number = best_record.get('oclcNumber', 'Unknown')
        title = best_record.get('title', 'Unknown Title')
        author = best_record.get('author', 'Unknown Author')
        
        best_score = score_record(best_record)
        cat_info = best_record.get('catalogingInfo', {})
        encoding_level = cat_info.get('levelOfCataloging', '')
        if encoding_level == ' ':
            encoding_level = 'Full'
        agency = cat_info.get('catalogingAgency', 'Unknown')

        print(f"\nSelected the highest scored record with a 020 $a match:")

        print("-" * 40)
        print(f"Title:          {title}")
        print(f"Author:         {author}")
        print(f"OCLC Number:    {oclc_number}")
        print(f"Algorithm Score:{best_score}")
        print(f"Encoding Level: {encoding_level}")
        print(f"Cat Agency:     {agency}")
        print("-" * 40)

        if best_score >= 100:
            print("\nRecord score is 100 or above. Auto-accepting this record for Alma.")
            choice = 'y'
        else:
            choice = input("\nDo you want to add this record to Alma? (y/n): ").strip().lower()

        if choice == 'y':
            if not marcxml_str:
                print("Failed to procure valid MARCXML from OCLC validation.")
                return

#             print("\nChecking Alma if the title from OCLC is unique...")
#             title_is_duplicate = False
#             used_qualifiers = []
#             try:
#                 from unique_title_search import get_base_title_and_normalization, search_sru_catalog, parse_sru_results
#                 import unicodedata
#                 
#                 query_base_title, target_normalized = get_base_title_and_normalization(marcxml_str)
#                 if query_base_title:
#                     query_title = unicodedata.normalize('NFKD', query_base_title).encode('ASCII', 'ignore').decode('utf-8')
#                     bib_xml_list = search_sru_catalog(query_title, alma_sru_url, limit=200)
#                     results = parse_sru_results(bib_xml_list, target_normalized)
# 
#                     # Extract all 130 qualifiers from Alma hits before we filter them out
#                     used_qualifiers = [r.get('uniform_title') for r in results if r.get('uniform_title')]
#                     
#                     if results:
#                         duplicate_count = len(results)
#                         print(f"Warning: Found {duplicate_count} exact or similar title(s) in Alma for '{query_base_title}':")
#                         for idx, r in enumerate(results, 1):
#                             title_display = r['title']
#                             if r.get('uniform_title'):
#                                 title_display = f"130: {r['uniform_title']} | 245: {r['title']}"
#                             else:
#                                 title_display = f"245: {r['title']}"
#                             print(f"  Result #{idx}: MMS ID: {r['mms_id']} | {title_display}")
#                             
#                         # If ALL found records already have a 130, this new 245 might be technically unique as-is, BUT 
#                         # standard cataloging dictates we still need to disambiguate it from the existing qualified editions.
#                         proceed = input("Do you still want to proceed and generate a 130 qualifier? (y/n): ").strip().lower()
#                         if proceed != 'y':
#                             print("Operation cancelled.")
#                             return
#                         title_is_duplicate = True
#                     else:
#                         print(f"Title '{query_base_title}' appears to be unique in Alma.")
#                 else:
#                     print("Could not extract a valid 245 $a, $n, $p to check uniqueness.")
#             except Exception as e:
#                 print(f"Error checking unique title: {e}")
# 
            print("Applying Alma Normalization Rules to MARCXML...")
            try:
                ET.register_namespace('', 'http://www.loc.gov/MARC21/slim')
                root = ET.fromstring(marcxml_str)
                record = root.find('.//{http://www.loc.gov/MARC21/slim}record')
                if record is None:
                    record = root.find('.//record')
                if record is None:
                    record = root

#                 if title_is_duplicate and query_base_title:
#                     has_1xx = False
#                     for f in list(record):
#                         if f.tag.endswith('datafield') and f.get('tag') in ['100', '110', '111']:
#                             has_1xx = True
#                             break
#                     
#                     if has_1xx:
#                         print(f"\nTitle is not unique, but record already has a 1XX field to act as a qualifier for '{query_base_title}'. Skipping 130 generation.")
#                     else:
#                         print(f"\nTitle '{query_base_title}' is not unique and lacks a 1XX field. A 130 qualifier is needed.")
#                         
#                         # Try to extract the first editor's last name from 245 $c
#                         c_text = ""
#                         for f in list(record):
#                             if f.tag.endswith('datafield') and f.get('tag') == '245':
#                                 for s in list(f):
#                                     if s.tag.endswith('subfield') and s.get('code') == 'c' and s.text:
#                                         c_text = s.text
#                                         break
#                                 break
#                         
#                         suggested_qualifier = ""
#                         if c_text:
#                             # Heuristic to grab last name of first person listed
#                             t = re.sub(r'^\s*/*\s*(?:edited )?by\s+', '', c_text, flags=re.IGNORECASE)
#                             parts = re.split(r'[,;&/\[]|\band\b|\bwith\b|\bby\b', t, flags=re.IGNORECASE)
#                             if parts:
#                                 first_person = parts[0].strip()
#                                 words = first_person.split()
#                                 if words:
#                                     suggested_qualifier = f"({words[-1].strip('.,()[]*')})"
#                         
#                         print(f"\n--- 130 Qualifier Generation ---")
#                         # Prepend Title base for Alma string check
#                         if used_qualifiers:
#                             print(f"Found {len(used_qualifiers)} earlier editions in Alma that already use a 130:")
#                             for uq in used_qualifiers:
#                                 print(f"  - {uq}")
#                             print("Tip: You may want to reuse one of the qualifiers above if this is a later edition of the same work.")
#                         
#                         if suggested_qualifier:
#                             print(f"Automatically extracted suggested editor qualifier from 245 $c: {suggested_qualifier}")
#                         
#                         default_val = suggested_qualifier if suggested_qualifier else ""
#                         qualifier = input(f"Please supply the 130 qualifier string (e.g. '(Smith)'), or press Enter to use [{default_val}]: ").strip()
#                         if not qualifier and default_val:
#                             qualifier = default_val
#                             
#                         if qualifier:
#                             # Ensure it has parentheses
#                             if not qualifier.startswith('('): qualifier = '(' + qualifier
#                             if not qualifier.endswith(')'): qualifier = qualifier + ')'
#                             new_130 = ET.Element('datafield', {'tag': '130', 'ind1': '0', 'ind2': ' '})
#                             new_130_sub_a = ET.SubElement(new_130, 'subfield', {'code': 'a'})
#                             
#                             clean_130_title = query_base_title.strip()
#                             if clean_130_title:
#                                 while clean_130_title[-1] in ['/', ':', '.', ',', ';']:
#                                     clean_130_title = clean_130_title[:-1].strip()
#                                 
#                             new_130_sub_a.text = f"{clean_130_title} {qualifier}"
#                             record.append(new_130)
#                             
#                             # Change 245 first indicator to 1 since we added a 130
#                             for field_245 in list(record):
#                                 if field_245.tag.endswith('datafield') and field_245.get('tag') == '245':
#                                     field_245.set('ind1', '1')
#                                     break
# 
                
                tags_to_remove = ['012', '016', '029', '037', '049', '051', '060', '096', '265', '380', '386', '541', '561', '562', '563', '752', '758', '776', '850', '856', '886', '887', '891', '938', '948', '994']
                tags_to_950 = ['600', '610', '611', '630', '647', '648', '650', '651', '653', '654', '655', '656', '657', '658', '662', '688']
                seen_035_content = set()

                for field in list(record):
                    tag = field.get('tag')
                    if not tag:
                        continue
                        
                    # Also normalize the 001 field so Alma doesn't auto-create the ocm/ocn prefixed 035
                    if tag == '001' and field.text:
                        text = field.text.strip()
                        if text.startswith('ocm') or text.startswith('ocn') or text.startswith('on'):
                            text = text.replace('ocm', '', 1).replace('ocn', '', 1).replace('on', '', 1)
                        field.text = text

                    # Remove OCLC specific fields
                    if tag in tags_to_remove:
                        record.remove(field)
                        continue
                        
                    # Change 6XX to 950
                    if tag in tags_to_950:
                        field.set('tag', '950')
                        continue
                        
                    # Handle 035 logic
                    if tag == '035':
                        subfields = list(field)
                        
                        # Remove 035 fields with specific OCLC prefixes in $a
                        remove_prefix = False
                        for sf in subfields:
                            if sf.get('code') == 'a' and sf.text:
                                text = sf.text.strip()
                                if text.startswith('(OCoLC)ocn') or text.startswith('(OCoLC)ocm') or text.startswith('(OCoLC)on'):
                                    remove_prefix = True
                                    break
                                    
                        if remove_prefix:
                            record.remove(field)
                            continue
                            
                        # Resequence subfields order: 9, a, z, then others
                        sf_9, sf_a, sf_z, sf_oth = [], [], [], []
                        for sf in subfields:
                            field.remove(sf)
                            code = sf.get('code')
                            if code == '9': sf_9.append(sf)
                            elif code == 'a': sf_a.append(sf)
                            elif code == 'z': sf_z.append(sf)
                            else: sf_oth.append(sf)
                            
                        for sf in sf_9 + sf_a + sf_z + sf_oth:
                            field.append(sf)
                            
                        # Remove exact duplicate mapped 035 fields
                        field_str = ET.tostring(field, encoding='unicode')
                        if field_str in seen_035_content:
                            record.remove(field)
                        else:
                            seen_035_content.add(field_str)

                # Check 008 for lang and country to build 041 and 044
                lang_code = None
                country_code = None
                for elem in record:
                    if elem.get('tag') == '008':
                        if elem.text and len(elem.text) >= 38:
                            country_code = elem.text[15:18].strip().lower()
                            lang_code = elem.text[35:38].strip().lower()
                            break

                # Check existance of 041 and 044
                has_041 = any(f.get('tag') == '041' for f in record)
                if not has_041 and lang_code:
                    new_041 = ET.Element('datafield', {'ind1': '0', 'ind2': ' ', 'tag': '041'})
                    ET.SubElement(new_041, 'subfield', {'code': 'a'}).text = lang_code
                    record.append(new_041)

                has_044 = any(f.get('tag') == '044' for f in record)
                if not has_044 and country_code:
                    full_country = MARC_COUNTRY_MAP.get(country_code)
                    if not full_country and len(country_code) == 3:
                        if country_code.endswith('u'): full_country = "United States"
                        elif country_code.endswith('c'): full_country = "Canada"
                        elif country_code.endswith('a'): full_country = "Australia"
                        
                    if full_country:
                        new_044 = ET.Element('datafield', {'ind1': ' ', 'ind2': ' ', 'tag': '044'})
                        ET.SubElement(new_044, 'subfield', {'code': '9'}).text = full_country
                        record.append(new_044)

                import datetime
                date_str = datetime.datetime.now().strftime("%Y%m%d")
                
                # 992
                new_992 = ET.Element('datafield', {'ind1': ' ', 'ind2': ' ', 'tag': '992'})
                ET.SubElement(new_992, 'subfield', {'code': 'p'}).text = 'Px'
                ET.SubElement(new_992, 'subfield', {'code': 'e'}).text = 'EF'
                ET.SubElement(new_992, 'subfield', {'code': 'a'}).text = date_str
                record.append(new_992)
                
                # 993 -> 996 loop
                for tag in ['993', '994', '995', '996']:
                    new_tag = ET.Element('datafield', {'ind1': ' ', 'ind2': ' ', 'tag': tag})
                    ET.SubElement(new_tag, 'subfield', {'code': 'a'}).text = '[CAT ONLY]'
                    ET.SubElement(new_tag, 'subfield', {'code': 'b'}).text = date_str
                    record.append(new_tag)
                
                # 997
                new_997 = ET.Element('datafield', {'ind1': ' ', 'ind2': ' ', 'tag': '997'})
                ET.SubElement(new_997, 'subfield', {'code': 'a'}).text = '[CAT ONLY]'
                record.append(new_997)
                
                # 999
                new_999 = ET.Element('datafield', {'ind1': ' ', 'ind2': ' ', 'tag': '999'})
                ET.SubElement(new_999, 'subfield', {'code': 'a'}).text = 'ZZZ'
                record.append(new_999)

                # Sort all fields in the record numerically by tag so injected fields are in the correct sequence
                def get_sort_key(elem):
                    if 'leader' in elem.tag.lower():
                        return '0000' # Leader always first
                    return elem.get('tag', 'ZZZZ') # Fallback if tag is missing

                sorted_elems = sorted(list(record), key=get_sort_key)

                # Clear the record and append elements back in sorted order
                for elem in list(record):
                    record.remove(elem)
                for elem in sorted_elems:
                    record.append(elem)

                normalized_xml = f"<bib><suppress_from_publishing>false</suppress_from_publishing><suppress_from_external_search>false</suppress_from_external_search>{ET.tostring(record, encoding='unicode')}</bib>"
                print("Successfully Normalized Record.")

            except Exception as e:
                print(f"Normalization failed: {e}")
                normalized_xml = f"<bib><suppress_from_publishing>false</suppress_from_publishing><suppress_from_external_search>false</suppress_from_external_search>{marcxml_str}</bib>"
                
            # Log the final XML to the local folder for reference
            try:
                with open('book_record.xml', 'w', encoding='utf-8') as debug_f:
                    debug_f.write(normalized_xml)
            except Exception:
                pass

            print(f"\nPushing normalized record {oclc_number} to Alma...")

            headers = {
                "Accept": "application/xml",
                "Content-Type": "application/xml",
                "Authorization": f"apikey {alma_api_key}"
            }
            
            # Post a new bib record: /almaws/v1/bibs with the XML content
            response = requests.post(alma_api_base_url, headers=headers, data=normalized_xml.encode('utf-8'))
            
            if response.status_code in [200, 201]:
                print(f"Successfully pushed record to Alma!")
                
                try:
                    response_xml = ET.fromstring(response.content)
                    mms_id = response_xml.findtext('.//mms_id')
                    if mms_id:
                        print(f"Created Alma MMS ID: {mms_id}")
                        
                        print(f"\nAdding holdings record to {mms_id}...")
                        import datetime
                        today_str = datetime.datetime.now().strftime("%y%m%d")
                        holdings_xml = f"""<holding>
  <record>
    <leader>00214ny  a2200085zn 4500</leader>
    <controlfield tag="008">{today_str}0u    7   0001uu   0000000</controlfield>
    <datafield ind1="2" ind2=" " tag="852">
      <subfield code="b">NLM</subfield>
      <subfield code="c">GENCOLL</subfield>
    </datafield>
  </record>
</holding>"""
                        holdings_url = f"{alma_api_base_url}/{mms_id}/holdings"
                        h_resp = requests.post(holdings_url, headers=headers, data=holdings_xml.encode('utf-8'))
                        
                        if h_resp.status_code in [200, 201]:
                            try:
                                h_id = ET.fromstring(h_resp.content).findtext('.//holding_id')
                                print(f"Successfully created Alma Holding ID: {h_id}")
                            except Exception:
                                print("Created holding record successfully.")
                        else:
                            print(f"Failed to create holding. Status code: {h_resp.status_code}")
                            print(f"Response: {h_resp.text}")

                except Exception:
                    print("Could not parse MMS ID from response.")
            else:
                print(f"Failed to push to Alma. Status code: {response.status_code}")
                print(f"Response: {response.text}")
                
        else:
            print("Operation cancelled.")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == '__main__':
    main()
