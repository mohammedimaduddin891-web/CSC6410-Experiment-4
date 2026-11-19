#!/usr/bin/env python3
"""CSC 6410 Experiment 4: measure per-core-uplink byte deltas in a live Mininet fat-tree.

Run INSIDE the professor's fattree_ecmp.py Mininet CLI; this file does not build a
second network. Example pilot from mininet>:

py exec(open('/work/EXP4/exp4_measure.py').read(), dict(net=net, __name__='__main__', N_LIST=[16], TRIALS=1, DURATION=10, PHASE='pilot'))

Full assignment run later: N_LIST=[4,8,16,32], TRIALS=3, DURATION=20,
PHASE='baseline'. When a link is intentionally down, use PHASE='link_down'.
Review and adapt the comments, explain your approach in your report, and record
any AI assistance in the course consultation section.
"""

import csv
import datetime
import re
import subprocess
import time
from pathlib import Path

CORE_PORTS = (
    ("a00", 3, "c00"),
    ("a00", 4, "c01"),
    ("a01", 3, "c10"),
    ("a01", 4, "c11"),
)
RESULT_DIR = Path("/work/EXP4")
TX_RE = re.compile(r"(?m)^\s*tx\s+pkts=(\d+),\s*bytes=(\d+)")


def get_core_tx_bytes():
    """Read OVS OpenFlow *transmitted* port counters (not RX or total bytes)."""
    values = {}
    for sw, port, core in CORE_PORTS:
        command = ["ovs-ofctl", "-O", "OpenFlow13", "dump-ports", sw, str(port)]
        result = subprocess.run(command, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"Failed {' '.join(command)}: {result.stderr.strip()}")
        match = TX_RE.search(result.stdout)
        if match is None:
            raise RuntimeError(f"Could not parse TX counters from {sw} port {port}:\n{result.stdout}")
        values[f"{sw}-eth{port}_to_{core}"] = int(match.group(2))
    return values


def one_trial(net, n_flows, trial, seconds, phase, server_port=5001):
    """Generate n parallel 1-Mb/s UDP streams and record only *new* TX bytes."""
    src = net.get("h000")
    dst = net.get("h300")
    command = (
        f"iperf -c 10.3.0.2 -u -b 1M -P {n_flows} "
        f"-t {seconds} -p {server_port} -f m"
    )
    before = get_core_tx_bytes()
    start = time.time()
    output = src.cmd(command)
    elapsed = round(time.time() - start, 3)
    after = get_core_tx_bytes()
    differences = {name: after[name] - before[name] for name in before}
    if any(value < 0 for value in differences.values()):
        raise RuntimeError("A port counter decreased, possibly because the switch reset. Rerun the trial.")

    log_path = RESULT_DIR / f"iperf_{phase}_N{n_flows}_trial{trial}.txt"
    log_path.write_text(
        f"UTC date: {datetime.datetime.now(datetime.timezone.utc).isoformat()}\n"
        f"Source: h000 (10.0.0.2), destination: h300 (10.3.0.2)\n"
        f"Command: h000 {command}\n\n{output}",
        encoding="utf-8",
    )

    total = sum(differences.values())
    if total <= 0:
        raise RuntimeError(f"All measured core TX byte deltas are zero. Check the traffic and {log_path}.")
    biggest = max(differences.values())
    max_share = 100.0 * biggest / total
    max_mean = biggest / (total / len(CORE_PORTS))
    row = {
        "phase": phase,
        "N": n_flows,
        "trial": trial,
        "seconds_requested": seconds,
        "client_elapsed_s": elapsed,
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    for name, value in differences.items():
        row[f"{name}_bytes_before"] = before[name]
        row[f"{name}_bytes_after"] = after[name]
        row[f"{name}_delta_bytes"] = value
        row[f"{name}_share_pct"] = round(100 * value / total, 3)
    row.update({
        "total_delta_bytes": total,
        "busiest_link_share_pct": round(max_share, 3),
        "max_mean_ratio": round(max_mean, 3),
        "iperf_log": str(log_path),
    })

    print(f"\n{'='*74}", flush=True)
    print(f"{phase}: N={n_flows}, trial {trial}, requested duration={seconds}s", flush=True)
    print(f"Traffic command: h000 {command}", flush=True)
    print("Link (pod 0 -> core)       before TX B      after TX B      delta TX B    share", flush=True)
    for name, value in differences.items():
        print(f"{name:24} {before[name]:12,d} {after[name]:15,d} {value:15,d}   {100*value/total:5.1f}%", flush=True)
    print(f"TOTAL DELTA BYTES: {total:,}", flush=True)
    print(f"BUSIEST LINK SHARE: {max_share:.2f}% | MAX/MEAN: {max_mean:.3f}", flush=True)
    print(f"Iperf client elapsed: {elapsed:.3f}s; raw output saved to {log_path}", flush=True)
    sum_lines = [line.strip() for line in output.splitlines() if "[SUM]" in line]
    if sum_lines:
        print("Iperf [SUM] lines (last three):", flush=True)
        for line in sum_lines[-3:]:
            print("  " + line, flush=True)
    else:
        print("No iperf [SUM] lines detected; inspect the raw iperf file.", flush=True)
    if "ERROR" in output.upper() or "FAIL" in output.upper():
        print("WARNING: iperf output contains an error/failure string; inspect raw output.", flush=True)
    return row


def run_experiment(net, n_list, trials, seconds, phase):
    """Run the requested matrix without modifying topology or OpenFlow groups."""
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    src = net.get("h000")
    dst = net.get("h300")
    print("Experiment 4 ECMP measurement using current live fat-tree", flush=True)
    print(f"Hosts: {src.name} -> {dst.name} | N={n_list}, trials={trials}, seconds={seconds}", flush=True)
    print("Only pod-0 core-facing TX bytes are used; counters are sampled before/after each run.", flush=True)
    print("Do not run pingall or other traffic concurrently with the trials.", flush=True)
    print("Opening the UDP iperf server on h300...", flush=True)
    server = dst.popen(
        ["iperf", "-s", "-u", "-p", "5001"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    results = []
    try:
        time.sleep(1.2)
        if server.poll() is not None:
            raise RuntimeError("iperf server quit immediately. Check that iperf is installed and port 5001 is free.")
        for n in n_list:
            for trial in range(1, trials + 1):
                results.append(one_trial(net, n, trial, seconds, phase))
                # Permit late iperf replies to finish before the next counter sample.
                time.sleep(1)
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()

    out_csv = RESULT_DIR / f"ecmp_results_{phase}.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(results[0].keys()))
        writer.writeheader()
        writer.writerows(results)
    print(f"\nCompleted {len(results)} trials. CSV saved: {out_csv}", flush=True)
    print("Keep this Mininet network open for the next stage.", flush=True)


if __name__ == "__main__":
    # The Mininet CLI's 'py' command supplies 'net' to this isolated namespace.
    if "net" not in globals():
        raise SystemExit("Run within the live Mininet CLI using the command in the file header.")
    run_experiment(
        net=net,
        n_list=globals().get("N_LIST", [4, 8, 16, 32]),
        trials=int(globals().get("TRIALS", 3)),
        seconds=int(globals().get("DURATION", 20)),
        phase=str(globals().get("PHASE", "baseline")),
    )
