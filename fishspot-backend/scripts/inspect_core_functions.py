import copernicusmarine
import json
from inspect import getsource

print('core_functions attributes:')
print(sorted([n for n in dir(copernicusmarine.core_functions) if not n.startswith('_')]))
# try to open help for core_functions
try:
    import inspect
    print('\nsource snippet:')
    src = inspect.getsource(copernicusmarine.core_functions)
    print(src[:1000])
except Exception as e:
    print('could not get source:', e)
