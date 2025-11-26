import copernicusmarine
import json
from inspect import getsource

C = copernicusmarine.CopernicusMarineCatalogue
print('class:', C)
print('attributes:', [a for a in dir(C) if not a.startswith('_')])
# try to instantiate and call methods
try:
    cat = C()
    methods = [m for m in dir(cat) if not m.startswith('_')]
    print(json.dumps({'inst_methods': methods}, indent=2))
    # try to call describe if available
    if hasattr(cat, 'describe'):
        try:
            print('describe sample:', cat.describe()[:200])
        except Exception as e:
            print('describe error:', e)
except Exception as e:
    print('instantiate error:', e)
