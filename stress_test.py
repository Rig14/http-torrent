import atexit
import os
import signal
import subprocess
import time
import shutil

# process type / name : process obj
processes = {}

# Cleanup function to kill all subprocesses
def cleanup():
    for _, p in processes.items():
        if p.poll() is None:  # Check if process is still running
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)  # Kill entire process group
            if os.path.exists(f"/tmp/http-torrent/"):
                shutil.rmtree(f"/tmp/http-torrent/")

def clean(pr):
    if pr.poll() is None:  # Check if process is still running
        os.killpg(os.getpgid(pr.pid), signal.SIGTERM)  # Kill entire process group

def start_subprocess(name: str, command, tmp_dir = ""):
    if tmp_dir != "":
        p = subprocess.Popen(command, preexec_fn=os.setpgrp, cwd=tmp_dir)  # Create a new process group
    else:              
        p = subprocess.Popen(command, preexec_fn=os.setpgrp)  # Create a new process group
    processes[name] = p

# Register cleanup function to run at exit
atexit.register(cleanup)

client_location = "/home/gkiviv/projects/python/http-torrent"
client_file = os.path.join(client_location, "client.py")
client_torrent = os.path.join(client_location, "torrent.json")

def run_client(n, dht_enabled):
    client_name = f"client_{n}"
    tmp_dir = f"/tmp/http-torrent/{client_name}"
    os.makedirs(tmp_dir)
    if dht_enabled:
        start_subprocess(client_name, ["python3", client_file, client_torrent, "dht_enabled"], tmp_dir)
    else:
        start_subprocess(client_name, ["python3", client_file, client_torrent], tmp_dir)

def test_case_1_dht_tracker_killing():
    start_subprocess("tracker", ["python3", "tracker.py", "6969"])

    # start up both dht enabled and non dht enabled services.
    # the service, which has the initial file is non dht enabled
    SERVICE_COUNT = 40
    
    start_subprocess("client_0", ["python3", "client.py", "torrent.json"])
    
    for i in range(1, SERVICE_COUNT // 2):
        run_client(i, True)

    for i in range(SERVICE_COUNT // 2, SERVICE_COUNT):
        run_client(i, False)

    # wait for a while to let the clients start
    time.sleep(20)

    # kill the tracker
    clean(processes["tracker"])


def test_case_2_no_100_percent_killing():
    start_subprocess("tracker", ["python3", "tracker.py", "6969"])

    # start up both dht enabled and non dht enabled services.
    # the service, which has the initial file is non dht enabled
    SERVICE_COUNT = 40
    start_subprocess("client_0", ["python3", "client.py", "torrent.json"])

    for i in range(1, SERVICE_COUNT // 2):
        run_client(i, True)

    for i in range(SERVICE_COUNT // 2, SERVICE_COUNT):
        run_client(i, False)

    # wait for a while to let the clients start
    time.sleep(20)
    # kill the initial client that has the file
    clean(processes["client_0"])

def test_case_3_kill_tracker_after_peer_discovery():
    start_subprocess("tracker", ["python3", "tracker.py", "5000"])

    SERVICE_COUNT = 10
    start_subprocess("client_0", ["python3", "client.py", "torrent.json", "dht_enabled"])

    for i in range(1, SERVICE_COUNT):
        run_client(i, True)

    # wait for a while to let the clients start
    time.sleep(20)

    # kill the tracker
    clean(processes["tracker"])

if __name__ == "__main__":
    # start always up services
    start_subprocess("metric_server", ["python3", "metric_server.py"])

    # test_case_1_dht_tracker_killing()
    # test_case_2_no_100_percent_killing()
    test_case_3_kill_tracker_after_peer_discovery()

    # Keep the main process running
    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("Main app interrupted. Cleaning up...")

