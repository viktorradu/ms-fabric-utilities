import os
import shutil
import subprocess
import re

parameters = {
    "DateParameterDemo": "#datetime(2025, 5, 17, 0, 0, 0)",
    "TextParameterDemo": '"B"',
    "IsolatedParameterDemo": '"demo"'
}

project = "c:\\temp\\sample\\parameterized report.pbip"
project_name = os.path.splitext(os.path.basename(project))[0]
stage = os.path.join(os.path.dirname(project), "stage")
os.makedirs(stage, exist_ok=True)

source_folder = os.path.join(os.path.dirname(project), f"{project_name}.Report")
destination_folder = os.path.join(stage, f"{project_name}.Report")
shutil.copytree(source_folder, destination_folder, dirs_exist_ok=True)

source_folder = os.path.join(os.path.dirname(project), f"{project_name}.SemanticModel")
destination_folder = os.path.join(stage, f"{project_name}.SemanticModel")
shutil.copytree(source_folder, destination_folder, dirs_exist_ok=True)

shutil.copy2(project, stage)

abf_file = os.path.join(destination_folder, f".pbi\\cache.abf")
if os.path.exists(abf_file):
    os.remove(abf_file)

for parameter, value in parameters.items():
    parameter_file = os.path.join(destination_folder, f"definition\\tables\\{parameter}.tmdl")
    if os.path.exists(parameter_file):
        with open(parameter_file, 'r', encoding='utf-8') as file:
            content = file.read()
        content = re.sub(r'source\s*=\s*.+meta', f'source={value} meta', content)
        with open(parameter_file, 'w', encoding='utf-8') as file:
            file.write(content)
    else:
        expressions_file = os.path.join(destination_folder, f"definition\\expressions.tmdl")
        with open(expressions_file, 'r', encoding='utf-8') as file:
            content = file.read()
        content = re.sub(rf'expression\s{re.escape(parameter)}\s*=\s*.+meta', f'expression {parameter}={value} meta', content)
        with open(expressions_file, 'w', encoding='utf-8') as file:
            file.write(content)


pbip_file = os.path.join(stage, os.path.basename(project))
subprocess.run(['start', '', pbip_file], shell=True, check=True)