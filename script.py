import os
import sys
import json
import requests
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

# Retrieve GitHub token and local project path
token = os.getenv('gt')
path = os.getenv("project_path")

# Fail fast if token is missing
if not token:
    print("GitHub token not found. Check your .env file.")
    os.system("pause")
    sys.exit(1)

def create_folder_and_repo():
    folder_name = sys.argv[1]
    public_private = sys.argv[2].lower()
    code_ide = sys.argv[3].lower()

    full_path = path + folder_name
    os.makedirs(full_path, exist_ok=True)

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    data = {
        "name": folder_name,
        "private": public_private == "private"
    }

    try:
        response = requests.post("https://api.github.com/user/repos", json=data, headers=headers)
        response.raise_for_status()
        print(f"Successfully created repository '{folder_name}'")
    except requests.exceptions.RequestException as err:
        print("GitHub API error:", err)
        print("Response:", response.text)

if __name__ == "__main__":
    create_folder_and_repo()