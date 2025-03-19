# Start subprocesses in a new process group
import atexit
import os
import signal
import subprocess
import time

processes: list[subprocess.Popen] = []
def start_subprocess(command, tmp_dir = ""):
    if tmp_dir != "":
        p = subprocess.Popen(command, preexec_fn=os.setpgrp, cwd=tmp_dir)  # Create a new process group
    else:              
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
start_subprocess(["flask", "--app", "metric_server.py", "run", "--debug", "-h", "192.168.2.11", "-p", "5000"])
time.sleep(1)

print("Starting tracker")
start_subprocess(["python", "tracker.py", "6969"])

time.sleep(5)

print("Starting original")
start_subprocess(["python", "client.py", "torrent.json"])

time.sleep(10)
print("Starting leechers")
for i in range(5):
    time.sleep(3)
    tmp_dir = f"/tmp/http-torrent/{i}"
    os.makedirs(tmp_dir)
    client_location = "/home/gkiviv/projects/python/http-torrent"
    client_file = os.path.join(client_location, "client.py")
    client_torrent = os.path.join(client_location, "torrent.json")
    start_subprocess(["python", client_file, client_torrent], tmp_dir)

time.sleep(20)

for p in processes[2:3]:
    clean(p)

# Keep the main process running
try:
    while True:
        pass
except KeyboardInterrupt:
    print("Main app interrupted. Cleaning up...")
