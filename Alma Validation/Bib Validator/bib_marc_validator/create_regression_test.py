import json
from bib_validator import validate_marcxml_record
from bib_xml_corrections import route_marc_error
from xml_formatters import format_xml, add_id_to_each_tag, remove_id_from_each_tag

def print_errors(errors):
    for error in normalize_errors(errors):
        print("\t" + error)

def correct_errors(errors, xml_string):
    for error in errors:
        xml_string = route_marc_error(error, xml_string)
    return xml_string

def normalize_errors(error_list):
    norm_errors = []
    for error in error_list:
        if isinstance(error, dict):
            error_message = error.get("error", "Unknown error")
            norm_errors.append(error_message)
        elif isinstance(error, str):
            norm_errors.append(error)

    return norm_errors

# Get the errored file
filepath = input("Enter the filepath of the errored XML file: \\")
if "\\" in filepath:
    filepath = filepath.replace("\\", "/")

file_name = filepath.split("/")[-1]

with open(filepath, "rb") as f:
    binary_string = f.read()
    xml_string = binary_string.decode('utf-8')

# Validate the errored file
xml_string = add_id_to_each_tag(xml_string)

errors = validate_marcxml_record(xml_string, "indexcat")
# errors = sorted(list(errors)) # Remove duplicates
print("Errors found in given XML:")
print_errors(errors)

# Correct the errors
print("Correcting errors...")

xml_string = correct_errors(errors, xml_string)

# Validate the corrected file
sticky_errors = validate_marcxml_record(xml_string, "regular")
# sticky_errors = sorted(list(set(sticky_errors))) # Remove duplicates


# Format the XML
print("Formatting XML...")
xml_string = remove_id_from_each_tag(xml_string)
xml_string = format_xml(xml_string)

print(xml_string)

print("Errors not corrected:")
print_errors(sticky_errors)

solved_errors = [error for error in errors if error not in sticky_errors]
print("Errors corrected:")
print_errors(solved_errors)

create_regression_test = input("Create regression test? (y/n): ")
if create_regression_test == "y":
    test_name = file_name
    errors_before_correction = errors
    errors_not_solved = sticky_errors
    errors_solved = solved_errors

    with open("tests/regression tests/test libraries/default.json", "r") as file:
        tests_file = json.load(file)
    with open(f"tests/regression tests/xml test outputs/{test_name}", "w", encoding='utf-8') as f:
        f.write(xml_string)
        
    tests_file.update({test_name: {
        "input_filepath": filepath,
        "errors_before_correction": errors_before_correction,
        "errors_not_solved": errors_not_solved,
        "errors_solved": errors_solved
    }})

    with open("tests/regression tests/test libraries/default.json", "w", encoding='utf-8') as file:
        json.dump(tests_file, file, indent=4)
    print("Regression test created.")
