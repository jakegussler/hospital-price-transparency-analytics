import ijson
import json
from decimal import Decimal
from itertools import islice

PATH = "data/vanderbilt.json"

with open(PATH, "rb") as f:
    items = ijson.items(f, "standard_charge_information.item")

    for i, item in enumerate(islice(items, 5), start=1):
        print(f"\n{'='*100}")
        print(f"ITEM {i}")
        print(f"{'='*100}")
        print(json.dumps(item, indent=2, default=lambda o: float(o) if isinstance(o, Decimal) else TypeError(type(o)))[:15000])  # prevent insane output