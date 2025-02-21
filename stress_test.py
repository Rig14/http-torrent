import subprocess
import os
import signal
import atexit
import time

NODE_COUNT = 200

# Start subprocesses in a new process group
processes: list[subprocess.Popen] = []
def start_subprocess(command):
    p = subprocess.Popen(command, preexec_fn=os.setpgrp)  # Create a new process group
    processes.append(p)

# Cleanup function to kill all subprocesses
def cleanup():
    for p in processes:
        if p.poll() is None:  # Check if process is still running
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)  # Kill entire process group

# Register cleanup function to run at exit
atexit.register(cleanup)

# Start processes
start_subprocess(["python", "main.py", "8000"])
print("waiting for master node to start")
time.sleep(1)

for port in range(50000, 50000 + NODE_COUNT):
    start_subprocess(["python", "main.py", str(port)])

# Keep the main process running
try:
    while True:
        pass
except KeyboardInterrupt:
    print("Main app interrupted. Cleaning up...")
