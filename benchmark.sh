#!/bin/bash

if [ -z "$1" ]; then
    TEST_DIR="/home/phw/Musik/Library/"
    #TEST_DIR="/media/phw/Backup/Library/"
    #TEST_DIR="/media/phw/Secure Backup/Library/"
    #TEST_DIR="/mnt/WinMusic/Library"
else
    TEST_DIR="$1"
fi

for i in 1 2 3
do
    echo "\nIteration $i ..."
    for t in 1 2 3 4 6 8
    do
  	echo "= Threads $t ..."
	export PICARD_MAX_LOAD_THREADS=$t
        sudo sysctl vm.drop_caches=3
        python tagger.py -Ps "$TEST_DIR" 2>/dev/null
    done
done
