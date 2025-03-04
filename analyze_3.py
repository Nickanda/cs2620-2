import os
import subprocess
import argparse
import time
import glob
import re
import pandas as pd
import matplotlib.pyplot as plt

def run_trial(trial_num, run_time, base_log_dir, variation_mode, internal_prob):
    """
    Run one trial of main.py with the given parameters.
    
    Assumes main.py accepts:
      --run_time <seconds>
      --log_dir <directory for logs>
      --variation_mode <e.g., 'order' or 'small'>
      --internal_prob <probability for internal event>
    """
    trial_log_dir = os.path.join(base_log_dir, f"trial_{trial_num}")
    os.makedirs(trial_log_dir, exist_ok=True)
    print(f"Starting trial {trial_num}: running simulation for {run_time} seconds.")
    
    command = [
        "python", "main.py",
        "--run_time", str(run_time),
        "--log_dir", trial_log_dir,
        "--variation_mode", str(variation_mode),
        "--internal_prob", str(internal_prob)
    ]
    start_time = time.time()
    subprocess.run(command)
    end_time = time.time()
    print(f"Trial {trial_num} completed in {end_time - start_time:.2f} seconds.")

def parse_log_line(line):
    """
    Parse a log line in the format:
       <system time> | <event type> | LC: <logical_clock> | <details>
    Returns a dictionary with parsed data.
    """
    parts = line.split('|')
    if len(parts) < 3:
        return None
    try:
        timestamp = float(parts[0].strip())
    except ValueError:
        return None
    event_type = parts[1].strip()
    lc_part = parts[2].strip()
    lc_match = re.search(r'LC:\s*(\d+)', lc_part)
    logical_clock = int(lc_match.group(1)) if lc_match else None
    details = parts[3].strip() if len(parts) > 3 else ''
    queue_len = None
    if "QueueLen:" in details:
        queue_match = re.search(r'QueueLen:\s*(\d+)', details)
        if queue_match:
            queue_len = int(queue_match.group(1))
    return {
        'timestamp': timestamp,
        'event_type': event_type,
        'logical_clock': logical_clock,
        'details': details,
        'queue_length': queue_len
    }

def load_log_file(filepath):
    """
    Read a log file and return a DataFrame of the parsed entries.
    """
    with open(filepath, 'r') as f:
        lines = f.readlines()
    records = []
    for line in lines:
        parsed = parse_log_line(line)
        if parsed:
            records.append(parsed)
    if records:
        df = pd.DataFrame(records)
        df.sort_values('timestamp', inplace=True)
        return df
    return pd.DataFrame()

def analyze_trial_logs(trial_log_dir, output_dir, trial_num):
    """
    Analyze log files for a single trial and save the plots.
    """
    log_files = glob.glob(os.path.join(trial_log_dir, "*.log"))
    if not log_files:
        print(f"No log files found in {trial_log_dir}")
        return

    combined_data = {}
    for log_file in log_files:
        df = load_log_file(log_file)
        if df.empty:
            continue
        machine_name = os.path.basename(log_file)
        combined_data[machine_name] = df

        plt.figure(figsize=(10, 6))
        plt.plot(df['timestamp'], df['logical_clock'], marker='o', linestyle='-', label=machine_name)
        plt.xlabel('System Time (s)')
        plt.ylabel('Logical Clock Value')
        plt.title(f'Logical Clock vs. System Time ({machine_name}) - Trial {trial_num}')
        plt.legend()
        plt.grid(True)
        plt.savefig(os.path.join(output_dir, f"{machine_name}_trial{trial_num}_logical_clock.png"))
        plt.close()

    if len(combined_data) > 1:
        plt.figure(figsize=(10, 6))
        for machine_name, df in combined_data.items():
            plt.plot(df['timestamp'], df['logical_clock'], marker='o', linestyle='-', label=machine_name)
        plt.xlabel('System Time (s)')
        plt.ylabel('Logical Clock Value')
        plt.title(f'Combined Logical Clock Comparison - Trial {trial_num}')
        plt.legend()
        plt.grid(True)
        plt.savefig(os.path.join(output_dir, f"combined_trial{trial_num}_logical_clock.png"))
        plt.close()

def main():
    parser = argparse.ArgumentParser(
        description="Run multiple trials of main.py and analyze the resulting logs to produce plots."
    )
    parser.add_argument("--num_trials", type=int, default=5, help="Number of trials to run.")
    parser.add_argument("--run_time", type=int, default=60, help="Duration (in seconds) for each trial.")
    parser.add_argument("--log_dir", type=str, default="logs", help="Base directory for storing log files.")
    parser.add_argument("--output_dir", type=str, default="plots", help="Directory to store the generated plots.")
    parser.add_argument("--variation_mode", type=str, default="order",
                        help="Clock variation mode: 'order' (order-of-magnitude variation) or 'small' (smaller variation).")
    parser.add_argument("--internal_prob", type=float, default=0.7, help="Probability of an internal event (0 to 1).")
    args = parser.parse_args()

    os.makedirs(args.log_dir, exist_ok=True)
    os.makedirs(args.output_dir, exist_ok=True)

    for trial in range(1, args.num_trials + 1):
        run_trial(trial, args.run_time, args.log_dir, args.variation_mode, args.internal_prob)
        trial_log_dir = os.path.join(args.log_dir, f"trial_{trial}")
        time.sleep(2)
        analyze_trial_logs(trial_log_dir, args.output_dir, trial)
    
    print("All trials completed. Analysis plots saved in", args.output_dir)

if __name__ == '__main__':
    main()
