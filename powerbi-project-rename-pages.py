import sys
import os
import json
import re
from pathlib import Path
import zipfile

def create_safe_folder_name(display_name):
    """Create a safe folder name from the display name."""
    # Replace invalid characters and commas with underscores
    safe_name = re.sub(r'[<>:"/\\|?*,]', '_', display_name)
    # Remove leading/trailing spaces and dots
    safe_name = safe_name.strip('. ')
    # Replace multiple spaces with single underscore
    safe_name = re.sub(r'\s+', '_', safe_name)
    # Ensure name is no longer than 42 characters
    if len(safe_name) > 42:
        safe_name = safe_name[:42].rstrip('_')
    return safe_name

def ensure_unique_name(name, existing_names):
    """Ensure the folder name is unique by adding a suffix if needed."""
    if name not in existing_names:
        return name
    
    counter = 1
    while f"{name}_{counter}" in existing_names:
        counter += 1
    return f"{name}_{counter}"

def main():
    # Check if folder path argument is provided
    if len(sys.argv) < 2:
        print("Error: Please provide the folder path as an argument (*.Report format)")
        sys.exit(1)
    
    report_path = Path(sys.argv[1])
    
    # Check if the provided path exists and is a directory
    if not report_path.exists():
        print(f"Error: The path '{report_path}' does not exist")
        sys.exit(1)
    
    if not report_path.is_dir():
        print(f"Error: The path '{report_path}' is not a directory")
        sys.exit(1)
    
    # Check if "definition" folder exists
    definition_folder = report_path / "definition"
    if not definition_folder.exists() or not definition_folder.is_dir():
        print(f"Error: The 'definition' folder does not exist in '{report_path}'")
        sys.exit(1)
    
    # Check if "pages" folder exists within definition
    pages_folder = definition_folder / "pages"
    if not pages_folder.exists() or not pages_folder.is_dir():
        print(f"Error: The 'pages' folder does not exist in '{definition_folder}'")
        sys.exit(1)
    
    # Check if pages.json exists
    pages_json_path = pages_folder / "pages.json"
    if not pages_json_path.exists():
        print(f"Error: 'pages.json' file not found in '{pages_folder}'")
        sys.exit(1)
    
    # Read pages.json file
    try:
        with open(pages_json_path, 'r', encoding='utf-8') as f:
            pages_data = json.load(f)
    except Exception as e:
        print(f"Error reading pages.json: {e}")
        sys.exit(1)
    
    # Extract active page ID and page order
    active_page_id = pages_data.get('activePageName')
    page_order = pages_data.get('pageOrder', [])
    
    # Get list of page IDs from pages subfolder names
    page_folders = [f for f in pages_folder.iterdir() if f.is_dir()]
    
    # Create mapping of old names to new names
    rename_map = {}
    existing_safe_names = set()
    
    # Process each page folder
    for page_folder in page_folders:
        page_id = page_folder.name
        page_json_path = page_folder / "page.json"
        
        if not page_json_path.exists():
            print(f"Warning: page.json not found in '{page_folder}', skipping")
            continue
        
        try:
            with open(page_json_path, 'r', encoding='utf-8') as f:
                page_data = json.load(f)
        except Exception as e:
            print(f"Error reading {page_json_path}: {e}")
            continue
        
        # Extract display name
        display_name = page_data.get('displayName', page_id)
        
        # Create safe folder name
        safe_name = create_safe_folder_name(display_name)
        
        # Ensure uniqueness
        unique_name = ensure_unique_name(safe_name, existing_safe_names)
        existing_safe_names.add(unique_name)
        
        # Store mapping if names differ
        if page_id != unique_name:
            rename_map[page_id] = unique_name
            print(f"Will rename: '{page_id}' -> '{unique_name}' (Display: '{display_name}')")
    
    backup_dir = report_path.parent
    base_name = report_path.name
    backup_path = backup_dir / f"{base_name}_backup.zip"

    if backup_path.exists():
        counter = 1
        while True:
            candidate = backup_dir / f"{base_name}_{counter}_backup.zip"
            if not candidate.exists():
                backup_path = candidate
                break
            counter += 1

    with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for root, _, files in os.walk(report_path):
            root_path = Path(root)
            for filename in files:
                file_path = root_path / filename
                archive.write(file_path, arcname=str(file_path.relative_to(report_path.parent)))

    print(f"Created backup archive at '{backup_path}'")

    # Rename folders and update page.json files
    for old_name, new_name in rename_map.items():
        old_path = pages_folder / old_name
        new_path = pages_folder / new_name
        
        try:
            old_path.rename(new_path)
            print(f"Renamed: '{old_name}' -> '{new_name}'")
            
            # Update the name attribute in page.json
            page_json_path = new_path / "page.json"
            if page_json_path.exists():
                with open(page_json_path, 'r', encoding='utf-8') as f:
                    page_data = json.load(f)
                
                page_data['name'] = new_name
                
                with open(page_json_path, 'w', encoding='utf-8') as f:
                    json.dump(page_data, f, indent=2, ensure_ascii=False)
                
                print(f"  Updated name attribute in page.json to '{new_name}'")
        except Exception as e:
            print(f"Error renaming '{old_name}' to '{new_name}': {e}")
            sys.exit(1)
    
    # Update pages.json with new folder names
    if active_page_id and active_page_id in rename_map:
        pages_data['activePageName'] = rename_map[active_page_id]
    
    if page_order:
        pages_data['pageOrder'] = [
            rename_map.get(page_id, page_id) for page_id in page_order
        ]
    
    # Write updated pages.json
    try:
        with open(pages_json_path, 'w', encoding='utf-8') as f:
            json.dump(pages_data, f, indent=2, ensure_ascii=False)
        print(f"\nUpdated pages.json successfully")
    except Exception as e:
        print(f"Error writing pages.json: {e}")
        sys.exit(1)
    
    print("\nPage renaming completed successfully!")

if __name__ == "__main__":
    main()