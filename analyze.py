#!/usr/bin/env python3
"""
analyze.py

This script runs experiments on the distributed system simulation by calling main.py
with different parameters. For each experimental condition, it runs the simulation 
5 times (each for one minute) and parses the generated logs to extract:
  - Average jump time: the mean wall-clock time between consecutive logged instructions.
  - Terminating drift time: the difference (range) among VMs of [final logical clock (converted to seconds via clock rate) minus elapsed wall-clock time].
  - Average message queue length (observed from RECEIVE events).
  - Clock rate used by each VM (parsed from "ClockRate: <num>" in vm_N.log).

It then produces a summary bar plot for the aggregated metrics and prints a table
showing the average metrics plus each VM's clock rate for each trial.

This updated version uses threading to run experimental conditions in parallel.
Each condition is assigned a unique port offset (passed to main.py via the --port_offset
argument) so that the fixed ports (e.g. 10001, 10002, 10003) do not conflict between
simultaneously running simulations.

Usage:
    python analyze.py
"""

import subprocess
import time
import os
import shutil
import re
import pandas as pd 
import threading

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt

# ----------------------------
# Utility Functions
# ----------------------------

def run_simulation(run_time, log_dir, variation_mode, internal_prob, port_offset):
    """
    Runs the simulation (main.py) with the provided parameters.
    Assumes main.py is in the same directory and that it logs "ClockRate: <num>".
    The additional port_offset parameter is passed to main.py so that each concurrent
    experiment uses a different set of ports.
    """
    command = [
        "python", "main.py",
        "--run_time", str(run_time),
        "--log_dir", log_dir,
        "--variation_mode", variation_mode,
        "--internal_prob", str(internal_prob),
        "--port_offset", str(port_offset)
    ]
    print(f"Running simulation: variation_mode={variation_mode}, "
          f"internal_prob={internal_prob}, port_offset={port_offset} for {run_time} sec in '{log_dir}'")
    subprocess.run(command)
    # Pause briefly to ensure logs are flushed.
    time.sleep(2)

def parse_logs(log_dir):
    """
    Parses the log files from the given directory.
    Each log line is expected to be in the format:
       <system time> | <event type> | LC: <logical_clock> | <details>

    Additionally, if the line contains "ClockRate: <num>", we capture that as well.

    Returns:
      vm_logs: dict of {vm_id -> list of event dicts}
      vm_clock_rates: dict of {vm_id -> clock_rate_int or None}
    """
    vm_logs = {}
    vm_clock_rates = {}
    for vm in [1, 2, 3]:
        file_path = os.path.join(log_dir, f"vm_{vm}.log")
        events = []
        clock_rate = None
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                for line in f:
                    parts = line.strip().split('|')
                    if len(parts) >= 3:
                        try:
                            # Parse system time and event type
                            ts = float(parts[0].strip())
                            event_type = parts[1].strip()

                            # Parse logical clock from "LC: <value>"
                            lc_part = parts[2].strip()
                            lc = int(lc_part.split()[1])

                            # Check for "ClockRate:" in details
                            details = parts[3].strip() if len(parts) >= 4 else ""
                            match_rate = re.search(r"ClockRate:\s*(\d+)", details)
                            if match_rate:
                                clock_rate = int(match_rate.group(1))

                            # Check for "QueueLen:" in details
                            queue_len = None
                            match_queue = re.search(r"QueueLen:\s*(\d+)", details)
                            if match_queue:
                                queue_len = int(match_queue.group(1))

                            events.append({
                                "ts": ts,
                                "event": event_type,
                                "lc": lc,
                                "queue_len": queue_len
                            })
                        except Exception as e:
                            print(f"Error parsing line: {line} => {e}")
        vm_logs[vm] = events
        vm_clock_rates[vm] = clock_rate
    return vm_logs, vm_clock_rates

def plot_log_progression(vm_logs, log_dir, trial_label):
    """
    Generates a plot of the logical clock progression for each VM over system time.
    Saves the plot as '<trial_label>_logical_clock_progression.png' in the log directory.
    """
    plt.figure(figsize=(10, 6))
    for vm, events in vm_logs.items():
        times = [e["ts"] for e in events]
        lcs = [e["lc"] for e in events]
        plt.plot(times, lcs, label=f"VM {vm}")
    plt.xlabel("System Time (s)")
    plt.ylabel("Logical Clock Value")
    plt.title(f"Logical Clock Progression - {trial_label}")
    plt.legend()
    plt.grid(True)
    plot_file = os.path.join(log_dir, f"{trial_label}_logical_clock_progression.png")
    plt.savefig(plot_file)
    plt.close()
    print(f"Plot saved: {plot_file}")

def analyze_queue_lengths(events):
    """
    For a list of events (dicts), extract the queue lengths from events that have them.
    Returns a list of observed queue lengths.
    """
    q_lengths = []
    for event in events:
        if event["event"].startswith("RECEIVE") and event["queue_len"] is not None:
            q_lengths.append(event["queue_len"])
    return q_lengths

# ----------------------------
# Experiment Runner
# ----------------------------

def run_trial(trial_num, run_time, variation_mode, internal_prob, base_log_dir, port_offset):
    """
    Runs a single simulation trial with the specified parameters.
    Returns a dictionary of:
       {
         "trial": trial_num,
         "avg_jump_time": float,  # average wall-clock time between log events (in seconds)
         "drift_time_range": float,  # range (max-min) of drift time (in seconds) across VMs,
         "avg_queue_length": float,
         "vm_1_rate": int or None,
         "vm_2_rate": int or None,
         "vm_3_rate": int or None
       }

    Note:
      - For each VM, the "drift time" is computed as:
            (final logical clock / clock_rate) - (elapsed wall-clock time)
        where elapsed wall-clock time = (timestamp of last event - timestamp of first event).
      - The drift_time_range is the difference between the maximum and minimum drift times across VMs.
    """
    log_dir = os.path.join(base_log_dir, f"trial_{trial_num}")
    # Remove previous log directory if it exists.
    if os.path.exists(log_dir):
        shutil.rmtree(log_dir)
    os.makedirs(log_dir, exist_ok=True)
    
    # Run the simulation with the given port_offset.
    run_simulation(run_time, log_dir, variation_mode, internal_prob, port_offset)

    # Parse logs
    vm_logs, vm_clock_rates = parse_logs(log_dir)
    
    # Compute wall-clock jump times across all events of all VMs.
    all_jump_times = []
    for events in vm_logs.values():
        if len(events) > 1:
            jump_times = [events[i+1]["ts"] - events[i]["ts"] for i in range(len(events)-1)]
            all_jump_times.extend(jump_times)
    avg_jump_time = sum(all_jump_times)/len(all_jump_times) if all_jump_times else 0.0

    # Compute drift time for each VM.
    drift_times = []
    for vm, events in vm_logs.items():
        if events and vm_clock_rates.get(vm):
            first_ts = events[0]["ts"]
            last_ts = events[-1]["ts"]
            elapsed = last_ts - first_ts
            logical_time = events[-1]["lc"]
            # Convert logical clock to seconds using the VM's clock rate.
            expected_time = logical_time / vm_clock_rates[vm]
            drift = expected_time - elapsed
            drift_times.append(drift)
    drift_time_range = max(drift_times) - min(drift_times) if drift_times else 0.0

    # Compute average queue lengths (from RECEIVE events)
    all_queue_lengths = []
    for events in vm_logs.values():
        q_lengths = analyze_queue_lengths(events)
        all_queue_lengths.extend(q_lengths)
    avg_queue_length = sum(all_queue_lengths)/len(all_queue_lengths) if all_queue_lengths else 0.0

    # Plot logical clock progression.
    trial_label_str = f"Trial_{trial_num}"
    plot_log_progression(vm_logs, log_dir, trial_label_str)
    
    print(f"Trial {trial_num}: avg_jump_time={avg_jump_time:.2f}s, drift_time_range={drift_time_range:.2f}s, "
          f"avg_queue_length={avg_queue_length:.2f}")
    
    return {
        "trial": trial_num,
        "avg_jump_time": avg_jump_time,
        "drift_time_range": drift_time_range,
        "avg_queue_length": avg_queue_length,
        "vm_1_rate": vm_clock_rates.get(1),
        "vm_2_rate": vm_clock_rates.get(2),
        "vm_3_rate": vm_clock_rates.get(3),
    }

def run_experiment_condition(condition_label, variation_mode, internal_prob, run_time=60, trials=5, port_offset=0):
    """
    Runs multiple trials for a given experimental condition and returns
    the averaged metrics across trials, along with trial-by-trial data.
    """
    print("\n========================================")
    print(f"Running experiment: {condition_label} with port_offset={port_offset}")
    
    # Use a dedicated log directory per experimental condition.
    base_log_dir = condition_label.replace(" ", "_")
    if os.path.exists(base_log_dir):
        shutil.rmtree(base_log_dir)
    os.makedirs(base_log_dir, exist_ok=True)
    
    trial_data = []
    for trial in range(1, trials+1):
        result = run_trial(trial, run_time, variation_mode, internal_prob, base_log_dir, port_offset)
        trial_data.append(result)

    # Aggregate the new metrics.
    avg_jump_time_list = [d["avg_jump_time"] for d in trial_data]
    drift_time_range_list = [d["drift_time_range"] for d in trial_data]
    avg_queue_list = [d["avg_queue_length"] for d in trial_data]

    avg_jump_time_mean = sum(avg_jump_time_list) / len(avg_jump_time_list) if avg_jump_time_list else 0.0
    drift_time_range_mean = sum(drift_time_range_list) / len(drift_time_range_list) if drift_time_range_list else 0.0
    avg_q_mean = sum(avg_queue_list) / len(avg_queue_list) if avg_queue_list else 0.0

    print(f"Condition [{condition_label}] over {trials} trials:")
    print(f"  Average Jump Time: {avg_jump_time_mean:.2f} seconds")
    print(f"  Drift Time Range Among VMs: {drift_time_range_mean:.2f} seconds")
    print(f"  Average Queue Length: {avg_q_mean:.2f}")

    # Print a quick table of all trials (including clock rates)
    print("\nTrial Results:")
    print("Trial | VM1_Rate | VM2_Rate | VM3_Rate | AvgJumpTime(s) | DriftTimeRange(s) | AvgQueue")
    print("------|----------|----------|----------|----------------|-------------------|---------")
    for d in trial_data:
        print(f"{d['trial']:5d} | {d['vm_1_rate']:9} | {d['vm_2_rate']:9} | "
              f"{d['vm_3_rate']:9} | {d['avg_jump_time']:.2f}         | "
              f"{d['drift_time_range']:.2f}            | {d['avg_queue_length']:.2f}")

    # Return aggregated metrics
    return {
        "avg_jump_time": avg_jump_time_mean,
        "drift_time_range": drift_time_range_mean,
        "avg_queue_length": avg_q_mean
    }

def plot_summary(results_dict):
    """
    Creates a summary bar plot comparing the metrics across experimental conditions,
    sorted in increasing order of the probability (extracted from the condition label).
    """
    import re

    def get_prob(label):
        # Extracts the probability value from the label string (e.g. "Internal Prob 0.3")
        m = re.search(r'Prob\s*([0-9.]+)', label)
        return float(m.group(1)) if m else 0.0

    # Sort conditions by extracted probability.
    sorted_conditions = sorted(results_dict.keys(), key=get_prob)

    avg_jump_times = [results_dict[cond]["avg_jump_time"] for cond in sorted_conditions]
    drift_time_ranges = [results_dict[cond]["drift_time_range"] for cond in sorted_conditions]
    avg_queues = [results_dict[cond]["avg_queue_length"] for cond in sorted_conditions]
    
    x = range(len(sorted_conditions))
    
    fig, axs = plt.subplots(3, 1, figsize=(10, 12))
    
    # Plot average jump times
    axs[0].bar(x, avg_jump_times, color="skyblue")
    axs[0].set_xticks(x)
    axs[0].set_xticklabels(sorted_conditions, rotation=45, ha="right")
    axs[0].set_ylabel("Avg Jump Time (s)")
    axs[0].set_title("Average Wall-Clock Jump Time Between Events")
    
    # Plot drift time ranges
    axs[1].bar(x, drift_time_ranges, color="salmon")
    axs[1].set_xticks(x)
    axs[1].set_xticklabels(sorted_conditions, rotation=45, ha="right")
    axs[1].set_ylabel("Drift Time Range (s)")
    axs[1].set_title("Terminating Drift Time (Range Across VMs)")
    
    # Plot average queue length
    axs[2].bar(x, avg_queues, color="lightgreen")
    axs[2].set_xticks(x)
    axs[2].set_xticklabels(sorted_conditions, rotation=45, ha="right")
    axs[2].set_ylabel("Avg Queue Length")
    axs[2].set_title("Average Message Queue Length (from RECEIVE events)")
    
    plt.tight_layout()
    summary_plot_file = "experiment_summary.png"
    plt.savefig(summary_plot_file)
    plt.close()
    print(f"\nSummary plot saved as: {summary_plot_file}")

# ----------------------------
# Main
# ----------------------------

if __name__ == "__main__":
    # Define experimental conditions.
    # Each condition is a dict with: label, variation_mode, internal_prob.
    experiment_conditions = [
        {"label": "Order Variation Internal Prob 0.1", "variation_mode": "order", "internal_prob": 0.1},
        {"label": "Order Variation Internal Prob 0.3", "variation_mode": "order", "internal_prob": 0.3},
        {"label": "Order Variation Internal Prob 0.5", "variation_mode": "order", "internal_prob": 0.5},
        {"label": "Order Variation Internal Prob 0.7", "variation_mode": "order", "internal_prob": 0.7},
        {"label": "Order Variation Internal Prob 0.9", "variation_mode": "order", "internal_prob": 0.9},
        
        {"label": "Small Variation Internal Prob 0.1", "variation_mode": "small", "internal_prob": 0.1},
        {"label": "Small Variation Internal Prob 0.3", "variation_mode": "small", "internal_prob": 0.3},
        {"label": "Small Variation Internal Prob 0.5", "variation_mode": "small", "internal_prob": 0.5},
        {"label": "Small Variation Internal Prob 0.7", "variation_mode": "small", "internal_prob": 0.7},
        {"label": "Small Variation Internal Prob 0.9", "variation_mode": "small", "internal_prob": 0.9},
    
        {"label": "Medium Variation Internal Prob 0.1", "variation_mode": "medium", "internal_prob": 0.1},
        {"label": "Medium Variation Internal Prob 0.3", "variation_mode": "medium", "internal_prob": 0.3},
        {"label": "Medium Variation Internal Prob 0.5", "variation_mode": "medium", "internal_prob": 0.5},
        {"label": "Medium Variation Internal Prob 0.7", "variation_mode": "medium", "internal_prob": 0.7},
        {"label": "Medium Variation Internal Prob 0.9", "variation_mode": "medium", "internal_prob": 0.9},
    ]
    
    # Each trial runs for 60 seconds and we perform 5 trials per condition.
    run_time = 60
    trials_per_condition = 5
    
    overall_results = {}
    threads = []
    
    # Worker function to run each experimental condition.
    def worker(condition, overall_results, port_offset):
        result = run_experiment_condition(
            condition_label=condition["label"],
            variation_mode=condition["variation_mode"],
            internal_prob=condition["internal_prob"],
            run_time=run_time,
            trials=trials_per_condition,
            port_offset=port_offset
        )
        overall_results[condition["label"]] = result
    
    # Start each experimental condition in its own thread.
    for i, condition in enumerate(experiment_conditions):
        # Use a port offset that is unique per condition (e.g. i*10).
        port_offset = i * 10
        t = threading.Thread(target=worker, args=(condition, overall_results, port_offset))
        threads.append(t)
        t.start()
    
    # Wait for all conditions to complete.
    for t in threads:
        t.join()
    
    # Save overall results as a pandas DataFrame.
    overall_results_df = pd.DataFrame(overall_results)
    print("\nOverall Results DataFrame:")
    print(overall_results_df)
    overall_results_df.to_csv("overall_results.csv")
    
    # Generate a summary plot comparing all conditions.
    plot_summary(overall_results)
    print("\nAll experiments completed.")
