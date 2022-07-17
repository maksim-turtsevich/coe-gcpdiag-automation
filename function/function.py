from flask import Flask, request
import gunicorn
import subprocess as sp
import re

app = Flask(__name__)

# Pattern for matching the gcpdiag rules
pattern = "([a-z]){3}\/([A-Z])\w+\/[12][0-9]{3}\_\d{3}"

# Rules prefixes that are longer than standard 3
lst_of_long_prefixes = ["apigee", "bigquery", "composer", "dataproc"]


def generate_rule_with_description(raw_rule_with_description):
    rule = re.search(pattern, raw_rule_with_description).group()
    rule_prefix = rule.split("/")[0]

    final_prefix = rule_prefix
    for long_prefix in lst_of_long_prefixes:
        if rule_prefix in long_prefix:
            final_prefix = long_prefix

    final_rule = rule.replace(rule_prefix, final_prefix)
    final_rule_with_description = final_rule + ": " + raw_rule_with_description.split(":")[1]

    return final_rule_with_description


def generate_final_string(logs_divided_by_rules):
    final_string = ""
    for rule_lst in logs_divided_by_rules:
        if len(rule_lst) == 1:
            continue

        starting_rule = generate_rule_with_description(rule_lst[0])
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


def logs_processing_driver(gcpdiag_logs):
    lst_of_logs = gcpdiag_logs.splitlines()

    logs_divided_by_rules = processing(lst_of_logs)
    final_string = generate_final_string(logs_divided_by_rules)

    return final_string


def execute_gcpdiag(project_name: str):
    command = f"./gcpdiag lint --project {project_name} --hide-ok"
    logs = sp.getoutput(command)

    return logs


@app.route("/", methods=['POST'])
def main():
    data = request.json
    project_name = data["issue"]["fields"]["GCP Project ID"]
    gcpdiag_logs = execute_gcpdiag(project_name)

    final_string = logs_processing_driver(gcpdiag_logs)
    print(final_string)

    return final_string


if __name__ == "__main__":
    app.run("localhost", port=5000)
