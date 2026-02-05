import sys
import os

backend_dir = os.path.dirname(os.path.abspath(__file__))
print(f"Backend directory: {backend_dir}")
print(f"Python path before: {sys.path[:3]}")

sys.path.insert(0, backend_dir)
print(f"Python path after: {sys.path[:3]}")

# Check if utils folder exists
utils_path = os.path.join(backend_dir, 'utils')
print(f"Utils path: {utils_path}")
print(f"Utils exists: {os.path.exists(utils_path)}")
print(f"Utils is directory: {os.path.isdir(utils_path)}")

# List files in utils
if os.path.exists(utils_path):
    print(f"Files in utils: {os.listdir(utils_path)}")

# Try importing
try:
    from utils.nlp_processor import extract_expense_data
    print("✓ Import successful!")
except Exception as e:
    print(f"✗ Import failed: {e}")