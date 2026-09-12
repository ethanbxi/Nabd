"""
Nab'd - a minimal instant-replay buffer for Windows.

Continuously encodes the screen to a rolling ring of MPEG-TS segments on disk.
Pressing the hotkey stitches the newest segments into an .mp4 with a stream
copy, so saving a clip costs no re-encode and no CPU spike mid-game.

Desktop audio is captured via WASAPI loopback in-process (Windows exposes no
DirectShow loopback device here) and piped to ffmpeg as raw PCM.
"""

import ctypes
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

import pyaudiowpatch as pyaudio

import brand

try:
    import audioop  # C-speed gain/mix/resample; stdlib through 3.12
except ImportError:  # pragma: no cover - only on 3.13+
    audioop = None

APP_NAME = "Nabd"       # internal: mutex, folders, filenames
DISPLAY_NAME = "Nab'd"  # anything the user actually reads
APP_DIR = Path(__file__).resolve().parent

# Frozen, the code and the artwork live wherever the installer put them - which
# is Program Files, and not writable - so anything the app writes goes to
# LOCALAPPDATA instead. From source both are the project folder.
FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    ASSET_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA",
                                   Path.home() / "AppData/Local")) / APP_NAME
else:
    ASSET_DIR = DATA_DIR = APP_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)

BUFFER_DIR = DATA_DIR / "buffer"
CONFIG_PATH = DATA_DIR / "config.json"
LOG_PATH = DATA_DIR / "nabd.log"
BANNER_TRIGGER = DATA_DIR / ".banner_trigger"


def helper_command(module, *args):
    """How to start one of our own helper processes.

    Frozen there is no interpreter to call, so the exe re-invokes itself with a
    mode flag; from source it runs the script under pythonw.
    """
    if FROZEN:
        return [sys.executable, f"--{module}", *args]
    pyw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pyw) if pyw.exists() else sys.executable
    return [exe, str(APP_DIR / f"{module}.py"), *args]

RATE = 48000
CHANNELS = 2
SAMPLE_WIDTH = 2  # s16le
BYTES_PER_SEC = RATE * CHANNELS * SAMPLE_WIDTH

CREATE_NO_WINDOW = 0x08000000
# A game at full tilt will happily starve a normal-priority capture process,
# which shows up as a recording that runs below its target frame rate.
ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000

CLIP_LENGTHS = [(60, "1 minute"), (180, "3 minutes"), (300, "5 minutes")]


# --------------------------------------------------------------------------
# job object - children must not outlive us
# --------------------------------------------------------------------------

class _BASIC_LIMITS(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint64) for n in
                ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                 "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _EXTENDED_LIMITS(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BASIC_LIMITS),
                ("IoInfo", _IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JobObjectExtendedLimitInformation = 9


def create_kill_on_close_job():
    """A job whose children die when this process does, however it dies.

    Python's cleanup never runs on TerminateProcess (Task Manager, a crash), so
    without this the capture ffmpeg is orphaned and keeps encoding forever.
    """
    k32 = ctypes.windll.kernel32
    job = k32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = _EXTENDED_LIMITS()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k32.SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                       ctypes.byref(info), ctypes.sizeof(info)):
        k32.CloseHandle(job)
        return None
    return job


def log(msg):
    line = f"{datetime.now():%H:%M:%S}  {msg}"
    print(line, flush=True)
    try:
        # Keep the log from growing without bound across an always-on session.
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 1_000_000:
            tail = LOG_PATH.read_text(encoding="utf-8", errors="replace")[-200_000:]
            LOG_PATH.write_text(tail, encoding="utf-8")
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------

DEFAULTS = {
    "clip_seconds": 300,
    # alt+f9 / alt+f10 belong to NVIDIA ShadowPlay, so neither is a safe
    # default; Insert is free and one-handed.
    "hotkey": "insert",
    "open_hotkey": "ctrl+alt+n",  # bring up the settings panel
    "output_dir": "",
    "monitor": 0,
    "fps": 60,
    "draw_mouse": True,
    "encoder": "auto",     # probed per machine; see probe_encoder()
    "preset": "p5",
    "cq": 23,
    "max_bitrate": "40M",
    "capture_mic": True,
    "mic_device": "",      # "" = auto-pick
    "speaker_device": "",  # "" = follow the Windows default output
    "desktop_volume": 1.0,
    "mic_volume": 1.0,
    # Measured on this machine: audio landed ~165-190 ms behind video against a
    # flash/tone reference. Capture latency accounts for only part of that, so
    # this is a starting point rather than a constant of nature - the settings
    # panel exposes it as a slider.
    "audio_offset_ms": -150,
    "segment_seconds": 2,
    "save_delay": 3.0,   # settle time so the keypress moment is on disk
    "reset_after_clip": False,  # start a fresh buffer once a clip is saved
    "notify": True,
    "banner_delay": 0.2,  # beat before the confirmation slides in
}

# Changing any of these means the ffmpeg pipeline has to be rebuilt.
CAPTURE_KEYS = {
    "clip_seconds", "monitor", "fps", "draw_mouse", "encoder", "preset", "cq",
    "max_bitrate", "capture_mic", "mic_device", "speaker_device",
    "desktop_volume", "mic_volume", "audio_offset_ms", "segment_seconds",
}


class _GUID(ctypes.Structure):
    _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD),
                ("d3", wintypes.WORD), ("d4", ctypes.c_ubyte * 8)]


def videos_dir():
    """Where this user's Videos folder actually is.

    Not ~/Videos. OneDrive's "back up my folders" relocates the known folders
    into the OneDrive tree, and plenty of setups redirect them elsewhere
    again; on those machines ~/Videos is either missing or a leftover nobody
    looks in. Ask the shell where it really is and only guess if it refuses.
    """
    fid = _GUID(0x18989B1D, 0x99B5, 0x455B,
                (ctypes.c_ubyte * 8)(0x84, 0x1C, 0xAB, 0x7C,
                                     0x74, 0xE4, 0xDD, 0xFC))
    out = ctypes.c_wchar_p()
    try:
        hr = ctypes.windll.shell32.SHGetKnownFolderPath(
            ctypes.byref(fid), 0, None, ctypes.byref(out))
        if hr == 0 and out.value:
            path = Path(out.value)
            ctypes.windll.ole32.CoTaskMemFree(out)
            return path
    except Exception as exc:
        log(f"could not resolve Videos folder ({exc}); falling back")
    return Path.home() / "Videos"


def load_config():
    cfg = dict(DEFAULTS)
    first_run = not CONFIG_PATH.exists()
    if not first_run:
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            log(f"config unreadable ({exc}); using defaults")
    if not cfg["output_dir"]:
        cfg["output_dir"] = str(videos_dir() / APP_NAME)
    if first_run:
        # Shipped defaults are whatever suited the machine this was built on.
        # Anything the local hardware can answer for itself, let it: capture
        # resolution already follows the display, and the audio devices
        # resolve from the Windows defaults, so frame rate is the last piece.
        cfg["fps"] = default_fps(cfg["monitor"])
    return cfg


def save_config(cfg):
    body = {k: cfg[k] for k in DEFAULTS if k in cfg}
    CONFIG_PATH.write_text(json.dumps(body, indent=2), encoding="utf-8")


# In preference order. NVENC first because ddagrab can hand it D3D11 frames
# without a round trip through system memory; the rest need a download.
ENCODERS = ("h264_nvenc", "h264_amf", "h264_qsv", "libx264")
_probed_encoder = None


def probe_encoder(ffmpeg, preferred="auto"):
    """The first encoder that actually initialises on this machine.

    Being listed by `-encoders` is not enough - an NVENC build on an AMD box
    lists it and then fails at runtime - so each candidate is asked to encode a
    few frames for real.
    """
    global _probed_encoder
    if _probed_encoder:
        return _probed_encoder

    order = [] if preferred in ("", "auto", None) else [preferred]
    order += [e for e in ENCODERS if e not in order]
    for name in order:
        try:
            res = subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "color=black:s=256x144:r=30",
                 "-c:v", name, "-frames:v", "3", "-f", "null", "NUL"],
                capture_output=True, timeout=30,
                creationflags=CREATE_NO_WINDOW)
        except (subprocess.SubprocessError, OSError):
            continue
        if res.returncode == 0:
            _probed_encoder = name
            log(f"encoder: {name}")
            return name
    _probed_encoder = "libx264"
    log("no hardware encoder available; falling back to libx264")
    return _probed_encoder


def encoder_flags(name, cq, maxrate, preset):
    """Quality settings per encoder family - they share no vocabulary."""
    common = ["-maxrate", maxrate, "-bufsize", maxrate, "-bf", "0"]
    if name.endswith("nvenc"):
        # No B-frames or lookahead: both hold frames inside the encoder, which
        # costs GPU time and delays footage reaching disk.
        return ["-preset", preset, "-rc", "vbr", "-cq", str(cq), "-b:v", "0",
                "-rc-lookahead", "0", "-delay", "0"] + common
    if name.endswith("amf"):
        return ["-quality", "balanced", "-rc", "vbr_peak",
                "-qp_i", str(cq), "-qp_p", str(cq)] + common
    if name.endswith("qsv"):
        return ["-preset", "medium", "-global_quality", str(cq)] + common
    return ["-preset", "veryfast", "-crf", str(cq)] + common


def find_ffmpeg():
    # The installed copy ships alongside the app, so a build is not at the
    # mercy of whatever is or is not on PATH.
    bundled = ASSET_DIR / "ffmpeg" / "ffmpeg.exe"
    if bundled.exists():
        return str(bundled)
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    packages = Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "WinGet" / "Packages"
    for candidate in packages.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"):
        return str(candidate)
    raise RuntimeError("ffmpeg not found on PATH")


# --------------------------------------------------------------------------
# device discovery (shared with the settings UI)
# --------------------------------------------------------------------------

def list_speakers():
    """Output endpoints that expose a WASAPI loopback we can record."""
    found, seen = [], set()
    pa = None
    try:
        pa = pyaudio.PyAudio()
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])["name"]
        for dev in pa.get_loopback_device_info_generator():
            name = dev["name"].replace(" [Loopback]", "").strip()
            if name in seen:
                continue
            seen.add(name)
            found.append({"name": name, "default": name == default})
    except Exception as exc:
        log(f"could not list speakers: {exc}")
    finally:
        if pa:
            try:
                pa.terminate()
            except Exception:
                pass
    return found


def list_microphones(ffmpeg=None):
    """WASAPI capture endpoints.

    The mic is mixed in-process rather than handed to ffmpeg, so these are
    PortAudio devices rather than DirectShow names. Giving ffmpeg a second
    audio input makes amix share a thread with ddagrab and costs video frames.
    """
    found, seen = [], set()
    pa = None
    try:
        pa = pyaudio.PyAudio()
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info["hostApi"] != wasapi["index"]:
                continue
            if info["maxInputChannels"] < 1:
                continue
            name = info["name"].strip()
            if "[Loopback]" in name or name in seen:
                continue
            seen.add(name)
            found.append(name)
    except Exception as exc:
        log(f"could not list microphones: {exc}")
    finally:
        if pa:
            try:
                pa.terminate()
            except Exception:
                pass
    return found


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32)]


class _DEVMODEW(ctypes.Structure):
    """Only correct as far as dmDisplayFrequency, which is all we read."""
    _fields_ = [("dmDeviceName", wintypes.WCHAR * 32),
                ("dmSpecVersion", wintypes.WORD),
                ("dmDriverVersion", wintypes.WORD),
                ("dmSize", wintypes.WORD),
                ("dmDriverExtra", wintypes.WORD),
                ("dmFields", wintypes.DWORD),
                ("dmPositionX", wintypes.LONG),
                ("dmPositionY", wintypes.LONG),
                ("dmDisplayOrientation", wintypes.DWORD),
                ("dmDisplayFixedOutput", wintypes.DWORD),
                ("dmColor", ctypes.c_short),
                ("dmDuplex", ctypes.c_short),
                ("dmYResolution", ctypes.c_short),
                ("dmTTOption", ctypes.c_short),
                ("dmCollate", ctypes.c_short),
                ("dmFormName", wintypes.WCHAR * 32),
                ("dmLogPixels", wintypes.WORD),
                ("dmBitsPerPel", wintypes.DWORD),
                ("dmPelsWidth", wintypes.DWORD),
                ("dmPelsHeight", wintypes.DWORD),
                ("dmDisplayFlags", wintypes.DWORD),
                ("dmDisplayFrequency", wintypes.DWORD)]


ENUM_CURRENT_SETTINGS = -1
# The frame rates the settings panel offers, and the ladder first-run picks
# from. Lives here rather than in settings.py so the default and the dropdown
# cannot drift apart.
FPS_CHOICES = [30, 60, 120]


def monitor_refresh(device):
    """Current refresh rate in Hz, or 0 if Windows will not say."""
    dm = _DEVMODEW()
    dm.dmSize = ctypes.sizeof(_DEVMODEW)
    try:
        ok = ctypes.windll.user32.EnumDisplaySettingsW(
            device, ENUM_CURRENT_SETTINGS, ctypes.byref(dm))
    except Exception:
        return 0
    return int(dm.dmDisplayFrequency) if ok else 0


def default_fps(monitor=0):
    """The shipped default, lowered if the display cannot keep up with it.

    Capturing above the refresh rate only manufactures duplicate frames, so a
    60 Hz machine should start at 60 rather than inheriting whatever the
    machine this was built on happened to run at. It only ever clamps down:
    a 240 Hz panel still starts at the shipped 60, because the default is a
    judgement about file size and GPU load, not about what the screen can do.
    """
    shipped = DEFAULTS["fps"]
    mons = list_monitors()
    if not mons:
        return shipped
    index = monitor if 0 <= monitor < len(mons) else 0
    hz = monitor_refresh(mons[index]["device"])
    if not hz:
        return shipped
    # 59 Hz panels report 59, so leave a little room before stepping down.
    usable = [f for f in FPS_CHOICES if f <= hz + 2 and f <= shipped]
    return max(usable) if usable else min(FPS_CHOICES)


def list_monitors():
    """Displays in the order ddagrab's output_idx uses.

    DXGI enumerates the primary output first, then left-to-right; Windows'
    own enumeration order is arbitrary, so sort rather than trust it.
    """
    found = []

    def callback(hmon, hdc, rect, lparam):
        mi = _MONITORINFOEXW()
        mi.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if ctypes.windll.user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            r = mi.rcMonitor
            found.append({"device": mi.szDevice,
                          "width": r.right - r.left,
                          "height": r.bottom - r.top,
                          "x": r.left, "y": r.top,
                          "primary": bool(mi.dwFlags & 1)})
        return 1

    proto = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                               ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    try:
        ctypes.windll.user32.EnumDisplayMonitors(None, None, proto(callback), 0)
    except Exception as exc:
        log(f"could not list monitors: {exc}")
    found.sort(key=lambda m: (not m["primary"], m["x"]))
    return found


def recent_clips(output_dir, limit=3):
    """Newest clips first, for the settings panel's recent strip."""
    try:
        files = [p for p in Path(output_dir).glob("*.mp4") if p.is_file()]
    except OSError:
        return []
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def clip_thumbnail(clip, dest, width=150, ffmpeg=None):
    """One frame from a clip, for the recent strip.

    Seeks a little way in: the first frame of a replay buffer is often a
    loading screen or a menu.
    """
    ffmpeg = ffmpeg or find_ffmpeg()
    res = subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-ss", "2", "-i", str(clip), "-frames:v", "1",
         "-vf", f"scale={width}:-2", str(dest)],
        capture_output=True, timeout=30, creationflags=CREATE_NO_WINDOW)
    if res.returncode != 0 or not Path(dest).exists():
        # Shorter than the seek; fall back to the very first frame.
        subprocess.run(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
             "-i", str(clip), "-frames:v", "1",
             "-vf", f"scale={width}:-2", str(dest)],
            capture_output=True, timeout=30, creationflags=CREATE_NO_WINDOW)
    return Path(dest).exists()


def clip_summary(clip):
    """'5m 00s . 1.1 GB' for the caption under a thumbnail."""
    try:
        size = clip.stat().st_size
    except OSError:
        return ""
    mb = size / (1024 * 1024)
    return f"{mb/1024:.1f} GB" if mb >= 1024 else f"{mb:,.0f} MB"


def grab_preview(monitor_idx, dest, ffmpeg=None):
    """Single frame from one display, so the UI can prove which is which."""
    ffmpeg = ffmpeg or find_ffmpeg()
    res = subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-init_hw_device", "d3d11va",
         "-filter_complex", f"ddagrab=output_idx={monitor_idx}:framerate=5,"
                            f"hwdownload,format=bgra,scale=960:-1",
         "-frames:v", "1", str(dest)],
        capture_output=True, text=True, timeout=30,
        creationflags=CREATE_NO_WINDOW,
    )
    return res.returncode == 0 and Path(dest).exists()


# --------------------------------------------------------------------------
# desktop audio -> ffmpeg stdin
# --------------------------------------------------------------------------

def _resolve_loopback(speaker):
    """Locate the loopback endpoint for the configured speakers."""
    def resolve(pa):
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        default = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])["name"]
        loopbacks = list(pa.get_loopback_device_info_generator())
        for dev in loopbacks:
            if (speaker or default) in dev["name"]:
                return dev, dev["name"].replace(" [Loopback]", "").strip()
        # A pinned device can be unplugged; following the default beats
        # silently recording nothing.
        if speaker:
            log(f"speakers {speaker!r} not found; using default {default!r}")
        for dev in loopbacks:
            if default in dev["name"]:
                return dev, dev["name"].replace(" [Loopback]", "").strip()
        raise RuntimeError("no WASAPI loopback endpoint available")
    return resolve


def _resolve_mic(name):
    def resolve(pa):
        wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        candidates = []
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if (info["hostApi"] == wasapi["index"]
                    and info["maxInputChannels"] >= 1
                    and "[Loopback]" not in info["name"]):
                candidates.append(info)
        for info in candidates:
            if name and name in info["name"]:
                return info, info["name"]
        if name:
            log(f"microphone {name!r} not found; using the default input")
        idx = wasapi.get("defaultInputDevice", -1)
        if idx is not None and idx >= 0:
            info = pa.get_device_info_by_index(idx)
            if info["maxInputChannels"] >= 1:
                return info, info["name"]
        if candidates:
            return candidates[0], candidates[0]["name"]
        raise RuntimeError("no WASAPI capture endpoint available")
    return resolve


class _InputTrack:
    """One WASAPI capture endpoint, normalised to 48kHz stereo s16le.

    Runs in callback mode so no thread is parked inside a blocking read - that
    is what previously made a dead endpoint unrecoverable, since nothing was
    left to notice it had stopped.
    """

    # Measured on this machine: a 1024-frame buffer reports 42.7 ms of input
    # latency, 256 frames reports 22.0 ms. Every millisecond here lands
    # directly on how late the audio is against the video.
    CHUNK = 256

    def __init__(self, label, resolve, optional=False):
        self.label = label
        self.resolve = resolve
        self.optional = optional
        self.chunks = queue.Queue(maxsize=64)
        self.last_data = 0.0
        self.device_name = None
        self.live = False
        self._rate = RATE
        self._channels = CHANNELS
        self._ratecv = None

    def open(self, pa):
        dev, name = self.resolve(pa)
        self._rate = int(dev["defaultSampleRate"])
        self._channels = max(1, min(int(dev["maxInputChannels"]), 2))
        self._ratecv = None
        stream = pa.open(format=pyaudio.paInt16, channels=self._channels,
                         rate=self._rate, input=True,
                         input_device_index=dev["index"],
                         frames_per_buffer=self.CHUNK,
                         stream_callback=self._on_audio)
        if name != self.device_name:
            log(f"{self.label}: {name} "
                f"({self._rate} Hz, {self._channels} ch)")
        self.device_name = name
        self.last_data = time.perf_counter()
        self.live = True
        return stream

    def _normalise(self, data):
        """Whatever the device hands us -> 48kHz stereo."""
        if audioop is None:
            return data
        if self._channels == 1:
            data = audioop.tostereo(data, SAMPLE_WIDTH, 1, 1)
        if self._rate != RATE:
            data, self._ratecv = audioop.ratecv(
                data, SAMPLE_WIDTH, CHANNELS, self._rate, RATE, self._ratecv)
        return data

    def _on_audio(self, in_data, frame_count, time_info, status):
        """PortAudio callback thread - must return promptly."""
        self.last_data = time.perf_counter()
        try:
            data = self._normalise(in_data)
        except Exception:
            data = in_data
        try:
            self.chunks.put_nowait(data)
        except queue.Full:
            # Device outrunning wall clock; drop oldest to stay live.
            try:
                self.chunks.get_nowait()
                self.chunks.put_nowait(data)
            except (queue.Empty, queue.Full):
                pass
        return (None, pyaudio.paContinue)


class AudioMixer:
    """Feeds ffmpeg a single gap-free 48kHz stereo PCM stream.

    Desktop audio and the microphone are combined here rather than by ffmpeg's
    amix. ddagrab shares a filter_complex with the audio filters and ffmpeg
    services a filtergraph from one thread, so a second audio input starves the
    video source - measured at roughly a third of the target frame rate.
    """

    # A working endpoint delivers buffers continuously, even through silence.
    # Going quiet for longer than this means the endpoint died rather than that
    # nothing is playing - a sleeping wireless headset, or the user switching
    # their default output out from under us.
    STALL_SECONDS = 2.0
    REBUILD_GRACE = 5.0
    MAX_BACKOFF = 30.0
    RETRY_MISSING = 30.0
    # Keep at most this much captured-but-unsent audio; beyond it the queue is
    # pure latency rather than useful buffering.
    MAX_BACKLOG = int(0.02 * BYTES_PER_SEC)  # 20 ms

    def __init__(self, speaker="", mic="", desktop_gain=1.0, mic_gain=1.0,
                 offset_ms=0):
        self._stop = threading.Event()
        self.desktop_gain = float(desktop_gain)
        self.mic_gain = float(mic_gain)
        # Negative pulls audio earlier. Applied here rather than with ffmpeg's
        # -itsoffset because aresample's first_pts=0 re-anchors the stream and
        # throws an input timestamp shift away.
        self.offset = float(offset_ms) / 1000.0
        self.desktop = _InputTrack("desktop audio", _resolve_loopback(speaker))
        self.mic = (_InputTrack("microphone", _resolve_mic(mic), optional=True)
                    if mic is not None else None)
        self._stdin = None
        self._written = 0
        self._padded = 0
        self._reopens = 0
        self._dropped = 0
        self._leftover = {"desktop": b"", "mic": b""}

    def _tracks(self):
        return [self.desktop] + ([self.mic] if self.mic else [])

    def start(self, stdin):
        self._stdin = stdin
        self._stop.clear()
        self._written = 0
        self._padded = 0
        self._reopens = 0
        self._dropped = 0
        self._leftover = {"desktop": b"", "mic": b""}
        for track in self._tracks():
            track.last_data = time.perf_counter()
        threading.Thread(target=self._supervisor, daemon=True).start()
        threading.Thread(target=self._pacer, daemon=True).start()

    def stop(self):
        self._stop.set()

    @property
    def padded_seconds(self):
        return self._padded / BYTES_PER_SEC

    @property
    def reopens(self):
        return self._reopens

    @property
    def backlog_seconds(self):
        """Audio captured but not yet handed to ffmpeg.

        The pacer drains at wall-clock speed, so anything sitting here is
        latency that never gets made up - it shifts every later sample.
        """
        pending = len(self._leftover["desktop"])
        pending += sum(len(c) for c in list(self.desktop.chunks.queue))
        return pending / BYTES_PER_SEC

    def _supervisor(self):
        """Own every capture stream, and rebuild them together when one dies.

        All tracks share a single PyAudio instance on purpose: PortAudio's
        global initialise/terminate is not safe to run concurrently from two
        threads, and doing so crashes the process with an access violation.
        """
        misses = 0
        while not self._stop.is_set():
            pa, streams = None, []
            got_audio = False
            try:
                pa = pyaudio.PyAudio()
                for track in self._tracks():
                    try:
                        streams.append(track.open(pa))
                    except Exception as exc:
                        track.live = False
                        if not track.optional:
                            raise
                        log(f"{track.label} unavailable ({exc}); "
                            f"continuing without it")

                opened_at = time.perf_counter()
                grace = min(self.REBUILD_GRACE * (2 ** misses), self.MAX_BACKOFF)
                while not self._stop.is_set():
                    time.sleep(0.25)
                    now = time.perf_counter()
                    stalled = None
                    for track in self._tracks():
                        if not track.live:
                            continue
                        if now - track.last_data < self.STALL_SECONDS:
                            got_audio = True
                        elif now - opened_at > grace:
                            stalled = track
                    if stalled:
                        self._reopens += 1
                        log(f"{stalled.label} stalled; rebuilding audio")
                        break
                    # Give a device that was missing at startup another chance.
                    if (any(not t.live for t in self._tracks())
                            and now - opened_at > self.RETRY_MISSING):
                        break
                misses = 0 if got_audio else misses + 1
            except Exception as exc:
                misses += 1
                if not self._stop.is_set() and misses == 1:
                    log(f"audio unavailable ({exc}); retrying")
                time.sleep(min(1.0 * misses, self.MAX_BACKOFF))
            finally:
                for stream in streams:
                    try:
                        stream.close()
                    except Exception:
                        pass
                for track in self._tracks():
                    track.live = False
                if pa:
                    try:
                        pa.terminate()
                    except Exception:
                        pass

    def _take(self, stream, key, need):
        """Exactly `need` bytes from one stream, padding silence if short."""
        buf = bytearray(self._leftover[key])
        self._leftover[key] = b""
        while True:
            try:
                buf += stream.chunks.get_nowait()
            except queue.Empty:
                break

        short = 0
        if len(buf) < need:
            short = need - len(buf)
            buf += b"\x00" * short

        # Anything held back is latency the pacer never makes up, because it
        # drains at wall-clock speed. Drop the oldest excess instead of
        # carrying it forward and delaying everything after it.
        ceiling = need + self.MAX_BACKLOG
        if len(buf) > ceiling:
            self._dropped += len(buf) - ceiling
            del buf[:len(buf) - ceiling]

        out = bytes(buf[:need])
        self._leftover[key] = bytes(buf[need:])
        return out, short

    def _mix(self, desktop, mic):
        if audioop is None:
            return desktop
        out = desktop
        if self.desktop_gain != 1.0:
            out = audioop.mul(out, SAMPLE_WIDTH, self.desktop_gain)
        if mic is not None:
            if self.mic_gain != 1.0:
                mic = audioop.mul(mic, SAMPLE_WIDTH, self.mic_gain)
            out = audioop.add(out, mic, SAMPLE_WIDTH)  # saturating
        return out

    def _pacer(self):
        """Write exactly wall-clock worth of samples, padding any shortfall.

        Raw PCM carries no timestamps, so ffmpeg infers them from sample count.
        Under-delivering once would slide audio permanently ahead of video, so a
        gap is filled with silence rather than skipped.
        """
        # Shifting the clock forward makes the pacer emit that much less
        # leading silence, so every captured sample lands earlier on the
        # timeline by exactly that amount.
        start = time.perf_counter() - self.offset
        while not self._stop.is_set():
            time.sleep(0.005)
            elapsed = time.perf_counter() - start
            target = int(elapsed * RATE) * CHANNELS * SAMPLE_WIDTH
            if target < 0:
                continue
            need = target - self._written
            if need <= 0:
                continue

            desktop, short = self._take(self.desktop, "desktop", need)
            self._padded += short
            mic = None
            if self.mic:
                # The mic is free to drift; the desktop stream is the clock.
                mic, _ = self._take(self.mic, "mic", need)

            try:
                self._stdin.write(self._mix(desktop, mic))
                self._written += need
            except (OSError, ValueError):
                return  # ffmpeg gone; supervisor will restart us


# Older name, kept so existing tests and scripts continue to work.
DesktopAudioPump = AudioMixer


# --------------------------------------------------------------------------
# capture process
# --------------------------------------------------------------------------

class Recorder:
    def __init__(self, cfg, ffmpeg):
        self.cfg = cfg
        self.ffmpeg = ffmpeg
        self.proc = None
        self.audio = None
        self.started_at = 0.0
        self.session = 0
        self.health = {}            # live fps / dup / drop from -progress
        self.on_trouble = None      # called when capture keeps losing the display
        self._restarts = []         # timestamps, for restart-storm detection
        self._warned = False
        self._last_access_lost = 0.0
        self._last_frozen_warn = 0.0
        self._lock = threading.Lock()
        self._supervise = threading.Event()
        self._job = create_kill_on_close_job()

    # -- ffmpeg command -----------------------------------------------------

    def _build_cmd(self):
        c = self.cfg
        seg = c["segment_seconds"]
        gop = max(1, int(c["fps"] * seg))

        # -progress gives clean key=value telemetry on stdout, which is how
        # capture health (real fps vs duplicated frames) is measured.
        cmd = [self.ffmpeg, "-hide_banner", "-loglevel", "warning", "-y",
               "-progress", "pipe:1", "-stats_period", "5",
               "-init_hw_device", "d3d11va"]

        # Exactly one audio input: desktop and mic are already mixed upstream.
        # A second input would put amix on the same filtergraph thread as
        # ddagrab and cost most of the video frame rate. A/V trim is applied by
        # the mixer's pacer, not here.
        cmd += ["-f", "s16le", "-ar", str(RATE), "-ac", str(CHANNELS), "-i", "pipe:0"]

        encoder = probe_encoder(self.ffmpeg, c["encoder"])
        ddagrab = (f"ddagrab=output_idx={c['monitor']}"
                   f":framerate={c['fps']}"
                   f":draw_mouse={1 if c['draw_mouse'] else 0}")
        # Only NVENC takes ddagrab's D3D11 frames directly; everything else
        # needs them pulled back into system memory first.
        if not encoder.endswith("nvenc"):
            ddagrab += ",hwdownload,format=bgra"

        chains = [f"{ddagrab}[v]",
                  "[0:a]aresample=async=1:first_pts=0,alimiter=limit=0.97[a]"]
        cmd += ["-filter_complex", ";".join(chains), "-map", "[v]", "-map", "[a]"]

        cmd += ["-c:v", encoder]
        cmd += encoder_flags(encoder, c["cq"], c["max_bitrate"], c["preset"])
        cmd += ["-g", str(gop),
                "-force_key_frames", f"expr:gte(t,n_forced*{seg})",
                "-c:a", "aac", "-b:a", "192k", "-ar", str(RATE), "-ac", str(CHANNELS)]

        # Each ffmpeg session writes under its own prefix. Segment numbering
        # restarts at zero every session, so without this a restart would
        # overwrite the buffer it is supposed to be extending. Zero padding
        # keeps plain filename sort in chronological order.
        # -flush_packets writes each packet straight through instead of sitting
        # in the muxer's buffer. Without it the newest seconds are still in
        # memory when you hit the hotkey, so a clip ends before the keypress.
        cmd += ["-f", "segment", "-segment_time", str(seg),
                "-segment_format", "mpegts", "-reset_timestamps", "1",
                "-segment_wrap", "0", "-flush_packets", "1",
                str(BUFFER_DIR / f"seg_{self.session:04d}_%06d.ts")]
        return cmd

    # -- lifecycle ----------------------------------------------------------

    def clear_buffer(self):
        """Drop everything on disk. Only correct at app startup - a restart
        mid-session must keep the footage it already has."""
        BUFFER_DIR.mkdir(parents=True, exist_ok=True)
        for old in BUFFER_DIR.glob("seg_*.ts"):
            try:
                old.unlink()
            except OSError:
                pass
        # Nothing can be mid-save at startup, so any staging copy is debris.
        for stale in BUFFER_DIR.glob(".stage_*"):
            shutil.rmtree(stale, ignore_errors=True)

    def start(self):
        with self._lock:
            if self.proc and self.proc.poll() is None:
                return
            BUFFER_DIR.mkdir(parents=True, exist_ok=True)
            self.session += 1

            cmd = self._build_cmd()
            self.proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=CREATE_NO_WINDOW | ABOVE_NORMAL_PRIORITY_CLASS,
            )
            if self._job:
                ctypes.windll.kernel32.AssignProcessToJobObject(
                    self._job, int(self.proc._handle))
            self.started_at = time.time()
            self.audio = AudioMixer(
                speaker=self.cfg["speaker_device"],
                mic=self.cfg["mic_device"] if self.cfg["capture_mic"] else None,
                desktop_gain=self.cfg["desktop_volume"],
                mic_gain=self.cfg["mic_volume"],
                offset_ms=self.cfg["audio_offset_ms"])
            self.audio.start(self.proc.stdin)
            threading.Thread(target=self._drain_stderr, args=(self.proc,), daemon=True).start()
            threading.Thread(target=self._drain_progress, args=(self.proc,), daemon=True).start()
            log(f"recording  {self.cfg['fps']}fps  monitor {self.cfg['monitor']}  "
                f"buffer {self.cfg['clip_seconds']}s")

        self._supervise.clear()
        threading.Thread(target=self._watch, daemon=True).start()

    def _drain_progress(self, proc):
        """Read ffmpeg's -progress stream and keep a live capture-health view.

        `dup_frames` is the number that matters: Desktop Duplication only hands
        over a frame when the screen actually changes, so a climbing dup count
        means the capture is frozen even though encoding looks healthy.
        """
        fields = {}
        last_log = time.time()
        last_dup = 0
        first_done = False
        for raw in iter(proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").strip()
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            fields[key] = value.strip()
            if key != "progress":
                continue

            try:
                fps = float(fields.get("fps", 0) or 0)
                dup = int(fields.get("dup_frames", 0) or 0)
                drop = int(fields.get("drop_frames", 0) or 0)
            except ValueError:
                continue
            self.health = {"fps": fps, "dup": dup, "drop": drop,
                           "at": time.time()}

            now = time.time()
            # Report once shortly after start as a sanity check, then hourly-ish.
            if now - last_log < (60 if first_done else 15):
                continue
            window = now - last_log
            new_dup = dup - last_dup
            target = float(self.cfg["fps"])
            # Share of emitted frames that were copies of the previous one.
            stale = new_dup / max(1.0, target * window)

            note = ""
            if stale > 0.5:
                note = (f"  ({stale*100:.0f}% of frames were copies - "
                        f"screen content is barely changing)")
            elif fps and fps < target * 0.9:
                note = f"  (below the {target:.0f} fps target)"
            log(f"capture health: {fps:.1f} fps, +{new_dup} duplicated, "
                f"{drop} dropped{note}")

            # An idle desktop is legitimately full of duplicates, so only raise
            # it when the display was also recently lost - that pairing means a
            # game is running that we cannot see.
            recent_loss = now - self._last_access_lost < 300
            if (stale > 0.5 and recent_loss
                    and now - self._last_frozen_warn > 120):
                self._last_frozen_warn = now
                log("capture appears frozen behind an exclusive-fullscreen app; "
                    "switch the game to Borderless Windowed")
                if self.on_trouble:
                    try:
                        self.on_trouble("frozen")
                    except Exception:
                        pass
            first_done = True
            last_log, last_dup = now, dup

    def _drain_stderr(self, proc):
        for raw in iter(proc.stderr.readline, b""):
            line = raw.decode("utf-8", "replace").strip()
            if not line or "Past duration" in line:
                continue
            # 887a0026 is DXGI_ERROR_ACCESS_LOST - the fingerprint of something
            # taking the display, which is what makes capture freeze.
            if "AcquireNextFrame failed" in line or "887a0026" in line:
                self._last_access_lost = time.time()
            log(f"ffmpeg: {line}")

    # Desktop Duplication hands back DXGI_ERROR_ACCESS_LOST whenever something
    # takes the display - an exclusive-fullscreen game, a mode switch, a UAC
    # prompt. Recovery is a fresh ffmpeg, so it needs to be quick and quiet.
    QUICK_RESTART = 0.4
    STORM_WINDOW = 40.0
    STORM_COUNT = 4

    def _watch(self):
        """Restart ffmpeg if it dies (display mode change, driver reset, etc.)."""
        while not self._supervise.is_set():
            time.sleep(0.25)
            proc = self.proc
            if not proc or proc.poll() is None or self._supervise.is_set():
                continue

            now = time.time()
            self._restarts = [t for t in self._restarts if now - t < self.STORM_WINDOW]
            self._restarts.append(now)
            storm = len(self._restarts) >= self.STORM_COUNT

            # Backing off during a storm avoids hammering a display that is
            # simply unavailable, but the buffer is preserved either way.
            delay = 3.0 if storm else self.QUICK_RESTART
            log(f"ffmpeg exited (code {proc.returncode}); "
                f"restarting in {delay:.1f}s (buffer kept)")
            if storm and not self._warned:
                self._warned = True
                log("capture keeps losing the display - exclusive fullscreen "
                    "cannot be captured; switch the game to Borderless Windowed")
                if self.on_trouble:
                    try:
                        self.on_trouble("lost")
                    except Exception:
                        pass

            if self.audio:
                self.audio.stop()
            time.sleep(delay)
            self.start()
            return

    def stop(self):
        self._supervise.set()
        with self._lock:
            if self.audio:
                self.audio.stop()
            proc, self.proc = self.proc, None
            if not proc or proc.poll() is not None:
                return
            try:
                proc.stdin.close()
            except OSError:
                pass
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except (subprocess.TimeoutExpired, OSError):
                proc.kill()
            log("recording stopped")

    def restart(self):
        self.stop()
        time.sleep(0.4)
        self.start()

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    @property
    def buffered_seconds(self):
        """Derived from what is actually on disk rather than from uptime, so it
        stays honest across capture restarts and buffer resets."""
        if not self.running:
            return 0.0
        try:
            count = sum(1 for _ in BUFFER_DIR.glob("seg_*.ts"))
        except OSError:
            return 0.0
        return min(count * float(self.cfg["segment_seconds"]),
                   float(self.cfg["clip_seconds"]))


# --------------------------------------------------------------------------
# clip assembly
# --------------------------------------------------------------------------

class Clipper:
    def __init__(self, cfg, ffmpeg, recorder):
        self.cfg = cfg
        self.ffmpeg = ffmpeg
        self.recorder = recorder
        self._busy = threading.Lock()

    @staticmethod
    def _session_of(path):
        """seg_<session>_<index>.ts - the zero-padded session it came from."""
        parts = path.stem.split("_")
        return parts[1] if len(parts) >= 3 else ""

    def _concat(self, work, staged, out):
        listing = work / "list.txt"
        listing.write_text(
            "".join(f"file '{p.as_posix()}'\n" for p in staged), encoding="utf-8")
        res = subprocess.run(
            [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", str(listing),
             "-c", "copy", "-bsf:a", "aac_adtstoasc",
             "-movflags", "+faststart", str(out)],
            capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
        ok = (res.returncode == 0 and out.exists() and out.stat().st_size > 0)
        return ok, res.stderr

    def segments(self):
        # Zero-padded session and index make filename order chronological.
        return sorted(BUFFER_DIR.glob("seg_*.ts"))

    def prune(self):
        """Trim the ring to the configured window (plus a little slack)."""
        seg = self.cfg["segment_seconds"]
        keep = int(self.cfg["clip_seconds"] / seg) + 4
        files = self.segments()
        for old in files[:-keep] if len(files) > keep else []:
            try:
                old.unlink()
            except OSError:
                pass
        self.sweep_staging()

    @staticmethod
    def sweep_staging(max_age=300):
        """Remove staging copies orphaned by a kill or crash.

        _save deletes its own, but TerminateProcess skips finally blocks and
        each orphan holds a whole clip's worth of segments - hundreds of MB.
        """
        cutoff = time.time() - max_age
        for path in BUFFER_DIR.glob(".stage_*"):
            try:
                if path.is_dir() and path.stat().st_mtime < cutoff:
                    shutil.rmtree(path, ignore_errors=True)
            except OSError:
                pass

    def _drop_through(self, last_used):
        """Discard everything the clip just consumed.

        Leaves anything recorded after it, so the next clip picks up exactly
        where this one ended rather than repeating it. ffmpeg still holds the
        newest segment open and Windows will refuse to unlink it; that costs at
        most one segment of overlap and clears itself on the next pass.
        """
        dropped = 0
        for path in self.segments():
            if path.name > last_used.name:
                break
            try:
                path.unlink()
                dropped += 1
            except OSError:
                pass
        log(f"buffer reset after nab ({dropped} segments dropped)")

    def save(self, on_done=None):
        """Returns whether a save actually started, so the caller can confirm
        to the user immediately rather than waiting for the settle delay."""
        if not self._busy.acquire(blocking=False):
            return False
        threading.Thread(target=self._save, args=(on_done,), daemon=True).start()
        return True

    def _settle(self):
        """Let the moment you pressed the key reach disk before assembling.

        The segment being written when the hotkey fires is still open, and its
        tail is only guaranteed once the muxer closes it and starts the next
        one. Assembling immediately is what made clips end just before the
        keypress. Waiting for a new segment to appear also captures a couple of
        seconds of aftermath, which is usually what you wanted anyway.
        """
        delay = float(self.cfg.get("save_delay", 3.0))
        if delay > 0:
            # Longer than segment_seconds, so the segment holding the keypress
            # is guaranteed to have been closed and flushed by the time we read.
            time.sleep(delay)

    def _save(self, on_done):
        work = None
        try:
            self._settle()
            seg = self.cfg["segment_seconds"]
            files = self.segments()
            if len(files) < 2:
                self._finish(on_done, False, "buffer still filling")
                return

            wanted = max(1, int(round(self.cfg["clip_seconds"] / seg)))
            chosen = files[-(wanted + 1):]

            out_dir = Path(self.cfg["output_dir"])
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / f"nab_{datetime.now():%Y-%m-%d_%H-%M-%S}.mp4"

            # ffmpeg still holds the newest segment open. Copy the set aside so
            # concat reads stable bytes and the janitor can't delete underneath.
            work = BUFFER_DIR / f".stage_{os.getpid()}_{int(time.time())}"
            work.mkdir(exist_ok=True)
            staged = []
            for src in chosen:
                dst = work / src.name
                try:
                    shutil.copyfile(src, dst)
                    if dst.stat().st_size > 0:
                        staged.append(dst)
                except OSError:
                    pass  # in-progress segment may vanish; skip it
            if not staged:
                self._finish(on_done, False, "no readable segments")
                return

            ok, err = self._concat(work, staged, out)

            # Segments can span several capture sessions after a display loss.
            # If the display mode changed across that seam the streams will not
            # copy together, so fall back to the newest session rather than
            # handing back nothing.
            if not ok and len({self._session_of(p) for p in staged}) > 1:
                newest = max(self._session_of(p) for p in staged)
                subset = [p for p in staged if self._session_of(p) == newest]
                log(f"concat across sessions failed ({err.strip()[:160]}); "
                    f"retrying with the newest {len(subset)} segments")
                ok, err = self._concat(work, subset, out)
                if ok:
                    staged = subset

            if not ok:
                log(f"nab failed: {err.strip()[:400]}")
                self._finish(on_done, False, "nab failed - see nabd.log")
                return

            secs = len(staged) * seg
            mb = out.stat().st_size / (1024 * 1024)
            log(f"saved {out.name}  ~{secs}s  {mb:.1f}MB")
            if self.cfg.get("reset_after_clip"):
                self._drop_through(chosen[-1])
            self._finish(on_done, True, f"{out.name}  ({secs // 60}m {secs % 60}s)")
        except Exception as exc:
            log(f"nab error: {exc}")
            self._finish(on_done, False, str(exc))
        finally:
            if work:
                shutil.rmtree(work, ignore_errors=True)
            self._busy.release()

    def _finish(self, on_done, ok, detail):
        if on_done:
            try:
                on_done(ok, detail)
            except Exception:
                pass


# --------------------------------------------------------------------------
# global hotkey (Win32 RegisterHotKey - no keyboard hook, anti-cheat safe)
# --------------------------------------------------------------------------

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 1, 2, 4, 8, 0x4000
WM_HOTKEY = 0x0312

MODIFIERS = {"alt": MOD_ALT, "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
             "shift": MOD_SHIFT, "win": MOD_WIN}

VK_EXTRA = {"space": 0x20, "insert": 0x2D, "delete": 0x2E, "home": 0x24,
            "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "print": 0x2C,
            "scrolllock": 0x91, "pause": 0x13, "tab": 0x09, "`": 0xC0}


def parse_hotkey(spec):
    mods, vk = 0, None
    for part in spec.lower().replace(" ", "").split("+"):
        if part in MODIFIERS:
            mods |= MODIFIERS[part]
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            vk = 0x70 + int(part[1:]) - 1
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        elif part in VK_EXTRA:
            vk = VK_EXTRA[part]
    if vk is None:
        raise ValueError(f"unrecognised hotkey: {spec!r}")
    return mods | MOD_NOREPEAT, vk


def hotkey_available(spec):
    """Whether the combo can be claimed right now (used by the settings UI)."""
    try:
        mods, vk = parse_hotkey(spec)
    except ValueError:
        return False
    result = []

    def check():
        user32 = ctypes.windll.user32
        if user32.RegisterHotKey(None, 77, mods, vk):
            user32.UnregisterHotKey(None, 77)
            result.append(True)
        else:
            result.append(False)

    t = threading.Thread(target=check)  # RegisterHotKey is per-thread
    t.start()
    t.join(5)
    return bool(result and result[0])


class HotkeyListener(threading.Thread):
    """RegisterHotKey delivers WM_HOTKEY to the registering thread, so the
    message pump has to live here rather than on the tray thread."""

    RETRY_SECONDS = 5.0

    def __init__(self, spec, callback, hotkey_id=1):
        super().__init__(daemon=True)
        self.mods, self.vk = parse_hotkey(spec)
        self.spec = spec
        self.callback = callback
        # Ids are per-thread, and each listener owns its own thread, but
        # distinct ids keep the two registrations easy to tell apart.
        self.hotkey_id = hotkey_id
        self.ok = threading.Event()
        self.error = None
        self.registered = False
        self._tid = None
        self._quit = threading.Event()

    def run(self):
        user32 = ctypes.windll.user32
        self._tid = ctypes.windll.kernel32.GetCurrentThreadId()

        # Overlays (ShadowPlay, Game Bar, Discord) can hold a combo transiently
        # and release it later, so a first failure is not fatal - keep trying.
        attempts = 0
        while not self._quit.is_set():
            if user32.RegisterHotKey(None, self.hotkey_id, self.mods, self.vk):
                self.registered = True
                if attempts:
                    log(f"hotkey {self.spec!r} registered after {attempts} retries")
                self.error = None
                self.ok.set()
                break
            attempts += 1
            if attempts == 1:
                self.error = (f"hotkey {self.spec!r} is in use by another app; "
                              f"retrying in the background")
                self.ok.set()
            self._quit.wait(self.RETRY_SECONDS)

        if not self.registered:
            return

        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    self.callback()
        finally:
            user32.UnregisterHotKey(None, self.hotkey_id)
            self.registered = False

    def shutdown(self):
        self._quit.set()
        if self._tid:
            ctypes.windll.user32.PostThreadMessageW(self._tid, 0x0012, 0, 0)  # WM_QUIT


# --------------------------------------------------------------------------
# tray
# --------------------------------------------------------------------------

def make_icon(recording):
    """The app tile in the tray.

    The guidelines' tray note prefers a monochrome template, on the grounds
    that Windows draws the tray over unknown wallpaper - but the tile is what
    was asked for here, and the same document argues the field treatment is
    what survives at 16px. Paused desaturates the field and keeps the
    silhouette identical, so the state reads without changing the shape.
    """
    if recording:
        return brand.tile_image(64)
    return brand.tile_image(64, field="#2E2B36", ring="#847F8D")


class Tray:
    def __init__(self, app):
        import pystray
        self.app = app
        self.cfg = app.cfg
        self.startup_warning = None
        self.icon = pystray.Icon(
            APP_NAME, make_icon(False), DISPLAY_NAME,
            menu=pystray.Menu(
                # Informational only; clicking the icon opens Settings, so
                # recording moved to an explicit checkbox below.
                pystray.MenuItem(self._status, lambda: None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(self._save_label, self._clip),
                pystray.MenuItem("Recording", self._toggle,
                                 checked=lambda _i: self.app.recorder.running),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Open nabs folder", self._open_clips),
                pystray.MenuItem("Settings...", self.open_settings,
                                 default=True),
                pystray.MenuItem("View log", self._view_log),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit", self._quit),
            ),
        )

    def _status(self, _):
        if not self.app.recorder.running:
            return "Paused - click to resume"
        have = int(self.app.recorder.buffered_seconds)
        total = int(self.cfg["clip_seconds"])
        if have >= total:
            return f"Recording - {total // 60} min buffered"
        return f"Recording - {have}s / {total}s buffered"

    def _save_label(self, _):
        mins = int(self.cfg["clip_seconds"]) // 60
        return f"Nab last {mins} min  ({self.cfg['hotkey']})"

    def notify(self, title, message):
        if not self.cfg["notify"]:
            return
        try:
            self.icon.notify(message, title)
        except Exception:
            pass

    def refresh(self):
        self.icon.icon = make_icon(self.app.recorder.running)
        self.icon.update_menu()

    def _toggle(self):
        if self.app.recorder.running:
            self.app.recorder.stop()
        else:
            self.app.recorder.start()
        self.refresh()

    def _clip(self):
        self.app.save_clip()

    def _open_clips(self):
        path = Path(self.cfg["output_dir"])
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def open_settings(self):
        """Run the UI out of process - tkinter and pystray cannot share a
        main thread, and a crash in the dialog must not take recording down."""
        try:
            proc = subprocess.Popen(helper_command("settings"),
                                    cwd=str(ASSET_DIR))
            # Hand our foreground rights to the panel. Without this Windows
            # refuses to let it come to the front, and it cannot tell that the
            # user has clicked away.
            ctypes.windll.user32.AllowSetForegroundWindow(proc.pid)
        except OSError as exc:
            log(f"could not open settings: {exc}")

    def _view_log(self):
        LOG_PATH.touch(exist_ok=True)
        os.startfile(LOG_PATH)

    def _quit(self):
        self.icon.visible = False
        self.icon.stop()

    def run(self):
        self.icon.run(setup=self._setup)

    def _setup(self, icon):
        icon.visible = True
        self.refresh()
        if self.startup_warning:
            self.notify(DISPLAY_NAME, self.startup_warning)
        threading.Thread(target=self._tick, daemon=True).start()

    def _tick(self):
        while True:
            time.sleep(3)
            try:
                self.app.clipper.prune()
                self.app.poll_config()
                self.app.ensure_banner_helper()
                self.refresh()
            except Exception:
                pass


# --------------------------------------------------------------------------
# application
# --------------------------------------------------------------------------

class App:
    def __init__(self, cfg, ffmpeg):
        self.cfg = cfg
        self.ffmpeg = ffmpeg
        self.recorder = Recorder(cfg, ffmpeg)
        self.clipper = Clipper(cfg, ffmpeg, self.recorder)
        self.tray = Tray(self)
        self.hotkey = None
        self.open_hotkey = None
        self._banner = None
        self._job = create_kill_on_close_job()
        self._cfg_stamp = self._stamp()

    def _stamp(self):
        try:
            return CONFIG_PATH.stat().st_mtime_ns
        except OSError:
            return 0

    def ensure_banner_helper(self):
        """Keep a warm banner process alive.

        tkinter cannot share a main thread with the tray icon, so the banner
        lives out of process. Launching a fresh interpreter per clip cost about
        a second before anything appeared, so the helper stays resident and
        watches a trigger file instead.
        """
        if self._banner and self._banner.poll() is None:
            return
        try:
            self._banner = subprocess.Popen(
                helper_command("banner", "--daemon"),
                cwd=str(ASSET_DIR), creationflags=CREATE_NO_WINDOW)
            if self._job:
                ctypes.windll.kernel32.AssignProcessToJobObject(
                    self._job, int(self._banner._handle))
        except OSError as exc:
            log(f"banner helper failed to start: {exc}")
            self._banner = None

    def show_banner(self, text, ok=True):
        """Fire-and-forget: a file write, so the keypress feels immediate."""
        if not self.cfg["notify"]:
            return
        self.ensure_banner_helper()
        try:
            BANNER_TRIGGER.write_text(
                json.dumps({"text": text, "kind": "ok" if ok else "fail",
                            "monitor": int(self.cfg["monitor"]),
                            "delay": float(self.cfg.get("banner_delay", 0.2))}),
                encoding="utf-8")
        except OSError as exc:
            log(f"banner trigger failed: {exc}")

    def _clip_done(self, ok, detail):
        # Success was already confirmed the instant the key was pressed; only
        # speak up again if it turned out badly.
        if not ok:
            self.show_banner(f"Nab Failed - {detail}", ok=False)

    def save_clip(self):
        """Confirm immediately, assemble in the background.

        Assembly deliberately waits for the newest segment to flush, but that
        delay should not sit between the keypress and the feedback.
        """
        if not self.clipper.save(on_done=self._clip_done):
            log("nab already in progress; ignoring")
            return
        log("nab requested")
        mins = max(1, int(round(self.cfg["clip_seconds"] / 60)))
        unit = "Minute" if mins == 1 else "Minutes"
        self.show_banner(f"Nab'd Last {mins} {unit}", ok=True)

    def _bind(self, spec, action, hotkey_id, label):
        if not spec:
            return None
        listener = HotkeyListener(spec, action, hotkey_id)
        listener.start()
        listener.ok.wait(5)
        if listener.error:
            log(listener.error)
            self.tray.startup_warning = listener.error
        else:
            log(f"hotkey ({label}): {spec}")
        return listener

    def start_hotkey(self):
        self.hotkey = self._bind(self.cfg["hotkey"], self.save_clip, 1, "nab")
        self.open_hotkey = self._bind(self.cfg.get("open_hotkey"),
                                      self.open_settings, 2, "open Nab'd")

    def open_settings(self):
        self.tray.open_settings()

    def poll_config(self):
        """Apply settings written by the UI (or by hand) without a restart."""
        stamp = self._stamp()
        if stamp == self._cfg_stamp:
            return
        self._cfg_stamp = stamp
        new = load_config()
        old = dict(self.cfg)
        if new == old:
            return

        self.cfg.clear()
        self.cfg.update(new)
        changed = {k for k in new if old.get(k) != new[k]}
        log(f"config changed: {', '.join(sorted(changed))}")

        if changed & CAPTURE_KEYS and self.recorder.running:
            self.recorder.restart()
        if changed & {"hotkey", "open_hotkey"}:
            for listener in (self.hotkey, self.open_hotkey):
                if listener:
                    listener.shutdown()
            self.start_hotkey()
        self.tray.refresh()

    def _capture_trouble(self, reason="lost"):
        if reason == "frozen":
            self.show_banner("Capture is frozen - switch to Borderless Windowed",
                             ok=False)
        else:
            self.show_banner("Capture lost the display - use Borderless Windowed",
                             ok=False)

    def run(self):
        # Recording comes first: a hotkey problem must never cost you the
        # buffer, and the tray menu can still save clips without one.
        self.recorder.on_trouble = self._capture_trouble
        self.recorder.clear_buffer()
        self.recorder.start()
        self.ensure_banner_helper()  # warm, so the first clip confirms instantly
        self.start_hotkey()
        try:
            self.tray.run()
        finally:
            log("shutting down")
            for listener in (self.hotkey, self.open_hotkey):
                if listener:
                    listener.shutdown()
            self.recorder.stop()
            if self._banner and self._banner.poll() is None:
                try:
                    self._banner.terminate()
                except OSError:
                    pass


def claim_single_instance():
    """Hold a named mutex for the session.

    Autostart plus a manual launch would otherwise leave two recorders writing
    into the same ring buffer and clobbering each other's segments.
    """
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, f"{APP_NAME}.Instance")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return None
    return handle


def main():
    # One executable, three roles. Frozen there is no interpreter to hand a
    # script to, so the helpers are this same binary re-invoked with a flag.
    if "--settings" in sys.argv:
        import settings
        return settings.main() or 0
    if "--banner" in sys.argv:
        import banner
        return banner.main() or 0

    log(f"--- {DISPLAY_NAME} starting ---")
    if claim_single_instance() is None:
        log("another instance is already running; exiting")
        ctypes.windll.user32.MessageBoxW(
            None, f"{DISPLAY_NAME} is already running - check the system tray.",
            DISPLAY_NAME, 0x40)
        return 0

    cfg = load_config()
    try:
        ffmpeg = find_ffmpeg()
    except RuntimeError as exc:
        ctypes.windll.user32.MessageBoxW(None, str(exc), DISPLAY_NAME, 0x10)
        return 1

    App(cfg, ffmpeg).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

