import logging
import subprocess
import os
import signal
import atexit
import time

NODE_COUNT = 100

# Start subprocesses in a new process group
processes: list[subprocess.Popen] = []
def start_subprocess(command):
    p = subprocess.Popen(command, preexec_fn=os.setpgrp, stdout=subprocess.DEVNULL)  # Create a new process group
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

# wait for nodes to start up then kill half of them. don't kill master
time.sleep(40)
for i in range(1, NODE_COUNT // 2):
    os.killpg(os.getpgid(processes[i].pid), signal.SIGTERM)


# create 100 more nodes
time.sleep(30)
for port in range(50000 + NODE_COUNT + 1, 50000 + NODE_COUNT + 100):
    start_subprocess(["python", "main.py", str(port)])


# Keep the main process running
try:
    while True:
        pass
except KeyboardInterrupt:
    print("Main app interrupted. Cleaning up...")

exit(0)