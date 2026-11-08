"""Compare captured final test identities with the observed pre-sprint baseline."""
from collections import Counter
from pathlib import Path
import re
import sys
from xml.etree import ElementTree as ET

EVIDENCE = Path('planning/sprints/011-baseline-and-stack/evidence')

def cases(path):
    return list(ET.parse(path).iter('testcase'))

def identity(test):
    module, name = test.get('classname'), test.get('name')
    if module == 'tests.e2e.test_console_api' and name.startswith((
        'test_a_missing_audit_read_scope_gives_403_and_a_deny_row[',
        'test_each_read_writes_an_audit_read_allow_row[',
    )):
        name = re.sub(r'(?<=/v1/decisions/)[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', '{generated_uuid}', name)
    if module == 'tests.contracts.test_object_store_contract':
        name = re.sub(r'\[minio(?=-|\])', '[seaweedfs', name)
    return module, name

baseline = cases(EVIDENCE/'baseline-pytest.xml')
unit = cases(EVIDENCE/'architect-final-unit.xml')
integration = cases(Path(sys.argv[1]))
for label, tests in [('unit', unit), ('integration/e2e', integration)]:
    failed = [t for t in tests if t.find('failure') is not None or t.find('error') is not None]
    skipped = [t for t in tests if t.find('skipped') is not None]
    print(f'{label}: {len(tests)-len(failed)-len(skipped)} passed; {len(failed)} failed/errors; {len(skipped)} skipped')
    assert not failed, [t.attrib for t in failed]
print('Normalize only the generated audit-route UUID and the ten explicit MinIO -> SeaweedFS provider parameter identities.')
old, new = Counter(map(identity, baseline)), Counter(map(identity, unit+integration))
missing, added = old-new, new-old
print('Observed baseline collected:', len(baseline))
print('Final collected:', len(unit+integration))
print('Removed baseline cases:', sum(missing.values()))
print('Added cases:', sum(added.values()))
assert len(baseline) == 1591
assert not missing, missing
assert len(unit) == 884 and len(integration) == 845
assert sum(t.find('skipped') is not None for t in unit+integration) == 10
print('Added cases by module:')
for name, count in sorted(Counter(name for (name,_),n in added.items() for _ in range(n)).items()):
    print(f'  {name}: {count}')
print('PASS: every captured baseline identity retained; provider rename explicit; original assertions separately reviewed.')
