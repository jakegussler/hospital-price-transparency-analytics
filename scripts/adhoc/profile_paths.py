"""
profile_paths.py

Streams a hospital price-transparency JSON file with ijson and emits a
human-readable schema report covering:
  - every JSON path observed
  - inferred type(s)
  - occurrence count and null rate
  - cardinality (distinct non-null values seen in the sample)
  - sample values
  - numeric stats (min / max / mean) for numeric fields
  - array length stats where applicable
"""

from collections import Counter, defaultdict
import ijson
import statistics
import textwrap

PATH = "data/vanderbilt.json"

# ── collection limits ────────────────────────────────────────────────────────
MAX_SAMPLE_VALUES   = 10   # distinct sample values kept per path
MAX_EVENTS          = 1000000  # set an int to cap streaming (e.g. 500_000)

# ── ijson events that carry scalar values ────────────────────────────────────
SCALAR_EVENTS = {"null", "boolean", "integer", "double", "number", "string"}
NUMERIC_EVENTS = {"integer", "double", "number"}


def profile_paths(path: str, max_events=None) -> dict:
    """
    Stream-parse *path* and return a dict keyed by JSON path string.
    Each value is a stats dict ready for report rendering.
    """
    counts:        Counter              = Counter()          # total events per path
    null_counts:   Counter              = Counter()          # null events per path
    types:         dict[str, set]       = defaultdict(set)   # observed scalar types
    seen_values:   dict[str, set]       = defaultdict(set)   # distinct values (capped)
    sample_values: dict[str, list]      = defaultdict(list)  # ordered samples
    numerics:      dict[str, list]      = defaultdict(list)  # raw numbers for stats
    array_lengths: dict[str, list]      = defaultdict(list)  # items between start/end_array

    # track open arrays so we can measure their lengths
    array_item_count: dict[str, int]    = {}

    with open(path, "rb") as f:
        for i, (prefix, event, value) in enumerate(ijson.parse(f), start=1):
            counts[prefix] += 1

            if event == "null":
                null_counts[prefix] += 1

            elif event in SCALAR_EVENTS:
                types[prefix].add(event)
                str_value = str(value)

                if str_value not in seen_values[prefix]:
                    seen_values[prefix].add(str_value)
                    if len(sample_values[prefix]) < MAX_SAMPLE_VALUES:
                        sample_values[prefix].append(value)

                if event in NUMERIC_EVENTS:
                    numerics[prefix].append(float(value))

            elif event == "start_array":
                array_item_count[prefix] = 0

            elif event == "end_array":
                if prefix in array_item_count:
                    array_lengths[prefix].append(array_item_count.pop(prefix))

            # count items inside each open array
            for arr_prefix in list(array_item_count):
                # an item belongs to an array if its prefix starts with the array prefix
                if prefix.startswith(arr_prefix + ".") or prefix.startswith(arr_prefix + "["):
                    pass  # item events are counted below via start_map / scalar detection
            if event in ("start_map", "start_array") and prefix:
                parent = _parent(prefix)
                if parent in array_item_count and event == "start_map":
                    array_item_count[parent] += 1
                elif parent in array_item_count and event == "start_array":
                    array_item_count[parent] += 1
            if event in SCALAR_EVENTS:
                parent = _parent(prefix)
                if parent in array_item_count:
                    array_item_count[parent] += 1

            if max_events and i >= max_events:
                break

    # ── assemble per-path stats ──────────────────────────────────────────────
    stats: dict[str, dict] = {}
    for path_key in sorted(counts):
        total      = counts[path_key]
        null_n     = null_counts.get(path_key, 0)
        non_null   = total - null_n
        nums       = numerics.get(path_key, [])
        arr_lens   = array_lengths.get(path_key, [])

        numeric_stats = None
        if nums:
            numeric_stats = {
                "min":  min(nums),
                "max":  max(nums),
                "mean": statistics.mean(nums),
            }

        array_stats = None
        if arr_lens:
            array_stats = {
                "min_len":  min(arr_lens),
                "max_len":  max(arr_lens),
                "mean_len": statistics.mean(arr_lens),
            }

        stats[path_key] = {
            "count":         total,
            "null_count":    null_n,
            "non_null":      non_null,
            "null_pct":      round(null_n / total * 100, 1) if total else 0,
            "types":         sorted(types.get(path_key, [])),
            "cardinality":   len(seen_values.get(path_key, [])),
            "sample_values": sample_values.get(path_key, []),
            "numeric_stats": numeric_stats,
            "array_stats":   array_stats,
        }

    return stats


def _parent(prefix: str) -> str:
    """Return the parent path of an ijson prefix (strip last segment)."""
    if "." in prefix:
        return prefix.rsplit(".", 1)[0]
    if "[" in prefix:
        return prefix.rsplit("[", 1)[0]
    return ""


# ── rendering ────────────────────────────────────────────────────────────────

def _fmt_samples(values: list) -> str:
    parts = []
    for v in values:
        s = repr(v) if isinstance(v, str) else str(v)
        parts.append(s[:80] + "…" if len(str(v)) > 80 else s)
    return ", ".join(parts)


def print_report(stats: dict) -> None:
    HEADER_WIDTH = 100
    SEP_MAJOR = "═" * HEADER_WIDTH
    SEP_MINOR = "─" * HEADER_WIDTH

    print(SEP_MAJOR)
    print("  HOSPITAL PRICE TRANSPARENCY — JSON SCHEMA PROFILE")
    print(f"  Paths observed: {len(stats):,}")
    print(SEP_MAJOR)

    for path_key, s in stats.items():
        # skip internal ijson bookkeeping paths (empty prefix = root)
        if path_key == "":
            continue

        print(f"\n  PATH : {path_key}")
        print(SEP_MINOR)

        # occurrence
        null_flag = f"  ({s['null_pct']}% null)" if s['null_count'] else ""
        print(f"  Occurrences  : {s['count']:>12,}{null_flag}")
        if s['null_count']:
            print(f"  Non-null     : {s['non_null']:>12,}")

        # type(s)
        if s['types']:
            print(f"  Type(s)      : {', '.join(s['types'])}")

        # cardinality
        if s['cardinality']:
            card_note = f"  (≥{s['cardinality']} distinct values seen in sample)" \
                        if s['cardinality'] >= MAX_SAMPLE_VALUES else \
                        f"  ({s['cardinality']} distinct)"
            print(f"  Cardinality  :{card_note}")

        # numeric stats
        if s['numeric_stats']:
            ns = s['numeric_stats']
            print(f"  Numeric      : min={ns['min']:g}  max={ns['max']:g}  mean={ns['mean']:.4g}")

        # array stats
        if s['array_stats']:
            a = s['array_stats']
            print(f"  Array length : min={a['min_len']}  max={a['max_len']}  mean={a['mean_len']:.1f}")

        # sample values
        if s['sample_values']:
            samples_str = _fmt_samples(s['sample_values'])
            wrapped = textwrap.wrap(samples_str, width=85)
            print(f"  Samples      : {wrapped[0]}")
            for line in wrapped[1:]:
                print(f"               {line}")

    print(f"\n{SEP_MAJOR}")
    print("  END OF REPORT")
    print(SEP_MAJOR)


if __name__ == "__main__":
    print(f"Profiling {PATH} …")
    stats = profile_paths(PATH, max_events=MAX_EVENTS)
    print_report(stats)
