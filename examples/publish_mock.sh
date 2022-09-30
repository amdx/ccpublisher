#!/bin/bash

echo "Sleeping 10 seconds, pretending we're publishing"
for i in $(seq 10)
do
    echo "Step $i/10 (stdout)"
    echo "Step $i/10 (log)" >>/tmp/test.log
    sleep 1
done
echo "Done"
