# CSC6410 Experiment 4 - ECMP Flow Distribution

## Objective
Measure how ECMP distributes UDP flows across four core-facing links in a k=4 Mininet fat-tree.

## Environment
- Docker / Ubuntu 22.04
- Mininet 2.3.0
- Open vSwitch 2.17.12
- Userspace datapath
- iperf3 3.9 (iperf used for traffic generation)

## Experiment
- 16 hosts and 20 switches
- Four core paths
- 4, 8, 16 and 32 UDP flows
- Three 20-second trials per flow count
- Core-link failure and restoration tests

## Results
The default select groups concentrated the pilot traffic on one core link.
Explicit hashing improved distribution across the four paths.
The link-failure test revealed incomplete failover.

## Files
- exp4_measure.py: measurement script
- fattree_ecmp.py: course-provided topology starter
- results/: measured CSV data
- logs/: raw iperf output

## Acknowledgment
The fat-tree topology starter was supplied in CSC6410 Week 4 Demos. The measurement script was developed with AI assistance and evaluated using the student's own laboratory runs.
