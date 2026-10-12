import json
R=[json.loads(l) for l in open('/tmp/cs2/run2_rows.jsonl')]
R.sort(key=lambda r:r['seed'])
def passed(m): return m['exit2']==0 and m['tests_passed']>0
def full_del(m): return m['restored']>0 and m['early_disposed_of_restored']==m['restored']
X=[r for r in R if r['n_dc']==2 and r['none']['region_ids_at_restart']==[]]
notX=[r for r in R if r not in X]
unknown=[r['seed'] for r in R if r['none']['region_ids_at_restart'] is None]
print('seeds',len(R),'| class X',len(X),[r['seed'] for r in X],'| class unknown (no recovered-config event in control):',unknown)
print('P3 controls pass: none',sum(passed(r['none']) for r in R),'zone',sum(passed(r['zone']) for r in R),'of',len(R))
print('P1 class X: dc full deletion',sum(full_del(r['dc']) for r in X),'| dc phase 2 fails',sum(not passed(r['dc']) for r in X),'| dc_keep fails',sum(not(r['dc_keep_exit']==0 and r['dc_keep_passed']>0) for r in X),'| control full deletion none/zone',sum(full_del(r['none']) for r in X),sum(full_del(r['zone']) for r in X),'of',len(X))
print('P2 outside X: full deletion in none/zone/dc',sum(full_del(r['none']) for r in notX),sum(full_del(r['zone']) for r in notX),sum(full_del(r['dc']) for r in notX),'of',len(notX))
print('dc fail overall',sum(not passed(r['dc']) for r in R),'| dc fail outside X',sum(not passed(r['dc']) for r in notX),'| early disposals in dc outside X (max)',max(r['dc']['early_disposed'] for r in notX))
mc=[r['seed'] for r in R if not(r['dc']['mod_dc']>0 and r['none']['mod_dc']==0 and r['zone']['mod_dc']==0 and r['zone']['mod_zone']>0 and r['dc']['mod_zone']>0)]
native=[r['seed'] for r in R if r['none']['mod_zone']>0]
print('rename-not-applied failures:',mc,'| seeds where the simulator natively renamed zones in the untouched control:',native)
import collections
g=collections.defaultdict(list)
for r in R: g[r['n_dc']].append(r)
print('by datacenter count: n_dc seeds dc_fail dc_full_deletion')
for k in sorted(g): print(' ',k,len(g[k]),sum(not passed(r['dc']) for r in g[k]),sum(full_del(r['dc']) for r in g[k]))
print('\nseed n_dc regions_at_restart(control) | none zone dc dc_keep | dc restored/early-disposed | none early | zone early')
for r in R:
    print(r['seed'],r['n_dc'],r['none']['region_ids_at_restart'],'|','P' if passed(r['none']) else 'F','P' if passed(r['zone']) else 'F','P' if passed(r['dc']) else 'F','P' if (r['dc_keep_exit']==0 and r['dc_keep_passed']>0) else 'F','|',f"{r['dc']['restored']}/{r['dc']['early_disposed_of_restored']}",'|',f"{r['none']['restored']}/{r['none']['early_disposed_of_restored']}",'|',f"{r['zone']['restored']}/{r['zone']['early_disposed_of_restored']}")
