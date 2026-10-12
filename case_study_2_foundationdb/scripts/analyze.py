import csv, glob, re, os, collections
rows = list(csv.DictReader(open('/tmp/cs2/summary.csv')))
by = collections.defaultdict(dict)
for r in rows: by[int(r['seed'])][r['cond']] = r
def passed(r): return r['exit2']=='0' and r['tests_passed']!='0'
def early(seed, cond, t=30.0):
    n=0; first=None
    for f in glob.glob(f'/tmp/cs2/conf/seed{seed}/{cond}/trace*'):
        for line in open(f, errors='replace'):
            if 'Type="KVSRemoved"' in line:
                tm=float(re.search(r'Time="([0-9.]+)"', line).group(1))
                if tm<t: n+=1
    return n
def nss(seed):  # storage servers present at restart: StorageServer role count unknown; use distinct SS IDs that logged KVSRemoved early as numerator only
    return None
out=[]
mc_bad=[]
for s in sorted(by):
    n,z,d = by[s]['none'],by[s]['zone'],by[s]['dc']
    ok_mc = (int(d['mod_dc_events'])>0 and int(n['mod_dc_events'])==0 and int(z['mod_dc_events'])==0 and int(z['mod_zone_events'])>0 and int(d['mod_zone_events'])>0 and int(n['mod_zone_events'])==0)
    if not ok_mc: mc_bad.append(s)
    out.append(dict(seed=s, n_dc=int(n['n_dc']), mc=ok_mc, none=passed(n), zone=passed(z), dc=passed(d),
        nb=(int(n['noBestSet']),int(z['noBestSet']),int(d['noBestSet'])),
        early=(early(s,'none'),early(s,'zone'),early(s,'dc')), exit2=d['exit2'], reg=d['region_cfgs']))
import json; json.dump(out, open('/tmp/cs2/analysis.json','w'))
print('seeds',len(out),'manipulation-check failures',mc_bad)
print('controls: none pass',sum(o['none'] for o in out),'zone pass',sum(o['zone'] for o in out))
print('dc pass',sum(o['dc'] for o in out),'dc fail',sum(not o['dc'] for o in out))
print('primary outcome (dc fails, both controls pass):',sum((not o['dc']) and o['none'] and o['zone'] for o in out))
print('signature as fixed (noBestSet>0 in dc, 0 in both controls):',sum(o['nb'][2]>0 and o['nb'][0]==0 and o['nb'][1]==0 for o in out))
print('controls with noBestSet>0: none',sum(o['nb'][0]>0 for o in out),'zone',sum(o['nb'][1]>0 for o in out))
print('early(<30 simsec) KVSRemoved: seeds with >0  none',sum(o['early'][0]>0 for o in out),'zone',sum(o['early'][1]>0 for o in out),'dc',sum(o['early'][2]>0 for o in out))
print('dc exit codes',collections.Counter(o['exit2'] for o in out))
print()
print('by datacenter count:  n_dc: seeds, dc_fail, dc_early_deletion_seeds')
g=collections.defaultdict(list)
for o in out: g[o['n_dc']].append(o)
for k in sorted(g): print(' ',k,len(g[k]),sum(not o['dc'] for o in g[k]),sum(o['early'][2]>0 for o in g[k]))
print()
print('seed n_dc none zone dc | early KVSRemoved none/zone/dc')
for o in out: print(o['seed'],o['n_dc'],'P' if o['none'] else 'F','P' if o['zone'] else 'F','P' if o['dc'] else 'F','|',*o['early'])
