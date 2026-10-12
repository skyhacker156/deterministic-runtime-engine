import sys, json, re
S=int(sys.argv[1]); B=sys.argv[2]; r={'seed':S}
ini=open(B+'/base/simfdb/restartInfo.ini',errors='replace').read()
r['n_dc']=len(set(re.findall(r'^dcUID = (\S+)',ini,re.M)))
for c in ('none','zone','dc'): r[c]=json.load(open(f'{B}/{c}/metrics.json'))
r['dc_keep_exit']=int(open(B+'/dc_keep/exit3.txt').read()); r['dc_keep_passed']=open(B+'/dc_keep/phase3.log',errors='replace').read().count('tests passed')
print(json.dumps(r))
