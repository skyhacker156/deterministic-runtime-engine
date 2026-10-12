import sys, glob, re, html, json, os
D=sys.argv[1]; restored=set(); disposed={}; first=None; moddc=0; modzone=0; nb=0
for f in glob.glob(D+'/trace*'):
    for line in open(f, errors='replace'):
        m=re.search(r'Time="([0-9.]+)"',line)
        if not m: continue
        t=float(m.group(1)); ty=re.search(r'Type="([^"]+)"',line); ty=ty.group(1) if ty else ''
        low=line.lower()
        if 'dcid="modified/' in low or 'datacenter="modified/' in low: moddc+=1
        if 'zoneid="modified/' in low: modzone+=1
        if ty=='TLogPeekLocalNoBestSet': nb+=1
        i=re.search(r' ID="([0-9a-f]+)"',line); i=i.group(1) if i else None
        if ty=='StorageServerRestoreDurableState': restored.add(i)
        if ty=='KVSRemoved': disposed.setdefault(i,t)
        if 'RecoveredConfig' in ty and 'Conf="' in line and (first is None or t<first[0]):
            first=(t, html.unescape(re.search(r'Conf="([^"]*)"',line).group(1)))
early={i for i,t in disposed.items() if t<30}
ids=re.findall(r'"id":"([^"]+)"', first[1]) if first else None
log=open(D+'/phase2.log',errors='replace').read()
print(json.dumps(dict(exit2=int(open(D+'/exit2.txt').read()), tests_passed=log.count('tests passed'), restored=len(restored),
  early_disposed_of_restored=len(early & restored), early_disposed=len(early), kvs_total=len(disposed), noBestSet=nb,
  region_ids_at_restart=ids, mod_dc=moddc, mod_zone=modzone, edit=open(D+'/edit.txt').read().strip())))
