import pandas as pd
import os

csv_base_folder = "csv"
llm_models = ["gemini", "internvl", "qwenvl"]
# Load csv files and get the common videos
def load_common_videos():
    common_videos = set()
    
    for i in range(len(llm_models)):
        model = llm_models[i]
        csv_file = os.path.join(csv_base_folder, model, f"{model}.csv")
        if os.path.exists(csv_file):
            df = pd.read_csv(csv_file)
            print(model)
            print(len(df))
            df = df.dropna(subset = ['summary'])
            print(len(df))
            if i == 0:
                common_videos = set(df['video_id'].unique())
            else:
                common_videos.intersection_update(df['video_id'].dropna().unique())
    
    return list(common_videos)

common_videos_list = load_common_videos()

with open("common_videos_list.txt", "w") as f:
    for item in common_videos_list:
        f.write(f"{item}\n")

print(f"Total common videos across all models: {len(common_videos_list)}")