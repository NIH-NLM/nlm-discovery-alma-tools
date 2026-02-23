from xml.etree import ElementTree as ET
import uuid
import re
from bib_marc_validator.xml_helpers import (
    id_exists,
    set_subfield,
    set_subfield_by_id,
    set_indicator_by_id,
    remove_subfield_by_id,
    remove_tag_by_id,
    set_tag_by_id, 
    add_subfield_by_id,
    fix_punctuation,
    precise_get_by_id,
    precise_set_by_id,
    precise_remove_by_id
)
from bib_marc_validator.resources.validation.marc_validation_resources import (
    valid_country_codes,
    valid_language_codes,
    unicode_embeddings_to_remove)


def preprocess_error_message(error_message: str) -> str:
    """
    Preprocesses an error message by normalizing quotation marks and whitespace.
    This function cleans up error messages by removing leading/trailing whitespace
    and converting curly/smart quotes to standard straight quotes for consistency.
    Args:
        error_message (str): The raw error message string to be preprocessed.
    Returns:
        str: The cleaned error message with normalized quotation marks and trimmed whitespace.
    """

    error_message = error_message.strip()
    error_message = error_message.replace('‘', "'")
    error_message = error_message.replace('’', "'")
    return error_message

def get_leader_field(xml_string: str) -> str:
    """
    Get the leader field from a MARC XML record
    Args:
        xml_string (str): The MARC XML string to parse.
    Returns:
        str: The leader field as a string, or None if not found.
    """
    root = ET.fromstring(xml_string)
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    
    leader = root.find(".//{http://www.loc.gov/MARC21/slim}leader")
    return leader.text if leader is not None else None

def set_leader_chars(xml_string: str, start: int, chars: str) -> str:
    """
    Set specific characters in the leader field
    Args:
        xml_string (str): The MARC XML string to modify.
        start (int): The starting position in the leader field to set characters.
        chars (str): The characters to set in the leader field.
    Returns:
        str: The modified MARC XML string with the updated leader field.
    """
    root = ET.fromstring(xml_string)
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    
    leader = root.find(".//{http://www.loc.gov/MARC21/slim}leader")
    if leader is not None:
        # Ensure the text is long enough
        if len(leader.text) <= start:
            leader.text = leader.text.ljust(start + len(chars))
        # Replace characters at position
        leader.text = leader.text[:start] + chars + leader.text[start + len(chars):]
    
    return ET.tostring(root, encoding='unicode', method='xml')

def get_controlfield_length(xml_string: str, tag: str) -> int:
    """
    Get the length of a controlfield
    Args:
        xml_string (str): The MARC XML string to parse.
        tag (str): The tag of the controlfield to check.
    Returns:
        int: The length of the controlfield text, or 0 if not found.
    """
    
    root = ET.fromstring(xml_string)
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    
    controlfield = root.find(f".//*[@tag='{tag}']")
    if controlfield is not None:
        return len(controlfield.text)
    return 0

def create_field(xml_string: str, tag: str, type='datafield'):
    """
    Create a new field in the MARC XML record
    Args:
        xml_string (str): The MARC XML string to modify.
        tag (str): The tag of the field to create.
        type (str): The type of field to create ('datafield' or 'controlfield').
    Returns:
        str: The modified MARC XML string with the new field added.
    """
    root = ET.fromstring(xml_string)
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    field_id = str(uuid.uuid4())
    if type == 'datafield':
        new_field = ET.SubElement(root, 'datafield', {'tag': tag, 'id': field_id, 'ind1': ' ', 'ind2': ' '})
        new_field.text = " "
    else:
        if type == 'controlfield':
            new_field = ET.SubElement(root, 'controlfield', {'tag': tag})
            new_field.text = " "
    return ET.tostring(root, encoding='unicode', method='xml')

def set_controlfield_chars(xml_string: str, tag: str, start: int, chars: str) -> str:
    """
    Set specific characters in a controlfield
    Args:
        xml_string (str): The MARC XML string to modify.
        tag (str): The tag of the controlfield to modify.
        start (int): The starting position in the controlfield text to set characters.
        chars (str): The characters to set in the controlfield text.
    Returns:
        str: The modified MARC XML string with the updated controlfield.
    """
    
    root = ET.fromstring(xml_string)
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    
    controlfield = root.find(f".//*[@tag='{tag}']")
    if controlfield is not None:
        text = controlfield.text
        # Ensure the text is long enough
        if len(text) <= start:
            text = text.ljust(start + len(chars))
        # Replace characters at position
        text = text[:start] + chars + text[start + len(chars):]
        controlfield.text = text
    
    return ET.tostring(root, encoding='unicode', method='xml')

def get_controlfield_chars(xml_string: str, tag: str, start: int, length: int) -> str:
    """
    Get specific characters from a controlfield
    Args:
        xml_string (str): The MARC XML string to parse.
        tag (str): The tag of the controlfield to check.
        start (int): The starting position in the controlfield text to get characters.
        length (int): The number of characters to retrieve from the controlfield text.
    Returns:
        str: The substring of the controlfield text starting at `start` with length `length`, or None if not found.
    """
    root = ET.fromstring(xml_string)
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    
    controlfield = root.find(f".//*[@tag='{tag}']")
    if controlfield is not None:
        text = controlfield.text
        return text[start:start + length]
    return None

def get_subfield(xml_string: str, field_tag: str, subfield_code: str) -> str:
    """Get the value of a specific subfield"""
    root = ET.fromstring(xml_string)
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    
    datafield = root.find(f".//*[@tag='{field_tag}']")
    if datafield is not None:
        subfield = datafield.find(f"*[@code='{subfield_code}']")
        if subfield is not None:
            return subfield.text
    return None

def get_all_indicators_and_subfields_for_tag(xml_string: str, field_tag: str) -> list[ET.Element]:
    """
    Get all subfield for a specific datafield as a dict
    Args:
        xml_string (str): The MARC XML string to parse.
        field_tag (str): The tag of the datafield to retrieve.
    Returns:
        list: A list of dictionaries, each containing the id, indicators, and subfields of the datafield.
    """
    root = ET.fromstring(xml_string)
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    
    datafields = root.findall(f".//*[@tag='{field_tag}']")
    indicators = get_indicators(xml_string, field_tag)
    list_of_fields_and_subfield_dictionaries = []
    # iterate through datafields, printing the subfield codes and the values
    for i, field in enumerate(datafields):
        subfields = field.findall("*")
        subfield_dict = {
            "id": field.get("id"),
            "indicators": indicators[i],
            "subfields": {}}
        for subfield in subfields:
            subfield_dict['subfields'][subfield.get('code')] = subfield.text
        list_of_fields_and_subfield_dictionaries.append(subfield_dict)
    return list_of_fields_and_subfield_dictionaries

def reorder_subfields(xml_string: str, field_tag: str, code1: str, code2: str) -> str:
    """
    Reorder subfields within a datafield to ensure code1 comes before code2
    Args:
        xml_string (str): The MARC XML string to modify.
        field_tag (str): The tag of the datafield to modify.
        code1 (str): The code of the first subfield to ensure comes first.
        code2 (str): The code of the second subfield to ensure comes after the first.
    Returns:
        str: The modified MARC XML string with the reordered subfields.
    """
    root = ET.fromstring(xml_string)
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    
    datafield = root.find(f".//*[@tag='{field_tag}']")
    if datafield is not None:
        subfields = list(datafield)
        # Find the indices of the subfields we want to reorder
        idx1 = next((i for i, sf in enumerate(subfields) if sf.get('code') == code1), -1)
        idx2 = next((i for i, sf in enumerate(subfields) if sf.get('code') == code2), -1)
        
        if idx1 > idx2 and idx1 != -1 and idx2 != -1:
            # Swap subfields in the XML tree
            sf1, sf2 = subfields[idx1], subfields[idx2]
            datafield.remove(sf1)
            datafield.remove(sf2)
            datafield.insert(idx2, sf1)
            datafield.insert(idx1, sf2)
    
    return ET.tostring(root, encoding='unicode', method='xml')

def append_to_subfield(xml_string: str, field_tag: str, subfield_code: str, append_text: str) -> str:
    """
    Append text to a subfield's value
    Args:
        xml_string (str): The MARC XML string to modify.
        field_tag (str): The tag of the datafield containing the subfield.
        subfield_code (str): The code of the subfield to append text to.
        append_text (str): The text to append to the subfield's value.
    Returns:
        str: The modified MARC XML string with the updated subfield value.
    """
    root = ET.fromstring(xml_string)
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    
    datafield = root.find(f".//*[@tag='{field_tag}']")
    if datafield is not None:
        subfield = datafield.find(f"*[@code='{subfield_code}']")
        if subfield is not None:
            subfield.text = subfield.text + append_text
    
    return ET.tostring(root, encoding='unicode', method='xml')

def get_indicators(xml_string: str, field_tag: str) -> str:
    """
    Get indicator value for a specific datafield
    Args:
        xml_string (str): The MARC XML string to parse.
        field_tag (str): The tag of the datafield to retrieve indicators for.
    Returns:
        list: A list of dictionaries containing the indicators for the specified datafield.
    """
    root = ET.fromstring(xml_string)
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    
    datafields = root.findall(f".//*[@tag='{field_tag}']")
    indicators = []
    for datafield in datafields:
        if datafield is not None:
            indicators.append({
                'ind1': datafield.get(f'ind1'),
                'ind2': datafield.get(f'ind2')
            })
            
    return indicators

def set_indicator(xml_string: str, field_tag: str, ind_num: int, value: str) -> str:
    """
    Set indicator value for a specific datafield
    Args:
        xml_string (str): The MARC XML string to modify.
        field_tag (str): The tag of the datafield to set the indicator for.
        ind_num (int): The indicator number (1 or 2) to set.
        value (str): The value to set for the indicator.
    Returns:
        str: The modified MARC XML string with the updated indicator value.
    """
    root = ET.fromstring(xml_string)
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    
    datafield = root.find(f".//*[@tag='{field_tag}']")
    if datafield is not None:
        datafield.set(f'ind{ind_num}', value)
    
    return ET.tostring(root, encoding='unicode', method='xml')

def add_655_genre(xml_string: str, genre: str) -> str:
    """
    Add a 655 genre field if it doesn't exist
    Args:
        xml_string (str): The MARC XML string to modify.
        genre (str): The genre to add to the 655 field.
    Returns:
        str: The modified MARC XML string with the new 655 field added."""
    root = ET.fromstring(xml_string)
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    
    # Check if genre already exists
    existing = root.findall(".//*[@tag='655']")
    for field in existing:
        subfield_a = field.find("*[@code='a']")
        if subfield_a is not None and subfield_a.text == genre:
            return xml_string
    
    # Add new 655 field
    new_655 = ET.SubElement(root, 'datafield', {'tag': '655', 'ind1': ' ', 'ind2': ' '})
    new_subfield = ET.SubElement(new_655, 'subfield', {'code': 'a'})
    new_subfield.text = genre
    
    return ET.tostring(root, encoding='unicode', method='xml')

def add_008_genre(xml_string: str, char: str) -> str:
    """
    Add a 008 genre field if it doesn't exist
    Args:
        xml_string (str): The MARC XML string to modify.
        char (str): The character to add to the 008 genre field.
    Returns:
        str: The modified MARC XML string with the updated 008 genre field."""
    genres_bytes = get_controlfield_chars(xml_string, "008", 24, 4)
    if " " not in genres_bytes:
        return xml_string
    genres_bytes = genres_bytes.replace(" ", char, 1)
    return set_controlfield_chars(xml_string, "008", 24, genres_bytes)

def remove_008_genre(xml_string: str, char: str) -> str:
    """
    Remove a character and reformat the characters in 008 genre field
    Args:
        xml_string (str): The MARC XML string to modify.
        char (str): The character to remove from the 008 genre field.
    Returns:
        str: The modified MARC XML string with the updated 008 genre field."""
    genres_bytes = get_controlfield_chars(xml_string, "008", 24, 4)
    if char not in genres_bytes:
        return xml_string
    genres_bytes = genres_bytes.replace(char, "", 1)
    genres_bytes =  genres_bytes + " " * (4 - len(genres_bytes))
    return set_controlfield_chars(xml_string, "008", 24, genres_bytes)

def remove_subfield(xml_string: str, field_tag: int, subfield_code: str) -> str:
    """
    Remove a specific subfield from a datafield
    Args:
        xml_string (str): The MARC XML string to modify.
        field_tag (int): The tag of the datafield containing the subfield.
        subfield_code (str): The code of the subfield to remove.
    Returns:
        str: The modified MARC XML string with the specified subfield removed.
    """
    root = ET.fromstring(xml_string)
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    
    datafield = root.find(f".//*[@tag='{field_tag}']")
    if datafield is not None:
        subfield = datafield.find(f"*[@code='{subfield_code}']")
        if subfield is not None:
            datafield.remove(subfield)
    
    return ET.tostring(root, encoding='unicode', method='xml')

def correct_marc_error(error_message: str, xml_string: str) -> str:
    """
    Correct MARC XML errors based on error message
    
    Args:
        error_message (str): The error message describing the issue
        xml_string (str): The MARC XML string to be corrected
        
    Returns:
        str: The corrected MARC XML string
    """
    #print(f"Debug - Processing error: {error_message}")

    # Exact error message matches
    error_message = preprocess_error_message(error_message)

    # Handle 008 byte corrections
    if get_controlfield_length(xml_string, "008") == 40: # Don't correct 008 if it's not 40 characters
        genre_messages_for_008 = {
            "CATALOGER: 655 $a Abstracts found, but 'a' is missing in 008 bytes 24-27.": "a",
            "CATALOGER: 655 $a Bibliography found, but 'b' is missing in 008 bytes 24-27.": "b",
            "CATALOGER: 655 $a Encyclopedia found, but 'e' is missing in 008 bytes 24-27.": "e",
            "CATALOGER: 655 $a Handbook found, but 'f' is missing in 008 bytes 24-27.": "f",
            "CATALOGER: 655 $a Index found, but 'i' is missing in 008 bytes 24-27.": "i",
            "CATALOGER: 655 $a Patent found, but 'j' is missing in 008 bytes 24-27.": "j",
            "CATALOGER: 655 $a Programmed Instruction found, but 'p' is missing in 008 bytes 24-27.": "p",
            "CATALOGER: 655 $a Directory found, but 'r' is missing in 008 bytes 24-27.": "r",
            "CATALOGER: 655 $a Legal Case, but 'v' is missing in 008 bytes 24-27.": "v",
            "CATALOGER: 655 $a Legislation, but 'l' is missing in 008 bytes 24-27.": "l",
            "CATALOGER: 655 $a Statistics, but 's' is missing in 008 bytes 24-27.": "s",
            "CATALOGER: 655 $a Technical Report, but 't' is missing in 008 bytes 24-27.": "t",
            "CATALOGER: 655 $a Graphic Novel, but '6' is missing in 008 bytes 24-27.": "6",
            "CATALOGER: 655 $a Catalog (or specific Catalog PT) found, but 'c' is missing in 008 bytes 24-27.": "c",
            "CATALOGER: 655 $a Dictionary (or specific Dictionary PT) found, but 'd' is missing in 008 bytes 24-27.": "d",
            "502 exists and bytes 24-27 does not contain 'm'.": "m"
            }

        if error_message in genre_messages_for_008:
            return add_008_genre(xml_string, genre_messages_for_008[error_message])
        
        if "CATALOGER: 655 $a 'Biography' is present, but 008/34 is not 'b' or 'c'." in error_message:
            temp = get_subfield(xml_string, "060", "a")
            if temp is None or "WZ" not in temp:
                return xml_string
            if temp is not None and temp == "WZ 100":
                return set_controlfield_chars(xml_string, "008", 34, "b")
            return set_controlfield_chars(xml_string, "008", 34, "c")
        
        if "008 Date 1 is empty." in error_message or "008/7-14 are all 'blank'." in error_message:
            year_match = None
            temp = get_all_indicators_and_subfields_for_tag(xml_string, "260")
            temp = [tag['subfields']['c'] for tag in temp if tag['subfields'].get('c', '') != ""]
            if len(temp) > 0:
                year_match = re.search(r'(\d{4})', temp[0])
                if year_match:
                    return set_controlfield_chars(xml_string, "008", 7, year_match.group(1))
            
            temp = get_all_indicators_and_subfields_for_tag(xml_string, "264")
            temp = [tag['subfields']['c'] for tag in temp if tag['subfields'].get('c', '') != ""]
            if len(temp) > 0:
                year_match = re.search(r'(\d{4})', temp[0])
                if year_match:
                    return set_controlfield_chars(xml_string, "008", 7, year_match.group(1))

        if "008/24-27 contains 'n' and 'b'." in error_message:
            temp = get_all_indicators_and_subfields_for_tag(xml_string, "655")
            for tag in temp:
                if tag['subfields'].get('a','') == "Review":
                    return remove_008_genre(xml_string, "b")
            return remove_008_genre(xml_string, "n")
        
        if "504$a contains 'Includes' and 'bibliograh*', 008/24-27 does not contain 'b' or 'n'." in error_message:
            temp = get_all_indicators_and_subfields_for_tag(xml_string, "655")
            for tag in temp:
                if tag['subfields'].get('a','') == "Review":
                    return add_008_genre(xml_string, "n")
            return add_008_genre(xml_string, "b")
        
        if "300$b exists and 008/18-21 are all 'blank'." in error_message:
            return set_controlfield_chars(xml_string, "008", 18, "a")
        
        if "040 $a begins with DNLM, Cataloging Source (008/39) not 'blank'." in error_message: 
            return set_controlfield_chars(xml_string, "008", 39, " ")
        
        if "008/06 is 's', 008/11-14 not 'blank'" in error_message:
            return set_controlfield_chars(xml_string, "008", 11, "    ")
        
        if "008 byte 6 is 'c', Date 2 should be '9999'." in error_message: 
            return set_controlfield_chars(xml_string, "008", 11, "9999")
        
        #if "044 is United States but 008 byte 17 isn't 'u'." in error_message:
            #return set_controlfield_chars(xml_string, "008", 17, "u")
        
        if "CATALOGER: 655 $a Festschrift found, but '1' is missing in 008 byte 30." in error_message:
            return set_controlfield_chars(xml_string, "008", 30, "1")
        
        if "CATALOGER: 655 $a 'Congress' is present, but 008/29 is not '1'." in error_message:
            return set_controlfield_chars(xml_string, "008", 29, "1")
        
        if "CATALOGER: 655 $a 'Autobiography' is present, but 008/34 is not 'a'." in error_message:
            return set_controlfield_chars(xml_string, "008", 34, "a")
        
        if "500 or 504 includes note about index and 008/31 is not '1'." in error_message:
            return set_controlfield_chars(xml_string, "008", 31, "1")
        
        if "500 or 504$a contains 'index*' and 008/31 is not '1'." in error_message:
            return set_controlfield_chars(xml_string, "008", 31, "1")

    # Handle other specific cases

    if "035 $9 has LTR character at the end." in error_message:
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "035")
        temp = [tag for tag in temp if tag['subfields'].get("9", "") != ""]
        for t in temp:
            val = t['subfields'].get("9", "")
            # Remove all unicode characters with regex
            val = re.sub(rf"[{''.join(unicode_embeddings_to_remove)}]", "", val)
            xml_string = set_subfield_by_id(xml_string, t['id'], "9", val)

    if "exists and 336 $a still image not present." in error_message:
        xml_string = create_field(xml_string, "336")
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "336")
        # Get 336 with no subfields (new one)
        temp = [tag for tag in temp if len(tag['subfields']) == 0]

        xml_string = set_subfield_by_id(xml_string, temp[0]['id'], "a", "still image")
        xml_string = set_subfield_by_id(xml_string, temp[0]['id'], "b", "sti")
        xml_string = set_subfield_by_id(xml_string, temp[0]['id'], "2", "rdacontent")
        return xml_string

    # logic is not sound here, commenting out for now and adding something similar as an error in bib_validator.py
    #if "040 $e is rda and 264 field is missing." in error_message:
        #temp = get_all_indicators_and_subfields_for_tag(xml_string, "260")
        #if len(temp) > 0:
            #return set_tag_by_id(xml_string, temp[0]['id'], "264")

    if "337 subfield a is 'computer' but 006 field is missing." in error_message: 
        xml_string = create_field(xml_string, "006", type='controlfield')
        xml_string = set_controlfield_chars(xml_string, "006", 0, "m     o  d        ")
        return xml_string
    
    if "337 subfield a is 'computer' but 007 field is missing." in error_message:
        xml_string = create_field(xml_string, "007", type='controlfield')
        xml_string = set_controlfield_chars(xml_string, "007", 0, "cr |||||||||||")
        
    if "510 has PMC but is missing PMC URL" in error_message:
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "999")
        temp = [tag for tag in temp if tag['subfields'].get("a", "") == "AUTH"]
        if len(temp) <= 0:
            return xml_string
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "035")
        temp = [tag for tag in temp if tag['subfields'].get("9", "") != ""]
        if len(temp) <= 0:
            return xml_string
        
        url_val = f"https://pmc.ncbi.nlm.nih.gov/journals/?term={temp[0]['subfields']['9']}"
        
        xml_string = create_field(xml_string, "856", type='datafield')
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "856")
        temp = [tag for tag in temp if len(tag['subfields']) == 0]
        xml_string = set_subfield_by_id(xml_string, temp[0]['id'], "u", url_val)
        xml_string = set_indicator_by_id(xml_string, temp[0]['id'], '1', "4")

        if get_controlfield_chars(xml_string, "006", 0, 1) == "m":
            return set_indicator_by_id(xml_string, temp[0]['id'], '2', "0")
        return set_indicator_by_id(xml_string, temp[0]['id'], '2', " ")
            
    if "041 1st indicator should be 0 or 1" in error_message:
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "041")
        for tag in temp:
            if tag['subfields'].get('h',None) is not None:
                xml_string =  set_indicator(xml_string, "041", 1, "1")
            else:
                xml_string = set_indicator(xml_string, "041", 1, "0")

    if "CATALOGER: 999 is AUTH but 950's exist" in error_message:
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "950")
        for tag in temp:
            xml_string = remove_tag_by_id(xml_string, tag['id'])
        return xml_string
    
    if "264 has a 2nd indicator of '0', Leader character 7 is 'a'" in error_message:
        return set_indicator(xml_string, "264", 2, "1")
    
    #Commenting this rule out as we only want it to print an error message and not update the record.
    #if "Leader byte 18 is 'i', but 040 $e is not 'rda'." in error_message:
        #temp = get_all_indicators_and_subfields_for_tag(xml_string, "040")
        #if len(temp) > 0:
            #return add_subfield_by_id(xml_string, temp[0]['id'], "e", "rda")
    
    if "245 $n should come before $p." in error_message: 
        return reorder_subfields(xml_string, "245", "n", "p")
    
    if "If subfield h is present in the 041 field, the first indicator should be 1." in error_message: 
        return set_indicator(xml_string, "041", 1, "1")
    
    if "510 $9 is '0' (zero), 510 Ind 1 not equal '0' (zero)" in error_message:
        return set_indicator(xml_string, "510", 1, "0")
    
    if "245 first indicator should be '1'" in error_message:
        return set_indicator(xml_string, "245", 1, "1")
    
    if "245 first indicator should be '0'" in error_message:
        return set_indicator(xml_string, "245", 1, "0")
    
    if "CATALOGER: 650 field with 2nd indicator '7' is missing subfield 2 with value 'meshscr'" in error_message:
        return set_subfield(xml_string, "650", "2", "meshscr", ind2="7")
    
    if "040$e = rda and 264 2nd indicator '1' not present" in error_message:
        if get_leader_field(xml_string)[6] != "t":
            return set_indicator(xml_string, "264", 2, "1")
    
    if "The first 264 field does not have ind1=' ' and ind2='1', and there is no 260 field present." in error_message:
        if get_leader_field(xml_string)[6] != "t":
            xml_string = set_indicator(xml_string, "264", 1, " ")
            xml_string = set_indicator(xml_string, "264", 2, "1")
            return xml_string
    
    ### Complex Errors ###
    
    if "CATALOGER: Encoding level is not full. Newly cataloged monographs should have a full encoding level" in error_message \
    or "CATALOGER: encoding level is 7. Monographs should be full level." in error_message:
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "994")
        temp = [tag for tag in temp if tag['subfields'].get('b', '') != ""]
        if len(temp) <= 0:
            return xml_string

        temp_date = temp[0]['subfields']['b']
        date_length = len(temp_date)
        if date_length not in [4, 6, 8]:
            return xml_string
        
        if len(temp_date) == 8 and temp_date < "20240101":
            return xml_string
        if len(temp_date) == 6 and temp_date < "202401":
            return xml_string
        if len(temp_date) == 4 and temp_date < "2024":
            return xml_string
        
        return set_leader_chars(xml_string, 17, " ")
        
    if "More than one 362 field with first indicator of 0." in error_message:
        # Find all 362 fields with ind1=1
        fields = get_all_indicators_and_subfields_for_tag(xml_string, "362")
        fields = [field for field in fields if field['indicators']["ind1"] == "0"]
        new_a_value = "; ".join([field['subfields']['a'] for field in fields])
        target_field_id = fields[0]['id']

        xml_string = set_subfield_by_id(xml_string, target_field_id, "a", new_a_value)

        if len(fields) > 1:
            # Remove all but the first
            for field in fields[1:]:
                xml_string = remove_tag_by_id(xml_string, field.get("id"))
        return xml_string
    
    if "More than one 362 field with first indicator of 1." in error_message:
        # Find all 362 fields with ind1=1
        fields = get_all_indicators_and_subfields_for_tag(xml_string, "362")
        fields = [field for field in fields if field['indicators']["ind1"] == "1"]
        new_a_value = "; ".join([field['subfields']['a'] for field in fields])
        new_z_value = "; ".join([field['subfields']['z'] for field in fields])
        target_field_id = fields[0]['id']

        xml_string = set_subfield_by_id(xml_string, target_field_id, "a", new_a_value)
        xml_string = set_subfield_by_id(xml_string, target_field_id, "z", new_z_value)

        if len(fields) > 1:
            # Remove all but the first
            for field in fields[1:]:
                xml_string = remove_tag_by_id(xml_string, field.get("id"))
        return xml_string

    if "Error: 264 field with ind2='4' is missing subfield c." in error_message:
        subfields_by_tag = get_all_indicators_and_subfields_for_tag(xml_string, "264")
        if len(subfields_by_tag) == 0:
            return xml_string
        
        chosen_tag_dict = None
        for subfield_dict in subfields_by_tag:
            if subfield_dict['indicators']['ind2'] == "4":
                chosen_tag_dict = subfield_dict
                break

        # Check that there are no other subfields except a
        if chosen_tag_dict is not None and len(chosen_tag_dict['subfields']) == 1 and "a" in chosen_tag_dict['subfields']:
            xml_string = set_subfield_by_id(xml_string, chosen_tag_dict['id'], "c", chosen_tag_dict['subfields']['a'])
            return remove_subfield_by_id(xml_string, chosen_tag_dict['id'], "a")
           
        # First try date 2
        date = get_controlfield_chars(xml_string, "008", 11, 4)
        if date not in ["uuuu", "    "]:
            return set_subfield_by_id(xml_string, chosen_tag_dict['id'], "c", date)
        
        # Then try date 1
        date = get_controlfield_chars(xml_string, "008", 7, 4)
        if date not in ["uuuu", "    "]:
            return set_subfield_by_id(xml_string, chosen_tag_dict['id'], "c", date)
 
    if "The 856 field should not have a second indicator of 1." in error_message:
        if get_controlfield_chars(xml_string, "006", 0, 1) == "m" or get_subfield(xml_string, "337", "a") == "computer":
            return set_indicator(xml_string, "856", 2, "0")
        return set_indicator(xml_string, "856", 2, " ")

    if "CATALOGER: Both 041 and 044 fields are missing." in error_message:
        # Copy language down from 008 to 041
        lang = get_controlfield_chars(xml_string, "008", 35, 3)
        if lang != "   " and lang in valid_language_codes:
            xml_string = create_field(xml_string, "041", type='datafield')
            xml_string = set_indicator(xml_string, "041", 1, "0")
            xml_string = set_subfield(xml_string, "041", "a", lang)
        
        # Copy country code down from 008 to 044
        country_code = get_controlfield_chars(xml_string, "008", 15, 3)
        if country_code in valid_country_codes:
            country = valid_country_codes[country_code]
            xml_string = create_field(xml_string, "044", type='datafield')
            #9, and 999 range is for local use. Mainly any 9 for the 3 digit fields (ex: 900-999, 9xx, subfield 9)
            xml_string = set_subfield(xml_string, "044", "9", country) 
        
        return xml_string
        
    if "CATALOGER: 040 $e = rda and 100 field is present, 100 $e not present" in error_message:
        # If there is a single contributor, 100$e is author
        potential_author = get_subfield(xml_string, "100", "a")
        other_contributors = list()
        other_contributors += [
            {"name": get_subfield(xml_string, "700", "a"), "relationship": get_subfield(xml_string, "700", "e")},
            {"name": get_subfield(xml_string, "710", "a"), "relationship": get_subfield(xml_string, "710", "e")},
            {"name": get_subfield(xml_string, "711", "a"), "relationship": get_subfield(xml_string, "711", "j")},
            {"name": get_subfield(xml_string, "720", "a"), "relationship": get_subfield(xml_string, "720", "e")},
            {"name": get_subfield(xml_string, "111", "a"), "relationship": get_subfield(xml_string, "111", "j")}
        ]
        
        author_exists = False
        other_contributors_exist = False
        for item in other_contributors:
            if item["name"] is not None and item["name"] == potential_author:
                # If the relationship is already set, use that
                return set_subfield(xml_string, "100", "e", item["relationship"])
            if item["name"] is not None and item["name"] == "author":
                # If another author exists, we do not know this relationship
                author_exists = True
                other_contributors_exist = True
                break
            if item["name"] is not None:
                other_contributors_exist = True

        if not author_exists and not other_contributors_exist:
            return set_subfield(xml_string, "100", "e", "author")
        
    # Handle IndexCat punctuation errors
    # 245 FIELD CORRECTIONS
    if error_message == "INDEXCAT: 245 $a should end with ' :' when followed by $b":
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "245")
        for tag in temp:
            if 'a' in tag['subfields'] and 'b' in tag['subfields']:
                a_value = tag['subfields']['a']
                xml_string = set_subfield_by_id(xml_string, tag['id'], "a", fix_punctuation(a_value, ' :'))
        return xml_string

    if error_message == "INDEXCAT: 245 $b should end with ' /' when followed by $c":
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "245")
        for tag in temp:
            if 'b' in tag['subfields'] and 'c' in tag['subfields']:
                b_value = tag['subfields']['b']
                xml_string = set_subfield_by_id(xml_string, tag['id'], "b", fix_punctuation(b_value, ' /'))
        return xml_string

    if error_message == "INDEXCAT: 245 $a should end with ' /' when directly followed by $c (without $b)":
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "245")
        for tag in temp:
            if 'a' in tag['subfields'] and 'c' in tag['subfields'] and 'b' not in tag['subfields']:
                a_value = tag['subfields']['a']
                xml_string = set_subfield_by_id(xml_string, tag['id'], "a", fix_punctuation(a_value, ' /'))
        return xml_string

    # 264 FIELD CORRECTIONS
    if error_message == "INDEXCAT: 264 $a should end with ' :' when followed by $b":
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "264")
        for tag in temp:
            if 'a' in tag['subfields'] and 'b' in tag['subfields']:
                a_value = tag['subfields']['a']
                xml_string = set_subfield_by_id(xml_string, tag['id'], "a", fix_punctuation(a_value, ' :'))
        return xml_string

    if error_message == "INDEXCAT: 264 $b should end with ',' when followed by $c":
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "264")
        for tag in temp:
            if 'b' in tag['subfields'] and 'c' in tag['subfields']:
                b_value = tag['subfields']['b']
                xml_string = set_subfield_by_id(xml_string, tag['id'], "b", fix_punctuation(b_value, ','))
        return xml_string

    if error_message == "INDEXCAT: 264 $a should end with ',' when directly followed by $c (without $b)":
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "264")
        for tag in temp:
            if 'a' in tag['subfields'] and 'c' in tag['subfields'] and 'b' not in tag['subfields']:
                a_value = tag['subfields']['a']
                xml_string = set_subfield_by_id(xml_string, tag['id'], "a", fix_punctuation(a_value, ','))
        return xml_string

    if error_message == "INDEXCAT: 264 $c should end with a period or other punctuation":
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "264")
        for tag in temp:
            if 'c' in tag['subfields']:
                c_value = tag['subfields']['c']
                c_value = c_value.rstrip()
                if not (c_value.endswith('.') or c_value.endswith('?') or 
                      c_value.endswith('!') or c_value.endswith(']') or 
                      c_value.endswith(')')):
                    xml_string = set_subfield_by_id(xml_string, tag['id'], "c", fix_punctuation(c_value, '.'))
        return xml_string

    # 300 FIELD CORRECTIONS
    if error_message == "INDEXCAT: 300 $a should end with ' :' when followed by $b":
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "300")
        for tag in temp:
            if 'a' in tag['subfields'] and 'b' in tag['subfields']:
                a_value = tag['subfields']['a']
                xml_string = set_subfield_by_id(xml_string, tag['id'], "a", fix_punctuation(a_value, ' :'))
        return xml_string

    if error_message == "INDEXCAT: 300 $b should end with ' ;' when followed by $c":
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "300")
        for tag in temp:
            if 'b' in tag['subfields'] and 'c' in tag['subfields']:
                b_value = tag['subfields']['b']
                xml_string = set_subfield_by_id(xml_string, tag['id'], "b", fix_punctuation(b_value, ' ;'))
        return xml_string

    if error_message == "INDEXCAT: 300 $a should end with ' ;' when directly followed by $c (without $b)":
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "300")
        for tag in temp:
            if 'a' in tag['subfields'] and 'c' in tag['subfields'] and 'b' not in tag['subfields']:
                a_value = tag['subfields']['a']
                xml_string = set_subfield_by_id(xml_string, tag['id'], "a", fix_punctuation(a_value, ' ;'))
        return xml_string

    # Correction for Academic Dissertation check
    if error_message == "INDEXCAT: 655 'Academic Dissertation' present but 008/24 is not 'm'":
        xml_string = set_controlfield_chars(xml_string, "008", 24, "m")
    
    # Correction for 590 brackets check
    if error_message == "INDEXCAT: 590 $a contains bracketed content which should be removed":
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "590")
        for tag in temp:
            if 'a' in tag['subfields'] and '[' in tag['subfields']['a'] and ']' in tag['subfields']['a']:
                a_value = tag['subfields']['a']
                # Replace bracketed text by removing the brackets but keeping the content
                bracket_pattern = r'\[(.*?)\]'
                a_value = re.sub(bracket_pattern, r'\1', a_value)
                xml_string = set_subfield_by_id(xml_string, tag['id'], 'a', a_value)
    
   # Correction for 650 field check
    if error_message == "INDEXCAT: 650 field should not exist in IndexCat records":
        try:
            # Parse the XML
            root = ET.fromstring(xml_string)
            ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
            
            # Find all 650 tags
            tags_to_remove = []
            for tag in root.findall(".//{http://www.loc.gov/MARC21/slim}datafield"):
                if tag.get("tag") == "650":
                    tags_to_remove.append(tag)
            
            # Remove each tag
            for tag in tags_to_remove:
                parent = None
                # Find the parent element
                for node in root.iter():
                    if tag in list(node):
                        parent = node
                        break
                
                # Only remove if we found the parent
                if parent is not None:
                    try:
                        parent.remove(tag)
                    except ValueError:
                        # If for some reason the tag is not in the parent, just continue
                        pass
            
            # Convert back to string
            xml_string = ET.tostring(root, encoding='unicode', method='xml')
        except Exception:
            # Original XML is preserved if an error occurs
            pass


    # Correction for 300 field "cm." check
    if error_message == "INDEXCAT: 300 field contains 'cm.' which should be 'cm'":
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "300")
        for tag in temp:
            for code, value in tag['subfields'].items():
                if "cm." in value:
                    xml_string = set_subfield_by_id(xml_string, tag['id'], code, value.replace("cm.", "cm"))
    
    # Correction for 500 field brackets check
    if error_message == "INDEXCAT: 500 field contains brackets which should be removed":
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "500")
        for tag in temp:
            for code, value in tag['subfields'].items():
                if '[' in value or ']' in value:
                    # Replace bracketed text by removing the brackets but keeping the content
                    bracket_pattern = r'\[(.*?)\]'
                    corrected_value = re.sub(bracket_pattern, r'\1', value)
                    # Remove any remaining brackets not caught by the pattern
                    corrected_value = corrected_value.replace("[", "").replace("]", "")
                    xml_string = set_subfield_by_id(xml_string, tag['id'], code, corrected_value)

    # Handle IndexCat 044 field corrections
    if error_message == "INDEXCAT: 044 field has subfields other than $a or $9":
        try:
            # Parse the XML
            root = ET.fromstring(xml_string)
            ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
            
            # Find all 044 fields
            for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                if datafield.attrib['tag'] == '044':
                    # Find all subfields that are not $a or $9
                    invalid_subfields = []
                    for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                        if subfield.attrib['code'] not in ['a', '9']:
                            invalid_subfields.append(subfield)
                    
                    # Remove all invalid subfields
                    for subfield in invalid_subfields:
                        datafield.remove(subfield)
            
            return ET.tostring(root, encoding='unicode', method='xml')
        except Exception:
            # If any error occurs, return the original XML
            return xml_string
        
    if error_message == "INDEXCAT: 044 field uses $a instead of $9":
        # Get all 044 fields with their subfields
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "044")
        
        # Process each 044 field
        for tag in temp:
            if 'a' in tag['subfields']:
                # Get the $a value
                a_value = tag['subfields']['a']
                
                # Remove $a and add $9 with the same value
                xml_string = remove_subfield_by_id(xml_string, tag['id'], 'a')
                xml_string = add_subfield_by_id(xml_string, tag['id'], '9', a_value)
        
        return xml_string

    # Handle illustration code errors
    if "INDEXCAT: Illustration codes in 008/18-21 should be" in error_message:
        return correct_illustration_codes(xml_string, error_message)

    if "008/31 = '1', but the 500 or 504 field does not contain index*" in error_message:
        # Change 008/31 to '0'
        return set_controlfield_chars(xml_string, "008", 31, "0")

    # Return original if no correction needed
    return xml_string

def correct_marc_error_precise(error_message: str, datafield_id: str, subfield_id: str, xml_string: str) -> str:
    """Correct specific MARC XML errors based on precise datafield and subfield IDs.
    Args:
        error_message (str): The error message to process.
        datafield_id (str): The ID of the datafield to correct.
        subfield_id (str): The ID of the subfield to correct.
        xml_string (str): The MARC XML string to correct.
    Returns:
        str: The corrected MARC XML string.
    """
    if not (id_exists(xml_string, datafield_id) and id_exists(xml_string, subfield_id)):
        return xml_string

    if error_message == "INDEXCAT: 044 field uses $a instead of $9":
        temp_subfield_val = precise_get_by_id(xml_string, subfield_id)
        xml_string = precise_remove_by_id(xml_string, subfield_id)
        return add_subfield_by_id(xml_string, datafield_id, '9', temp_subfield_val)
    
    if "Subfield h should not exist in the 245 field." in error_message:
        return precise_remove_by_id(xml_string, subfield_id)

    if "245 $n should end with a comma." in error_message:
        temp_subfield_val = precise_get_by_id(xml_string, subfield_id)
        return precise_set_by_id(xml_string, subfield_id, temp_subfield_val.rstrip() + ",")
    
    if "CATALOGER: 830 $a contains unbalanced parentheses." in error_message:
        temp_subfield_val = precise_get_by_id(xml_string, subfield_id)

        excess_left = temp_subfield_val.count("(") - temp_subfield_val.count(")")
        if excess_left > 0:
            temp_subfield_val = temp_subfield_val + ")" * excess_left
            return precise_set_by_id(xml_string, subfield_id, temp_subfield_val)
        
    if "041 $a is 'und'." in error_message:
        lang = get_controlfield_chars(xml_string, "008", 35, 3)
        if lang != "   " and lang in valid_language_codes:
            xml_string = set_indicator_by_id(xml_string, datafield_id, "1", "0")
            return precise_set_by_id(xml_string, subfield_id, lang)
    
    if "CATALOGER: Record has 042 pcc but 992 $e is EL. Should it be EF?" in error_message:
        temp = get_all_indicators_and_subfields_for_tag(xml_string, "994")
        temp = [tag for tag in temp if tag['subfields'].get('b', '') != ""]
        if len(temp) <= 0:
            return xml_string

        temp_date = temp[0]['subfields']['b']
        date_length = len(temp_date)
        if date_length not in [4, 6, 8]:
            return xml_string
        
        if len(temp_date) == 8 and temp_date < "20240101":
            return xml_string
        if len(temp_date) == 6 and temp_date < "202401":
            return xml_string
        if len(temp_date) == 4 and temp_date < "2024":
            return xml_string
        
        temp_subfield_val = precise_get_by_id(xml_string, subfield_id)
        if temp_subfield_val != "EL":
            return xml_string
        
        return precise_set_by_id(xml_string, subfield_id, "EF")
    
    if "Subfield b in field 040 should be 'eng'." in error_message:
        temp_subfield_val = precise_get_by_id(xml_string, subfield_id)
        return precise_set_by_id(xml_string, subfield_id, "eng")
    
    if "CATALOGER: Subfield a in field" in error_message and \
    "should not end with a period." in error_message:
        # Remove all periods at the end of the string with regex
        temp_subfield_val = precise_get_by_id(xml_string, subfield_id)
        temp_subfield_val = re.sub(r'\.+$', '', temp_subfield_val)
        return precise_set_by_id(xml_string, subfield_id, temp_subfield_val)
    
    if "indicators should be blank and 2." in error_message:
        # Set indicators to blank and 2
        xml_string = set_indicator_by_id(xml_string, datafield_id, "1", " ")
        return set_indicator_by_id(xml_string, datafield_id, "2", "2")


    return xml_string

def route_marc_error(error: object, xml_string: str) -> str:
    """
    Correct MARC XML errors based on a specific error dictionary
    
    Args:
        error (dict): The error dictionary containing the error message and other details
        xml_string (str): The MARC XML string to be corrected
        
    Returns:
        str: The corrected MARC XML string
    """
    datafield_id, subfield_id = None, None
    if isinstance(error, dict):
        error_message = error.get("error", None)
        datafield_id = error.get("datafield_id", None)
        subfield_id = error.get("subfield_id", None)
    
    else:
        error_message = str(error)
    
    error_message = preprocess_error_message(error_message)

    if error_message is None:
        return xml_string
    if datafield_id is None or subfield_id is None:
        return correct_marc_error(error_message, xml_string)
    else:
        return correct_marc_error_precise(error_message, datafield_id, subfield_id, xml_string)
    
def correct_illustration_codes(xml_string, error_message):
    """
    Correct illustration codes in 008/18-21 based on 300 field content.
    
    Args:
        xml_string: The MARC XML string to correct
        error_message: The error message from validator
        
    Returns:
        The corrected MARC XML string
    """
    if "INDEXCAT: Illustration codes in 008/18-21 should be" not in error_message:
        return xml_string
    
    # Extract the expected codes from the error message
    match = re.search(r"should be '([^']+)'", error_message)
    if not match:
        return xml_string
    
    expected_codes = match.group(1)
    
    # Update the 008 field with the expected codes
    return set_controlfield_chars(xml_string, "008", 18, expected_codes)

def correct_marc_error_batch(xml_string: str, error_messages: list[str]) -> str:
    """
    Correct MARC XML errors based on error messages
    
    Args:
        error_messages (list[str]): The error messages describing the issues
        xml_string (str): The MARC XML string to be corrected
        
    Returns:
        str: The corrected MARC XML string
    """
    for error_message in error_messages:
        xml_string = correct_marc_error(error_message, xml_string)
    return xml_string