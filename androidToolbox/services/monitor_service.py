import re
from androidToolbox.core.adb import ADBManager

class MonitorService:
    @staticmethod
    def get_resources():
        """获取内存和磁盘的聚合数据"""
        data = {
            "ram_available_mb": 0,
            "disk_info": "未知"
        }

        # 1. 内存解析
        mem_out = ADBManager.run("shell cat /proc/meminfo")
        match = re.search(r'MemAvailable:\s+(\d+)', mem_out)
        if match:
            data["ram_available_mb"] = int(match.group(1)) // 1024

        # 2. 磁盘解析
        disk_out = ADBManager.run("shell df -h /data")
        try:
            line = disk_out.splitlines()[-1]
            parts = line.split()
            # 兼容不同 df 版本，通常可用空间在倒数几列
            data["disk_info"] = parts[3] if len(parts) >= 4 else "?"
        except:
            pass
            
        return data