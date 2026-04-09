

Python grabs data and loads it into Min-IO
Python parses format: Parse(file_path, hospital_config) → yields batches of rows
JsonMrfParser handles JSON streaming and Flattening
CsvTallParser handles mapping CSV tall values
CsvWideParser handles unpivoting and mapping columns


When mapping CSV columns to tables, need to store original column names for lineage (ex. code|2 would become a row in the code table, with one column tracking that it came from code|2)

