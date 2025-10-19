import platform
import os
import json
import psutil
import socket
import uuid
from datetime import datetime
from cpuinfo import get_cpu_info
from flask import Flask, jsonify


def get_basic_info():
    return {
        "hostname": socket.gethostname(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat(),
        "uuid": str(uuid.getnode())
    }

def get_cpu_info_data():
    try:
        info = get_cpu_info()
        freq = psutil.cpu_freq()
        return {
            "brand": info.get("brand_raw", "Unknown"),
            "arch": info.get("arch", ""),
            "bits": info.get("bits", ""),
            "count_logical": psutil.cpu_count(logical=True),
            "count_physical": psutil.cpu_count(logical=False),
            "freq": freq._asdict() if freq else {}
        }
    except Exception as e:
        return {"error": str(e)}

def get_memory_info():
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "total": mem.total,
        "available": mem.available,
        "used": mem.used,
        "percent": mem.percent,
        "swap_total": swap.total,
        "swap_used": swap.used,
        "swap_percent": swap.percent
    }

def get_disk_info():
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent
            })
        except PermissionError:
            continue
    return disks

def get_network_info():
    interfaces = psutil.net_if_addrs()
    stats = psutil.net_if_stats()
    io = psutil.net_io_counters(pernic=True)
    network_data = {}

    for iface_name, iface_addrs in interfaces.items():
        iface_data = {
            "mac_address": None,
            "ipv4": [],
            "ipv6": [],
            "is_up": stats[iface_name].isup if iface_name in stats else None,
            "speed_mbps": stats[iface_name].speed if iface_name in stats else None,
            "mtu": stats[iface_name].mtu if iface_name in stats else None,
            "io_counters": io[iface_name]._asdict() if iface_name in io else {}
        }

        for addr in iface_addrs:
            family = str(addr.family)
            if "AF_LINK" in family or "AF_PACKET" in family:  # MAC address
                iface_data["mac_address"] = addr.address
            elif "AF_INET" in family:  # IPv4
                iface_data["ipv4"].append({
                    "address": addr.address,
                    "netmask": addr.netmask,
                    "broadcast": addr.broadcast
                })
            elif "AF_INET6" in family:  # IPv6
                iface_data["ipv6"].append({
                    "address": addr.address,
                    "netmask": addr.netmask,
                    "broadcast": addr.broadcast
                })

        network_data[iface_name] = iface_data

    return network_data

def get_battery_info():
    try:
        battery = psutil.sensors_battery()
        if battery:
            return battery._asdict()
    except Exception:
        pass
    return {"status": "Battery info not available"}

def get_platform_extra():
    system = platform.system().lower()
    if "android" in system or "termux" in os.getenv("PREFIX", ""):
        device_type = "Android"
    elif "darwin" in system:
        device_type = "macOS / iOS"
    elif "windows" in system:
        device_type = "Windows"
    else:
        device_type = "Linux/Other"
    return {"device_type": device_type}

def gather_all():
    return {
        "basic": get_basic_info(),
        "cpu": get_cpu_info_data(),
        "memory": get_memory_info(),
        "disks": get_disk_info(),
        "network": get_network_info(),
        "battery": get_battery_info(),
        "platform": get_platform_extra(),
    }


data = gather_all()
print(json.dumps(data, indent=2))

app = Flask(__name__)
@app.route('/info', methods=['GET'])
def info():
    data = gather_all()
    return jsonify(data) ,200

app.run(host='0.0.0.0', port=5000)