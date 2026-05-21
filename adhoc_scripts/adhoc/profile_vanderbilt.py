import ijson

PATH = "data/vanderbilt.json"

def inspect_first_events(path, limit=80):
    with open(path, "rb") as f:
        for i, (prefix, event, value) in enumerate(ijson.parse(f), start=1):
            print(f"{i:04d} | prefix={prefix!r:40} | event={event:12} | value={value!r}")
            if i >= limit:
                break

if __name__ == "__main__":
    inspect_first_events(PATH)