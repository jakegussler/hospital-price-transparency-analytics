{% macro hpt_snapshot_grained_incremental_models() -%}
    {{ return([
        'val__charge_item_violations',
        'val__code_violations',
        'val__drug_violations',
        'val__header_violations',
        'val__metadata_child_violations',
        'val__modifier_violations',
        'val__payer_rate_violations',
        'val__standard_charge_violations',
        'val__structural_parse_violations',
        'val__all_violations',
        'val__charge_item_rejections',
        'val__code_rejections',
        'val__drug_rejections',
        'val__npi_rejections',
        'val__provision_rejections',
        'val__modifier_rejections',
        'val__modifier_payer_rejections',
        'val__payer_rate_rejections',
        'val__standard_charge_rejections',
        'slv_base__hospital_snapshots',
        'slv_base__hospital_locations',
        'slv_base__type2_npis',
        'slv_base__general_contract_provisions',
        'slv_base__csv_charge_row_items',
        'slv_base__charge_items',
        'slv_base__standard_charges',
        'slv_base__charge_item_codes',
        'slv_base__drug_information',
        'slv_base__payer_rates',
        'slv_base__modifiers',
        'slv_base__modifier_payer_info',
        'slv_base__charge_modifier_declarations',
        'slv_base__charge_modifier_members',
        'slv_base__payer_rate_modifiers',
        'slv_core__payer_rates',
        'val_stats__snapshot_summary',
        'val_stats__anomalies',
        'val_stats__value_distributions',
    ]) }}
{%- endmacro %}


{% macro hpt_resolved_snapshot_state_sql() -%}
    {%- if execute and not hpt_has_bronze_files('hospital_mrf_snapshots') -%}
        {{ exceptions.raise_compiler_error(
            "Cannot resolve current Silver snapshots because no Bronze "
            ~ "hospital_mrf_snapshots Parquet files were found. Check "
            ~ "HPT_BRONZE_ROOT."
        ) }}
    {%- endif -%}

    {#-
        Currentness is derived here, not stored. Per hospital, the snapshot with
        the most recent valid_from is current; every older snapshots valid_to is
        the valid_from of the snapshot that superseded it. Reads Bronze unscoped
        (no hpt_snapshot_filter) so the per-hospital window is always complete,
        even on snapshot-scoped runs.
    -#}
    {%- set bronze_root = env_var('HPT_BRONZE_ROOT', '../data/bronze') -%}
    with raw as (
        select
            snapshot_id,
            hospital_id,
            try_cast(valid_from as timestamp) as valid_from,
            try_cast(ingested_at as timestamp) as ingested_at
        from read_parquet(
            '{{ bronze_root }}/hospital_mrf_snapshots/**/*.parquet',
            hive_partitioning=true,
            union_by_name=true
        )
    ),

    ranked as (
        select
            snapshot_id,
            hospital_id,
            row_number() over (
                partition by hospital_id
                order by valid_from desc nulls last,
                         ingested_at desc nulls last,
                         snapshot_id desc
            ) as recency_rank,
            lead(valid_from) over (
                partition by hospital_id
                order by valid_from asc nulls first,
                         ingested_at asc nulls first,
                         snapshot_id asc
            ) as superseded_at
        from raw
    )

    select
        snapshot_id,
        hospital_id,
        (recency_rank = 1) as is_current_snapshot,
        case when recency_rank = 1 then null else superseded_at end as valid_to
    from ranked
{%- endmacro %}


{% macro hpt_current_snapshot_ids_sql() -%}
    select distinct snapshot_id
    from (
        {{ hpt_resolved_snapshot_state_sql() }}
    ) current_snapshots
    where is_current_snapshot = true
{%- endmacro %}


{% macro hpt_normalize_model_list(models) -%}
    {%- if models is none -%}
        {{ return(hpt_snapshot_grained_incremental_models()) }}
    {%- elif models is string -%}
        {%- set normalized = [] -%}
        {%- for model_name in models.split(',') -%}
            {%- set cleaned = model_name | trim -%}
            {%- if cleaned -%}
                {%- do normalized.append(cleaned) -%}
            {%- endif -%}
        {%- endfor -%}
        {{ return(normalized) }}
    {%- else -%}
        {{ return(models) }}
    {%- endif -%}
{%- endmacro %}


{% macro hpt_sync_hospital_snapshot_current_state() -%}
    {%- set target_relation = ref('slv_base__hospital_snapshots') -%}
    {%- set existing_relation = adapter.get_relation(
        database=target_relation.database,
        schema=target_relation.schema,
        identifier=target_relation.identifier
    ) -%}

    {%- if existing_relation is none -%}
        {{ log("Skipping snapshot current-state sync because slv_base__hospital_snapshots is missing.", info=true) }}
        {{ return('skipped') }}
    {%- endif -%}

    {%- set sync_sql -%}
        update {{ existing_relation }} as target
        set
            is_current_snapshot = source.is_current_snapshot,
            valid_to = source.valid_to
        from (
            {{ hpt_resolved_snapshot_state_sql() }}
        ) source
        where target.snapshot_id = source.snapshot_id
    {%- endset -%}

    {{ log("Syncing slv_base__hospital_snapshots current-state metadata from Bronze.", info=true) }}
    {%- if execute -%}
        {%- do run_query(sync_sql) -%}
    {%- endif -%}
    {{ return('synced') }}
{%- endmacro %}


{% macro hpt_prune_stale_snapshots(models=None, retention_mode=None) -%}
    {%- set resolved_mode = (
        retention_mode
        if retention_mode is not none
        else var('hpt_silver_retention_mode', env_var('HPT_SILVER_RETENTION_MODE', 'current_only'))
    ) | lower -%}

    {%- if resolved_mode not in ['current_only', 'all_snapshots'] -%}
        {{ exceptions.raise_compiler_error(
            "hpt_silver_retention_mode must be 'current_only' or "
            ~ "'all_snapshots', got '" ~ resolved_mode ~ "'."
        ) }}
    {%- endif -%}

    {%- set model_names = hpt_normalize_model_list(models) -%}
    {%- set current_snapshot_ids_sql = hpt_current_snapshot_ids_sql() -%}
    {%- set snapshot_state_sync = hpt_sync_hospital_snapshot_current_state() -%}

    {%- if resolved_mode == 'all_snapshots' -%}
        {{ log("Skipping stale snapshot prune because retention mode is all_snapshots.", info=true) }}
        {{ return({
            'status': 'skipped_prune',
            'retention_mode': resolved_mode,
            'snapshot_state_sync': snapshot_state_sync,
            'models_pruned': [],
        }) }}
    {%- endif -%}

    {%- set pruned = [] -%}
    {%- set skipped = [] -%}

    {%- for model_name in model_names -%}
        {%- set target_relation = ref(model_name) -%}
        {%- set existing_relation = adapter.get_relation(
            database=target_relation.database,
            schema=target_relation.schema,
            identifier=target_relation.identifier
        ) -%}

        {%- if existing_relation is none -%}
            {%- do skipped.append(model_name) -%}
            {{ log("Skipping stale snapshot prune for missing relation " ~ model_name ~ ".", info=true) }}
        {%- else -%}
            {%- set prune_sql -%}
                delete from {{ existing_relation }}
                where snapshot_id not in (
                    {{ current_snapshot_ids_sql }}
                )
            {%- endset -%}
            {{ log("Pruning stale snapshot rows from " ~ existing_relation ~ ".", info=true) }}
            {%- if execute -%}
                {%- do run_query(prune_sql) -%}
            {%- endif -%}
            {%- do pruned.append(model_name) -%}
        {%- endif -%}
    {%- endfor -%}

    {{ return({
        'status': 'pruned',
        'retention_mode': resolved_mode,
        'snapshot_state_sync': snapshot_state_sync,
        'models_pruned': pruned,
        'models_skipped': skipped,
    }) }}
{%- endmacro %}
