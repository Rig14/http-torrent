import atexit
import os
import signal
import subprocess
import time

# process type / name : process obj
processes = {}

# Cleanup function to kill all subprocesses
def cleanup():
    for _, p in processes.items():
        if p.poll() is None:  # Check if process is still running
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)  # Kill entire process group

def clean(pr):
    if pr.poll() is None:  # Check if process is still running
        os.killpg(os.getpgid(pr.pid), signal.SIGTERM)  # Kill entire process group

def start_subprocess(name: str, command):
    p = subprocess.Popen(command, preexec_fn=os.setpgrp)  # Create a new process group
    processes[name] = p

# Register cleanup function to run at exit
atexit.register(cleanup)

# start always up services
start_subprocess("metric_server", ["python3", "metric_server.py"])

def test_case_1_dht_tracker_killing():
    start_subprocess("tracker", ["python3", "tracker.py", "5000"])

    # start up both dht enabled and non dht enabled services.
    # the service, which has the initial file is non dht enabled
    SERVICE_COUNT = 40
    start_subprocess("client_0", ["python3", "client.py", "has_file"])

    for i in range(1, SERVICE_COUNT // 2):
        start_subprocess(f"client_{i}", ["python3", "client.py", "dht_enabled"])

    for i in range(SERVICE_COUNT // 2, SERVICE_COUNT):
        start_subprocess(f"client_{i}", ["python3", "client.py"])

    # wait for a while to let the clients start
    time.sleep(20)

    # kill the tracker
    clean(processes["tracker"])


if __name__ == "__main__":
    test_case_1_dht_tracker_killing()

    # Keep the main process running
    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("Main app interrupted. Cleaning up...")

