from flask import Flask, request
import gunicorn
import subprocess as sp
import re

app = Flask(__name__)


def execute_gcpdiag(project_name: str):
    # command = f"./gcpdiag lint --project {project_name} --hide-ok"
    command = f"./gcpdiag lint --project {project_name}"
    logs = sp.getoutput(command)

    with open("sample_inputs/sample_output_with_ok.txt", "w+") as file:
        file.write(logs)

    return logs


def logs_processing(gcpdiag_logs):
    lst_of_logs = gcpdiag_logs.splitlines()


@app.route("/", methods=['POST'])
def main():
    data = request.json
    project_name = data["issue"]["fields"]["GCP Project ID"]
    gcpdiag_logs = execute_gcpdiag(project_name)

    logs_processing(gcpdiag_logs)

    return "ass"


if __name__ == "__main__":
    app.run("localhost", port=5000)
