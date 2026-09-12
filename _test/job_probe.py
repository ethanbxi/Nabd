"""Diagnose why the kill-on-close job is not claiming the child process."""
import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nabd  # noqa: E402

k32 = ctypes.windll.kernel32

# Is *this* process already inside a job? Nested jobs need Windows 8+.
in_job = wintypes.BOOL()
k32.IsProcessInJob(k32.GetCurrentProcess(), None, ctypes.byref(in_job))
print(f"parent already in a job : {bool(in_job.value)}")

job = nabd.create_kill_on_close_job()
print(f"CreateJobObject         : {job} (err {ctypes.get_last_error()})")
if not job:
    sys.exit(1)

proc = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(120)"],
    creationflags=nabd.CREATE_NO_WINDOW,
)
print(f"child pid               : {proc.pid}")

ctypes.set_last_error(0)
ok = k32.AssignProcessToJobObject(job, int(proc._handle))
err = ctypes.get_last_error()
print(f"AssignProcessToJobObject: ok={bool(ok)} err={err}")
if err == 5:
    print("  -> ERROR_ACCESS_DENIED: handle lacks rights, or breakaway blocked")

child_in_job = wintypes.BOOL()
k32.IsProcessInJob(int(proc._handle), job, ctypes.byref(child_in_job))
print(f"child in our job        : {bool(child_in_job.value)}")

# Now drop every handle to the job and see whether the child dies.
print("\nclosing job handle...")
k32.CloseHandle(job)
time.sleep(1.5)
alive = proc.poll() is None
print(f"child still alive       : {alive}")
if alive:
    proc.kill()
    print("RESULT: kill-on-close did NOT work")
    sys.exit(1)
print("RESULT: kill-on-close works")

