from flask import Flask, request

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
    "All": ["All"]
}

# Auth key
# authentication_key = "/home/maksim_turtsevich/gcp-coe-msp-sandbox-9d73c756e918.json"
authentication_key = "/app/gcp-coe-msp-sandbox-9d73c756e918.json"

# Jira Authentication
options = {'server': r"https://devoteamgcloud.atlassian.net/"}
jira = JIRA(basic_auth=("maksim.turtsevich@devoteam.com", os.getenv("jira_token")), options=options)


# Needed metrics (will think about it)
# metrics = ["ERR", "WARN"]


def generate_rule_with_description(raw_rule_with_description):
    """
    Function that processes the gcpdiag rule string in a human readable
    format, corrects prefixes if needed and outputs them for further
    processing and filtering

    Parameters:
    raw_rule_with_description(str): raw gcpdiag rule with its description

    Returns:
    final_rule_with_description (str): gcpdiag rule string in a human readable format
    final_prefix (str): prefix for further filtering and validation

    """
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
    """
    Function extracts the prefixes of the affected resources
    using the "resource_map", adds them in a set (in order to
    avoid the duplicates) and outputs it for filtering

    Parameters:
        lst_of_resources(list): List of types of resources
                                requested to be inspected
                                (e.g Compute Engine, GKE)

    Returns:
        all_prefixes(str): set of the prefixes that can be
                           used to match the resources affected
                           or requested for inspection
    """
    all_prefixes = []

    for field in lst_of_resources:
        all_prefixes += resource_map.get(field, [])

    all_prefixes = set(all_prefixes)
    print(all_prefixes)

    return all_prefixes


def create_list_of_resources(lst_of_dicts):
    lst_of_resources = []

    for dct in lst_of_dicts:
        lst_of_resources.append(dct["value"])

    return lst_of_resources


def validate_the_resource(starting_rule, data, prefix):
    """
    Function that validates the rule inputted (if it should
    be included in the final outputted string) and outputs
    True or False boolean value

    Parameters:
        data(dict): List of logs grouped by rules
        prefix(str): Payload of the Webhook

    Returns:
        bool
    """
    lst_of_dicts = data["issue"]["fields"]["customfield_10141"]
    if not lst_of_dicts:
        return True

    lst_of_resources = create_list_of_resources(lst_of_dicts)

    all_prefixes = extract_mentioned_resources(lst_of_resources)
    if prefix not in all_prefixes and lst_of_resources[0] != "All":  # Testing thing will be changed later
        return False

    return True


def generate_final_string(logs_divided_by_rules, data) -> str:
    """
    Function that generates a final string from the logs
    that are divided by gcpdiag rules

    Parameters:
        logs_divided_by_rules(list): List of logs grouped by rules
        data(dict): Payload of the Webhook

    Returns:
        final_string(str): Processed gcpdiag logs
    """

    final_string = ""
    rules_count = 1

    # Iterating through the list of rules and their respective data
    for rule_lst in logs_divided_by_rules:

        # If length of the rule's list is 1 => it means that there is no data associated
        # with a particular rule, as a result it will be passed
        if len(rule_lst) == 1:  # Last item without filters contains two elements in the list [rule, ""], fix it
            continue

        # Calling method that processes the string with the rule in a human readable format
        # and to extract the prefix for futher filtering
        starting_rule, prefix_for_validation = generate_rule_with_description(rule_lst[0])

        # Calling a method in order to validate whether a prefix of a specific rule that
        # concerns a specific resource (e.g gke, coe, gcf) need to be outputted
        validation = validate_the_resource(starting_rule, data, prefix_for_validation)

        # If validation equals "False" the record will be passed
        if not validation:
            continue

        # Building the final string
        final_string += str(rules_count) + ")" + " " + starting_rule + "\n"
        rules_count += 1

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

        final_string += "\n\n"

    # If final_string will be empty (all resources passed) the following string will be outputted
    if not final_string:
        final_string = "Unfortunately gcpdiag doesn't support the affected resources or he didn\'t find the ones " \
                       "mentioned! "

    return final_string


def processing(logs):
    """
    Function that groups the logs by the rules  (i.e gke/ERR/2022_001, iam/SEC/2021_001)
    and stores all the related data (documentation, resources affected) in the same list
    with them for further processing

    Parameters:
        logs (list): Logs divided by rows

    Returns:
        logs_divided_by_rules (str): Logs that are grouped by rules
    """
    # Initial Processing
    new_logs = [log.strip() for log in logs]

    logs_divided_by_rules = []

    # Iterates through the list of rows
    for i in range(len(new_logs)):
        rule_match = re.search(pattern, new_logs[i])

        # If rule matches the regex pattern for "gcpdiag" rules and doesn't
        # have an "http" in it. It will be considered as a "host of the group"
        if rule_match and i != len(new_logs) - 1 and "http" not in new_logs[i]:
            next_string = re.search(pattern, new_logs[i + 1])
            unmatched_string_index = i + 1

            # Iterating through the values after the "matched" string
            # until the new matched string (group) will be found
            while not next_string and unmatched_string_index != len(new_logs) - 1:
                unmatched_string_index += 1
                next_string = re.search(pattern, new_logs[unmatched_string_index])

                if next_string and "http" in new_logs[unmatched_string_index]:
                    next_string = False

            # Adding slice of values from the first "matched" string (rule)
            # to the second "matched" string (rule) in the list of lists
            logs_divided_by_rules.append(new_logs[i:unmatched_string_index])
        else:
            continue

    return logs_divided_by_rules


def logs_processing_driver(gcpdiag_logs, data):
    """
    Function that executes all the data processing methods

    Parameters:
        gcpdiag_logs (str): Logs outputted for "gcpdiag"
        data (dict): payload of the Webhook

    Returns:
        final_string (str) - processed logs from "gcpdiag"
    """
    lst_of_logs = gcpdiag_logs.splitlines()

    logs_divided_by_rules = processing(lst_of_logs)
    final_string = generate_final_string(logs_divided_by_rules, data)

    return final_string


def execute_gcpdiag(project_name: str):
    """
    Function executes the "gcpdiag" command and collects
    the outputs of it

    Parameters:
        project_name (str): Name of the project to extract
                        logs from

    Returns:
        logs (str) - logs outputted from "gcpdiag"
    """

    # Command for running "gcpdiag"
    # command = f"sudo ./gcpdiag lint --project {project_name} --hide-ok --auth-key={authentication_key}"
    # command = f"sudo ./gcpdiag lint --project {project_name} --hide-ok --auth-adc"
    command = f"./gcpdiag lint --project {project_name} --hide-ok"

    # Storing the output of the command
    logs = sp.getoutput(command)

    return logs


def submit_to_jira(name_of_the_ticket, final_string):
    """
    Function submits the internal comment to the Jira ticket
    by using the name of the ticket (name_of_the_ticket) and
    comment itself (final_string)

    Parameters:
        name_of_the_ticket (str): Name of the ticket
        final_string (str): String to put in the comment

    """

    comment = jira.add_comment(name_of_the_ticket, final_string, visibility={'key': 'sd.public.comment'},
                               is_internal=True)


@app.route("/", methods=['POST', 'GET'])
def main():
    """
    Main function that listens to the incoming requests
    and handles the Webhooks from Jira, i.e receives POST
    requests and extracts the needed data from them.

    Returns:
        final_string (str) - final string that's being returned
        after all the processing performed
    """

    # If request method is GET, return 'Hello, World!' for testing purposes
    if request.method == "GET":
        return "Hello World!"

    # Extracting the data from the request
    data = request.json
    # print(data)
    # return data

    project_name = data["issue"]["fields"]["customfield_10169"]

    # Running gcpdiag command and running logs_processing_driver method
    gcpdiag_logs = execute_gcpdiag(project_name)
    final_string = logs_processing_driver(gcpdiag_logs, data)

    # Working with Jira
    name_of_the_ticket = data["issue"]["key"]
    submit_to_jira(name_of_the_ticket, final_string)

    return final_string


if __name__ == "__main__":
    app.run("127.0.0.1", port=5000, debug=True)
