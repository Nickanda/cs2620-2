#!/usr/bin/env python3
"""
run_experiments.py

This script runs experiments on the distributed system simulation by calling main.py
with different parameters. For each experimental condition, it runs the simulation 
5 times (each for one minute) and parses the generated logs to extract:
  - Average jump size in the logical clock values.
  - Drift among VMs (difference between highest and lowest final logical clock).
  - Average message queue length (observed from RECEIVE events).

It then produces descriptive bar plots summarizing these findings across conditions.

Experimental Conditions:
  1. Order variation (clock rates vary 1-6), internal event probability = 0.7.
  2. Order variation (clock rates vary 1-6), internal event probability = 0.3.
  3. Small variation (clock rates vary 1-2), internal event probability = 0.7.
  4. Small variation (clock rates vary 1-2), internal event probability = 0.3.

Usage:
    python run_experiments.py
"""

import subprocess
import time
import os
import glob
import shutil
import re
import matplotlib.pyplot as plt

# ----------------------------
# Utility Functions
# ----------------------------

def run_simulation(run_time, log_dir, variation_mode, internal_prob):
    """
    Runs the simulation (main.py) with the provided parameters.
    Assumes main.py is in the same directory.
    """
    command = [
        "python", "main.py",
        "--run_time", str(run_time),
        "--log_dir", log_dir,
        "--variation_mode", variation_mode,
        "--internal_prob", str(internal_prob)
    ]
    print(f"Running simulation: variation_mode={variation_mode}, internal_prob={internal_prob} for {run_time} sec in '{log_dir}'")
    subprocess.run(command)
    # Pause briefly to ensure logs are flushed.
    time.sleep(2)

def parse_logs(log_dir):
    """
    Parses the log files from the given directory.
    Each log line is expected to be in the format:
       <system time> | <event type> | LC: <logical_clock> | <details>
    
    Returns a dictionary mapping VM id (1,2,3) to a list of events.
    Each event is a dict with keys: 'ts', 'event', 'lc', 'queue_len' (if available, else None).
    """
    vm_logs = {}
    for vm in [1, 2, 3]:
        file_path = os.path.join(log_dir, f"vm_{vm}.log")
        events = []
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                for line in f:
                    parts = line.strip().split('|')
                    if len(parts) >= 3:
                        try:
                            ts = float(parts[0].strip())
                            event_type = parts[1].strip()
                            # Expect LC: <value>
                            lc_part = parts[2].strip()
                            lc = int(lc_part.split()[1])
                            queue_len = None
                            if len(parts) >= 4:
                                details = parts[3].strip()
                                # Look for 'QueueLen: <num>' in details.
                                match = re.search(r"QueueLen:\s*(\d+)", details)
                                if match:
                                    queue_len = int(match.group(1))
                            events.append({"ts": ts, "event": event_type, "lc": lc, "queue_len": queue_len})
                        except Exception as e:
                            print(f"Error parsing line: {line} => {e}")
        vm_logs[vm] = events
    return vm_logs

def analyze_vm_log(events):
    """
    Given a list of events for a VM (each event is a dict with key 'lc'),
    compute the jump sizes (difference between consecutive LC values).
    Returns a list of jump sizes.
    """
    jumps = []
    prev_lc = None
    for event in events:
        lc = event["lc"]
        if prev_lc is not None:
            jumps.append(lc - prev_lc)
        prev_lc = lc
    return jumps

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

# ----------------------------
# Experiment Runner
# ----------------------------

def run_trial(trial_num, run_time, variation_mode, internal_prob, base_log_dir):
    """
    Runs a single simulation trial with the specified parameters.
    Returns a tuple with:
       (avg_jump, drift, avg_queue_length)
    """
    log_dir = os.path.join(base_log_dir, f"trial_{trial_num}")
    # Remove previous log directory if it exists.
    if os.path.exists(log_dir):
        shutil.rmtree(log_dir)
    os.makedirs(log_dir, exist_ok=True)
    
    run_simulation(run_time, log_dir, variation_mode, internal_prob)
    vm_logs = parse_logs(log_dir)
    
    # For each VM, compute jump sizes.
    all_jumps = []
    final_lcs = {}
    all_queue_lengths = []
    for vm, events in vm_logs.items():
        jumps = analyze_vm_log(events)
        all_jumps.extend(jumps)
        if events:
            final_lcs[vm] = events[-1]["lc"]
        else:
            final_lcs[vm] = 0
        q_lengths = analyze_queue_lengths(events)
        all_queue_lengths.extend(q_lengths)
    
    # Drift: difference between max and min final LC across VMs.
    drift = max(final_lcs.values()) - min(final_lcs.values())
    avg_jump = sum(all_jumps)/len(all_jumps) if all_jumps else 0
    avg_queue_length = sum(all_queue_lengths)/len(all_queue_lengths) if all_queue_lengths else 0

    trial_label = f"Trial_{trial_num}"
    plot_log_progression(vm_logs, log_dir, trial_label)
    
    print(f"Trial {trial_num}: avg_jump={avg_jump:.2f}, drift={drift}, avg_queue_length={avg_queue_length:.2f}")
    return avg_jump, drift, avg_queue_length

def run_experiment_condition(condition_label, variation_mode, internal_prob, run_time=60, trials=5):
    """
    Runs multiple trials for a given experimental condition and returns
    the averaged metrics across trials.
    """
    print("\n========================================")
    print(f"Running experiment: {condition_label}")
    
    # Use a dedicated log directory per experimental condition.
    base_log_dir = condition_label.replace(" ", "_")
    if os.path.exists(base_log_dir):
        shutil.rmtree(base_log_dir)
    os.makedirs(base_log_dir, exist_ok=True)
    
    trial_results = {"avg_jump": [], "drift": [], "avg_queue_length": []}
    for trial in range(1, trials+1):
        avg_jump, drift, avg_q = run_trial(trial, run_time, variation_mode, internal_prob, base_log_dir)
        trial_results["avg_jump"].append(avg_jump)
        trial_results["drift"].append(drift)
        trial_results["avg_queue_length"].append(avg_q)
    
    # Average metrics over trials.
    avg_jump_mean = sum(trial_results["avg_jump"])/len(trial_results["avg_jump"])
    drift_mean = sum(trial_results["drift"])/len(trial_results["drift"])
    avg_q_mean = sum(trial_results["avg_queue_length"])/len(trial_results["avg_queue_length"])
    
    print(f"Condition [{condition_label}] averaged over {trials} trials:")
    print(f"  Average Jump Size: {avg_jump_mean:.2f}")
    print(f"  Drift among VMs: {drift_mean}")
    print(f"  Average Queue Length (RECEIVE events): {avg_q_mean:.2f}")
    
    return {
        "avg_jump": avg_jump_mean,
        "drift": drift_mean,
        "avg_queue_length": avg_q_mean
    }

def plot_summary(results_dict):
    """
    Creates a summary bar plot comparing the metrics across experimental conditions.
    """
    conditions = list(results_dict.keys())
    avg_jumps = [results_dict[cond]["avg_jump"] for cond in conditions]
    drifts = [results_dict[cond]["drift"] for cond in conditions]
    avg_queues = [results_dict[cond]["avg_queue_length"] for cond in conditions]
    
    x = range(len(conditions))
    
    fig, axs = plt.subplots(3, 1, figsize=(10, 12))
    
    # Plot average jump sizes.
    axs[0].bar(x, avg_jumps, color="skyblue")
    axs[0].set_xticks(x)
    axs[0].set_xticklabels(conditions, rotation=45, ha="right")
    axs[0].set_ylabel("Avg Jump Size")
    axs[0].set_title("Average Logical Clock Jump Size")
    
    # Plot drift.
    axs[1].bar(x, drifts, color="salmon")
    axs[1].set_xticks(x)
    axs[1].set_xticklabels(conditions, rotation=45, ha="right")
    axs[1].set_ylabel("Drift")
    axs[1].set_title("Drift Among Final Logical Clock Values")
    
    # Plot average queue length.
    axs[2].bar(x, avg_queues, color="lightgreen")
    axs[2].set_xticks(x)
    axs[2].set_xticklabels(conditions, rotation=45, ha="right")
    axs[2].set_ylabel("Avg Queue Length")
    axs[2].set_title("Average Message Queue Length (from RECEIVE events)")
    
    plt.tight_layout()
    summary_plot_file = "experiment_summary.png"
    plt.savefig(summary_plot_file)
    plt.close()
    print(f"Summary plot saved as: {summary_plot_file}")

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
        {"label": "Order Variation Internal Prob 0.7", "variation_mode": "order", "internal_prob": 0.5},
        {"label": "Order Variation Internal Prob 0.9", "variation_mode": "order", "internal_prob": 0.9},
        
        {"label": "Small Variation Internal Prob 0.1", "variation_mode": "small", "internal_prob": 0.1},
        {"label": "Small Variation Internal Prob 0.3", "variation_mode": "small", "internal_prob": 0.3},
        {"label": "Small Variation Internal Prob 0.5", "variation_mode": "small", "internal_prob": 0.5},
        {"label": "Small Variation Internal Prob 0.7", "variation_mode": "small", "internal_prob": 0.7},
        {"label": "Small Variation Internal Prob 0.9", "variation_mode": "small", "internal_prob": 0.9},
    
        {"label": "Medium Variation Internal Prob 0.1", "variation_mode": "small", "internal_prob": 0.1},
        {"label": "Medium Variation Internal Prob 0.3", "variation_mode": "small", "internal_prob": 0.3},
        {"label": "Medium Variation Internal Prob 0.5", "variation_mode": "small", "internal_prob": 0.5},
        {"label": "Medium Variation Internal Prob 0.7", "variation_mode": "small", "internal_prob": 0.7},
        {"label": "Medium Variation Internal Prob 0.9", "variation_mode": "small", "internal_prob": 0.9},
    
    ]
    
    # Each trial runs for 60 seconds and we perform 5 trials per condition.
    run_time = 60
    trials_per_condition = 5
    
    overall_results = {}
    
    for condition in experiment_conditions:
        res = run_experiment_condition(
            condition_label=condition["label"],
            variation_mode=condition["variation_mode"],
            internal_prob=condition["internal_prob"],
            run_time=run_time,
            trials=trials_per_condition
        )
        overall_results[condition["label"]] = res
    
    # Generate a summary plot comparing all conditions.
    plot_summary(overall_results)
    