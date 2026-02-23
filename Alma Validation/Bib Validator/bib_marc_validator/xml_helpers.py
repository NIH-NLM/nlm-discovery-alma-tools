from xml.etree import ElementTree as ET
import uuid

def set_subfield(xml_string: str, field_tag: str, subfield_code: str, new_value: str, ind2: str = None) -> str:
    """
    Set the value of a specific subfield in a MARC XML record
    
    Args:
        xml_string (str): The MARC XML record as a string
        field_tag (int): The datafield tag number (e.g. 300)
        subfield_code (str): The subfield code (e.g. "a")
        new_value (str): The new value to set for the subfield
        ind2 (str, optional): The second indicator value to match
        
    Returns:
        str: The modified XML record as a string
    """
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    root = ET.fromstring(xml_string)
    
    # Find all matching datafields
    xpath = f".//*[@tag='{field_tag}']"
    datafields = root.findall(xpath)
    
    for datafield in datafields:
        # Skip if ind2 is specified and doesn't match
        if ind2 is not None and datafield.get('ind2') != ind2:
            continue
            
        # Find or create subfield
        subfield = datafield.find(f"*[@code='{subfield_code}']")
        if subfield is not None:
            subfield.text = new_value
        else:
            new_subfield = ET.SubElement(datafield, 'subfield', {'code': subfield_code, 'id': str(uuid.uuid4())})
            new_subfield.text = new_value
    
    return ET.tostring(root, encoding='unicode', method='xml')

def get_subfield(xml_string: str, field_tag: str, subfield_code: str) -> str:
    """
    Get the value of a specific subfield in a MARC XML record
    
    Args:
        xml_string (str): The MARC XML record as a string
        field_tag (int): The datafield tag number (e.g. 300)
        subfield_code (str): The subfield code (e.g. "a")
        
    Returns:
        str | None: The subfield value if found, None otherwise
    """
    # Register the namespace
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    
    # Parse the XML string
    root = ET.fromstring(xml_string)
    
    # Find the specific datafield
    datafield = root.find(f".//*[@tag='{field_tag}']")
    
    if datafield is not None:
        # Find the specific subfield
        subfield = datafield.find(f".//*[@code='{subfield_code}']")
        
        if subfield is not None:
            return subfield.text
    
    return None

def get_tag_by_id(xml_string, id):
    """
    Get a specific tag by its ID from the XML string.
    Args:       
        xml_string (str): The MARC XML record as a string
        id (str): The ID of the datafield to retrieve
    Returns:
        Element | None: The XML element with the specified ID, or None if not found
"""
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    root = ET.fromstring(xml_string)
    for tag in root.findall(".//{http://www.loc.gov/MARC21/slim}datafield"):
        if tag.get("id") == id:
            return tag
    return None

def remove_tag_by_id(xml_string, id):
    """
    Remove a specific datafield tag by its ID from the XML string.
    Args:
        xml_string (str): The MARC XML record as a string
        id (str): The ID of the datafield to remove
    Returns:
        str: The modified XML record as a string with the specified tag removed
    """
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    root = ET.fromstring(xml_string)
    for tag in root.findall(".//{http://www.loc.gov/MARC21/slim}datafield"):
        if tag.get("id") == id:
            root.remove(tag)
    return ET.tostring(root, encoding='unicode', method='xml')

def get_subfield_by_id(xml_string, id, subfield_code):
    """
    Get a specific subfield value by its ID from the XML string.
    Args:
        xml_string (str): The MARC XML record as a string
        id (str): The ID of the datafield to search within
        subfield_code (str): The subfield code to retrieve (e.g. 'a')
    Returns:
        str | None: The value of the subfield if found, None otherwise
    """
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    root = ET.fromstring(xml_string)
    my_tag = get_tag_by_id_no_string(root, id)
    if my_tag is not None:
        subfield = my_tag.find(f"*[@code='{subfield_code}']")
        if subfield is not None:
            return subfield.text

    return None

def set_subfield_by_id(xml_string, id, subfield_code, new_value):
    """
    Set or create a subfield value in a MARC XML record by tag ID.
    Args:
        xml_string (str): The MARC XML string to modify
        id (str): The ID of the tag to find
        subfield_code (str): The code of the subfield to set or create
        new_value (str): The new value to set for the subfield
    Returns:
        str: The modified MARC XML string with the subfield value updated
    """
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    root = ET.fromstring(xml_string)
    my_tag = get_tag_by_id_no_string(root, id)

    if my_tag is not None:
        subfield = my_tag.find(f"*[@code='{subfield_code}']")
        if subfield is not None:
            subfield.text = new_value
        else:
            new_subfield = ET.SubElement(my_tag, 'subfield', {'code': subfield_code, 'id': str(uuid.uuid4())})
            new_subfield.text = new_value
    return ET.tostring(root, encoding='unicode', method='xml')

def add_subfield_by_id(xml_string, id, subfield_code, value):
    """
    Add a new subfield to a specific tag in a MARC XML record by tag ID
    Args:
        xml_string (str): The MARC XML record as a string
        id (str): The ID of the datafield to add the subfield to
        subfield_code (str): The subfield code to add (e.g. 'a')
        value (str): The value to set for the new subfield
    Returns:
        str: The modified XML record as a string with the new subfield added
    """
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    root = ET.fromstring(xml_string)
    my_tag = get_tag_by_id_no_string(root, id)
    my_id = str(uuid.uuid4())
    new_subfield = ET.SubElement(my_tag, 'subfield', {'code': subfield_code, 'id': my_id})
    new_subfield.text = value

    return ET.tostring(root, encoding='unicode', method='xml')

def remove_subfield_by_id(xml_string, id, subfield_code):
    """
    Remove a specific subfield from a tag in a MARC XML record by tag ID.
    Args:
        xml_string (str): The MARC XML record as a string
        id (str): The ID of the datafield to search within
        subfield_code (str): The subfield code to remove (e.g. 'a')
    Returns:
        str: The modified XML record as a string with the specified subfield removed
    """
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    root = ET.fromstring(xml_string)
    my_tag = get_tag_by_id_no_string(root, id)

    if my_tag is not None:
        subfield = my_tag.find(f"*[@code='{subfield_code}']")
        if subfield is not None:
            my_tag.remove(subfield)

    return ET.tostring(root, encoding='unicode', method='xml')

def get_indicator_by_id(xml_string, id, indicator):
    """
    Get the value of a specific indicator (1 or 2) for a tag by its ID in a MARC XML record.
    Args:
        xml_string (str): The MARC XML record as a string
        id (str): The ID of the datafield to search within
        indicator (str): The indicator number to retrieve ('1' or '2')
    Returns:
        str | None: The value of the specified indicator if found, None otherwise
    """
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    root = ET.fromstring(xml_string)
    my_tag = get_tag_by_id_no_string(root, id)
    if my_tag is not None:
        return my_tag.get(f"ind{indicator}", None)

    return None

def set_indicator_by_id(xml_string, id, indicator, new_value):
    """
    Set the value of a specific indicator (1 or 2) for a tag by its
    ID in a MARC XML record.
    Args:
        xml_string (str): The MARC XML record as a string
        id (str): The ID of the datafield to search within
        indicator (str): The indicator number to set ('1' or '2')
        new_value (str): The new value to set for the indicator
    Returns:
        str: The modified XML record as a string with the indicator updated
    """
    if indicator not in ['1', '2']:
        return xml_string
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    root = ET.fromstring(xml_string)
    my_tag = get_tag_by_id_no_string(root, id)

    if my_tag is not None:
        my_tag.set(f"ind{indicator}", new_value)

    return ET.tostring(root, encoding='unicode', method='xml')

def set_tag_by_id(xml_string, id, new_value):
    """
    Set the value of a specific tag by its ID in a MARC XML record.
    Args:
        xml_string (str): The MARC XML record as a string
        id (str): The ID of the datafield to modify
        new_value (str): The new value to set for the tag
    Returns:
        str: The modified XML record as a string with the tag value updated
    """
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    root = ET.fromstring(xml_string)
    my_tag = get_tag_by_id_no_string(root, id)

    if my_tag is not None:
        my_tag.set("tag", new_value)

    return ET.tostring(root, encoding='unicode', method='xml')

def get_tag_by_id_no_string(root, id):
    """
    Get a specific tag by its ID from the XML root element.
    Args:
        root (Element): The root element of the XML tree
        id (str): The ID of the datafield to retrieve
    Returns:
        Element | None: The XML element with the specified ID, or None if not found
    """
    for tag in root.findall(".//{http://www.loc.gov/MARC21/slim}datafield"):
        if tag.get("id") == id:
            return tag
    return None

def fix_punctuation(value, ending):
    """
    Remove any existing punctuation at the end and add the correct punctuation
    
    Args:
        value (str): The original text value
        ending (str): The correct ending punctuation
        
    Returns:
        str: Text with correct punctuation
    """
    # Return if value is None
    if value is None:
        return ending
        
    # First strip any whitespace
    value = value.rstrip()
    
    # Remove any existing punctuation at the end
    # Check for common punctuation that might be at the end
    while value and value[-1] in ':,;/':
        value = value[:-1].rstrip()
        
    # Add the correct punctuation
    return value + ending

def precise_remove_by_id(xml_string, id):
    """
    Remove a specific subfield with a given value by its ID from the XML string.
    
    Args:
        xml_string (str): The MARC XML record as a string
        id (str): The ID of the datafield to modify
        value (str): The value of the subfield to match for removal
        
    Returns:
        str: The modified XML record as a string
    """
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    root = ET.fromstring(xml_string)
    # Find the specific subfield by its id attribute
    subfield = root.find(f".//*[@id='{id}']")
    
    # if subfield is not None:
    #     # Get the parent element and remove the subfield
    #     parent = subfield.getparent()
    #     if parent is not None:
    #         parent.remove(subfield)

    if subfield is not None:
        # Remove the subfield directly
        subfield.clear()
        subfield.tag = None
    
    return ET.tostring(root, encoding='unicode', method='xml')

def precise_set_by_id(xml_string, id, value):
    """
    Set a specific subfield with a given value by its ID in the XML string.
    
    Args:
        xml_string (str): The MARC XML record as a string
        id (str): The ID of the datafield to modify
        value (str): The new value for the subfield
        
    Returns:
        str: The modified XML record as a string
    """
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    root = ET.fromstring(xml_string)
    
    # Find the specific subfield by its id attribute
    subfield = root.find(f".//*[@id='{id}']")
    
    if subfield is not None:
        subfield.text = value

    else:
        print(f"No element found with id='{id}'")
    
    result = ET.tostring(root, encoding='unicode', method='xml')
    return result

def precise_get_by_id(xml_string, subfield_code):
    """
    Get a specific subfield value by its ID from the XML string.
    
    Args:
        xml_string (str): The MARC XML record as a string
        id (str): The ID of the datafield to modify
        subfield_code (str): The subfield code to get
        
    Returns:
        str | None: The value of the subfield if found, None otherwise
    """
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    root = ET.fromstring(xml_string)
    
    # Find the specific subfield by its id attribute
    subfield = root.find(f".//*[@id='{subfield_code}']")
    
    if subfield is not None:
        return subfield.text
    
    return None

def id_exists(xml_string, id):
    """
    Check if a specific ID exists in the XML string.
    
    Args:
        xml_string (str): The MARC XML record as a string
        id (str): The ID to check
        
    Returns:
        bool: True if the ID exists, False otherwise
    """
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    root = ET.fromstring(xml_string)
    
    thing = root.find(f".//*[@id='{id}']")
    return (thing is not None)