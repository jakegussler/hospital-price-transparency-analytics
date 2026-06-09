{% macro hpt_csv_code_unpivot(source_sql) -%}
    with csv_rows as (
        {{ source_sql }}
    ),

    code_values as (
        unpivot csv_rows
        on columns('^code_[0-9]+$')
        into
            name code_column
            value raw_code
    ),

    code_types as (
        unpivot csv_rows
        on columns('^code_[0-9]+_type$')
        into
            name code_type_column
            value raw_code_type
    )

    select
        cv.snapshot_id,
        cv.row_ordinal,
        try_cast(regexp_extract(cv.code_column, '^code_([0-9]+)$', 1) as integer) as code_ordinal,
        cv.raw_code,
        ct.raw_code_type
    from code_values cv
    left join code_types ct
        on cv.snapshot_id = ct.snapshot_id
        and cv.row_ordinal = ct.row_ordinal
        and regexp_extract(cv.code_column, '^code_([0-9]+)$', 1)
            = regexp_extract(ct.code_type_column, '^code_([0-9]+)_type$', 1)
    where {{ hpt_trimmed_text('cv.raw_code') }} is not null
        or {{ hpt_trimmed_text('ct.raw_code_type') }} is not null
{%- endmacro %}
