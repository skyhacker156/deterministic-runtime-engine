import re, subprocess, os, shutil, json, collections
out={}
for s in range(10000,10800,2):
    d=f'/tmp/cs2/screen4/s{s}'; shutil.rmtree(d,ignore_errors=True); os.makedirs(d)
    try:
        subprocess.run(['/tmp/fdbbin/fdbserver.7.3.77','-r','simulation','--crash','--logsize','1024MB','-f','/tmp/cs2/tests/T1.toml','--buggify','off','--seed',str(s)],cwd=d,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=600)
        ini=open(d+'/simfdb/restartInfo.ini',errors='replace').read()
        out[s]=len(set(re.findall(r'^dcUID = (\S+)',ini,re.M)))
    except Exception as e:
        out[s]=-1
    shutil.rmtree(d,ignore_errors=True)
json.dump(out,open('/tmp/cs2/screen4.json','w'))
two=[s for s in sorted(out) if out[s]==2]
print('screened',len(out),'distribution',dict(sorted(collections.Counter(out.values()).items())),'two-datacenter seeds',len(two))
open('/tmp/cs2/run4_seeds.txt','w').write('\n'.join(map(str,two[:20]))+'\n')
print('selected',two[:20])
