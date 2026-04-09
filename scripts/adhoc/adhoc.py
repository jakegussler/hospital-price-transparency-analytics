import pandas as pd


df = pd.read_json('data/vanderbilt.json')

standard_charges = df['standard_charge_information']

print(standard_charges.sample(5, random_state=42))