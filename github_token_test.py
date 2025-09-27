import requests
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("gt")

headers = {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github.v3+json"
}

response = requests.get("https://api.github.com/user", headers=headers)
print(response.status_code)
print(response.json())

# Windows-only: keep the window open
os.system("pause")
