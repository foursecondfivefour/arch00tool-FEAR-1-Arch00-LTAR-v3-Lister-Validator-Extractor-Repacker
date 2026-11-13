"""Upload a tested package from CI to the explicitly created alpha draft."""
import subprocess
import sys
import time
from pathlib import Path

release = 'v0.1.0-alpha'
package = next(Path('packages').glob('*.zip'))
for _ in range(60):
    result = subprocess.run(['gh', 'release', 'view', release], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode == 0:
        break
    time.sleep(5)
else:
    sys.exit('Alpha draft release was not found within five minutes')
subprocess.run(['gh', 'release', 'upload', release, str(package)], check=True)
