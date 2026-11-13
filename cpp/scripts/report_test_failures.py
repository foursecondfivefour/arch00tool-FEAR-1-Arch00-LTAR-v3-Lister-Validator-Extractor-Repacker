"""Expose CTest failures as a CI annotation, including when raw logs are unavailable."""
from pathlib import Path
p = Path('cpp/build/Testing/Temporary/LastTest.log')
if p.exists():
    text = p.read_text(encoding='utf-8', errors='replace')
    escaped = text[-50000:].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    print('::error title=CTest log::' + escaped)
