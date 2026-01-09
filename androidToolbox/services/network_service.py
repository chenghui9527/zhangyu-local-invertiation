import re
from androidToolbox.core.adb import ADBManager

class NetworkService:
    """
    网络业务逻辑类：负责获取数据、分析数据
    """
    
    @staticmethod
    def analyze_network_status():
        """获取当前网络状态并返回结构化数据"""
        
        # 1. 获取并解析 WiFi
        wifi_out = ADBManager.run("shell dumpsys wifi | grep RSSI")
        rssi_match = re.search(r'RSSI:\s*(-?\d+)', wifi_out)
        wifi_rssi = int(rssi_match.group(1)) if rssi_match else -127
        
        # 2. 获取并解析 移动网络
        tele_out = ADBManager.run("shell dumpsys telephony.registry")
        
        # 业务判断逻辑 (这里是纯逻辑，不涉及 UI 颜色)
        mobile_data = {
            "type": "未知/无SIM",
            "is_5g": False,
            "is_weak": False,
            "warning": ""
        }

        # 判断网络类型
        is_5g = "nrState=CONNECTED" in tele_out or "CellSignalStrengthNr" in tele_out
        
        if is_5g:
            mobile_data["type"] = "5G (NR)"
            mobile_data["is_5g"] = True
            # 核心业务规则：假 5G 判断
            if "level=1" in tele_out or "level=0" in tele_out:
                mobile_data["is_weak"] = True
                mobile_data["warning"] = "检测到虚弱 5G 信号 (Level<=1)"
        elif "CellSignalStrengthLte" in tele_out:
            mobile_data["type"] = "4G (LTE)"
            # 这里也可以加 4G 弱网判断逻辑

        return {
            "wifi_rssi": wifi_rssi,
            "mobile": mobile_data
        }

    @staticmethod
    def ping_target(target):
        """执行 Ping 任务"""
        return ADBManager.run(f"shell ping -c 3 -W 1 {target}")