#!/bin/bash
FDB=/tmp/fdbbin/fdbserver.7.3.63; T=/tmp/cs2/tests; S=$1; B=/tmp/cs2/conf/seed$S
D=/tmp/cs2/p3/seed$S/dc_keep; rm -rf $D; mkdir -p $D; cp -a $B/dc/simfdb $D/; cd $D
grep -ac '^dcUID = modified/' simfdb/restartInfo.ini > mc.txt
timeout 300 $FDB -r simulation --restarting --crash --logsize 1024MB -f $T/T2.toml --buggify off --seed $((S+2)) > phase3.log 2>&1; E=$?
TR=$(find . -maxdepth 1 -type f -name 'trace*')
echo "$S,dc_keep,$E,$(grep -ac 'tests passed' phase3.log),renamed_dc_lines=$(cat mc.txt),ssInit=$(cat $TR | grep -ac 'Type="StorageServerInit\|Type="SSRestoreDurableState\|Type="RestoringStorageServer'),$(cat $TR | grep -a 'Severity="40"' | grep -ao 'Type="[A-Za-z]*"' | sort | uniq -c | tr '\n' ' ')"
rm -f $TR
