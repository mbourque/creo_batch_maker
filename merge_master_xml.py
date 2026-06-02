import argparse
import os
import glob
import xml.etree.ElementTree as ET
import re


def clean_xml(file_path):
    with open(file_path, 'rb') as f:
        content = f.read().decode('utf-8', errors='ignore')
    
    # Remove non-printable characters
    cleaned_content = re.sub(r'[^\x20-\x7E\n\r\t]', '', content)
    
    cleaned_file_path = file_path + '.cleaned'
    with open(cleaned_file_path, 'w', encoding='utf-8') as f:
        f.write(cleaned_content)
    
    return cleaned_file_path

def extract_check_content(file_path):
    cleaned_file_path = clean_xml(file_path)
    tree = ET.parse(cleaned_file_path)
    root = tree.getroot()
    checks = root.findall('.//check')
    
    # Extract additional details
    model = root.find('.//model').text if root.find('.//model') is not None else ''
    pro_type = root.find('.//pro_type').text if root.find('.//pro_type') is not None else ''
    date = root.find('.//date').text if root.find('.//date') is not None else ''
    last_saved = root.find('.//last_saved').text if root.find('.//last_saved') is not None else ''
    created = root.find('.//created').text if root.find('.//created') is not None else ''
    
    file_size = 0
    num_features = 0
    overall_size = 'Unknown'
    units_length = 'Unknown'

    def _direct_ans(check_el):
        """First direct child <ans> only (find('ans') can match nested descendants)."""
        for child in check_el:
            if child.tag == "ans":
                return child
        return None

    def _normalize_units_length(raw: str) -> str:
        """Display-friendly length units from ModelCHECK UNITS_LENGTH check."""
        text = raw.strip()
        if not text:
            return "Unknown"
        key = text.upper()
        return {"MM": "mm", "INCH": "in", "IN": "in"}.get(key, text)

    for check in root.findall('.//check'):
        name = check.get('name')
        if name == 'FILE_SIZE':
            ans_el = _direct_ans(check)
            if ans_el is not None and ans_el.text:
                text = ans_el.text.strip()
                # Creo: bytes as decimal digits; do not overwrite with 0 on NOT APPLICABLE etc.
                if text.isdigit():
                    file_size = round(int(text) / (1024 * 1024), 2)
        elif name == 'REG_FEATURES':
            num_features = check.find('ans').text if check.find('ans') is not None else 0
        elif name == 'OVERALL_SIZE':
            overall_size = check.find('ans').text if check.find('ans') is not None else 'Unknown'
        elif name == 'UNITS_LENGTH':
            ans_el = _direct_ans(check)
            if ans_el is not None and ans_el.text:
                units_length = _normalize_units_length(ans_el.text)

    os.remove(cleaned_file_path)  # Clean up temporary file
    return checks, model, pro_type, date, last_saved, created, file_size, num_features, overall_size, units_length

def indent(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

def write_master_xml(checks_dict, output_file, folder_path):
    root = ET.Element("MasterXML")
    
    for file_path, (checks, model, pro_type, date, last_saved, created, file_size, num_features, overall_size, units_length) in checks_dict.items():
        file_element = ET.SubElement(root, "File")
        
        # Path = scan folder (same as working directory / CLI directory) + model name
        path_element = ET.SubElement(file_element, "Path")
        path_element.text = os.path.join(folder_path, model)
        
        model_element = ET.SubElement(file_element, "Model")
        model_element.text = model
        
        pro_type_element = ET.SubElement(file_element, "ProType")
        pro_type_element.text = pro_type
        
        date_element = ET.SubElement(file_element, "Date")
        date_element.text = date
        
        last_saved_element = ET.SubElement(file_element, "LastSaved")
        last_saved_element.text = last_saved
        
        created_element = ET.SubElement(file_element, "Created")
        created_element.text = created

        file_size_element = ET.SubElement(file_element, "FileSize")
        file_size_element.text = str(file_size) + ' MB'
        
        num_features_element = ET.SubElement(file_element, "NumFeatures")
        num_features_element.text = str(num_features)
        
        overall_size_element = ET.SubElement(file_element, "OverallSize")
        overall_size_element.text = overall_size
        
        units_length_element = ET.SubElement(file_element, "UnitsLength")
        units_length_element.text = units_length
        
        checks_element = ET.SubElement(file_element, "Checks")
        for check in checks:
            checks_element.append(check)
    
    indent(root)
    tree = ET.ElementTree(root)
    tree.write(output_file, encoding='utf-8', xml_declaration=True)


def build_master_xml(working_directory=None, output_file=None):
    """
    Scan ``working_directory`` for per-model check XML (``*.p.xml``,
    ``*.a.xml``, ``*.d.xml``) and write a single ``master.xml`` (or
    ``output_file``).

    Each ``<Path>`` in ``master.xml`` is ``scan_folder`` + model name, where
    ``scan_folder`` is the resolved absolute path of the directory you pass
    (or ``.`` when omitted).

    For GUI use, pass the current working-directory path from main.py.

    If ``working_directory`` is empty or omitted, uses ``.`` (current
    working directory). If ``output_file`` is empty or omitted, uses
    ``master.xml``.
    """
    wd = (working_directory or "").strip()
    directory_to_scan = wd or "."
    path_root = os.path.normpath(os.path.abspath(directory_to_scan))
    out = (output_file or "").strip() or "master.xml"

    patterns = ["**/*.p.xml", "**/*.a.xml", "**/*.d.xml"]
    files = [
        f
        for pattern in patterns
        for f in glob.glob(os.path.join(directory_to_scan, pattern), recursive=True)
    ]

    checks_dict = {}
    for file_path in files:
        try:
            checks, model, pro_type, date, last_saved, created, file_size, num_features, overall_size, units_length = extract_check_content(file_path)
            checks_dict[file_path] = (checks, model, pro_type, date, last_saved, created, file_size, num_features, overall_size, units_length)
        except ET.ParseError as e:
            print(f"Error parsing file {file_path}: {e}")

    write_master_xml(checks_dict, out, path_root)
    print(f"Output file written: {out}")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Merge per-model check XML files into one master.xml.",
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Folder to scan for *.p.xml, *.a.xml, *.d.xml (default: .)",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        default=None,
        help="Output file (default: master.xml)",
    )
    args = parser.parse_args(argv)
    return build_master_xml(working_directory=args.directory, output_file=args.output)


if __name__ == "__main__":
    main()
