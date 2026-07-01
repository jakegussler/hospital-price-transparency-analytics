# Downloads

The public download surface is limited to BI presentation marts. The atomic
fact, code bridge, validation tables, and source-faithful pipeline layers are not
part of this v1 public Evidence artifact.

```sql downloads
select
  public_table_name,
  row_count,
  corpus_label,
  exported_at_utc,
  source_table
from hpt.public_metadata
order by public_table_name
```

<DataTable data={downloads} />

