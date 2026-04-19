import re

with open('book_workflow.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Swap the check from 022 to 020 for the matching condition
content = re.sub(r'tag\.endswith\(\'datafield\'\) and f\.get\(\'tag\'\) == \'022\'', 
                 r"tag.endswith('datafield') and f.get('tag') == '020'", content)
content = re.sub(r'022 \$a', '020 $a', content)

# Remove the TA tool logic block
content = re.sub(r'(?s)# Run the TA tool.*?print\("Successfully Normalized Record\."\)', 
                 'print("Successfully Normalized Record.")', content)

with open('book_workflow.py', 'w', encoding='utf-8') as f:
    f.write(content)
