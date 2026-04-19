from xml.etree import ElementTree as ET
from urllib.parse import urlparse
from bib_marc_validator.bib_xml_corrections import get_all_indicators_and_subfields_for_tag, get_controlfield_length, get_controlfield_chars
from bib_marc_validator.resources.validation.marc_validation_resources import unicode_embeddings_to_remove

#global variables: 
# List of values to check in 655 $a
atlas_like_values = [
                'Atlas',
                'Book Illustrations',
                'Caricature',
                'Cartoon',
                'Comic Book',
                'Graphic Novel',
                'Infographic',
                'Drawing',
                'Map',
                'Portrait',
                'Photograph',
                'Photomechanical Print',
                'Postcard',
                'Poster',
                'Pictorial Work'
            ]

# Adding a comment for Alvin
def format_error(error_message, datafield, subfield):
    """
    Format an error message with datafield and subfield UUIDs.
    Args:
        error_message (str): The error message to format.
        datafield (Element): The datafield element from the MARCXML.
        subfield (Element): The subfield element from the MARCXML.
    Returns:
        dict: A dictionary containing the formatted error message and UUIDs."""
    if datafield is None:
        datafield_uuid = "unknown"
    else:
        datafield_uuid = datafield.attrib['id'] if 'id' in datafield.attrib else "unknown"
    if subfield is None:
        subfield_uuid = "unknown"
    else:
        subfield_uuid = subfield.attrib['id'] if 'id' in subfield.attrib else "unknown"

    return {"error": error_message,
        "datafield_id": datafield_uuid,
        "subfield_id": subfield_uuid}

def validate_marcxml_record(marcxml_data, record_type):
    """ Validate a MARCXML record against various rules and return a list of errors.
    Args:
        marcxml_data (str): The MARCXML data as a string.
        record_type (str): The type of the record, either "regular" or "indexcat".
    Returns:
        bool: Whether or not the record should be validated (pre-validation).
        list: A list of error messages found during validation.
    """
    errors = []

    
    record_type = "regular" # Default to regular always so it can be inferred automatically.
    # Parse the MARXML data
    root = ET.fromstring(marcxml_data)

    # List of 999 subfield a values to skip validation
    skip_values = {'BRF', 'ACC', 'BDW', 'IDM', 'NLM', 'SMC', 'WDN'}

    # Flag to determine if validation should be skipped
    skip_validation = False

    # Check for 999 subfield a with specified values
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '999':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a' and subfield.text == "IDX":
                    record_type = "indexcat"
                if subfield.attrib['code'] == 'a' and subfield.text in skip_values:
                    errors.append("Validator doesn't work on records with a 999 $a value of: BRF, ACC, BDW, IDM, NLM, SMC, WDN.")
                    skip_validation = True
                    break
        if skip_validation:
            break

    # If validation should be skipped, exit the script
    if skip_validation:
        return False, errors
        
    # Perform nightly validation checks
    errors += nightly_validation_checks(marcxml_data, record_type)

    # Check for the presence of required fields
    required_fields = ['336', '337', '338']
    for field in required_fields:
        field_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == field:
                field_present = True
                break
        if not field_present:
            errors.append(f"Missing {field} field in the record.")

    # Get the leader field
    leader_field = root.find('.//{http://www.loc.gov/MARC21/slim}leader').text

    # Check if the leader field is present and has enough characters
    if leader_field and len(leader_field) >= 8:
        character_8 = leader_field[7]  # Get the 8th character (0-based indexing)

        # Check if the 8th character is 'a', 'm', 's', 'c', or 'i'
        if character_8 not in ['a', 'm', 's', 'c', 'i']:
            errors.append("Leader Byte 07 not 'a', 'm', 's', 'c', or 'i'.")
    else:
        errors.append("Leader field is missing or does not contain enough characters.")
            
    # Check the length of the 008 field
    field_008 = None
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
        if controlfield.attrib['tag'] == '008':
            field_008 = controlfield.text
            if len(field_008) != 40:
                errors.append(f"Length of the 008 field is {len(field_008)}, should be 40 characters.")
            break

    leader_blank_18 = False
    has_042_field = False
    has_655_postcard = False

    # Check Leader character 18. Updated 8/14
    leader_text = root.find('.//{http://www.loc.gov/MARC21/slim}leader').text
    if len(leader_text) >= 19:
        leader_char_18 = leader_text[17]
        if leader_char_18 == ' ':
            leader_blank_18 = True

    # Check for the presence of the 042 field
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '042':
            has_042_field = True

        # Check for the 655 field with subfield a value "Postcard"
        if datafield.attrib['tag'] == '655':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a' and subfield.text.strip().lower() == 'postcard':
                    has_655_postcard = True
                    break

    # Check if 999 $a is "NOC": 999 $a NOC equals Not Our Collection
    has_noc_999 = False
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '999':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a' and subfield.text.strip() == 'NOC':
                    has_noc_999 = True
                    break
        if has_noc_999:
            break

    # Add error message if necessary, but skip if 999 $a is "NOC"
    if leader_blank_18 and not has_042_field and not has_655_postcard and not has_noc_999:
        errors.append("Leader Byte 17 is blank and 042 field is not present. Do you want to add 042 pcc?")

    # Check for the presence of the 060 field
    has_060_field = False
    has_999_specific_values = False
    has_210_field = False
    noc_condition_met = False
    has_999_field = False  # Flag to track if 999 field exists
    has_postcard = False  # Flag to track if 655 $a contains "Postcard"

    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '060':
            has_060_field = True

        if datafield.attrib['tag'] == '999':
            has_999_field = True  # Mark that 999 field is present
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a' and subfield.text.strip() in ['AUTH', 'WTC', 'CIP', 'NOC']:
                    has_999_specific_values = True
                    if subfield.text.strip() == 'NOC':
                        noc_condition_met = True

        if datafield.attrib['tag'] == '210':
            has_210_field = True

        # Check if 655 $a contains "Postcard"
        if datafield.attrib['tag'] == '655':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a' and subfield.text.strip().lower() == "postcard":
                    has_postcard = True
                    break

    # Add error message if necessary, but skip if "Postcard" is found in 655 $a
    if not has_060_field and (has_999_specific_values or not has_999_field) and not has_postcard:
        if not (noc_condition_met and has_210_field):
            errors.append("CATALOGER: No 060 in record. Do you need one?")

    # Initialize counter for 035 fields with subfield 9
    count_035_subfield_9 = 0

    # Look for all 035 fields in the record
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '035':
            # Check if there is a subfield 9 present
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == '9':
                    # Catch if nexpected unicode characters are found at end of 035 $ 9
                    temp = subfield.text[-1]
                    if temp in unicode_embeddings_to_remove:
                        errors.append("035 $9 has LTR character at the end.")
                    count_035_subfield_9 += 1


    # Check if there are two 035 fields with subfield 9
    if count_035_subfield_9 == 2:
        errors.append("Record contains 2 035 $9's.")
    
    # Check for '|' character in the 008 characters 7-18
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
        if controlfield.attrib['tag'] == '008':
            if len(controlfield.text) >= 18:
                characters_7_18 = controlfield.text[6:18]
                if '|' in characters_7_18:
                    errors.append("008/06-17 contains a fill character (|).")
            else:
                errors.append("008 field does not contain enough characters to check for fill character.")
                break  # Exit the loop if 008 field doesn't have enough characters

    # Check for '|' character in the 008 characters 36-40
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
        if controlfield.attrib['tag'] == '008':
            if len(controlfield.text) >= 40:
                characters_36_40 = controlfield.text[35:40]
                if '|' in characters_36_40:
                    errors.append("008/35-39 contains a fill character (|).")
            else:
                errors.append("008 field does not contain enough characters to check for fill character.")
                break  # Exit the loop if 008 field doesn't have enough characters

    # Initialize variables to store the 041 subfield a value and 008 language code
    language_041 = None
    language_008 = None

    # Find the first 041 field and extract the value of subfield a
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '041':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a':
                    language_041 = subfield.text.strip()
                    break
        if language_041:
            break  # Stop after finding the first 041 $a

    # Extract the language code from the 008 field (characters 36-38)
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
        if controlfield.attrib['tag'] == '008':
            if len(controlfield.text) >= 39:  # Ensure the field contains enough characters
                language_008 = controlfield.text[35:38].strip()  # Characters 36-38 are at positions 35-37 (0-based index)
            else:
                errors.append("008 field does not contain enough characters.")
            break

    # Compare the two language codes
    if language_041 and language_008 and language_041 != language_008:
        errors.append("008 language and 041 $a do not match.")


    # Check if 008 characters 16-18 are 'xxu'
    if record_type != "indexcat":
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 18:
                    characters_16_18 = controlfield.text[15:18]
                    if characters_16_18.strip() == 'xxu':
                        errors.append("008/15-17 = xxu, does a more specific location exist?")
                else:
                    errors.append("008 field does not contain enough characters to check for specific location.")
                    break  # Exit the loop if 008 field doesn't have enough characters

    # Check if 008 characters 16-18 are 'xxc'
    if record_type != "indexcat":
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 18:
                    characters_16_18 = controlfield.text[15:18]
                    if characters_16_18.strip() == 'xxc':
                        errors.append("008/15-17 = xxc, does a more specific location exist?")
                else:
                    errors.append("008 field does not contain enough characters to check for specific location.")
                    break  # Exit the loop if 008 field doesn't have enough characters

    # Check for subfield h in the 245 field
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '245':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'h':
                    errors.append(format_error("Subfield h should not exist in the 245 field.", datafield, subfield))
                    break

    # Initialize counters for specified 1XX fields
    count_100_fields = 0
    count_110_fields = 0
    count_111_fields = 0
    count_130_fields = 0

    # Loop through the datafields and count the occurrences of specified 1XX fields
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        tag = datafield.attrib['tag']
        if tag == '100':
            count_100_fields += 1
        elif tag == '110':
            count_110_fields += 1
        elif tag == '111':
            count_111_fields += 1
        elif tag == '130':
            count_130_fields += 1

    # Calculate total count of specified 1XX fields
    total_1xx_fields = count_100_fields + count_110_fields + count_111_fields + count_130_fields

    # If the total count of specified 1XX fields is more than 1, show an error message
    if total_1xx_fields > 1:
        errors.append("Record can't have more than one 1XX field.")

    # Check if 245 $n and $p are present, and ensure $n comes first and ends with a comma
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '245':
            subfield_n_position = None
            subfield_p_position = None
            subfield_n_value = None
            
            for i, subfield in enumerate(datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield')):
                if subfield.attrib['code'] == 'n':
                    temp_subfield = subfield
                    subfield_n_position = i
                    subfield_n_value = subfield.text
                elif subfield.attrib['code'] == 'p':
                    subfield_p_position = i
            
            if subfield_n_position is not None and subfield_p_position is not None:
                if subfield_n_position > subfield_p_position:
                    errors.append("245 $n should come before $p.")
                if not subfield_n_value.endswith(','):
                    errors.append(format_error("245 $n should end with a comma.", datafield, temp_subfield))

    # Check for the presence of 040 subfield 'e' with value 'rda'
    if record_type != "indexcat":
        rda_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '040':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'e' and subfield.text == 'rda':
                        rda_present = True
                        break
            if rda_present:
                break

        if rda_present:
            # Check for the presence of 100, 110 fields
            for tag in ['100', '110']:
                xpath_query = f'.//{{http://www.loc.gov/MARC21/slim}}datafield[@tag="{tag}"]'
                datafields = root.findall(xpath_query)
                if datafields:
                    for datafield in datafields:
                        subfield_e_present = False
                        for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                            if subfield.attrib['code'] == 'e':
                                subfield_e_present = True
                                break
                        if not subfield_e_present:
                            errors.append(f"CATALOGER: 040 $e = rda and {tag} field is present, {tag} $e not present")
                            break  # Exit the loop once an error is found
                    if not subfield_e_present:
                        break  # Exit the loop if error is found in any tag

        # Check for the presence of 040 subfield 'e' with value 'rda'. Updated 8/14
        rda_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '040':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'e' and subfield.text == 'rda':
                        rda_present = True
                        break
            if rda_present:
                break

        if rda_present:
            # Check for the presence of 111 fields
            for tag in ['111']:
                xpath_query = f'.//{{http://www.loc.gov/MARC21/slim}}datafield[@tag="{tag}"]'
                datafields = root.findall(xpath_query)
                if datafields:
                    for datafield in datafields:
                        subfield_e_present = False
                        for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                            if subfield.attrib['code'] == 'j':
                                subfield_e_present = True
                                break
                        if not subfield_e_present:
                            errors.append(f"CATALOGER: 040 $e = rda and {tag} field is present, {tag} $j not present")
                            break  # Exit the loop once an error is found
                    if not subfield_e_present:
                        break  # Exit the loop if error is found in any tag


    # Check for period at the end of subfield a in 651 and 655 fields
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] in ['651', '655']:
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a' and subfield.text.endswith('.'):
                    errors.append(format_error(f"CATALOGER: Subfield a in field {datafield.attrib['tag']} should not end with a period.", datafield, subfield))

            if datafield.attrib['ind1'] != ' ' or datafield.attrib['ind2'] != '2':
                errors.append(format_error(f"CATALOGER: Field {datafield.attrib['tag']} indicators should be blank and 2.", datafield, None))
                
    # Check the first indicator of the 245 field
    field_245_indicator1 = None
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '245':
            field_245_indicator1 = datafield.attrib['ind1']
            break

    # Check for the presence of 246 subfield $i and $a
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '246':
            subfield_i_present = False
            subfield_a_present = False
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'i':
                    subfield_i_present = True
                elif subfield.attrib['code'] == 'a':
                    subfield_a_present = True
            # If subfield $i exists but $a does not, show an error message
            if subfield_i_present and not subfield_a_present:
                errors.append("246 $i exists and 246 $a not present.")
                break  # exit the loop once an error is found

    # Check if the 040 subfield b equals 'eng'
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '040':
            subfield_b = None
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'b':
                    subfield_b = subfield.text
                    temp_subfield = subfield 
                    break
            if subfield_b is not None and subfield_b != 'eng':
                errors.append(format_error("Subfield b in field 040 should be 'eng'.", datafield, temp_subfield))
                break

    # Check for the presence of 040 subfield a beginning with "DNLM"
    subfield_a_dnlm_present = False
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '040':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a' and subfield.text.startswith("DNLM"):
                    subfield_a_dnlm_present = True
                    break

    # If 040 subfield a begins with "DNLM", check character 40 in the 008 field
    if subfield_a_dnlm_present:
        # Check character 40 in the 008 field
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                controlfield_text = controlfield.text
                if len(controlfield_text) >= 40:  # Check if the field contains enough characters, including whitespace
                    character_40 = controlfield_text[39]  # Get character 40
                    if not character_40.isspace():  # Check if character 40 is not a whitespace character
                        errors.append("040 $a begins with DNLM, Cataloging Source (008/39) not 'blank'.")
                        break  # Exit the loop once an error is found
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters


    # Check for the presence of subfield a, subfield b, and subfield c in the 040 field
    subfield_a_present = False
    subfield_b_present = False
    subfield_c_present = False

    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '040':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a':
                    subfield_a_present = True
                elif subfield.attrib['code'] == 'b':
                    subfield_b_present = True
                elif subfield.attrib['code'] == 'c':
                    subfield_c_present = True

    # If any of subfield a, b, or c is missing in the 040 field, show an error message
    if not subfield_a_present or not subfield_b_present or not subfield_c_present:
        missing = []
        if not subfield_a_present:
            missing.append('$a')
        if not subfield_b_present:
            missing.append('$b')
        if not subfield_c_present:
            missing.append('$c')
        errors.append(f"040 missing subfield(s): {', '.join(missing)}.")

    # Initialize flags to track the presence of 041 and 044 fields
    has_041_field = False
    has_044_field = False

    # Check for the presence of the 999 field with subfield 'a'
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '999':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a' and subfield.text.strip() in ['WTC', 'AUTH']:
                    # If 999 $a is WTC or AUTH, check for 041 and 044 fields
                    for check_field in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                        if check_field.attrib['tag'] == '041':
                            has_041_field = True
                        elif check_field.attrib['tag'] == '044':
                            has_044_field = True

                    # Check which fields are missing and print appropriate messages
                    missing_fields = []
                    if not has_041_field:
                        missing_fields.append("041")
                    if not has_044_field:
                        missing_fields.append("044")

                    # Print messages based on missing fields
                    if missing_fields:
                        if len(missing_fields) == 2:
                            errors.append("CATALOGER: Both 041 and 044 fields are missing.")
                        else:
                            for field in missing_fields:
                                errors.append(f"CATALOGER: {field} field is missing.")
                    break  # Exit the loop once the condition is met


    # Check if the 044 subfield 9 value is "United States"
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '044':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == '9' and subfield.text == 'United States':
                    # Find the 008 field
                    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                        if controlfield.attrib['tag'] == '008':
                            # Count whitespace characters
                            count_whitespace = sum(1 for char in controlfield.text if char.isspace())
                            # Check if the 18th character is 'u'
                            if len(controlfield.text) >= 18 and controlfield.text[17] != 'u':
                                errors.append("044 is United States but 008 byte 17 isn't 'u'.")
                            break

    # Check if the 18th character in the 008 field is 'u'
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
        if controlfield.attrib['tag'] == '008':
            if len(controlfield.text) >= 18 and controlfield.text[17] == 'u':
                # Check if the 044 subfield 9 value is not "United States"
                for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                    if datafield.attrib['tag'] == '044':
                        for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                            if subfield.attrib['code'] == '9' and subfield.text != 'United States':
                                errors.append("008 byte 17 is 'u', but 044 is not 'United States'.")
                                break                
            
    # Check if the 856 field has a second indicator of 1
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '856':
            if 'ind2' in datafield.attrib and datafield.attrib['ind2'] == '1':
                errors.append("The 856 field should not have a second indicator of 1.")
                break
                            
    # Check if the 264 field has a second indicator of 4 and ensure subfield c is present. Update 8/14
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '264':
            if datafield.attrib.get('ind2') == '4':
                has_subfield_c = False
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'c':
                        has_subfield_c = True
                        break
                if not has_subfield_c:
                    errors.append("Error: 264 field with ind2='4' is missing subfield c.")
            
    # Check if the 041 first indicator is 1 and a subfield h is present
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '041':
            if 'ind1' in datafield.attrib and datafield.attrib['ind1'] == '1':
                subfield_h_present = False
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'h':
                        subfield_h_present = True
                        break
                if not subfield_h_present:
                    errors.append("If the 041 first indicator is 1, subfield h must be present.")
                    break
                    
    # Check if the 041 has a subfield h and the first indicator is not 1
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '041':
            subfield_h_present = False
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'h':
                    subfield_h_present = True
                    break
            if subfield_h_present and ('ind1' not in datafield.attrib or datafield.attrib['ind1'] != '1'):
                errors.append("If subfield h is present in the 041 field, the first indicator should be 1.")
                break

    # Check for the presence of subfield a with value 'und' in the 041 field
    subfield_a_und_present = False

    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '041':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a' and subfield.text == 'und':
                    temp_datafield = datafield
                    temp_subfield = subfield
                    subfield_a_und_present = True

    # If subfield a with value 'und' is present in the 041 field, show an error message
    if subfield_a_und_present:
        errors.append(format_error("041 $a is 'und'.", temp_datafield, temp_subfield))

    
    # Check if the 040 subfield e equals "rda" and the 19th character in the Leader is 'a'
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '040':
            subfield_e_value = None
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'e':
                    subfield_e_value = subfield.text
                    break
            if subfield_e_value == 'rda':
                leader_text = root.find('.//{http://www.loc.gov/MARC21/slim}leader').text.strip()
                if len(leader_text) >= 19 and leader_text[18] == 'a':
                    errors.append("040 $e is 'rda', the Leader byte 18 should not be 'a'.")
                    break

    # Check if the 19th position of the Leader is 'i' and if so, the 040 field needs subfield e value 'rda' Updated 8/14
    leader_text = root.find('.//{http://www.loc.gov/MARC21/slim}leader').text.strip()
    if len(leader_text) >= 19 and leader_text[18] == 'i':
        rda_found = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '040':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'e' and subfield.text == 'rda':
                        rda_found = True
                        break
                if rda_found:
                    break
        if not rda_found:
            #Turned off automatic correction and enhanced the print statement"
            errors.append("Leader byte 18 is 'i', but 040 $e is not 'rda'. Should the record be coded as RDA?")

    # Check for the presence of subfield e with value "rda" in the 040 field
    subfield_e_present = False
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '040':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'e' and subfield.text == "rda":
                    subfield_e_present = True
                    break

    # If subfield e with value "rda" (Resource Description and Access) is present, check for the presence of a 264 field. 
    # cataloging changed in 2013: 260 field (pre-RDA) or the 264 field (RDA field)
    # poor quality OCLC catalog records imported into Alma that we put 040 $e rda in but sometimes the cataloger forgets to change the 260 to a 264.
    if subfield_e_present:
        field_264_present = False
        field_260_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '264':
                field_264_present = True
            elif datafield.attrib['tag'] == '260':
                field_260_present = True
        
        if not field_264_present and field_260_present:
            errors.append("040 $e is rda but record has 260 field instead of 264.")
        elif not field_264_present:
            errors.append("040 $e is rda and 264 field is missing.")

    # Check for the presence of both subfield 'c' and subfield '3' in a single 260 or 264 field
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] in ['260', '264']:
            has_subfield_c = False
            has_subfield_3 = False

            # Check for subfields within the current datafield
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'c':
                    has_subfield_c = True
                elif subfield.attrib['code'] == '3':
                    has_subfield_3 = True

            # If both subfields are found, print a message
            if has_subfield_c and has_subfield_3:
                errors.append(f"Field {datafield.attrib['tag']} has both $c and $3.")


    # Check for the presence of 260 and 264 fields
    field_260_present = False
    field_264_present = False

    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '260':
            field_260_present = True
        elif datafield.attrib['tag'] == '264':
            field_264_present = True

    # If both 260 and 264 fields are missing, generate an error message
    if not field_260_present and not field_264_present:
        errors.append("Both 260 and 264 fields are missing.")

    # Iterate through datafields to find 264 fields
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '264':
            # Check the second indicator
            ind2 = datafield.attrib.get('ind2', '')
            if ind2 == '0':
                # Find the 7th character in the Leader
                leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
                if leader is not None:
                    leader_text = leader.text
                    if len(leader_text) >= 7 and leader_text[6] == 'a':
                        errors.append("264 has a 2nd indicator of '0', Leader character 7 is 'a'")

    # {tag} $c ends in hyphen, 008/06 not 'c', 'm', 'd', or 'u'
    # Iterate through datafields to find 260 and 264 fields
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        tag = datafield.attrib['tag']
        if tag in ['260', '264']:
            # Find subfield c value
            subfield_c_value = None
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'c':
                    subfield_c_value = subfield.text
                    break

            # Check if subfield c ends with a hyphen
            if subfield_c_value and subfield_c_value.endswith('-'):
                # Find the 7th character in the 008 field
                for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                    if controlfield.attrib['tag'] == '008':
                        if len(controlfield.text) >= 7:
                            character_7 = controlfield.text[6]
                            if character_7 not in ['c', 'm', 'd', 'u']:
                                errors.append(f"{tag} $c ends in hyphen, 008/06 not 'c', 'm', 'd', or 'u'")
                                break
            
                
    # Check if the 7th character in the 008 is 's', then ensure the 12-15th characters in the 008 are whitespace characters
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
        if controlfield.attrib['tag'] == '008':
            controlfield_text = controlfield.text.strip()
            if len(controlfield_text) > 6 and controlfield_text[6] == 's':
                if len(controlfield_text) >= 15:
                    if not controlfield_text[11:15].isspace():
                        errors.append("008/06 is ‘s’, 008/11-14 not ‘blank’ ")
                        break
                
    # Check if the 7th character in the 008 is 'c', then ensure the 12-15th characters in the 008 are "9999"
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
        if controlfield.attrib['tag'] == '008':
            controlfield_text = controlfield.text.strip()
            if len(controlfield_text) > 6 and controlfield_text[6] == 'c':
                if len(controlfield_text) >= 15:
                    if controlfield_text[11:15] != "9999":
                        errors.append("008 byte 6 is 'c', Date 2 should be '9999'.")
                        break

    # Check if the 7th character in the 008 is 'd', then ensure the 12-15th characters in the 008 are not "9999"
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
        if controlfield.attrib['tag'] == '008':
            controlfield_text = controlfield.text.strip()
            if len(controlfield_text) > 6 and controlfield_text[6] == 'd':
                if len(controlfield_text) >= 15:
                    if controlfield_text[11:15] == "9999":
                        errors.append("008 byte 6 is 'd', Date 2 should not be '9999'.")
                        break
                    
    # Check if the 7th character in the 008 is 'u', then ensure the 15th character in the 008 is not "u"
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
        if controlfield.attrib['tag'] == '008':
            txt = controlfield.text.strip()
            if len(txt) > 6 and txt[6] == 'u':
                if len(txt) > 14 and txt[14] != 'u':
                    errors.append("008: byte 6 is 'u'; byte 14 must be 'u'.")
                break

                    
    # Check if the 7th character in the 008 is 'r', then ensure the total value in characters 8-11 is equal to or higher than the value in characters 12-15
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
        if controlfield.attrib['tag'] == '008':
            controlfield_text = controlfield.text.strip()
            if len(controlfield_text) > 6 and controlfield_text[6] == 'r':
                if len(controlfield_text) >= 16:
                    characters_8_to_11 = controlfield_text[7:11].strip()
                    characters_12_to_15 = controlfield_text[11:15].strip()

                     # Skip validation for indexcat records when Date 2 is blank/'uuuu'
                    if record_type == "indexcat" and (characters_12_to_15 == "uuuu" or not characters_12_to_15):
                        pass  # Skip validation for this case
                    elif not characters_12_to_15:
                        errors.append("008 byte 7 is 'r', Date 2 can't be blank")
                    elif characters_8_to_11 and characters_12_to_15:
                        try:
                            if int(characters_8_to_11) < int(characters_12_to_15):
                                errors.append("008/06 is ‘r’, 008/7-10 not greater than 008/11-14")
                                break
                        except ValueError:
                            pass  # Skip comparison if values are not numeric

    # If 008/06 is ‘m’ or ‘n’ and 008/7-10 is greater than 008/11-14
    # Check for the presence of the 008 field
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
        if controlfield.attrib['tag'] == '008':
            if len(controlfield.text) >= 16:
                # Extract 008 characters 7, 8-11, and 12-15
                char_007 = controlfield.text[6].strip()
                char_008_011 = controlfield.text[7:11].strip()
                char_012_015 = controlfield.text[11:15].strip()

                # Check if char_007 is 'm' or 'n'
                if char_007 in ['m', 'n']:
                    #skip validation if both date fields are blank for IndexCat records
                    if record_type == "indexcat" and char_007 =='n'and char_008_011 == "uuuu" and char_012_015 == "uuuu":
                        pass #skip validation
                    else:
                    # Convert strings to integers
                        try:
                            char_008_011_value = int(char_008_011)
                            char_012_015_value = int(char_012_015)
                        
                            # Compare values
                            if char_008_011_value > char_012_015_value:
                                errors.append("If 008/06 is ‘m’ or ‘n’ and 008/7-10 is greater than 008/11-14.")
                        except ValueError:
                            errors.append("Invalid characters in 008/07-10 or 008/11-14.")
            else:
                errors.append("008 field does not contain enough characters.")
            break  # Exit the loop once the 008 field is found


    # Check if the 7th character in the 008 is 'd', 'i', 'k', or 'q', then ensure the total value in characters 8-11 is equal to or lower than the value in characters 12-15
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
        if controlfield.attrib['tag'] == '008':
            controlfield_text = controlfield.text.strip()
            if len(controlfield_text) > 6 and controlfield_text[6] in ['d', 'i', 'k', 'q']:
                if len(controlfield_text) >= 16:
                    characters_8_to_11 = controlfield_text[7:11].strip()
                    characters_12_to_15 = controlfield_text[11:15].strip()
                    if 'u' not in characters_8_to_11 and 'u' not in characters_12_to_15:
                        if characters_8_to_11 and characters_12_to_15:
                            try:
                                if int(characters_8_to_11) > int(characters_12_to_15):
                                    errors.append("008/06 is 'd', 'i', 'k', or 'q', 008/11-14 not greater than 008/7-10")
                                    break  # Exit the loop once an error is found
                            except ValueError:
                                errors.append("008/7-10 or 008/11-14 contains non-numeric characters")
                                break  # Exit the loop if there are non-numeric characters
                    # No need to append any error message or handle the 'else' case
                        
    # Check if there is more than one 362 field with first indicator of 1
    field_362_count = 0
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '362' and datafield.attrib['ind1'] == '1':
            field_362_count += 1
            if field_362_count > 1:
                errors.append("More than one 362 field with first indicator of 1.")
                break            

    # Check if there is more than one 362 field with first indicator of 0
    field_362_count = 0
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '362' and datafield.attrib['ind1'] == '0':
            field_362_count += 1
            if field_362_count > 1:
                errors.append("More than one 362 field with first indicator of 0.")
                break

    # Check if characters 8-11 in the 008 are blank
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
        if controlfield.attrib['tag'] == '008':
            if len(controlfield.text) >= 12 and controlfield.text[7:11].strip() == "":
                errors.append("008 Date 1 is empty.")
                break

    # Initialize a variable to track unbalanced parentheses
    unbalanced_parentheses = False

    # Look for the 830 field with subfield 'a'
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '830':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a':
                    subfield_text = subfield.text
                    # Check for unbalanced parentheses
                    if subfield_text.count('(') != subfield_text.count(')'):
                        unbalanced_parentheses = True
                        temp_datafield = datafield
                        temp_subfield = subfield
                        break  # Stop checking once unbalanced parentheses are found

            # If unbalanced parentheses are found, print an error
            if unbalanced_parentheses:
                errors.append(format_error("CATALOGER: 830 $a contains unbalanced parentheses.", temp_datafield, temp_subfield))
                unbalanced_parentheses = False  
    # Initialize flags
    has_pmc_510 = False
    has_pmc_url_856 = False

    # Check all 510 fields for subfield a with "PMC" (excluding "PMC Forthcoming")
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '510':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a':
                    if subfield.text.strip() == "PMC":
                        has_pmc_510 = True
                    elif subfield.text.strip() == "PMC Forthcoming":
                        has_pmc_510 = False
                        break  # Exit if "PMC Forthcoming" is found
            if has_pmc_510:
                break  # Stop once a valid "PMC" is found    # If a valid "PMC" is found, check for 856 field with URL containing "ncbi.nlm.nih.gov"
    if has_pmc_510:
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '856':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'u':
                        temp_url = subfield.text.strip()
                        if not temp_url.startswith(('http://', 'https://')):
                            temp_url = 'https://' + temp_url

                        hostname = urlparse(temp_url).netloc.split(':')[0]

                        if hostname.startswith('www.'):
                            hostname = hostname[4:]

                        # Check if hostname is or contains ncbi.nlm.nih.gov (to handle subdomains like pmc.ncbi.nlm.nih.gov)
                        if hostname == "ncbi.nlm.nih.gov" or hostname.endswith(".ncbi.nlm.nih.gov"):
                            has_pmc_url_856 = True
                            break
            if has_pmc_url_856:
                break  # Exit once the PMC URL is found

    # If "PMC" exists but no PMC URL is found, add an error
    if has_pmc_510 and not has_pmc_url_856:
        errors.append("510 has PMC but is missing PMC URL")

    # Check if 999 $a is "NOC"
    skip_encoding_check = False
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '999':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a' and subfield.text.strip() == 'NOC':
                    skip_encoding_check = True
                    break
        if skip_encoding_check:
            break

    # Check Leader byte 17 for encoding level if 999 $a is not "NOC"
    if not skip_encoding_check:
        leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
        
        if leader is not None and len(leader.text) >= 18:  # Ensure the leader has at least 18 characters
            encoding_level = leader.text[17]  # Get the value at byte 17 (index 17)
            if encoding_level == '5':
                errors.append("CATALOGER: encoding level is 5 and should be upgraded")
        else:
            errors.append("Leader field is missing or not long enough")

    # Initialize skip flag
    skip_validation = True

    # Check for 999 subfield 'a' value of 'NOC'
    has_noc_999 = False
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '999':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a' and subfield.text.strip().upper() == 'NOC':
                    has_noc_999 = True
                    break
        if has_noc_999:
            break

    # Check Leader character 8 for monograph indicators 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 in ['a', 'c', 'm']:
            skip_validation = False  # Continue validation for monographs

    # Proceed with the encoding level check for monographs if not skipped and NOC is not present
    if not skip_validation and not has_noc_999:
        # Check Leader byte 17 for encoding level '7'
        if len(leader.text) >= 18:  # Ensure the leader has at least 18 characters
            encoding_level = leader.text[17]  # Get the value at byte 17 (index 17)
            if encoding_level == '7':
                errors.append("CATALOGER: encoding level is 7. Monographs should be full level.")
        else:
            errors.append("Leader field is missing or not long enough.")


    # Initialize skip flag
    skip_validation = True

    # Check for 999 subfield 'a' value of 'NOC'
    has_noc_999 = False
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '999':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a' and subfield.text.strip().upper() == 'NOC':
                    has_noc_999 = True
                    break
        if has_noc_999:
            break

    # Check Leader character 8 for serial indicators 'b', 'i', or 's'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 in ['b', 'i', 's']:
            skip_validation = False  # Continue validation for serials

    # Proceed with the encoding level check for serials if not skipped and NOC is not present
    if not skip_validation and not has_noc_999:
        # Check Leader byte 17 for encoding level '7'
        if len(leader.text) >= 18:  # Ensure the leader has at least 18 characters
            encoding_level = leader.text[17]  # Get the value at byte 17 (index 17)
            if encoding_level == '7':
                errors.append("CATALOGER: Warning, encoding level 7 is only used for NOTCONSER records.")
        else:
            errors.append("Leader field is missing or not long enough.")

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 29:
                    characters_25_28 = controlfield.text[24:28]
                    if 'a' in characters_25_28:
                        # Check for the presence of 655 subfield 'a' with value "Abstracts"
                        subfield_a_present = False
                        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                            if datafield.attrib['tag'] == '655':
                                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                                    if subfield.attrib['code'] == 'a' and subfield.text == "Abstracts":
                                        subfield_a_present = True
                                        break
                        if not subfield_a_present:
                            errors.append("CATALOGER: 655 $a Abstracts is missing.")
                            break  # Exit the loop once an error is found
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 655 subfield 'a' with value "Abstracts"
        subfield_a_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and subfield.text == "Abstracts":
                        subfield_a_present = True
                        break
        if subfield_a_present:
            # Check for the presence of 'a' in characters 25-28 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 29:
                        characters_25_28 = controlfield.text[24:28]
                        if 'a' not in characters_25_28:
                            errors.append("CATALOGER: 655 $a Abstracts found, but 'a' is missing in 008 bytes 24-27.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 655 subfield 'a' with value "Bibliography"
        subfield_a_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and subfield.text == "Bibliography":
                        subfield_a_present = True
                        break
        if subfield_a_present:
            # Check for the presence of 'a' in characters 25-28 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 29:
                        characters_25_28 = controlfield.text[24:28]
                        if 'b' not in characters_25_28:
                            errors.append("CATALOGER: 655 $a Bibliography found, but 'b' is missing in 008 bytes 24-27.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 29:
                    characters_25_28 = controlfield.text[24:28]
                    if 'e' in characters_25_28:
                        # Check for the presence of 655 subfield 'a' with value "Encyclopedia"
                        subfield_a_present = False
                        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                            if datafield.attrib['tag'] == '655':
                                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                                    if subfield.attrib['code'] == 'a' and subfield.text == "Encyclopedia":
                                        subfield_a_present = True
                                        break
                        if not subfield_a_present:
                            errors.append("CATALOGER: 655 $a Encyclopedia is missing.")
                            break  # Exit the loop once an error is found
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters   

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 655 subfield 'e' with value "Encyclopedia"
        subfield_a_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and subfield.text == "Encyclopedia":
                        subfield_a_present = True
                        break
        if subfield_a_present:
            # Check for the presence of 'e' in characters 25-28 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 29:
                        characters_25_28 = controlfield.text[24:28]
                        if 'e' not in characters_25_28:
                            errors.append("CATALOGER: 655 $a Encyclopedia found, but 'e' is missing in 008 bytes 24-27.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:    
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 29:
                    characters_25_28 = controlfield.text[24:28]
                    if 'f' in characters_25_28:
                        # Check for the presence of 655 subfield 'f' with value "Handbook"
                        subfield_a_present = False
                        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                            if datafield.attrib['tag'] == '655':
                                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                                    if subfield.attrib['code'] == 'a' and subfield.text == "Handbook":
                                        subfield_a_present = True
                                        break
                        if not subfield_a_present:
                            errors.append("CATALOGER: 655 $a Handbook is missing.")
                            break  # Exit the loop once an error is found
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters 

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 655 subfield 'f' with value "Handbook"
        subfield_a_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and subfield.text == "Handbook":
                        subfield_a_present = True
                        break
        if subfield_a_present:
            # Check for the presence of 'f' in characters 25-28 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 29:
                        characters_25_28 = controlfield.text[24:28]
                        if 'f' not in characters_25_28:
                            errors.append("CATALOGER: 655 $a Handbook found, but 'f' is missing in 008 bytes 24-27.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 29:
                    characters_25_28 = controlfield.text[24:28]
                    if 'i' in characters_25_28:
                        # Check for the presence of 655 subfield 'a' with value "Index"
                        subfield_a_present = False
                        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                            if datafield.attrib['tag'] == '655':
                                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                                    if subfield.attrib['code'] == 'a' and subfield.text == "Index":
                                        subfield_a_present = True
                                        break
                        if not subfield_a_present:
                            errors.append("CATALOGER: 655 $a Index is missing.")
                            break  # Exit the loop once an error is found
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters 

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 655 subfield 'i' with value "Index"
        subfield_a_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and subfield.text == "Index":
                        subfield_a_present = True
                        break
        if subfield_a_present:
            # Check for the presence of 'i' in characters 25-28 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 29:
                        characters_25_28 = controlfield.text[24:28]
                        if 'i' not in characters_25_28:
                            errors.append("CATALOGER: 655 $a Index found, but 'i' is missing in 008 bytes 24-27.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 29:
                    characters_25_28 = controlfield.text[24:28]
                    if 'j' in characters_25_28:
                        # Check for the presence of 655 subfield 'a' with value "Patent"
                        subfield_a_present = False
                        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                            if datafield.attrib['tag'] == '655':
                                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                                    if subfield.attrib['code'] == 'a' and subfield.text == "Patent":
                                        subfield_a_present = True
                                        break
                        if not subfield_a_present:
                            errors.append("CATALOGER: 655 $a Patent is missing.")
                            break  # Exit the loop once an error is found
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters 

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 655 subfield 'j' with value "Patent"
        subfield_a_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and subfield.text == "Patent":
                        subfield_a_present = True
                        break
        if subfield_a_present:
            # Check for the presence of 'j' in characters 25-28 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 29:
                        characters_25_28 = controlfield.text[24:28]
                        if 'j' not in characters_25_28:
                            errors.append("CATALOGER: 655 $a Patent found, but 'j' is missing in 008 bytes 24-27.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 29:
                    characters_25_28 = controlfield.text[24:28]
                    if 'p' in characters_25_28:
                        # Check for the presence of 655 subfield 'a' with value "Programmed Instruction"
                        subfield_a_present = False
                        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                            if datafield.attrib['tag'] == '655':
                                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                                    if subfield.attrib['code'] == 'a' and subfield.text == "Programmed Instruction":
                                        subfield_a_present = True
                                        break
                        if not subfield_a_present:
                            errors.append("CATALOGER: 655 $a Programmed Instruction is missing.")
                            break  # Exit the loop once an error is found
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 655 subfield 'p' with value "Programmed Instruction"
        subfield_a_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and subfield.text == "Programmed Instruction":
                        subfield_a_present = True
                        break
        if subfield_a_present:
            # Check for the presence of 'p' in characters 25-28 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 29:
                        characters_25_28 = controlfield.text[24:28]
                        if 'p' not in characters_25_28:
                            errors.append("CATALOGER: 655 $a Programmed Instruction found, but 'p' is missing in 008 bytes 24-27.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 29:
                    characters_25_28 = controlfield.text[24:28]
                    if 'r' in characters_25_28:
                        # Check for the presence of 655 subfield 'a' with value "Directory"
                        subfield_a_present = False
                        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                            if datafield.attrib['tag'] == '655':
                                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                                    if subfield.attrib['code'] == 'a' and subfield.text == "Directory":
                                        subfield_a_present = True
                                        break
                        if not subfield_a_present:
                            errors.append("CATALOGER: 655 $a Directory is missing.")
                            break  # Exit the loop once an error is found
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 655 subfield 'r' with value "Directory"
        subfield_a_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and subfield.text == "Directory":
                        subfield_a_present = True
                        break
        if subfield_a_present:
            # Check for the presence of 'r' in characters 25-28 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 29:
                        characters_25_28 = controlfield.text[24:28]
                        if 'r' not in characters_25_28:
                            errors.append("CATALOGER: 655 $a Directory found, but 'r' is missing in 008 bytes 24-27.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 29:
                    characters_25_28 = controlfield.text[24:28]
                    if 'v' in characters_25_28:
                        # Check for the presence of 655 subfield 'a' with value "Legal Case"
                        subfield_a_present = False
                        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                            if datafield.attrib['tag'] == '655':
                                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                                    if subfield.attrib['code'] == 'a' and subfield.text == "Legal Case":
                                        subfield_a_present = True
                                        break
                        if not subfield_a_present:
                            errors.append("CATALOGER: 655 $a Legal Case is missing.")
                            break  # Exit the loop once an error is found
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 655 subfield 'v' with value "Legal Case"
        subfield_a_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and subfield.text == "Legal Case":
                        subfield_a_present = True
                        break
        if subfield_a_present:
            # Check for the presence of 'v' in characters 25-28 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 29:
                        characters_25_28 = controlfield.text[24:28]
                        if 'v' not in characters_25_28:
                            errors.append("CATALOGER: 655 $a Legal Case, but 'v' is missing in 008 bytes 24-27.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 29:
                    characters_25_28 = controlfield.text[24:28]
                    if 'l' in characters_25_28:
                        # Check for the presence of 655 subfield 'l' with value "Legislation"
                        subfield_a_present = False
                        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                            if datafield.attrib['tag'] == '655':
                                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                                    if subfield.attrib['code'] == 'a' and subfield.text == "Legislation":
                                        subfield_a_present = True
                                        break
                        if not subfield_a_present:
                            errors.append("CATALOGER: 655 $a Legislation is missing.")
                            break  # Exit the loop once an error is found
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 655 subfield 'l' with value "Legislation"
        subfield_a_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and subfield.text == "Legislation":
                        subfield_a_present = True
                        break
        if subfield_a_present:
            # Check for the presence of 'l' in characters 25-28 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 29:
                        characters_25_28 = controlfield.text[24:28]
                        if 'l' not in characters_25_28:
                            errors.append("CATALOGER: 655 $a Legislation, but 'l' is missing in 008 bytes 24-27.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 29:
                    characters_25_28 = controlfield.text[24:28]
                    if 's' in characters_25_28:
                        # Check for the presence of 655 subfield 'a' with value "Statistics"
                        subfield_a_present = False
                        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                            if datafield.attrib['tag'] == '655':
                                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                                    if subfield.attrib['code'] == 'a' and subfield.text == "Statistics":
                                        subfield_a_present = True
                                        break
                        if not subfield_a_present:
                            errors.append("CATALOGER: 655 $a Statistics is missing.")
                            break  # Exit the loop once an error is found
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 655 subfield 's' with value "Statistics"
        subfield_a_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and subfield.text == "Statistics":
                        subfield_a_present = True
                        break
        if subfield_a_present:
            # Check for the presence of 's' in characters 25-28 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 29:
                        characters_25_28 = controlfield.text[24:28]
                        if 's' not in characters_25_28:
                            errors.append("CATALOGER: 655 $a Statistics, but 's' is missing in 008 bytes 24-27.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 29:
                    characters_25_28 = controlfield.text[24:28]
                    if 't' in characters_25_28:
                        # Check for the presence of 655 subfield 'a' with value "Technical Report"
                        subfield_a_present = False
                        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                            if datafield.attrib['tag'] == '655':
                                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                                    if subfield.attrib['code'] == 'a' and subfield.text == "Technical Report":
                                        subfield_a_present = True
                                        break
                        if not subfield_a_present:
                            errors.append("CATALOGER: 655 $a Technical Report is missing.")
                            break  # Exit the loop once an error is found
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 655 subfield 't' with value "Technical Report"
        subfield_a_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and subfield.text == "Technical Report":
                        subfield_a_present = True
                        break
        if subfield_a_present:
            # Check for the presence of 's' in characters 25-28 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 29:
                        characters_25_28 = controlfield.text[24:28]
                        if 't' not in characters_25_28:
                            errors.append("CATALOGER: 655 $a Technical Report, but 't' is missing in 008 bytes 24-27.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 29:
                    characters_25_28 = controlfield.text[24:28]
                    if '6' in characters_25_28:
                        # Check for the presence of 655 subfield '6' with value "Graphic Novel"
                        subfield_a_present = False
                        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                            if datafield.attrib['tag'] == '655':
                                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                                    if subfield.attrib['code'] == 'a' and subfield.text == "Graphic Novel":
                                        subfield_a_present = True
                                        break
                        if not subfield_a_present:
                            errors.append("CATALOGER: 655 $a Graphic Novel is missing.")
                            break  # Exit the loop once an error is found
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 655 subfield '6' with value "Graphic Novel"
        subfield_a_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and subfield.text == "Graphic Novel":
                        subfield_a_present = True
                        break
        if subfield_a_present:
            # Check for the presence of 's' in characters 25-28 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 29:
                        characters_25_28 = controlfield.text[24:28]
                        if '6' not in characters_25_28:
                            errors.append("CATALOGER: 655 $a Graphic Novel, but '6' is missing in 008 bytes 24-27.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 'Catalog' in any part of subfield 'a' of 655 field
        subfield_catalog_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and "Catalog" in subfield.text:
                        subfield_catalog_present = True
                        break

        if subfield_catalog_present:
            # Check for the presence of 'c' in characters 25-28 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 29:
                        characters_25_28 = controlfield.text[24:28]
                        if 'c' not in characters_25_28:
                            errors.append("CATALOGER: 655 $a Catalog (or specific Catalog PT) found, but 'c' is missing in 008 bytes 24-27.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 29:
                    characters_25_28 = controlfield.text[24:28]
                    if 'c' in characters_25_28:
                        # Check for the presence of 655 subfield 'a' containing the term "Catalog"
                        subfield_a_present = False
                        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                            if datafield.attrib['tag'] == '655':
                                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                                    if subfield.attrib['code'] == 'a' and "Catalog" in subfield.text:
                                        subfield_a_present = True
                                        break
                        if not subfield_a_present:
                            errors.append("CATALOGER: 655 $a containing 'Catalog (or specific Catalog PT)' is missing.")
                            break  # Exit the loop once an error is found
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 'Dictionary' in any part of subfield 'a' of 655 field
        subfield_catalog_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and "Dictionary" in subfield.text:
                        subfield_catalog_present = True
                        break

        if subfield_catalog_present:
            # Check for the presence of 'd' in characters 25-28 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 29:
                        characters_25_28 = controlfield.text[24:28]
                        if 'd' not in characters_25_28:
                            errors.append("CATALOGER: 655 $a Dictionary (or specific Dictionary PT) found, but 'd' is missing in 008 bytes 24-27.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 29:
                    characters_25_28 = controlfield.text[24:28]
                    if 'd' in characters_25_28:
                        # Check for the presence of 655 subfield 'a' containing the term "Dictionary"
                        subfield_a_present = False
                        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                            if datafield.attrib['tag'] == '655':
                                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                                    if subfield.attrib['code'] == 'a' and "Dictionary" in subfield.text:
                                        subfield_a_present = True
                                        break
                        if not subfield_a_present:
                            errors.append("CATALOGER: 655 $a containing 'Dictionary (or specific Dictionary PT)' is missing.")
                            break  # Exit the loop once an error is found
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                # Check if the field contains enough characters
                if len(controlfield.text) >= 32:  # Modified to check for character 31
                    character_31 = controlfield.text[30]  # Get character 31
                    if character_31 == '1':  # Check if character 31 is '1'
                        # Check for the presence of 655 subfield 'a' with value "Festschrift"
                        subfield_a_present = False
                        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                            if datafield.attrib['tag'] == '655':
                                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                                    if subfield.attrib['code'] == 'a' and subfield.text == "Festschrift":
                                        subfield_a_present = True
                                        break
                        if not subfield_a_present:
                            errors.append("CATALOGER: 655 $a Festschrift is missing.")
                            break  # Exit the loop once an error is found
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 655 subfield 'a' with value "Festschrift"
        subfield_a_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and subfield.text == "Festschrift":
                        subfield_a_present = True
                        break

        # If 655 subfield 'a' with value "Festschrift" is present, check character 31 in the 008 field
        if subfield_a_present:
            # Check for the presence of '1' in character 31 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    # Check if the field contains enough characters
                    if len(controlfield.text) >= 32:  # Modified to check for character 31
                        character_31 = controlfield.text[30]  # Get character 31
                        if character_31 != '1':  # Check if character 31 is not '1'
                            errors.append("CATALOGER: 655 $a Festschrift found, but '1' is missing in 008 byte 30.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the validation if not skipped
    if not skip_validation:
        # Initialize variables
        congress_found = False
        conference_proceedings_found = False
        webcast_found = False
        char_30_is_1 = False

        # Look for the 655 field with subfield 'a' value of "Congress" or "Conference Proceedings" or "Webcast"
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a':
                        value = subfield.text.strip().lower()
                        if value == "congress":
                            congress_found = True
                        elif value == "conference proceedings":
                            conference_proceedings_found = True
                        elif value == "webcast":
                            webcast_found = True

        # Only check the 008/30 character if Congress or Conference Proceedings is found and Webcast is NOT found
        if (congress_found or conference_proceedings_found) and not webcast_found:
            # Check the 008 field's 30th character
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 31:
                        char_30_is_1 = controlfield.text[29] == '1'
                    else:
                        errors.append("008 field does not contain enough characters.")
                    break

            # If 008/30 is not '1', print an error
            if not char_30_is_1:
                errors.append("CATALOGER: 655 $a 'Congress' or 'Conference Proceedings' is present, but 008/29 is not '1'.")



    
    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        skip_validation = leader_char_8 not in ['a', 'c', 'm']
    else:
        skip_validation = True

    # Proceed with the validation if not skipped
    if not skip_validation:
        char_30_is_1 = False
        congress_or_conf_proc_found = False

        # Check the 008 field's 30th character for '1'
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 31:
                    char_30_is_1 = controlfield.text[29] == '1'
                else:
                    errors.append("008 field does not contain enough characters.")
                break

        # If 008/29 is '1', check for 655 $a Congress or Conference Proceedings
        if char_30_is_1:
            for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                if datafield.attrib['tag'] == '655':
                    for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                        if subfield.attrib['code'] == 'a':
                            value = subfield.text.strip().lower()
                            if value in ["congress", "conference proceedings"]:
                                congress_or_conf_proc_found = True
                                break
                if congress_or_conf_proc_found:
                    break

            if not congress_or_conf_proc_found:
                errors.append(
                    "CATALOGER: 008/29 is '1', but 655 $a 'Congress' or 'Conference Proceedings' is missing."
                )


    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the validation if not skipped
    if not skip_validation:
        # Initialize variables
        char_35_is_a = False
        autobiography_found = False

        # Check the 008 field's 35th character for 'a'
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 36:
                    if controlfield.text[34] == 'a':  # Check if 008 character 35 (index 34) is 'a'
                        char_35_is_a = True
                else:
                    errors.append("008 field does not contain enough characters.")
                break

        # If 008/35 is 'a', check for the presence of 655 $a with "Autobiography"
        if char_35_is_a:
            for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                if datafield.attrib['tag'] == '655':
                    for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                        if subfield.attrib['code'] == 'a' and subfield.text.strip().lower() == "autobiography":
                            autobiography_found = True
                            break
                if autobiography_found:
                    break

            # If 655 $a "Autobiography" is not found, print an error
            if not autobiography_found:
                errors.append("CATALOGER: 008/35 is 'a', but 655 $a 'Autobiography' is missing.")

    # Initialize variables
    has_autobiography_655 = False
    char_35_is_a = False
    skip_validation = False

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True

    # Proceed with validation if not skipped
    if not skip_validation:
        # Check for the presence of 655 $a with "Autobiography"
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and subfield.text.strip().lower() == "autobiography":
                        has_autobiography_655 = True
                        break
            if has_autobiography_655:
                break

        # If 655 $a "Autobiography" is found, check if 008/35 is 'a'
        if has_autobiography_655:
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 36:
                        if controlfield.text[34] == 'a':  # Check if 008 character 35 (index 34) is 'a'
                            char_35_is_a = True
                    else:
                        errors.append("008 field does not contain enough characters.")
                    break

            # If 008/35 is not 'a', print an error
            if not char_35_is_a:
                errors.append("CATALOGER: 655 $a 'Autobiography' is present, but 008/34 is not 'a'.")


    # Initialize variables
    char_35_is_b_or_c = False  # Updated to check for both 'b' and 'c'
    has_biography_655 = False
    skip_validation = True

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 in ['a', 'c', 'm']:
            skip_validation = False

    # Proceed with the validation if not skipped
    if not skip_validation:
        # Check if 008/35 is 'b' or 'c'
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 36:  # Ensure the 008 field has enough characters
                    if controlfield.text[34] in ['b', 'c']:  # Check if 008 character 35 (index 34) is 'b' or 'c'
                        char_35_is_b_or_c = True
                else:
                    errors.append("008 field does not contain enough characters.")
                break

        # If 008/35 is 'b' or 'c', check for the presence of 655 $a with "Biography"
        if char_35_is_b_or_c:
            for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                if datafield.attrib['tag'] == '655':
                    for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                        if subfield.attrib['code'] == 'a' and subfield.text.strip().lower() == "biography":
                            has_biography_655 = True
                            break
                if has_biography_655:
                    break

            # If 655 $a "Biography" is not found, print an error
            if not has_biography_655:
                errors.append("CATALOGER: 008/34 is 'b' or 'c', but 655 $a 'Biography' is missing.")


    # Initialize variables
    has_biography_655 = False
    char_35_is_b_or_c = False  # Updated to check for both 'b' and 'c'
    skip_validation = True

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 in ['a', 'c', 'm']:
            skip_validation = False

    # Proceed with the validation if not skipped
    if not skip_validation:
        # Check for the presence of 655 $a with "Biography"
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '655':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == 'a' and subfield.text.strip().lower() == "biography":
                        has_biography_655 = True
                        break
            if has_biography_655:
                break

        # If 655 $a "Biography" is found, check if 008/35 is 'b' or 'c'
        if has_biography_655:
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    if len(controlfield.text) >= 36:  # Ensure the 008 field has enough characters
                        if controlfield.text[34] in ['b', 'c']:  # Check if 008 character 35 (index 34) is 'b' or 'c'
                            char_35_is_b_or_c = True
                    else:
                        errors.append("008 field does not contain enough characters.")
                    break

            # If 008/35 is neither 'b' nor 'c', print an error
            if not char_35_is_b_or_c:
                errors.append("CATALOGER: 655 $a 'Biography' is present, but 008/34 is not 'b' or 'c'.")



    # Check characters 25-28 in the 008 field for 'n' and 'b' values
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
        if controlfield.attrib['tag'] == '008':
            if len(controlfield.text) >= 29:  # Check if the field contains enough characters
                characters_25_28 = controlfield.text[24:28]  # Get characters 25-28
                if 'n' in characters_25_28 and 'b' in characters_25_28:  # Check if both 'n' and 'b' are present
                    errors.append("008/24-27 contains ‘n’ and ‘b’.")
                    break  # Exit the loop once an error is found
            else:
                errors.append("008 field does not contain enough characters.")
                break  # Exit the loop if 008 field doesn't have enough characters

    # Check for the presence of "index" in the 500 and 504 fields
    word_index_present = False
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '500' or datafield.attrib['tag'] == '504':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if "index" in subfield.text.lower():
                    word_index_present = True
                    break

    # Check if "index" is present, excluding "indexcat"
    contains_index = False
    indexcat_present = False

    # Loop through 500 and 504 fields to find "index" and exclude "indexcat"
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] in ['500', '504']:
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a':
                    subfield_text = subfield.text.lower()
                    if 'indexcat' in subfield_text:
                        indexcat_present = True
                        break  # Stop further checks if "IndexCat" is found
                    elif 'index' in subfield_text:
                        contains_index = True

    # Proceed to check the 008 field only if "index" is found and "indexcat" is not present
    if contains_index and not indexcat_present:
        # Check character 32 in the 008 field
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 33:  # Check if the field contains enough characters
                    character_32 = controlfield.text[31]  # Get character 32
                    if character_32 != '1':  # Check if character 32 is not '1'
                        errors.append("500 or 504 includes note about index and 008/31 is not ‘1’.")
                    break  # Exit the loop once an error is found or check is completed
                else:
                    errors.append("008 field does not contain enough characters.")
                    break  # Exit the loop if 008 field doesn't have enough characters

    def check_subfields(root, field_tag, subfield_a, subfield_t):
        error_found = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == field_tag:
                subfield_a_present = False
                subfield_t_present = False
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == subfield_a:
                        subfield_a_present = True
                    elif subfield.attrib['code'] == subfield_t:
                        subfield_t_present = True
                if subfield_a_present and not subfield_t_present:
                    errors.append(f"{field_tag} ${subfield_a} is present and {field_tag} ${subfield_t} is not present.")
                    error_found = True
        return error_found



    # Usage:
    fields_to_check = ['765', '767', '770', '772', '775', '777', '780', '785', '787']
    for field_tag in fields_to_check:
        check_subfields(root, field_tag, 'a', 't')

    # Check Leader character 8 for value of 'a', 'c', or 'm'
    leader = root.find('.//{http://www.loc.gov/MARC21/slim}leader')
    if leader is not None and len(leader.text) >= 9:
        leader_char_8 = leader.text[7]
        if leader_char_8 not in ['a', 'c', 'm']:
            skip_validation = True
        else:
            skip_validation = False

    # Proceed with the existing validation if not skipped
    if not skip_validation:
        # Check for the presence of 502 field
        field_502_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '502':
                field_502_present = True
                break

        # If 502 field is present, check for 'm' in characters 25-28 of the 008 field
        if field_502_present:
            # Check for the presence of 'm' in characters 25-28 of the 008 field
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    controlfield_text = controlfield.text
                    if len(controlfield_text) >= 29:  # Check if the field contains enough characters
                        characters_25_28 = controlfield_text[24:28]  # Get characters 25-28
                        if not any(char.strip() == 'm' for char in characters_25_28):  # Check if 'm' is not present after stripping whitespace
                            errors.append("502 exists and bytes 24-27 does not contain ‘m’.")
                            break  # Exit the loop once an error is found
                    else:
                        errors.append("008 field does not contain enough characters.")
                        break  # Exit the loop if 008 field doesn't have enough characters


    # Check if the record has a 510 with a subfield 9, then a 210 field with a subfield 2 value of DNLM must exist
    has_510_with_subfield_9 = False
    has_210_with_subfield_2 = False

    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '510':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == '9':
                    has_510_with_subfield_9 = True
                    break  # No need to check further once subfield 9 is found

        if datafield.attrib['tag'] == '210':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == '2' and subfield.text == 'DNLM':
                    has_210_with_subfield_2 = True
                    break  # No need to check further once subfield 2 with DNLM is found

    # Only add error if 510 with subfield 9 is present but 210 with subfield 2 (DNLM) is missing
    if has_510_with_subfield_9 and not has_210_with_subfield_2:
        errors.append("510 $9 is present, 210 field with $2 of 'DNLM' not present.")


    # Check if 210 field with $2 DNLM has correct indicators (1st ind = 1, 2nd ind = 0)
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '210':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == '2' and subfield.text == 'DNLM':
                    # Found a 210 with $2 DNLM, check the indicators
                    ind1 = datafield.attrib.get('ind1', ' ')
                    ind2 = datafield.attrib.get('ind2', ' ')
                    if ind1 != '1' or ind2 != '0':
                        errors.append("210 $2 DNLM exists, but indicators should be 1 and 0. Current indicators: " + ind1 + ind2)
                    break  # Only check the first occurrence of $2 DNLM in this 210 field


    # Check for the presence of subfield 9 (not '0') and subfield b in the same 510 field
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '510':
            subfield_9_value = None
            subfield_b_present = False
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == '9':
                    subfield_9_value = subfield.text
                elif subfield.attrib['code'] == 'b':
                    subfield_b_present = True
            # Only error if this 510 has $9 (not '0') and is missing $b
            if subfield_9_value and subfield_9_value != '0' and not subfield_b_present:
                errors.append("510 $9 not 0, 510 $b not present")

    # 510 $9 is '0' (zero), 510 Ind 1 not equal '0' (zero)
    # Iterate through datafields to find 510 fields
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '510':
            subfield_9_value = None
            ind1_value = datafield.attrib['ind1']
            # Find subfield 9 value
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == '9':
                    subfield_9_value = subfield.text
                    break
            # Check conditions and raise error if needed
            if subfield_9_value == '0' and ind1_value != '0':
                errors.append("510 $9 is '0' (zero), 510 Ind 1 not equal '0' (zero)")

    # 510 $9 is '1' and 510 $a is not 'PubMed', 510 Ind 1 not equal '1' or '2'
    # Iterate through datafields to find 510 fields
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield[@tag="510"]'):
        subfield_9_value = None
        subfield_a_value = None
        ind1_value = datafield.attrib['ind1']
        
        # Find subfield 9 and subfield a values
        for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
            if subfield.attrib['code'] == '9':
                subfield_9_value = subfield.text
            elif subfield.attrib['code'] == 'a':
                subfield_a_value = subfield.text
        
        # Check conditions and raise error if needed
        if subfield_9_value == '1' and subfield_a_value != 'PubMed' and ind1_value not in ['1', '2']:
            errors.append("510 $9 is '1' and 510 $a is not 'PubMed', 510 Ind 1 not equal '1' or '2'")


    # 510 $9 is '2' or '4', 008/06 not equal 'd'
    # Iterate through datafields to find 510 fields
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '510':
            subfield_9_value = None
            # Find subfield 9 value
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == '9':
                    subfield_9_value = subfield.text
                    break
            # Check conditions and raise error if needed
            if subfield_9_value in ['2', '4']:
                controlfield_008 = root.find('.//{http://www.loc.gov/MARC21/slim}controlfield[@tag="008"]')
                if controlfield_008 is not None:
                    controlfield_008_text = controlfield_008.text
                    if len(controlfield_008_text) >= 8:
                        if controlfield_008_text[6] != 'd':  # Change index to 6 for the 7th character
                            errors.append("510 $9 is '2' or '4', 008/06 not equal 'd'")
                            break


    # 510 $9 is '2' or '3' or '4', 510 $b ends in hyphen
    # Iterate through datafields to find 510 fields
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '510':
            subfield_9_value = None
            subfield_b_value = None
            # Find subfield 9 and subfield b values
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == '9':
                    subfield_9_value = subfield.text
                elif subfield.attrib['code'] == 'b':
                    subfield_b_value = subfield.text
            # Check conditions and raise error if needed
            if subfield_9_value in ['2', '3', '4'] and subfield_b_value and subfield_b_value.endswith('-'):
                errors.append("510 $9 is '2' or '3' or '4', 510 $b ends in hyphen")

    # 510 MEDLINE 1st indicator should be 1 or 2
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '510':
            subfield_a_value = None
            # Find subfield a value
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a':
                    subfield_a_value = subfield.text
                    break
            # Check if subfield a value is 'MEDLINE' and validate the first indicator
            if subfield_a_value == 'MEDLINE':
                first_indicator = datafield.attrib.get('ind1')
                if first_indicator not in ['1', '2']:
                    errors.append("510 MEDLINE 1st indicator should be 1 or 2")

    # 880 field does not have one $6
    # Check if the record has an 880 field
    field_880_present = False
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '880':
            field_880_present = True

    # If an 880 field is present, check if it contains subfield 6
    if field_880_present:
        subfield_6_present = False
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == '880':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib['code'] == '6':
                        subfield_6_present = True
                        break

        # If subfield 6 is not present, print error message
        if not subfield_6_present:
            errors.append("880 field does not have one $6")


    # Check the entire record for the illegal character "ǂ"
    illegal_character = "ǂ"

    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
            if illegal_character in subfield.text:
                errors.append(f"Illegal character {illegal_character} found in {datafield.attrib['tag']} field.")
                break

    # Check if the 337 subfield a is "computer" and validate the presence of the 006 and 007 fields
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        tag = datafield.attrib['tag']
        if tag == "337":
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a' and subfield.text.strip() == "computer":
                    # Check for the existence of the 006 and 007 fields
                    found_006 = False
                    found_007 = False
                    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                        if controlfield.attrib['tag'] == "006":
                            found_006 = True
                        elif controlfield.attrib['tag'] == "007":
                            found_007 = True
                    if not found_006:
                        errors.append("337 subfield a is 'computer' but 006 field is missing.")
                    if not found_007:
                        errors.append("337 subfield a is 'computer' but 007 field is missing.")
                    break
            

    # Check for the presence of fields 100, 110, 111, and 130
    fields_100_110_111_130_present = False
    for field in ['100', '110', '111', '130']:
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib['tag'] == field:
                fields_100_110_111_130_present = True
                break
        if fields_100_110_111_130_present:
            break

    # Leader 17 is '8', 010 field not present
    # Check for the condition in the Leader
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}leader'):
        leader = controlfield.text
        if len(leader) >= 19:  # Ensure the leader has at least 19 characters
            if leader[7] in ['a', 'c', 'm'] and leader[17] == '8':
                # Check if the 010 field is present
                field_010_present = False
                for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                    if datafield.attrib['tag'] == '010':
                        field_010_present = True
                        break

                if not field_010_present:
                    errors.append("Leader 17 is '8', 010 field not present")
        else:
            errors.append("Leader does not contain enough characters.")

    # 008/18-21 contains a value other than blank or fill character (|) and 300 $b not present
    # Check for the condition in the Leader and 008 fields
    leader_field = None
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}leader'):
        leader_field = controlfield.text

    # Ensure we have a leader field and it has enough characters
    if record_type != "indexcat" and leader_field and len(leader_field) >= 19:
        if leader_field[7] in ['a', 'c', 'm']:
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    field_008 = controlfield.text
                    # Ensure the 008 field has at least 22 characters
                    if len(field_008) >= 22:
                        characters_19_22 = field_008[18:22]
                        if not all(char in [' ', '|'] for char in characters_19_22):
                            # Check if the 300 field with subfield b is present
                            field_300_b_present = False
                            for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                                if datafield.attrib['tag'] == '300':
                                    for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                                        if subfield.attrib['code'] == 'b':
                                            field_300_b_present = True
                                            break
                            if not field_300_b_present:
                                errors.append("008/18-21 contains a value other than blank or fill character (|) and 300 $b not present")
                    else:
                        errors.append("008 field does not contain enough characters.")
            # No need to add else block for Leader length as this will check all control fields before breaking
    else:
        if not leader_field or len(leader_field) < 19:
            errors.append("Leader does not contain enough characters.")

    # 300$b exists and 008/18-21 are all ‘blank’
    # Check for the condition in the Leader and 008 fields
    leader_field = None
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}leader'):
        leader_field = controlfield.text

    # Ensure we have a leader field and it has enough characters
    if leader_field and len(leader_field) >= 19:
        if leader_field[7] in ['a', 'c', 'm']:
            field_300_b_present = False
            # Check if the 300 field with subfield b is present
            for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                if datafield.attrib['tag'] == '300':
                    for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                        if subfield.attrib['code'] == 'b':
                            field_300_b_present = True
                            break
                if field_300_b_present:
                    break

            if field_300_b_present:
                for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                    if controlfield.attrib['tag'] == '008':
                        field_008 = controlfield.text
                        # Ensure the 008 field has at least 22 characters
                        if len(field_008) >= 22:
                            characters_19_22 = field_008[18:22]
                            if all(char in [' ', '|'] for char in characters_19_22):
                                errors.append("300$b exists and 008/18-21 are all ‘blank’.")
                        else:
                            errors.append("008 field does not contain enough characters.")
    else:
        if not leader_field or len(leader_field) < 19:
            errors.append("Leader does not contain enough characters.")

    # 008/7-14 are all ‘blank’
    # Check for the condition in the Leader and 008 fields
    leader_field = None
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}leader'):
        leader_field = controlfield.text

    # Ensure we have a leader field and it has enough characters
    if leader_field and len(leader_field) >= 19:
        if leader_field[7] in ['a', 'c', 'm']:
            # Check if the 008 field characters 8-15 are all blank
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    field_008 = controlfield.text
                    # Ensure the 008 field has at least 16 characters
                    if len(field_008) >= 16:
                        characters_8_15 = field_008[7:15]
                        if all(char == ' ' for char in characters_8_15):
                            errors.append("008/7-14 are all ‘blank’.")
                    else:
                        errors.append("008 field does not contain enough characters.")
    else:
        if not leader_field or len(leader_field) < 19:
            errors.append("Leader does not contain enough characters.")

    # 008/06 = ‘b’
    # Check for the condition in the Leader and 008 fields
    leader_field = None
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}leader'):
        leader_field = controlfield.text

    # Ensure we have a leader field and it has enough characters
    if leader_field and len(leader_field) >= 19:
        if leader_field[7] in ['a', 'c', 'm']:
            # Check if the 008 field characters 7 is 'b'
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    field_008 = controlfield.text
                    # Ensure the 008 field has at least 8 characters
                    if len(field_008) >= 8:
                        if field_008[6] == 'b':
                            errors.append("008/06 = ‘b’.")
                    else:
                        errors.append("008 field does not contain enough characters.")
    else:
        if not leader_field or len(leader_field) < 19:
            errors.append("Leader does not contain enough characters.")

    # Check for the condition in the Leader and 008 fields
    leader_field = None
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}leader'):
        leader_field = controlfield.text

    # Ensure we have a leader field and it has enough characters
    if leader_field and len(leader_field) >= 19:
        if leader_field[7] in ['a', 'c', 'm']:
            # Check the 008 field characters 25-28
            for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                if controlfield.attrib['tag'] == '008':
                    field_008 = controlfield.text
                    # Ensure the 008 field has at least 28 characters
                    if len(field_008) >= 28:
                        characters_25_28 = field_008[24:28]
                        if 'n' in characters_25_28 and 'b' in characters_25_28:
                            errors.append("‘n’ is present in 008/24-27 and ‘b’ is also present")
                    else:
                        errors.append("008 field does not contain enough characters.")
    else:
        if not leader_field or len(leader_field) < 19:
            errors.append("Leader does not contain enough characters.")

    # 490 1st indicator 1 and 8XX field not present
    # Check if Leader character 8 is 'a', 'c', or 'm'
    leader_field = None
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}leader'):
        leader_field = controlfield.text

    if leader_field and len(leader_field) >= 19:
        if leader_field[7] in ['a', 'c', 'm']:
            # Check if 490 first indicator is '1'
            has_490_with_first_ind_1 = False
            for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                if datafield.attrib['tag'] == '490' and datafield.attrib.get('ind1') == '1':
                    has_490_with_first_ind_1 = True
                    break
            
            if has_490_with_first_ind_1:
                # Check if any of 800, 810, 811, or 830 fields are present
                has_8xx_field = False
                for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                    if datafield.attrib['tag'] in ['800', '810', '811', '830']:
                        has_8xx_field = True
                        break

                if not has_8xx_field:
                    errors.append("490 1st indicator 1 and 8XX field not present")
    else:
        if not leader_field or len(leader_field) < 19:
            errors.append("Leader does not contain enough characters.")

    # 504$a contains ‘Includes’ and 504$a contains ‘bibliograh*’ 008/24-27 does not contain ‘b’ or ‘n’
    # Check if Leader character 8 is 'a', 'c', or 'm'
    leader_field = None
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}leader'):
        leader_field = controlfield.text

    if leader_field and len(leader_field) >= 19:
        if leader_field[7] in ['a', 'c', 'm']:
            # Check if 504 subfield a includes 'Includes' and 'bibliograph'
            includes_bibliograph = False
            for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                if datafield.attrib['tag'] == '504':
                    for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                        if subfield.attrib['code'] == 'a':
                            if 'Includes' in subfield.text and 'bibliograph' in subfield.text:
                                includes_bibliograph = True
                                break
                if includes_bibliograph:
                    break

            if includes_bibliograph:
                # Check if 008 characters 25-28 contain 'b' or 'n'
                found_b_or_n = False
                for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
                    if controlfield.attrib['tag'] == '008':
                        if len(controlfield.text) >= 29:
                            characters_25_28 = controlfield.text[24:28]
                            if 'b' in characters_25_28 or 'n' in characters_25_28:
                                found_b_or_n = True
                                break
                if not found_b_or_n:
                    errors.append("504$a contains ‘Includes’ and ‘bibliograh*’, 008/24-27 does not contain ‘b’ or ‘n’.")
    else:
        if not leader_field or len(leader_field) < 19:
            errors.append("Leader does not contain enough characters.")

    # 040$e = rda and 264 2nd indicator '1' not present
    # Check if Leader character 8 is 'a', 'c', or 'm'
    leader_field = None
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}leader'):
        leader_field = controlfield.text

    if leader_field and len(leader_field) >= 19:
        if leader_field[7] in ['a', 'c', 'm']:
            # Check if 040 $e is 'rda'
            rda_present = False
            for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                if datafield.attrib['tag'] == '040':
                    for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                        if subfield.attrib['code'] == 'e' and subfield.text == 'rda':
                            rda_present = True
                            break
                if rda_present:
                    break

            if rda_present:
                # Check if 264 with 2nd indicator '1' exists
                indicator_1_present = False
                for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                    if datafield.attrib['tag'] == '264' and datafield.attrib['ind2'] == '1':
                        indicator_1_present = True
                        break

                if not indicator_1_present:
                    errors.append("040$e = rda and 264 2nd indicator '1' not present.")
    else:
        if not leader_field or len(leader_field) < 19:
            errors.append("Leader does not contain enough characters.")

    first_264_checked = False
    has_260 = False

    # Check if a 260 field is present in the record. Updated 8/14
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '260':
            has_260 = True
            break

    # Check all 264 fields for valid indicator combinations
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '264':
            first_indicator = datafield.attrib.get('ind1', '')
            second_indicator = datafield.attrib.get('ind2', '')

            if not first_264_checked:
                # This is the first 264 field
                first_264_checked = True
                if not (first_indicator == ' ' and second_indicator == '1'):
                    if not has_260:
                        errors.append("The first 264 field does not have ind1=' ' and ind2='1', and there is no 260 field present.")
            else:
                # This is any subsequent 264 field
                if first_indicator == ' ' and second_indicator == '1':
                    errors.append("There are multiple 264 tags with indicators of '_1'.")

    # More than one 060 field with first indicator '0'
    # Check if Leader character 8 is 'a', 'c', or 'm'
    leader_field = None
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}leader'):
        leader_field = controlfield.text

    if leader_field and len(leader_field) >= 19:
        if leader_field[7] in ['a', 'c', 'm']:
            # Count the number of 060 fields with first indicator '0'
            count_060_indicator_0 = 0
            for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                if datafield.attrib['tag'] == '060' and datafield.attrib['ind1'] == '0':
                    count_060_indicator_0 += 1

            if count_060_indicator_0 > 1:
                errors.append("More than one 060 field with first indicator '0'.")
    else:
        if not leader_field or len(leader_field) < 19:
            errors.append("Leader does not contain enough characters.")

    # Check if Leader character 8 is 'a', 'c', or 'm'
    leader_field = None
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}leader'):
        leader_field = controlfield.text

    if leader_field and len(leader_field) >= 19:
        if leader_field[7] in ['a', 'c', 'm']:
            # List of values to check in 655 $a

            subfield_a_atlas_present = False
            subfield_a_still_image_present = False
            matched_values = []  # List to store matched 655 $a values

            # Check for the presence of specified values in 655 $a and 'still image' in 336 $a
            for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                if datafield.attrib['tag'] == '655':
                    for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                        if subfield.attrib['code'] == 'a':
                            # Check if the subfield text matches any of the desired values
                            for value in atlas_like_values:
                                if value in subfield.text:
                                    subfield_a_atlas_present = True
                                    matched_values.append(subfield.text)  # Add matched value to the list
                                    break  # Exit inner loop if a match is found
                elif datafield.attrib['tag'] == '336':
                    for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                        if subfield.attrib['code'] == 'a' and 'still image' in subfield.text:
                            subfield_a_still_image_present = True
                            break

            if subfield_a_atlas_present and not subfield_a_still_image_present:
                # Create a comma-separated string of matched values for the error message
                matched_values_string = ', '.join(matched_values)
                errors.append(f"CATALOGER: 655 $a {matched_values_string} exists and 336 $a still image not present.")
    else:
        if not leader_field or len(leader_field) < 19:
            errors.append("Leader does not contain enough characters.")

    # Check if Leader character 8 is 'a', 'c', or 'm'
    leader_field = None
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}leader'):
        leader_field = controlfield.text

    if leader_field and len(leader_field) >= 19:
        if leader_field[7] in ['a', 'c', 'm']:
            # List of values to check in 655 $a

            subfield_a_present = False  # Flag to check for any 655 values
            subfield_a_still_image_present = False  # Flag for 336 $a with still image
            matched_values = []  # List to store matched 655 $a values

            # Check for the presence of 'still image' in 336 $a
            for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                if datafield.attrib['tag'] == '336':
                    for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                        if subfield.attrib['code'] == 'a' and 'still image' in subfield.text:
                            subfield_a_still_image_present = True
                            break  # Exit inner loop if a match is found

            # Check for the presence of specified values in 655 $a
            for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                if datafield.attrib['tag'] == '655':
                    for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                        if subfield.attrib['code'] == 'a':
                            # Check if the subfield text matches any of the desired values
                            for value in atlas_like_values:
                                if value in subfield.text:
                                    subfield_a_present = True
                                    matched_values.append(subfield.text)  # Add matched value to the list
                                    break  # Exit inner loop if a match is found

            # If 336 $a is present but no matching 655 $a values are found
            if subfield_a_still_image_present and not subfield_a_present:
                errors.append("CATALOGER: 336 $a is 'still image' but is missing required 655 $a values.")
    else:
        if not leader_field or len(leader_field) < 19:
            errors.append("Leader does not contain enough characters.")

    # Check if Leader character 8 is 'a', 'c', or 'm'
    leader_field = None
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}leader'):
        leader_field = controlfield.text

    if leader_field and len(leader_field) >= 9:
        if leader_field[7] in ['a', 'c', 'm']:
            # Check for the presence of the 999 field and the specific subfield a value
            subfield_a_value = None
            has_999_field = False
            for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                if datafield.attrib['tag'] == '999':
                    has_999_field = True
                    for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                        if subfield.attrib['code'] == 'a':
                            subfield_a_value = subfield.text.strip()
                            break

            # Determine if we should check for the 650 field. Removed checking for 999 $a NOC as we don't put 650's in those records.
            should_check_650 = (
                not has_999_field or 
                subfield_a_value in ['AUTH', 'WTC', 'CIP']
            )

            if should_check_650:
                # Check for the presence of the 650 field
                field_650_present = False
                for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                    if datafield.attrib['tag'] == '650':
                        field_650_present = True
                        break

                if not field_650_present:
                    errors.append("CATALOGER: 650 field not present.")
    else:
        if not leader_field or len(leader_field) < 9:
            errors.append("Leader does not contain enough characters.")
    
    # Check for 650 fields with 2nd indicator '7' and validate subfield 2 value
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '650' and datafield.attrib.get('ind2') == '7':
            has_subfield_2_meshscr = False
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == '2' and subfield.text.strip() == "meshscr":
                    has_subfield_2_meshscr = True
                    break
            if not has_subfield_2_meshscr:
                errors.append("CATALOGER: 650 field with 2nd indicator '7' is missing subfield 2 with value 'meshscr'.")



    # Check if 999 $a is AUTH and ensure there are no 950 fields in the record
    has_999_auth = False
    has_950_field = False

    # Loop through all datafields in the MARCXML record
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        # Check for 999 field with subfield a value of AUTH
        if datafield.attrib['tag'] == '999':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a' and subfield.text.strip() == 'AUTH':
                    has_999_auth = True

        # Check if a 950 field exists
        if datafield.attrib['tag'] == '950':
            has_950_field = True

    # If 999 $a is AUTH and a 950 field exists, add an error
    if has_999_auth and has_950_field:
        errors.append("CATALOGER: 999 is AUTH but 950's exist")

    # Check for 260 with 2nd indicator blank and 264 with 2nd indicator 1
    has_260_blank_2nd_indicator = False
    has_260_blank_1st_indicator = False
    has_264_2nd_indicator_1 = False
    has_264_blank_1st_indicator = False

    # Loop through all datafields in the MARCXML record
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        # Check for 260 with 2nd indicator blank
        if datafield.attrib['tag'] == '260':
            first_indicator = datafield.attrib.get('ind1', ' ')
            if first_indicator.strip() == '':
                has_260_blank_1st_indicator = True
            second_indicator = datafield.attrib.get('ind2', ' ')
            if second_indicator.strip() == '':
                has_260_blank_2nd_indicator = True

        # Check for 264 with 2nd indicator 1
        if datafield.attrib['tag'] == '264':
            first_indicator = datafield.attrib.get('ind1', ' ')
            if first_indicator.strip() == '':
                has_264_blank_1st_indicator = True
            second_indicator = datafield.attrib.get('ind2', ' ')
            if second_indicator.strip() == '1':
                has_264_2nd_indicator_1 = True

    # If all conditions are met, add an error
    if has_260_blank_1st_indicator and has_260_blank_2nd_indicator and has_264_blank_1st_indicator and has_264_2nd_indicator_1:
        errors.append("CATALOGER: Record cannot have a 260 __ and a 264 _1.")

    # Check the entire record for a dollar sign ($) in any field
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        tag = datafield.attrib.get('tag', '')
        # Skip fields 040, 066, and 880 as they can have legitimate $ signs
        if tag not in ['040', '066', '880']:
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if '$' in subfield.text:
                    errors.append(f"Warning: record has $ sign in field {tag}, is it being used as MARC coding?")
                if '|' in subfield.text:
                    errors.append(f"Warning: record has | sign in field {tag}, is it being used as MARC coding?")
    
    # Check the first indicator of the 041 field
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib.get('tag') == '041':
            ind1 = datafield.attrib.get('ind1', ' ')
            if ind1 not in ['0', '1']:
                errors.append("041 1st indicator should be 0 or 1")

    # Check if 999 $a is AUTH and for brackets in specific fields
    auth_flag = False

    # Check if the 999 $a value is AUTH
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib.get('tag') == '999':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib.get('code') == 'a' and subfield.text == 'AUTH':
                    auth_flag = True
                    break

    # If AUTH is found, check for brackets in 993, 994, 995, 996, 997 fields
    if auth_flag:
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib.get('tag') in ['993', '994', '995', '996', '997']:
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if '[' in subfield.text or ']' in subfield.text:
                        errors.append(f"Record is AUTH but has a bracket in field {datafield.attrib['tag']}")

    # Check if the record is a monograph
    is_monograph = False
    leader_field = None

    # Find and check the Leader field
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}leader'):
        leader_field = controlfield.text

    if leader_field and len(leader_field) >= 19:
        if leader_field[7] in ['a', 'c', 'm']:
            is_monograph = True

    # Check if 999 $a is AUTH
    is_auth = False
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib.get('tag') == '999':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib.get('code') == 'a' and subfield.text == 'AUTH':
                    is_auth = True
                    break

    # If the record is a monograph and 999 $a is AUTH, check the encoding level
    if is_monograph and is_auth:
        if len(leader_field) >= 19:  # Ensure the Leader has at least 19 characters
            encoding_level = leader_field[17]  # Get the 18th character (index 17)
            if encoding_level not in [' ', '1']:  # Encoding level should be blank or '1'
                errors.append("CATALOGER: Encoding level is not full. Newly cataloged monographs should have a full encoding level")
        else:
            errors.append("Leader field is missing or not long enough to determine the encoding level")

    # Check if the record has 042 with 'pcc'
    has_pcc = False
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib.get('tag') == '042':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib.get('code') == 'a' and 'pcc' in subfield.text:
                    has_pcc = True
                    break
        if has_pcc:
            break

    # If 042 contains 'pcc', check for 992 $e with value 'EL'
    if has_pcc:
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
            if datafield.attrib.get('tag') == '992':
                for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                    if subfield.attrib.get('code') == 'e' and subfield.text == 'EL':
                        errors.append(format_error("CATALOGER: Record has 042 pcc but 992 $e is EL. Should it be EF?", datafield, subfield))
                        break
                    
    # 008/31 = ‘1’, but the 500 or 504 field does not contain index*
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
        if controlfield.attrib['tag'] == '008':
            if controlfield.text[30] == '1':
                has_index = False
                for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                    if datafield.attrib['tag'] in ['500', '504']:
                        for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                            if subfield.text and 'index' in subfield.text.lower():
                                has_index = True
                                break
                    if has_index:
                        break
                if not has_index:
                    errors.append("008/31 = '1', but the 500 or 504 field does not contain index*")

    # Validate the first indicator of the 245 field
    if fields_100_110_111_130_present and field_245_indicator1 != '1':
        errors.append("245 first indicator should be '1' when fields 100, 110, 111, or 130 are present.")
    elif not fields_100_110_111_130_present and field_245_indicator1 != '0':
        errors.append("245 first indicator should be '0' when fields 100, 110, 111, or 130 are not present.")
    
    # If this is an indexcat record, perform additional IndexCat-specific validation
    if record_type == "indexcat":
        indexcat_errors = validate_indexcat_specific(root)
        errors.extend(indexcat_errors)

    return True, errors

def validate_indexcat_specific(root):
    """
    Perform IndexCat-specific validation checks on a MARCXML record.
    
    Args:
        root: The parsed XML Element tree of the MARCXML record
        
    Returns:
        List of validation error messages specific to IndexCat records
    """
    errors = []
    
    # Check punctuation in 245 field
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '245':
            subfields = []
            
            # Collect all subfields in order
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                code = subfield.attrib['code']
                text = subfield.text
                subfields.append((code, text))
            
            # If no subfields, skip validation
            if not subfields:
                continue
            
            # Create a map of subfield codes for easy checking
            subfield_codes = [sf[0] for sf in subfields]
            
            # Case 1: Full pattern with all three subfields a, b, c
            if 'a' in subfield_codes and 'b' in subfield_codes and 'c' in subfield_codes:
                # Find positions
                a_pos = subfield_codes.index('a')
                b_pos = subfield_codes.index('b')
                c_pos = subfield_codes.index('c')
                
                # Check $a punctuation
                if not subfields[a_pos][1].strip().endswith(' :'):
                    errors.append("INDEXCAT: 245 $a should end with ' :' when followed by $b")
                    
                # Check $b punctuation
                if not subfields[b_pos][1].strip().endswith(' /'):
                    errors.append("INDEXCAT: 245 $b should end with ' /' when followed by $c")
            
            # Case 2: Just $a and $c (no $b)
            elif 'a' in subfield_codes and 'c' in subfield_codes and 'b' not in subfield_codes:
                a_pos = subfield_codes.index('a')
                c_pos = subfield_codes.index('c')
                
                # Check if $a ends with " / " when directly followed by $c
                if not subfields[a_pos][1].strip().endswith(' /'):
                    errors.append("INDEXCAT: 245 $a should end with ' /' when directly followed by $c (without $b)")
            
            # Case 3: Just $a alone
            elif 'a' in subfield_codes and 'b' not in subfield_codes and 'c' not in subfield_codes:
                # No punctuation check needed when it's just $a
                pass
            
            # For any other pattern, look at each adjacent pair of subfields
            else:
                for i in range(len(subfields) - 1):
                    curr_code, curr_text = subfields[i]
                    next_code = subfields[i+1][0]
                    
                    # Check if $a ends with " : " when followed by $b
                    if curr_code == 'a' and next_code == 'b':
                        if not curr_text.strip().endswith(' :'):
                            errors.append("INDEXCAT: 245 $a should end with ' :' when followed by $b")
                    
                    # Check if $a ends with " / " when followed by $c (without $b in between)
                    elif curr_code == 'a' and next_code == 'c':
                        if not curr_text.strip().endswith(' /'):
                            errors.append("INDEXCAT: 245 $a should end with ' /' when followed by $c")
                    
                    # Check if $b ends with " / " when followed by $c
                    elif curr_code == 'b' and next_code == 'c':
                        if not curr_text.strip().endswith(' /'):
                            errors.append("INDEXCAT: 245 $b should end with ' /' when followed by $c")
    
    
    # Check punctuation in 264 field
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '264':
            subfields = []
            
            # Collect all subfields in order
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                code = subfield.attrib['code']
                text = subfield.text
                subfields.append((code, text))
            
            # If no subfields, skip validation
            if not subfields:
                continue
            
            # Create a map of subfield codes for easy checking
            subfield_codes = [sf[0] for sf in subfields]
            
            # Case 1: Full pattern with all three subfields a, b, c
            if 'a' in subfield_codes and 'b' in subfield_codes and 'c' in subfield_codes:
                # Find positions
                a_pos = subfield_codes.index('a')
                b_pos = subfield_codes.index('b')
                c_pos = subfield_codes.index('c')
                
                # Check $a punctuation
                if not subfields[a_pos][1].strip().endswith(' :'):
                    errors.append("INDEXCAT: 264 $a should end with ' :' when followed by $b")
                    
                # Check $b punctuation - should end with comma
                if not subfields[b_pos][1].strip().endswith(','):
                    errors.append("INDEXCAT: 264 $b should end with ',' when followed by $c")
                    
                # Check $c punctuation - should end with period unless it ends with other punctuation
                c_text = subfields[c_pos][1].strip()
                if not (c_text.endswith('.') or c_text.endswith('?') or c_text.endswith('!') or 
                        c_text.endswith(']') or c_text.endswith(')')):
                    errors.append("INDEXCAT: 264 $c should end with a period or other punctuation")
            
            # Case 2: Just $a and $c (no $b)
            elif 'a' in subfield_codes and 'c' in subfield_codes and 'b' not in subfield_codes:
                a_pos = subfield_codes.index('a')
                c_pos = subfield_codes.index('c')
                
                # Check if $a ends with comma when directly followed by $c
                if not subfields[a_pos][1].strip().endswith(','):
                    errors.append("INDEXCAT: 264 $a should end with ',' when directly followed by $c (without $b)")
                    
                # Check $c punctuation - should end with period unless it ends with other punctuation
                c_text = subfields[c_pos][1].strip()
                if not (c_text.endswith('.') or c_text.endswith('?') or c_text.endswith('!') or 
                        c_text.endswith(']') or c_text.endswith(')')):
                    errors.append("INDEXCAT: 264 $c should end with a period or other punctuation")
            
            # Case 3: Just $a and $b (no $c)
            elif 'a' in subfield_codes and 'b' in subfield_codes and 'c' not in subfield_codes:
                a_pos = subfield_codes.index('a')
                b_pos = subfield_codes.index('b')
                
                # Check if $a ends with " : " when followed by $b
                if not subfields[a_pos][1].strip().endswith(' :'):
                    errors.append("INDEXCAT: 264 $a should end with ' :' when followed by $b")
            
            # Case 4: Just $c alone
            elif 'c' in subfield_codes and 'a' not in subfield_codes and 'b' not in subfield_codes:
                c_pos = subfield_codes.index('c')
                
                # Check $c punctuation - should end with period unless it ends with other punctuation
                c_text = subfields[c_pos][1].strip()
                if not (c_text.endswith('.') or c_text.endswith('?') or c_text.endswith('!') or 
                       c_text.endswith(']') or c_text.endswith(')')):
                    errors.append("INDEXCAT: 264 $c should end with a period or other punctuation")
            
            # For any other pattern, look at each adjacent pair of subfields
            else:
                for i in range(len(subfields) - 1):
                    curr_code, curr_text = subfields[i]
                    next_code = subfields[i+1][0]
                    
                    # Check if $a ends with " : " when followed by $b
                    if curr_code == 'a' and next_code == 'b':
                        if not curr_text.strip().endswith(' :'):
                            errors.append("INDEXCAT: 264 $a should end with ' :' when followed by $b")
                    
                    # Check if $a ends with " , " when followed by $c (without $b in between)
                    elif curr_code == 'a' and next_code == 'c':
                        if not curr_text.strip().endswith(','):
                            errors.append("INDEXCAT: 264 $a should end with ',' when followed by $c")
                    
                    # Check if $b ends with " , " when followed by $c
                    elif curr_code == 'b' and next_code == 'c':
                        if not curr_text.strip().endswith(','):
                            errors.append("INDEXCAT: 264 $b should end with ',' when followed by $c")
                
                # Check if final subfield is $c and if it ends with appropriate punctuation
                if subfields[-1][0] == 'c':
                    c_text = subfields[-1][1].strip()
                    if not (c_text.endswith('.') or c_text.endswith('?') or c_text.endswith('!') or 
                           c_text.endswith(']') or c_text.endswith(')')):
                        errors.append("INDEXCAT: 264 $c should end with a period or other punctuation")

    

    # Check punctuation in 300 field
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '300':
            subfields = []
            
            # Collect all subfields in order
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                code = subfield.attrib['code']
                text = subfield.text
                subfields.append((code, text))
            
            # If no subfields, skip validation
            if not subfields:
                continue
            
            # Create a map of subfield codes for easy checking
            subfield_codes = [sf[0] for sf in subfields]
            
            # Case 1: Full pattern with all three subfields a, b, c
            if 'a' in subfield_codes and 'b' in subfield_codes and 'c' in subfield_codes:
                # Find positions
                a_pos = subfield_codes.index('a')
                b_pos = subfield_codes.index('b')
                c_pos = subfield_codes.index('c')
                
                # Check $a punctuation
                if not subfields[a_pos][1].strip().endswith(' :'):
                    errors.append("INDEXCAT: 300 $a should end with ' :' when followed by $b")
                    
                # Check $b punctuation
                if not subfields[b_pos][1].strip().endswith(' ;'):
                    errors.append("INDEXCAT: 300 $b should end with ' ;' when followed by $c")
            
            # Case 2: Just $a and $c (no $b)
            elif 'a' in subfield_codes and 'c' in subfield_codes and 'b' not in subfield_codes:
                a_pos = subfield_codes.index('a')
                c_pos = subfield_codes.index('c')
                
                # Check if $a ends with " ; " when directly followed by $c
                if not subfields[a_pos][1].strip().endswith(' ;'):
                    errors.append("INDEXCAT: 300 $a should end with ' ;' when directly followed by $c (without $b)")
            
            # Case 3: Just $a and $b (no $c)
            elif 'a' in subfield_codes and 'b' in subfield_codes and 'c' not in subfield_codes:
                a_pos = subfield_codes.index('a')
                b_pos = subfield_codes.index('b')
                
                # Check if $a ends with " : " when followed by $b
                if not subfields[a_pos][1].strip().endswith(' :'):
                    errors.append("INDEXCAT: 300 $a should end with ' :' when followed by $b")
            
            # Case 4: Just $a alone
            elif 'a' in subfield_codes and 'b' not in subfield_codes and 'c' not in subfield_codes:
                # No punctuation check needed when it's just $a
                pass
            
            # For any other pattern, look at each adjacent pair of subfields
            else:
                for i in range(len(subfields) - 1):
                    curr_code, curr_text = subfields[i]
                    next_code = subfields[i+1][0]
                    
                    # Check if $a ends with " : " when followed by $b
                    if curr_code == 'a' and next_code == 'b':
                        if not curr_text.strip().endswith(' :'):
                            errors.append("INDEXCAT: 300 $a should end with ' :' when followed by $b")
                    
                    # Check if $a ends with " ; " when followed by $c (without $b in between)
                    elif curr_code == 'a' and next_code == 'c':
                        if not curr_text.strip().endswith(' ;'):
                            errors.append("INDEXCAT: 300 $a should end with ' ;' when followed by $c")
                    
                    # Check if $b ends with " ; " when followed by $c
                    elif curr_code == 'b' and next_code == 'c':
                        if not curr_text.strip().endswith(' ;'):
                            errors.append("INDEXCAT: 300 $b should end with ' ;' when followed by $c")


    # Check 1: Academic Dissertation in 655 should have 'm' in 008/24
    has_academic_dissertation = False
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '655':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a' and subfield.text == "Academic Dissertation":
                    has_academic_dissertation = True
                    break
    
    if has_academic_dissertation:
        # Check if 008/24 doesn't have 'm'
        for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
            if controlfield.attrib['tag'] == '008':
                if len(controlfield.text) >= 25:
                    if controlfield.text[24] != 'm':
                        errors.append("INDEXCAT: 655 'Academic Dissertation' present but 008/24 is not 'm'")
    
    
    # Check 3: 590 field should not have brackets around shelving data
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '590':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'a' and subfield.text:
                    if '[' in subfield.text and ']' in subfield.text:
                        errors.append("INDEXCAT: 590 $a contains bracketed content which should be removed")

    # Check for field 650 that should not exist in IndexCat records
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '650':
            errors.append("INDEXCAT: 650 field should not exist in IndexCat records")
    
    # Check for "cm." in 300 field (should be "cm")
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '300':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.text and "cm." in subfield.text:
                    errors.append("INDEXCAT: 300 field contains 'cm.' which should be 'cm'")
    
    # Check for brackets in 500 field
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '500':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.text and ('[' in subfield.text or ']' in subfield.text):
                    errors.append("INDEXCAT: 500 field contains brackets which should be removed")

    # Add new check for 044 field
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '044':
            # Check 1: Check for subfields other than $a and $9
            subfields = datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield')
            has_invalid_subfields = any(subfield.attrib['code'] not in ['a', '9'] for subfield in subfields)
            if has_invalid_subfields:
                errors.append("INDEXCAT: 044 field has subfields other than $a or $9")
            
            # Check 2: Check for $a that should be $9

            # has_a_subfield = any(subfield.attrib['code'] == 'a' for subfield in subfields)
            for subfield in subfields:
                if subfield.attrib['code'] == 'a':
                    errors.append(format_error("INDEXCAT: 044 field uses $a instead of $9", datafield, subfield))
                

    # Add illustration code validation
    illustration_errors = validate_illustration_codes(root)
    errors.extend(illustration_errors)

    return errors

def nightly_validation_checks(marcxml_data, record_type="regular"):
    """
    Perform nightly validation checks on a MARCXML record.
    Args:
        marcxml_data (str): The MARCXML data as a string.
        record_type (str): The type of record, either "regular" or "indexcat".
    Returns:
        List of error messages found during validation.
    """
    errors = []

    # Parse the MARXML data
    root = ET.fromstring(marcxml_data)

    # "001 is missing"
    # 001 field is required
    temp = get_controlfield_chars(marcxml_data, '001', 0, 1)
    if record_type != "indexcat" and temp is None:
        errors.append("001 is missing")
    
    # "008 is missing"
    # 008 field is required
    temp = get_controlfield_chars(marcxml_data, '008', 0, 1)
    if temp is None:
        errors.append("008 is missing")

    # "001 field length is invalid"
    # 001 values must be between 8-19 digits
    if record_type != "indexcat" and "001 is missing" not in errors:
        len_001 = get_controlfield_length(marcxml_data, '001')
        if len_001 < 8 or len_001 > 19:
            errors.append("001 field length is invalid")

        # "Invalid character in 001"
        # 001 values must be numerical
        temp = get_controlfield_chars(marcxml_data, '001', 0, len_001)
        if not temp.isdigit():
            errors.append("Invalid character in 001 field")

    temp = get_all_indicators_and_subfields_for_tag(marcxml_data, '035')
    # "035 field is missing"
    # 035 field is required
    if len(temp) == 0:
        errors.append("035 field is missing")

    # "035 $9 field is missing"
    # 035 $9 field is required
    temp = [item for item in temp if item['subfields'].get('9', '') != '']
    if record_type != "indexcat" and len(temp) == 0:
        errors.append("035 $9 field is missing")

    else:
        for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
                if datafield.attrib['tag'] == '035':
                    # Check if there is a subfield 9 present
                    for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                        if subfield.attrib['code'] == '9':
                            if not subfield.text.isalnum():
                                errors.append(format_error("Invalid character in 035 $9 field", datafield, subfield))
    #NEW VERSION ---
    # "CITVIDEO is missing 035 $a beginning with (DNLM)CIT":
    # If 998$a == "CITREL" then 035 $a field is required, and must begin with (DNLM)CIT
    temp = get_all_indicators_and_subfields_for_tag(marcxml_data, '998')
    temp = [item for item in temp if item['subfields'].get('a','') == 'CITREL']
    if len(temp) > 0:
        temp = get_all_indicators_and_subfields_for_tag(marcxml_data, '035')
        temp = [item for item in temp if item['subfields'].get('a','').startswith('(DNLM)CIT')]
        if len(temp) == 0:
            errors.append("CITVIDEO is missing 035 $a beginning with (DNLM)CIT")
  
    # 995 $b and $d should contain 8 characters
    # That subfield should contain 8 characters
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '995':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'b':
                    if len(subfield.text) != 8:
                        errors.append(format_error("995 $b should contain 8 characters", datafield, subfield))
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.attrib['code'] == 'd':
                    if len(subfield.text) != 8:
                        errors.append(format_error("995 $d should contain 8 characters", datafield, subfield))
    
    return errors

def validate_illustration_codes(root):
    """
    Check if illustration codes in 008/18-21 match content in 300 field
    using the exact logic from the original function.
    
    Args:
        root: The parsed XML Element tree of the MARCXML record
        
    Returns:
        List of validation error messages
    """
    errors = []
    
    # Step 1: Extract the content of the 300 field
    field300_text = ""
    for datafield in root.findall('.//{http://www.loc.gov/MARC21/slim}datafield'):
        if datafield.attrib['tag'] == '300':
            for subfield in datafield.findall('.//{http://www.loc.gov/MARC21/slim}subfield'):
                if subfield.text:
                    field300_text += " " + subfield.text.lower()
    
    if not field300_text:
        return errors  # No 300 field found, no validation needed
    
    # Step 2: Apply the mapping logic from the original function
    illustration_found = False
    plate_found = False
    codes_found = ""
    
    # Mapping order: same as in the original function
    mapping_order = [
        (["illustration", "illustrations", "chart", "charts"], "a"),
        (["map", "maps"], "b"),
        (["portrait", "portraits"], "c"),
        (["plate", "plates"], "af")
    ]
    
    for terms, code in mapping_order:
        if any(term in field300_text for term in terms):
            if code == "a":
                illustration_found = True
                if "af" in codes_found:
                    continue  # Skip adding "a" if "af" already exists
            elif code == "af":
                plate_found = True
                if illustration_found and "a" in codes_found:
                    codes_found = codes_found.replace("a", "")  # Remove standalone "a"
            
            # Add the code if it's not already there
            if code not in codes_found:
                codes_found += code
            
            # Break if we've collected 4 or more characters
            if len(codes_found) >= 4:
                break
    
    # If no codes found, no further validation needed
    if not codes_found:
        return errors
    
    # Step 3: Check the 008 field against the expected codes
    expected_codes = codes_found.ljust(4, " ")[:4]
    
    for controlfield in root.findall('.//{http://www.loc.gov/MARC21/slim}controlfield'):
        if controlfield.attrib['tag'] == '008':
            if len(controlfield.text) < 22:
                errors.append("INDEXCAT: 008 field is too short (less than 22 characters)")
                return errors            
            actual_codes = controlfield.text[18:22]
            
            # Compare expected vs. actual codes
            if expected_codes != actual_codes:
                # Generate a detailed error message
                errors.append(f"INDEXCAT: Illustration codes in 008/18-21 should be '{expected_codes}' based on 300 field content, but found '{actual_codes}'")
    
    return errors
