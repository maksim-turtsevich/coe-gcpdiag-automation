from flask import Flask, request
import gunicorn

import subprocess as sp
import re

from jira import JIRA
import os

app = Flask(__name__)

# Pattern for matching the gcpdiag rules
pattern = "([a-z]){3}\/([A-Z])\w+\/[12][0-9]{3}\_\d{3}"

# Rules prefixes that are longer than standard 3
lst_of_long_prefixes = ["apigee", "bigquery", "composer", "dataproc"]

# Map with resources
resource_map = {
    "Apigee": ["apigee"], "Big Data": ["bigquery", "composer", "dataproc"], "App Engine": ["gae"],
    "CI/CD": ["gcb"], "Integration": ["gcb"], "Compute Engine": ["gce"], "Cloud Functions": ["gcf"],
    "Storage": ["gcs"], "Kubernetes Engine": ["gke"], "IAM": ["iam"], "Ass": ["tpu"], "Networking": ["vpc"],
    "All": "All"
}

# Auth key
authentication_key = "/home/maksi/gcp-coe-msp-sandbox-9d73c756e918.json"

# Jira Authentication
options = {'server': r"https://devoteamgcloud.atlassian.net/"}
jira = JIRA(basic_auth=("maksim.turtsevich@devoteam.com", os.getenv("jira_token")), options=options)


# Needed metrics (will think about it)
# metrics = ["ERR", "WARN"]


def generate_rule_with_description(raw_rule_with_description):
    rule = re.search(pattern, raw_rule_with_description).group()
    rule_prefix = rule.split("/")[0]

    final_prefix = rule_prefix
    for long_prefix in lst_of_long_prefixes:
        if rule_prefix in long_prefix:
            final_prefix = long_prefix

    final_rule = rule.replace(rule_prefix, final_prefix)
    final_rule_with_description = final_rule + ": " + raw_rule_with_description.split(":")[1]

    return final_rule_with_description, final_prefix


def extract_mentioned_resources(lst_of_resources):
    all_prefixes = []

    for field in lst_of_resources:
        all_prefixes += resource_map.get(field, [])

    all_prefixes = set(all_prefixes)
    print(all_prefixes)

    return all_prefixes


def validate_the_resource(starting_rule, data, prefix):
    lst_of_resources = data["issue"]["fields"]["resource"]
    all_prefixes = extract_mentioned_resources(lst_of_resources)
    if prefix not in all_prefixes and lst_of_resources[0] != "All":  # Testing thing will be changed later
        return False

    return True


def generate_final_string(logs_divided_by_rules, data):
    final_string = ""
    for rule_lst in logs_divided_by_rules:
        if len(rule_lst) == 1:  # Last item without filters contains two elements in the list [rule, ""], fix it
            continue

        starting_rule, prefix_for_validation = generate_rule_with_description(rule_lst[0])
        validation = validate_the_resource(starting_rule, data, prefix_for_validation)
        if not validation:
            continue

        final_string += starting_rule + "\n"

        for desc in rule_lst[1:]:
            if "FAIL" in desc:
                problem = re.sub("\s+", " ", desc)
                problem_splitted = problem.split(" ")
                final_problem = " - " + problem_splitted[1] + " FAIL"

                final_string += final_problem + "\n"
            elif "http" in desc:
                final_string += "Documentation: " + desc + "\n"
            else:
                final_string += desc + "\n"

        final_string += "\n"

    # If final_string will be empty (all resources passed) the following string will be outputted
    if not final_string:
        final_string = "Unfortunately gcpdiag doesn't support the affected resources or he didn\'t find the ones " \
                       "mentioned! "

    return final_string


def processing(logs):
    # Initial Processing
    new_logs = [log.strip() for log in logs]

    logs_divided_by_rules = []
    for i in range(len(new_logs)):
        rule_match = re.search(pattern, new_logs[i])
        if rule_match and i != len(new_logs) - 1 and "http" not in new_logs[i]:
            next_string = re.search(pattern, new_logs[i + 1])
            unmatched_string_index = i + 1

            while not next_string and unmatched_string_index != len(new_logs) - 1:
                unmatched_string_index += 1
                next_string = re.search(pattern, new_logs[unmatched_string_index])

                # URL with rule matches the REGEX pattern as well, in order to skip it we need put next_string to False
                # in order to not exit the loop
                if next_string and "http" in new_logs[unmatched_string_index]:
                    next_string = False

            logs_divided_by_rules.append(new_logs[i:unmatched_string_index])
        else:
            continue

    return logs_divided_by_rules


def logs_processing_driver(gcpdiag_logs, data):
    lst_of_logs = gcpdiag_logs.splitlines()

    logs_divided_by_rules = processing(lst_of_logs)
    final_string = generate_final_string(logs_divided_by_rules, data)

    return final_string


def execute_gcpdiag(project_name: str):
    print("executing command")
    # command = f"sudo ./gcpdiag lint --project {project_name} --hide-ok --auth-key={authentication_key}"
    command = f"./gcpdiag lint --project {project_name} --hide-ok"
    logs = sp.getoutput(command)

    print("Output of the command ", logs)

    return logs


def submit_to_jira(name_of_the_ticket, final_string):
    comment = jira.add_comment(name_of_the_ticket, final_string, visibility={'key': 'sd.public.comment'},
                               is_internal=True)


@app.route("/", methods=['POST', 'GET'])
def main():
    if request.method == "GET":
        return "Hello World!"

    print("request: POST")
    data = request.json
    project_name = data["issue"]["fields"]["GCP Project ID"]

    gcpdiag_logs = execute_gcpdiag(project_name)
    final_string = logs_processing_driver(gcpdiag_logs, data)

    # Working with Jira
    name_of_the_ticket = data["issue"]["key"]
    submit_to_jira(name_of_the_ticket, final_string)

    return final_string


if __name__ == "__main__":
    app.run("127.0.0.1", port=5000, debug=True)
