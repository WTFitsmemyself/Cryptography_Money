#!/usr/bin/env python3
"""
Universal System Intelligence Collector
- Cross-platform (Windows, macOS, Linux, Android/Termux, iOS-like Darwin)
- Collects as much system info as permitted by the environment
- Saves JSON output to a timestamped file

Usage:
  python universal_system_collector.py
"""

import os
import sys
import json
import socket
import uuid
import platform
import subprocess
import getpass
import locale
import time
from datetime import datetime
# from flask import Flask, jsonify

# Try optional imports
try:
    import psutil
except Exception:
    psutil = None

try:
    from cpuinfo import get_cpu_info as _get_cpu_info
except Exception:
    _get_cpu_info = None

try:
    import GPUtil
except Exception:
    GPUtil = None

try:
    import distro
except Exception:
    distro = None

try:
    import netifaces
except Exception:
    netifaces = None

# Helper: safe call
def safe(call, default=None):
    try:
        return call()
    except Exception as e:
        return {"error": str(e)}

# Platform detection
PLATFORM = platform.system().lower()
IS_WINDOWS = PLATFORM == "windows"
IS_DARWIN = PLATFORM == "darwin"  # macOS or iOS-like
IS_LINUX = PLATFORM == "linux"
IS_ANDROID = False
if IS_LINUX:
    # Termux sets PREFIX env and usually 'Android' in uname -o or in /system
    if "ANDROID_ROOT" in os.environ or os.environ.get("PREFIX", "").startswith("/data/data/com.termux"):
        IS_ANDROID = True
    else:
        # also check uname -o
        try:
            uname_o = subprocess.check_output(["uname", "-o"], text=True).strip().lower()
            if "android" in uname_o:
                IS_ANDROID = True
        except Exception:
            pass

# Timestamped filename for output
TIMESTAMP = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
OUTFILE = f"system_report_{TIMESTAMP}.json"

# Utilities
def to_serializable(obj):
    # Convert many psutil namedtuples and others to dicts
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_serializable(x) for x in obj]
    # namedtuple-like
    if hasattr(obj, "_asdict"):
        try:
            return to_serializable(obj._asdict())
        except Exception:
            pass
    # fallback to string
    try:
        return str(obj)
    except Exception:
        return None

# 1) Basic System Info
def get_basic_info():
    return safe(lambda: {
        "platform_system": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "platform_machine": platform.machine(),
        "platform_processor": platform.processor(),
        "platform_uname": to_serializable(platform.uname()),
        "hostname": socket.gethostname(),
        "fqdn": socket.getfqdn(),
        "uuid_node": str(uuid.getnode()),
        "python_version": platform.python_version(),
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "local_time": datetime.now().isoformat(),
        "is_android_termux": IS_ANDROID,
        "is_windows": IS_WINDOWS,
        "is_darwin": IS_DARWIN,
        "is_linux": IS_LINUX
    })

# 2) OS / Distro details
def get_os_details():
    if IS_LINUX and distro:
        return safe(lambda: {
            "distro_name": distro.name(pretty=True),
            "distro_id": distro.id(),
            "distro_version": distro.version(),
            "distro_like": distro.like()
        })
    if IS_DARWIN:
        return safe(lambda: {"darwin_version": platform.mac_ver()})
    return {}

# 3) CPU Info
def get_cpu():
    def _cpu():
        data = {}
        if _get_cpu_info:
            try:
                ci = _get_cpu_info()
                data["cpuinfo"] = {k: ci.get(k) for k in ("brand_raw", "hz_advertised_friendly", "hz_actual_friendly", "arch", "bits")}
            except Exception:
                data["cpuinfo"] = "error_fetching"
        if psutil:
            data["logical_cores"] = psutil.cpu_count(logical=True)
            data["physical_cores"] = psutil.cpu_count(logical=False)
            freq = psutil.cpu_freq()
            data["frequency"] = to_serializable(freq) if freq else {}
            data["cpu_percent_per_core"] = psutil.cpu_percent(interval=1, percpu=True)
            data["cpu_times"] = to_serializable(psutil.cpu_times())
        return data
    return safe(_cpu)

# 4) Memory
def get_memory():
    def _mem():
        if not psutil:
            return {"error": "psutil not installed"}
        vm = psutil.virtual_memory()
        sm = psutil.swap_memory()
        return {"virtual_memory": to_serializable(vm), "swap_memory": to_serializable(sm)}
    return safe(_mem)

# 5) Disks & FS
def get_disks():
    def _disks():
        if not psutil:
            return {"error": "psutil not installed"}
        partitions = []
        for p in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(p.mountpoint)
            except Exception:
                usage = None
            partitions.append({
                "device": p.device,
                "mountpoint": p.mountpoint,
                "fstype": p.fstype,
                "opts": p.opts,
                "usage": to_serializable(usage)
            })
        io = psutil.disk_io_counters(perdisk=True) if psutil else {}
        return {"partitions": partitions, "disk_io": to_serializable(io)}
    return safe(_disks)

# 6) Network (interfaces, mac, ipv4, ipv6, stats)
def get_network():
    def _net():
        if not psutil:
            return {"error": "psutil not installed"}
        interfaces = {}
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        io = psutil.net_io_counters(pernic=True)
        for iface, addrlist in addrs.items():
            iface_entry = {"ipv4": [], "ipv6": [], "mac": None}
            for a in addrlist:
                fam = str(a.family)
                # family names differ by platform; use string checks
                fam_s = str(a.family).upper()
                if "AF_LINK" in fam_s or "AF_PACKET" in fam_s or fam_s.endswith("17"):  # mac
                    iface_entry["mac"] = a.address
                elif "AF_INET" in fam_s or fam_s.endswith("2"):  # IPv4
                    iface_entry["ipv4"].append({"address": a.address, "netmask": a.netmask, "broadcast": a.broadcast})
                elif "AF_INET6" in fam_s or fam_s.endswith("10"):  # IPv6
                    iface_entry["ipv6"].append({"address": a.address, "netmask": a.netmask, "broadcast": a.broadcast})
                else:
                    # fallback
                    iface_entry.setdefault("other", []).append({"family": fam, "addr": a.address})
            iface_entry["is_up"] = stats[iface].isup if iface in stats else None
            iface_entry["speed_mbps"] = stats[iface].speed if iface in stats else None
            iface_entry["mtu"] = stats[iface].mtu if iface in stats else None
            iface_entry["io_counters"] = to_serializable(io.get(iface))
            interfaces[iface] = iface_entry

        # default gateway and DNS (platform-specific)
        gw = {}
        try:
            if netifaces:
                gws = netifaces.gateways()
                gw = to_serializable(gws)
        except Exception:
            gw = {"status": "netifaces not available or error"}
        return {"interfaces": interfaces, "gateway_dns": gw}
    return safe(_net)

# 7) Public IP & Geo (internet required; may fail offline)
def get_public_ip_geo():
    def _pub():
        import urllib.request, json
        try:
            with urllib.request.urlopen("https://ipapi.co/json/", timeout=5) as r:
                return json.loads(r.read().decode())
        except Exception as e:
            return {"error": "network_or_api_error", "detail": str(e)}
    return safe(_pub)

# 8) GPU (GPUtil)
def get_gpu():
    def _gpu():
        if GPUtil is None:
            return {"status": "GPUtil not installed"}
        try:
            gpus = GPUtil.getGPUs()
            return [g.dict for g in gpus]
        except Exception as e:
            return {"error": str(e)}
    return safe(_gpu)

# 9) Processes (top CPU and memory)
def get_processes(limit=20):
    def _procs():
        if not psutil:
            return {"error": "psutil not installed"}
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_percent', 'create_time']):
            try:
                info = p.info
                if info.get("create_time"):
                    info["create_time"] = datetime.fromtimestamp(info["create_time"]).isoformat()
                procs.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs_sorted_cpu = sorted(procs, key=lambda x: x.get("cpu_percent", 0), reverse=True)[:limit]
        procs_sorted_mem = sorted(procs, key=lambda x: x.get("memory_percent", 0), reverse=True)[:limit]
        return {"top_by_cpu": procs_sorted_cpu, "top_by_memory": procs_sorted_mem}
    return safe(_procs)

# 10) Sensors (temperatures, fans, battery) - may not be available everywhere
def get_sensors():
    def _sens():
        if not psutil:
            return {"error": "psutil not installed"}
        try:
            temps = psutil.sensors_temperatures() if hasattr(psutil, "sensors_temperatures") else None
            fans = psutil.sensors_fans() if hasattr(psutil, "sensors_fans") else None
            batt = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
            return {"temperatures": to_serializable(temps), "fans": to_serializable(fans), "battery": to_serializable(batt)}
        except Exception as e:
            return {"error": str(e)}
    return safe(_sens)

# 11) Users, sessions, current user, admin check
def get_user_info():
    def _u():
        data = {"current_user": getpass.getuser(), "home_dir": os.path.expanduser("~")}
        try:
            data["logged_in_users"] = [to_serializable(u) for u in psutil.users()] if psutil else []
        except Exception:
            data["logged_in_users"] = []
        # admin check
        try:
            if IS_WINDOWS:
                # On Windows, detect admin by checking SID or using ctypes
                import ctypes
                is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            else:
                is_admin = (os.getuid() == 0)
            data["is_admin"] = is_admin
        except Exception:
            data["is_admin"] = None
        return data
    return safe(_u)

# 12) Runtime / Python environment / packages (limited list)
def get_python_env(limit=200):
    def _py():
        data = {"python_executable": sys.executable, "python_version": platform.python_version()}
        try:
            import pkg_resources
            pkgs = sorted([(p.project_name, p.version) for p in pkg_resources.working_set])
            data["installed_packages_sample"] = pkgs[:limit]
        except Exception:
            data["installed_packages_sample"] = "pkg_resources unavailable"
        return data
    return safe(_py)

# 13) Services (systemctl / windows service query) - best-effort
def get_services():
    def _svc():
        if IS_LINUX:
            try:
                out = subprocess.check_output(["systemctl", "list-units", "--type=service", "--no-pager", "--all"], text=True, stderr=subprocess.DEVNULL)
                return {"systemctl_list": out}
            except Exception:
                return {"status": "systemctl unavailable or permission denied"}
        if IS_WINDOWS:
            try:
                out = subprocess.check_output(["sc", "query"], text=True, stderr=subprocess.DEVNULL)
                return {"sc_query": out}
            except Exception:
                return {"status": "sc query failed"}
        if IS_DARWIN:
            try:
                out = subprocess.check_output(["launchctl", "list"], text=True, stderr=subprocess.DEVNULL)
                return {"launchctl_list": out}
            except Exception:
                return {"status": "launchctl unavailable"}
        return {"status": "services not supported on this platform"}
    return safe(_svc)

# 14) BIOS / Board / Serial (Windows WMI or dmidecode on Linux)
def get_bios_board():
    def _bb():
        info = {}
        if IS_WINDOWS:
            try:
                # Try WMI if available
                import wmi
                c = wmi.WMI()
                bios = c.Win32_BIOS()[0] if c.Win32_BIOS() else None
                base = c.Win32_BaseBoard()[0] if c.Win32_BaseBoard() else None
                info["bios"] = {k: getattr(bios, k, None) for k in ("Manufacturer", "Name", "ReleaseDate", "SerialNumber")} if bios else None
                info["baseboard"] = {k: getattr(base, k, None) for k in ("Manufacturer", "Product", "SerialNumber")} if base else None
            except Exception as e:
                info["error"] = f"WMI not available or failed: {e}"
            return info
        if IS_LINUX:
            try:
                # dmidecode requires root
                out = subprocess.check_output(["sudo", "dmidecode", "-t", "system"], text=True, stderr=subprocess.DEVNULL)
                return {"dmidecode_system": out}
            except Exception as e:
                return {"status": "dmidecode unavailable or requires root", "detail": str(e)}
        if IS_DARWIN:
            try:
                out = subprocess.check_output(["system_profiler", "SPHardwareDataType", "-json"], text=True)
                return {"system_profiler": json.loads(out)}
            except Exception as e:
                return {"status": "system_profiler failed", "detail": str(e)}
        return {"status": "bios/board not supported"}
    return safe(_bb)

# 15) Virtualization / container detection
def detect_virtualization():
    def _virt():
        reasons = []
        # WSL
        try:
            if IS_LINUX and "microsoft" in platform.release().lower():
                reasons.append("wsl")
        except Exception:
            pass
        # cgroup/docker
        try:
            with open("/proc/self/cgroup", "r") as f:
                cgroup = f.read()
                if "docker" in cgroup or "kubepods" in cgroup:
                    reasons.append("docker/container")
        except Exception:
            pass
        # hypervisor via cpu flags
        try:
            if IS_LINUX:
                with open("/proc/cpuinfo", "r") as f:
                    cpuinfo = f.read().lower()
                    if "hypervisor" in cpuinfo:
                        reasons.append("hypervisor")
        except Exception:
            pass
        return {"detected": reasons or ["none_detected"]}
    return safe(_virt)

# 16) USB devices (lsusb or Windows PnP)
def get_usb_devices():
    def _usb():
        if IS_LINUX:
            try:
                out = subprocess.check_output(["lsusb"], text=True)
                return {"lsusb": out}
            except Exception:
                return {"status": "lsusb not available"}
        if IS_WINDOWS:
            try:
                out = subprocess.check_output(["powershell", "Get-PnpDevice | Select-Object -First 200"], text=True)
                return {"pnp_devices_sample": out}
            except Exception:
                return {"status": "powershell query failed"}
        if IS_DARWIN:
            try:
                out = subprocess.check_output(["system_profiler", "SPUSBDataType", "-json"], text=True)
                return {"spusb": json.loads(out)}
            except Exception:
                return {"status": "system_profiler USB failed"}
        return {"status": "usb detection not supported"}
    return safe(_usb)

# 17) Wi-Fi details (best-effort)
def get_wifi_info():
    def _wifi():
        if IS_WINDOWS:
            try:
                out = subprocess.check_output(["netsh", "wlan", "show", "interfaces"], text=True)
                return {"netsh_wlan_interfaces": out}
            except Exception:
                return {"status": "netsh wlan failed"}
        if IS_LINUX:
            # try nmcli then iwconfig
            try:
                out = subprocess.check_output(["nmcli", "-t", "-f", "active,ssid,signal,device", "device", "wifi"], text=True)
                return {"nmcli_wifi": out}
            except Exception:
                try:
                    out = subprocess.check_output(["iwconfig"], text=True)
                    return {"iwconfig": out}
                except Exception:
                    return {"status": "no wifi tool available"}
        if IS_DARWIN:
            try:
                out = subprocess.check_output(["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"], text=True)
                return {"airport_info": out}
            except Exception:
                return {"status": "airport command failed"}
        return {"status": "wifi not supported on this platform"}
    return safe(_wifi)

# 18) SMART info for disks (requires smartctl installed)
def get_smart_info():
    def _smart():
        devices = []
        try:
            # list block devices (Linux) or common device names; this is necessarily heuristic
            if IS_LINUX:
                out = subprocess.check_output(["lsblk", "-ndo", "NAME,TYPE"], text=True).strip().splitlines()
                for line in out:
                    name, typ = line.split()
                    if typ == "disk":
                        dev = f"/dev/{name}"
                        try:
                            smart = subprocess.check_output(["smartctl", "-a", dev], text=True, stderr=subprocess.DEVNULL)
                            devices.append({"device": dev, "smart": smart})
                        except Exception:
                            devices.append({"device": dev, "smart": "smartctl failed or requires sudo"})
                return {"devices": devices}
            elif IS_DARWIN:
                return {"status": "SMART via smartctl on macOS if installed; not enumerated"}
            elif IS_WINDOWS:
                return {"status": "SMART available via smartctl or manufacturer tools on Windows"}
            else:
                return {"status": "SMART not supported or not enumerated"}
        except Exception as e:
            return {"error": str(e)}
    return safe(_smart)

# 19) Runtime metrics (current process)
def get_runtime_metrics():
    def _rt():
        pinfo = {}
        try:
            p = psutil.Process(os.getpid()) if psutil else None
            if p:
                pinfo["memory_info"] = to_serializable(p.memory_info())
                pinfo["num_threads"] = p.num_threads()
                pinfo["open_files"] = [f.path for f in p.open_files()]
            pinfo["env_sample"] = dict(list(os.environ.items())[:200])
        except Exception as e:
            pinfo["error"] = str(e)
        return pinfo
    return safe(_rt)

# 20) Timezone & locale
def get_time_locale():
    def _tl():
        return {"local_time": datetime.now().isoformat(), "timezone": str(datetime.now().astimezone().tzinfo), "locale": locale.getdefaultlocale()}
    return safe(_tl)

# 21) Assemble everything
def collect_everything():
    report = {}
    order = [
        ("basic", get_basic_info),
        ("os", get_os_details),
        ("cpu", get_cpu),
        ("memory", get_memory),
        ("disks", get_disks),
        ("network", get_network),
        ("public_ip_geo", get_public_ip_geo),
        ("gpu", get_gpu),
        ("processes", get_processes),
        ("sensors", get_sensors),
        ("users", get_user_info),
        ("python_env", get_python_env),
        ("services", get_services),
        ("bios_board", get_bios_board),
        ("virtualization", detect_virtualization),
        ("usb_devices", get_usb_devices),
        ("wifi", get_wifi_info),
        ("smart", get_smart_info),
        ("runtime", get_runtime_metrics),
        ("time_locale", get_time_locale)
    ]

    for key, fn in order:
        try:
            report[key] = fn()
        except Exception as e:
            report[key] = {"error": f"collection_failed: {e}"}
    # add metadata
    report["_metadata"] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "platform": PLATFORM,
        "script_version": "1.0"
    }
    return report

# 22) CLI run
def main():
    print("Universal System Intelligence Collector — starting collection...")
    if psutil is None:
        print("Warning: psutil not installed. Install with pip install psutil for better results.")
    report = collect_everything()
    # serialize
    try:
        data = json.dumps(report, indent=2, ensure_ascii=False)
    except Exception:
        data = json.dumps(to_serializable(report), indent=2, ensure_ascii=False)
    # write file
    try:
        with open(OUTFILE, "w", encoding="utf-8") as f:
            f.write(data)
        print(f"Written report to {OUTFILE}")
    except Exception as e:
        print(f"Failed to write file: {e}")
    # print summary
    print("Summary:")
    print(json.dumps({
        "platform": PLATFORM,
        "timestamp": TIMESTAMP,
        "keys_collected": list(report.keys())
    }, indent=2))
    # final stdout: big JSON
    print("\nFull report (JSON):\n")
    print(data)

main()

# app = Flask(__name__)
# @app.route('/info', methods=['GET'])
# def info():
#     data = main()
#     return jsonify(data) ,200
#
# app.run(host='0.0.0.0', port=5000)