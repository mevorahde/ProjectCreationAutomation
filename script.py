import os
import sys
import json
import requests
from github import Github
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
load_dotenv(verbose=True)
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

# Get Github Token
token = os.getenv('gt')

# ENTER THE COMPLETE PATH TO YOUR LOCATION WHERE YOU WANT TO SAVE YOUR PROJECTS
# e.g. C:/Users/<USERNAME>/Documents/Projects/
## !!!YOU MUST SEPERATE FOLDERS WITH NORMAL-SLASHES NOT BACK-SLASHES AND AT THE END PUT A SLASH LIKE IN THE EXAMPLE!!!
path = os.getenv("project_path")


def create_folder_and_repo():
    folder_name = str(sys.argv[1])
    public_private = str(sys.argv[2])
    code_ide = str(sys.argv[3])
    os.makedirs(path + folder_name)

    GITHUB_URL = "https://api.github.com"
    headers = {
        "Authorization": "token " + token,
        "Accept": "application/vnd.github.v3+json"
    }

    try:
        if public_private == "private":
            data = {"name": "{}", "private": "true".format(folder_name)}
            r = requests.post(GITHUB_URL + "/user/repos", data=json.dumps(data), headers=headers)
            r.raise_for_status()
        else:
            data = {"name": "{}", "private": "false".format(folder_name)}
            r = requests.post(GITHUB_URL + "/user/repos", data=json.dumps(data), headers=headers)
            r.raise_for_status()
    except requests.exceptions.RequestException as err:
        raise SystemExit(err)

    print("Successfully created repository {}".format(folder_name))


if __name__ == "__main__":
    create_folder_and_repo()
