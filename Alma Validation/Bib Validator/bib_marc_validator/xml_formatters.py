from xml.etree import ElementTree as ET
from xml.dom import minidom
import uuid

def format_xml(xml_string: str) -> str:
    """
    Format XML by sorting fields and fixing indentation
    Args:
        xml_string (str): The XML string to format.
    Returns:
        str: The formatted XML string with sorted fields and proper indentation.
    """
    root = ET.fromstring(xml_string)
    ET.register_namespace('', "http://www.loc.gov/MARC21/slim")
    
    # Get all controlfields and datafields
    controlfields = root.findall(".//{http://www.loc.gov/MARC21/slim}controlfield")
    datafields = root.findall(".//{http://www.loc.gov/MARC21/slim}datafield")
    
    # Sort fields by tag
    controlfields.sort(key=lambda x: x.get('tag'))
    datafields.sort(key=lambda x: x.get('tag'))
    
    # Remove all existing fields
    for field in controlfields + datafields:
        root.remove(field)
    
    # Add back in sorted order
    for field in controlfields + datafields:
        root.append(field)
    
    # Convert to string with proper indentation
    rough_string = ET.tostring(root, encoding='unicode')
    parsed = minidom.parseString(rough_string)
    pretty_xml = parsed.toprettyxml(indent="    ")
    
    # Remove excessive newlines
    # First split into lines and remove empty lines
    lines = [line for line in pretty_xml.split('\n') if line.strip()]
    # Join back with single newlines
    return '\n'.join(lines)

def add_id_to_each_tag(xml_string: str):
    """Add a unique ID to each datafield and subfield tag in the XML string.
    Args:
        xml_string (str): The XML string to process.
    Returns:
        str: The XML string with IDs added to each datafield and subfield tag.
    """
    root = ET.fromstring(xml_string)
    for tag in root.findall(".//{http://www.loc.gov/MARC21/slim}datafield"):
        tag.set("id", str(uuid.uuid4()))
    
    for subfield in root.findall(".//{http://www.loc.gov/MARC21/slim}subfield"):
        subfield.set("id", str(uuid.uuid4()))

    return ET.tostring(root, encoding='unicode', method='xml')

def remove_id_from_each_tag(xml_string: str):
    """Remove the ID attribute from each datafield and subfield tag in the XML string.
    Args:
        xml_string (str): The XML string to process.
    Returns:
        str: The XML string with IDs removed from each datafield and subfield tag.
    """
    root = ET.fromstring(xml_string)
    for tag in root.findall(".//{http://www.loc.gov/MARC21/slim}datafield"):
        tag.attrib.pop("id")
    for tag in root.findall(".//{http://www.loc.gov/MARC21/slim}subfield"):
        tag.attrib.pop("id")
    return ET.tostring(root, encoding='unicode', method='xml')