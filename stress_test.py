# Start subprocesses in a new process group
import atexit
import os
import signal
import subprocess
import time

processes: list[subprocess.Popen] = []
def start_subprocess(command):
    p = subprocess.Popen(command, preexec_fn=os.setpgrp)  # Create a new process group
    processes.append(p)

# Cleanup function to kill all subprocesses
def cleanup():
    for p in processes:
        if p.poll() is None:  # Check if process is still running
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)  # Kill entire process group

def clean(pr):
    if pr.poll() is None:  # Check if process is still running
        os.killpg(os.getpgid(pr.pid), signal.SIGTERM)  # Kill entire process group


# Register cleanup function to run at exit
atexit.register(cleanup)


start_subprocess(["python", "metric_server.py"])

time.sleep(1)

start_subprocess(["python", "tracker.py", "5000"])

time.sleep(2)

start_subprocess(["python", "client.py", "has_file"])

for i in range(30):
    time.sleep(3)
    start_subprocess(["python", "client.py"])

time.sleep(20)

for p in processes[2:10]:
    clean(p)

# Keep the main process running
try:
    while True:
        pass
except KeyboardInterrupt:
    print("Main app interrupted. Cleaning up...")
