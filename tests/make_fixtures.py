from pathlib import Path
from backend.tests.test_engine import workbook
target=Path('tests/fixtures');target.mkdir(exist_ok=True)
for year in (2026,2027): (target/f'sales-{year}.xlsx').write_bytes(workbook(year))
print('Created two small synthetic workbooks for multi-year UI tests.')
