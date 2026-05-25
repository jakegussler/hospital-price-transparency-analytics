def convert_string_to_list(string: str) -> list[str]:
    if not string:
        return []
    return [part.strip().lower() for part in string.split(",") if part.strip()]
