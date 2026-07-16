PYTHON ?= python
DATA := data/processed/retail_store_sales_cleaned.csv
RAW := data/raw/retail_store_sales.csv

.PHONY: clean validate statistics model dashboard preview test all

clean:
	$(PYTHON) src/clean_data.py --input $(RAW) --output $(DATA) --log reports/generated/cleaning_log.json

validate:
	$(PYTHON) src/validate_data.py --input $(DATA) --output reports/generated/validation_summary.json

statistics:
	$(PYTHON) src/statistical_analysis.py --input $(DATA) --output reports/generated/statistical_analysis.json

model:
	$(PYTHON) src/train_model.py --input $(DATA) --output reports/generated/leakage_safe_model.json

dashboard:
	$(PYTHON) src/build_dashboard.py --input $(DATA) --template dashboard/template.html --output dashboard/index.html

preview:
	$(PYTHON) src/create_preview.py --input $(DATA) --output assets/dashboard-preview.png

test:
	$(PYTHON) -m unittest discover -s tests -v

all: clean validate statistics model dashboard preview test
