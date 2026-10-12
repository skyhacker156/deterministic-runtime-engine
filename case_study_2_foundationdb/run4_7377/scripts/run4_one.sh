#!/bin/bash
# usage: run2_one.sh <seed> ; prints one JSON line; deletes traces afterwards
FDB=/tmp/fdbbin/fdbserver.7.3.77; T=/tmp/cs2/tests; S=$1; B=/tmp/cs2/run4/seed$S
rm -rf $B; mkdir -p $B/base; cd $B/base
timeout 900 $FDB -r simulation --crash --logsize 1024MB -f $T/T1.toml --buggify off --seed $S > phase1.log 2>&1
for COND in none zone dc; do
  D=$B/$COND; mkdir -p $D; cp -a $B/base/simfdb $D/; cd $D
  python3 /tmp/cs2/scripts/edit_ini.py simfdb/restartInfo.ini $COND > edit.txt
  timeout 300 $FDB -r simulation --restarting --crash --logsize 1024MB -f $T/T2.toml --buggify off --seed $((S+1)) > phase2.log 2>&1; echo $? > exit2.txt
  python3 /tmp/cs2/scripts/extract2.py $D > metrics.json
  rm -f trace*
done
D=$B/dc_keep; mkdir -p $D; cp -a $B/dc/simfdb $D/; cd $D
timeout 300 $FDB -r simulation --restarting --crash --logsize 1024MB -f $T/T2.toml --buggify off --seed $((S+2)) > phase3.log 2>&1; echo $? > exit3.txt
rm -f trace*
python3 /tmp/cs2/scripts/row2.py $S $B
rm -rf $B/*/simfdb
