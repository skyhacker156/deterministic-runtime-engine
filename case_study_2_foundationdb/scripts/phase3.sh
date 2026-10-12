#!/bin/bash
FDB=/tmp/fdbbin/fdbserver.7.3.63; T=/tmp/cs2/tests; S=$1; B=/tmp/cs2/conf/seed$S
for ARM in none dc; do
  D=/tmp/cs2/p3/seed$S/$ARM; rm -rf $D; mkdir -p $D; cp -a $B/$ARM/simfdb $D/; cp $B/base/simfdb/restartInfo.ini $D/simfdb/restartInfo.ini; cd $D
  timeout 300 $FDB -r simulation --restarting --crash --logsize 1024MB -f $T/T2.toml --buggify off --seed $((S+2)) > phase3.log 2>&1; E=$?
  TR=$(find . -maxdepth 1 -type f -name 'trace*')
  echo "$S,$ARM,$E,$(grep -ac 'tests passed' phase3.log),$(cat $TR | grep -ac 'Severity="40"'),$(cat $TR | grep -a 'Severity="40"' | grep -ao 'Type="[A-Za-z]*"' | sort | uniq -c | tr '\n' ' ')"
  rm -f $TR
done
