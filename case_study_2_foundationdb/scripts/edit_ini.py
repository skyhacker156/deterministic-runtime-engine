#!/usr/bin/env python3
"""Rename zone IDs and/or datacenter IDs in a FoundationDB simulation restartInfo.ini.
usage: edit_ini.py <ini> <none|zone|dc>
  none: no change;  zone: zoneId -> modified/<zoneId>;  dc: zone change plus dcUID -> modified/<dcUID>
Prints counts of edited lines so the caller can verify the edit happened."""
import sys, re
path, cond = sys.argv[1], sys.argv[2]
raw = open(path, 'rb').read()
text = raw.decode('utf-8')
nz = nd = 0
out = []
for line in text.split('\n'):
    m = re.match(r'^(zoneId|dcUID) = (.*?)(\r?)$', line)
    if m:
        key, val, cr = m.groups()
        if key == 'zoneId' and cond in ('zone', 'dc') and val:
            line = f'{key} = modified/{val}{cr}'; nz += 1
        elif key == 'dcUID' and cond == 'dc' and val:
            line = f'{key} = modified/{val}{cr}'; nd += 1
    out.append(line)
new = '\n'.join(out).encode('utf-8')
if cond != 'none':
    open(path, 'wb').write(new)
else:
    assert new == raw
print(f'zone_edits={nz} dc_edits={nd}')
