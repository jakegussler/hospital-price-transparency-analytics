import pandas as pd

PATH = 'data/620476282_johnson-city-medical-center_standardcharges.csv'

print(pd.read_csv(PATH, encoding='latin1').columns)