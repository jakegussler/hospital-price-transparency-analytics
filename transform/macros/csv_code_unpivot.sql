{% macro hpt_csv_code_unpivot(source_sql) -%}
    with source_rows as (
        {{ source_sql }}
    ),

    csv_rows as (
        -- CSV-wide Bronze repeats charge-level code columns once per payer row.
        -- Collapse to the charge grain before unpivoting so the value/type join
        -- cannot fan out by payer count.
        select distinct
            snapshot_id,
            row_ordinal,
            columns('^code_[0-9]+(_type)?$')
        from source_rows
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
    where {{ hpt_clean_display_text('cv.raw_code') }} is not null
        or {{ hpt_clean_display_text('ct.raw_code_type') }} is not null
{%- endmacro %}
