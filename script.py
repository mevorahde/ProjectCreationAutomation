import os
import sys
from github import Github
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
load_dotenv(verbose=True)
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

# ENTER YOUR GITHUB USERNAME
git_username = os.getenv("username")

# ENTER YOUR GITHUB PASSWORD
git_password = os.getenv("password")

# ENTER THE COMPLETE PATH TO YOUR LOCATION WHERE YOU WANT TO SAVE YOUR PROJECTS
# e.g. C:/Users/<USERNAME>/Documents/Projects/
## !!!YOU MUST SEPERATE FOLDERS WITH NORMAL-SLASHES NOT BACK-SLASHES AND AT THE END PUT A SLASH LIKE IN THE EXAMPLE!!!
path = os.getenv("project_path")


def create_folder_and_repo():
    folder_name = str(sys.argv[1])
    public_private = str(sys.argv[2])
    code_ide = str(sys.argv[3])
    os.makedirs(path + folder_name)

    user = Github(git_username, git_password).get_user()

    if public_private == "private":
        print('PRIVATE')
        user.create_repo(folder_name, private=True)
    else:
        print('PUBLIC')
        user.create_repo(folder_name)

    print("Successfully created repository {}".format(folder_name))


if __name__ == "__main__":
    create_folder_and_repo()
