import os
import xml.etree.ElementTree as ET


def generate_summary_div(master_xml_path, model_checks_xml_path):
    # Load and parse the XML files
    master_tree = ET.parse(master_xml_path)
    master_root = master_tree.getroot()

    model_tree = ET.parse(model_checks_xml_path)
    model_root = model_tree.getroot()

    # Function to extract category descriptions from the model_checks.xml file
    def get_category_descriptions(model_root):
        category_descriptions = {}
        for category in model_root.find('Categories').findall('Category'):
            name = category.find('Name').text
            description = category.find('Description').text
            category_descriptions[name] = description
        return category_descriptions

    # Function to categorize checks based on the model_checks.xml file
    def categorize_checks(master_root, model_root):
        categories = {}

        # Create a mapping of ModelCheckName to Category from model_checks.xml
        model_check_mapping = {}
        for check in model_root.findall('Check'):
            model_check_name = check.find('ModelCheckName').text
            category = check.find('Category').text
            model_check_mapping[model_check_name] = category

        # Categorize the checks based on the mapping
        for check in master_root.findall('.//check'):
            name = check.get('name')
            stat = check.find('stat').text

            # Skip INFO stats
            if stat == 'INFO':
                continue

            if name in model_check_mapping:
                category = model_check_mapping[name]
                if category not in categories:
                    categories[category] = {'PASS': 0, 'WARNING': 0, 'ERROR': 0}
                categories[category][stat] += 1

        return categories

    # Function to calculate a grade based on the proportions
    def calculate_grade(sizes):
        total = sum(sizes)
        if total == 0:
            return 'N/A', "Green: 0%, Yellow: 0%, Red: 0%"

        green, yellow, red = sizes
        green_ratio = green / total
        yellow_ratio = yellow / total
        red_ratio = red / total

        breakdown = f"Green: {green_ratio * 100:.2f}%, Yellow: {yellow_ratio * 100:.2f}%, Red: {red_ratio * 100:.2f}%"

        if red > 0:
            return 'D', breakdown
        elif yellow_ratio > 0.25:
            return 'C', breakdown
        elif yellow_ratio >= 0.05:
            return 'B', breakdown
        else:
            return 'A', breakdown

    # Function to generate the div content with grading rationale and progress bars
    def generate_div_content(categories, category_descriptions):
        div_content = """
        <style>
            progress[value] {
                width: 100%;
                height: 20px;
                -webkit-appearance: none;
                appearance: none;
            }
            progress[value]::-webkit-progress-bar {
                background-color: #f3f3f3;
                border-radius: 5px;
                overflow: hidden;
            }
            progress[value]::-webkit-progress-value {
                transition: width 0.6s ease;
            }
            .progress-green::-webkit-progress-value {
                background-color: green;
            }
            .progress-yellow::-webkit-progress-value {
                background-color: yellow;
            }
            .progress-red::-webkit-progress-value {
                background-color: red;
            }
            progress[value]::-moz-progress-bar {
                background-color: green; /* Default color for Firefox */
            }
            .grading-rationale {
                margin-bottom: 20px;
            }
            .category {
                margin-bottom: 30px;
                padding: 10px;
                border: 1px solid #ccc;
                border-radius: 5px;
            }
            .grade {
                font-size: 20px;
                font-weight: bold;
                margin-bottom: 10px;
            }
            .description {
                font-size: 14px;
                margin-top: 10px;
            }
        </style>
        <div class="grading-rationale">
            <h3>How the Grade is Determined</h3>
            <p>
                The overall grade for each category is determined by the proportion of PASS, WARNING, and ERROR checks:
            </p>
            <ul>
                <li><strong>Grade A:</strong> Awarded when the models have a very high proportion of PASS checks, with minimal warnings (less than 5%) and no errors.</li>
                <li><strong>Grade B:</strong> Given when the models have a moderate number of warnings (between 5% and 25%) but no errors. This suggests that while the model is generally good, there are areas that need attention.</li>
                <li><strong>Grade C:</strong> Assigned if the models have a higher number of warnings (more than 25%) but still no errors. This indicates that the model requires significant improvements.</li>
                <li><strong>Grade D:</strong> This grade is given if any of the models have errors. Errors are critical and must be fixed to ensure the model is viable.</li>
            </ul>
        </div>
        """

        for category, checks in categories.items():
            sizes = [checks['PASS'], checks['WARNING'], checks['ERROR']]
            grade, breakdown = calculate_grade(sizes)
            green_ratio = sizes[0] / sum(sizes) * 100 if sum(sizes) > 0 else 0
            yellow_ratio = sizes[1] / sum(sizes) * 100 if sum(sizes) > 0 else 0
            red_ratio = sizes[2] / sum(sizes) * 100 if sum(sizes) > 0 else 0

            description = category_descriptions.get(category, "No description available.")

            div_content += f"""
            <div class="category">
                <h2 class="grade">{category} : Grade {grade}</h2>
                <p>{description}</p> 
                <p>{breakdown}</p>
                <div>
                    <progress class="progress-green" value="{green_ratio}" max="100"></progress> Green
                </div>
                <div>
                    <progress class="progress-yellow" value="{yellow_ratio}" max="100"></progress> Yellow
                </div>
                <div>
                    <progress class="progress-red" value="{red_ratio}" max="100"></progress> Red
                </div>
            </div>
            """

        return div_content

    # Get category descriptions
    category_descriptions = get_category_descriptions(model_root)

    # Categorize the checks
    categories = categorize_checks(master_root, model_root)

    # Generate the div content
    div_content = generate_div_content(categories, category_descriptions)

    return div_content


def write_summary_html_file(master_xml_path: str, model_checks_xml_path: str, output_path: str) -> str:
    """
    Run ``generate_summary_div`` and save the result as a minimal standalone HTML file.

    Returns the path written (``output_path``).
    """
    fragment = generate_summary_div(master_xml_path, model_checks_xml_path)
    doc = (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n'
        '  <meta charset="UTF-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        "  <title>Modelcheck summary</title>\n"
        "</head>\n<body>\n"
        f"{fragment}\n"
        "</body>\n</html>\n"
    )
    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(doc)
    return output_path
