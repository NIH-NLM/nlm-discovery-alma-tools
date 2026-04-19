import os
import pytest
import json
from bib_marc_validator.bib_validator import validate_marcxml_record
from bib_marc_validator.bib_xml_corrections import correct_marc_error
from xml_formatters import format_xml

with open("tests/regression tests/test libraries/default.json", "r") as file:
    tests_file = json.load(file)

tests = list()
for key in tests_file:
    print(key)
    test = tests_file[key]
    with open(test['input_filepath'], "rb") as file:
        tests.append((
            file.read(),
            test["input_filepath"],
            test["errors_before_correction"],
            test["errors_not_solved"],
            test["errors_solved"]
        ))

@pytest.mark.parametrize(
    "xml_payload_input, xml_payload_location, errors_before_correction, errors_not_solved, errors_solved",
    tests
)
def test_corrections_engine(xml_payload_input,
                            xml_payload_location,
                            errors_before_correction,
                            errors_not_solved,
                            errors_solved):
    
    # First gather the errors represented in the input
    errors_found_1 = validate_marcxml_record(xml_payload_input)
    errors_found_1 = sorted(list(set(errors_found_1)))
    errors_before_correction = sorted(errors_before_correction)

    # Test that validator works as normal
    assert errors_found_1 == errors_before_correction
    
    updated_xml_string = xml_payload_input

    # Correct the errors (as many as possible)
    for error in errors_found_1:
        updated_xml_string = correct_marc_error(error, updated_xml_string)
    
    # Get the errors after correction
    errors_found_2 = validate_marcxml_record(updated_xml_string)
    errors_found_2 = sorted(list(set(errors_found_2)))
    errors_not_solved = sorted(errors_not_solved)
    assert errors_found_2 == errors_not_solved

    errors_actually_solved =  [error for error in errors_found_1 if error not in errors_found_2]

    errors_actually_solved = sorted(errors_actually_solved)
    errors_solved = sorted(errors_solved)
    assert errors_actually_solved == errors_solved