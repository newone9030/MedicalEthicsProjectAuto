"""Check syntax of the case_manager_view.py file"""
import py_compile
import traceback

try:
    py_compile.compile('c:/PythonProject/app/case/case_manager_view.py', doraise=True)
    print("Syntax OK")
except py_compile.PyCompileError as e:
    print(f"Syntax Error: {e}")
    traceback.print_exc()
except Exception as e:
    print(f"Other Error: {e}")
    traceback.print_exc()
