"""Copy only commit candidates into a new ignored directory; never copy raw archive."""
import json
import shutil
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deployment.audit import candidate_files
from production.io import atomic_json

root = Path(__file__).resolve().parents[1]
(root / 'tmp').mkdir(exist_ok=True)
destination = Path(tempfile.mkdtemp(prefix='github-clean-checkout-', dir=root / 'tmp'))
for source in candidate_files(root):
    target = destination / source.relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
atomic_json(root / 'tmp/deployment_clean_checkout.json', {'path': str(destination)})
print(str(destination))
