# Test data

Fictional Nova Systems samples used by the seed script, tests and manual checks.

- nova_product_specification.pdf: 3-page PDF with battery, performance and warranty statements
- nova_terminology_guide.txt: plain-text terminology guide
- nova_spec_table.csv: specification table with headers
- corrupt.pdf: has a PDF header but cannot be parsed (expects processing_status=failed)
- unsupported.exe: rejected at upload (unsupported type)

Regenerate with `python -m app.scripts.make_test_data` from the backend directory.
