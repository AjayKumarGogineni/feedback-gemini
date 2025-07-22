# import pandas as pd
# import os

# LLM_MODELS = ["gemini", "internvl", "qwenvl"]

# model_idx = 0
# LLM_MODEL = LLM_MODELS[model_idx]
# csv_path_dict = {
#     "gemini": "gemini.csv",
#     "internvl": "internvl.csv",
#     "qwenvl": "qwenvl.csv"
# }
# file_name = csv_path_dict[LLM_MODEL]

# csv_file = f"csv/{LLM_MODEL}/{file_name}"

# df = pd.read_csv(csv_file)
# df_temp = df[df['video_id'] == 7372265021042101550]
# print(len(df_temp))

import requests
import re

def get_video_name_to_id_from_drive(folder_id):
    url = f"https://drive.google.com/embeddedfolderview?id={folder_id}#grid"

    response = requests.get(url)
    html = response.text
    print(f"Fetched HTML content from {url}")
    # print(html)
    # Extract file names and ids using regex
    # file_id_name_pairs = re.findall(r'data-id="(.*?)".*?title="(.*?)"', html)

    # Extract entries: ID from flip-entry and filename from flip-entry-title
    ids = re.findall(r'<div class="flip-entry" id="entry-(.*?)"', html)
    names = re.findall(r'<div class="flip-entry-title">(.*?)</div>', html)

    print(ids, names)
    names = [x.split('.')[0] for x in names]  # Remove file extensions from names

    # Match names to IDs
    video_map = dict(zip(names, ids))
    return video_map

# Example usage
FOLDER_ID = "1BRuBEvLp6bXyHQpk9gtXOUBtM57u5UOB"
video_name_to_id = get_video_name_to_id_from_drive(FOLDER_ID)

# Print the mapping
for name, file_id in video_name_to_id.items():
    print(f"{name} → {file_id}")

# Save this dictionary as a json file
with open("video_name_to_id.json", "w") as f:
    import json
    json.dump(video_name_to_id, f, indent=4)
