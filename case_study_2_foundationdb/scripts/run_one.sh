#!/bin/bash
# usage: run_one.sh <outdir> <seed>   -> runs phase 1 once, then phase 2 under none/zone/dc from identical copies
FDB=/tmp/fdbbin/fdbserver.7.3.63; T=/tmp/cs2/tests; OUT=$1; S=$2
B=$OUT/seed$S; rm -rf $B; mkdir -p $B/base; cd $B/base
timeout 900 $FDB -r simulation --crash --logsize 1024MB -f $T/T1.toml --buggify off --seed $S > phase1.log 2>&1; E1=$?
NDC=$(grep -a '^dcUID = .' simfdb/restartInfo.ini | sort -u | wc -l)
for COND in none zone dc; do
  D=$B/$COND; mkdir -p $D; cp -a $B/base/simfdb $D/; cd $D
  ED=$(python3 /tmp/cs2/scripts/edit_ini.py simfdb/restartInfo.ini $COND)
  timeout 300 $FDB -r simulation --restarting --crash --logsize 1024MB -f $T/T2.toml --buggify off --seed $((S+1)) > phase2.log 2>&1; E2=$?
  TR=$(find . -maxdepth 1 -type f -name 'trace*')
  MOD=$(cat $TR | grep -aic 'dcid="modified/\|datacenter="modified/\|dataHall="modified/')
  MODZ=$(cat $TR | grep -aic 'zoneid="modified/')
  REG=$(grep -ac 'regions=\[' phase2.log); UR2=$(grep -ac 'usable_regions=2' phase2.log)
  NB=$(cat $TR | grep -ac 'Type="TLogPeekLocalNoBestSet"')
  KV=$(cat $TR | grep -a 'Type="KVSRemoved"' | grep -ac 'worker_removed')
  KVALL=$(cat $TR | grep -ac 'Type="KVSRemoved"')
  ST=$(cat $TR | grep -ac 'Type="StorageServerTerminated"')
  SEV40=$(cat $TR | grep -ac 'Severity="40"')
  PASS=$(grep -ac 'tests passed' phase2.log)
  echo "$S,$COND,$NDC,$E1,$E2,\"$ED\",$MOD,$MODZ,$REG,$UR2,$NB,$KV,$KVALL,$ST,$SEV40,$PASS"
done
