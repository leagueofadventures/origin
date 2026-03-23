import requests
import os

url = 'https://league-of-adventures.onrender.com'
file_name = 'index'
full_path = os.path.join(os.getcwd(), file_name)
with requests.get('https://league-of-adventures.onrender.com', stream=True) as r:
    with open(full_path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)