# Data directory

## Included files

`processed/retail_store_sales_cleaned.csv` is the cleaned analytical dataset used by the reproducible validation, statistics, SQL, dashboard, and benchmark-model workflows. The project owner confirmed that the included file is cleared for public release.

`raw/retail_store_sales.csv` is the supplied raw dataset used to reproduce cleaning. The project owner confirmed that it is cleared for public release.

The original provider URL and named license were not supplied and are therefore not guessed in this repository.

Reproduce cleaning with:

```bash
python src/clean_data.py \
  --input data/raw/retail_store_sales.csv \
  --output data/processed/retail_store_sales_cleaned.csv \
  --log reports/generated/cleaning_log.json
```

Publication notes:

- The original source is cited.
- The included files were cleared for public release by the project owner.
- The original source URL and named license remain unavailable.
- Identifier provenance is not claimed to be synthetic or anonymized because that documentation was not supplied.
