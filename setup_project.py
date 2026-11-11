"""Create local runtime files without overwriting existing preferences or seeds."""
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parent
for directory in ('data','secrets','tmp','output'):
    (ROOT/directory).mkdir(exist_ok=True)
for example,local in [('config.example.json','config.json'),('seed.empty.html','original.html')]:
    target=ROOT/local
    if not target.exists():
        shutil.copyfile(ROOT/example,target)
        print('Created '+local)
    else:print('Kept existing '+local)
print('Setup complete. No keys, applications or real jobs are bundled. Add an employer board in Preferences.')
