{% macro hpt_description_tokens(expression) -%}
    {#-
        Drift-tolerant description normalization for item-identity signatures:
        lowercase, expand the small high-value abbreviation set, strip
        punctuation, then sort the distinct tokens. Abbreviation expansion must
        run before de-punctuation because the abbreviations themselves contain
        punctuation ('w/o', 'w/'). The map is deliberately tiny (w/o, w/, &);
        each addition trades continuity against precision and should be
        profiled, not guessed. Digits are preserved: ~80% of descriptions carry
        meaningful digits (drug strengths, sizes).
    -#}
    array_to_string(
        list_sort(
            list_distinct(
                list_filter(
                    string_split(
                        regexp_replace(
                            regexp_replace(
                                regexp_replace(
                                    regexp_replace(
                                        lower(cast({{ expression }} as varchar)),
                                        '\bw/o\b', ' without ', 'g'
                                    ),
                                    '\bw/', ' with ', 'g'
                                ),
                                '&', ' and ', 'g'
                            ),
                            '[^a-z0-9]+', ' ', 'g'
                        ),
                        ' '
                    ),
                    token -> token <> ''
                )
            )
        ),
        ' '
    )
{%- endmacro %}
