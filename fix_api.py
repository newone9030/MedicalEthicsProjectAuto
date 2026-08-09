"""Convert PopupMenuItem text= to content= for Flet 0.86+"""
import re
import glob
import os

root = r'c:\PythonProject'
py_files = glob.glob(os.path.join(root, '*.py'), recursive=False) + \
           glob.glob(os.path.join(root, 'app', '**', '*.py'), recursive=True)

for fpath in py_files:
    if 'fix_api' in fpath:
        continue
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()
    original = content
    content = re.sub(
        r'(PopupMenuItem\([^)]*?)\btext=',
        r'\1content=',
        content,
        flags=re.DOTALL
    )
    if content != original:
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f'Fixed: {fpath}')
print('Done.')
