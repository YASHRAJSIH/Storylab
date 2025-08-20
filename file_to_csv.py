import pandas as pd
import os

# Input parquet files
parquet_files = ["sentences_clean.parquet", "sentences_topic.parquet" , "sentences.parquet" , "sentences_time.parquet"]

# Output folder
output_dir = "outfolder_csv"
os.makedirs(output_dir, exist_ok=True)  # Create it if it doesn't exist

# Loop through and convert
for parquet_file in parquet_files:
    df = pd.read_parquet(parquet_file)
    csv_file_name = os.path.splitext(os.path.basename(parquet_file))[0] + ".csv"
    output_path = os.path.join(output_dir, csv_file_name)
    df.to_csv(output_path, index=False)
    print(f"Saved: {output_path}")
