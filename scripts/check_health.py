#!/usr/bin/env python3
"""健康检查脚本 - 验证后端是否正常运行"""
import requests
import sys
import json
from datetime import datetime

API_BASE = "http://localhost:8000"

def check_health():
    """检查后端健康状态"""
    print("=" * 80)
    print(f"🔍 后端健康检查 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    try:
        # 1. 基础健康检查
        print("\n1️⃣  检查基础健康状态...")
        response = requests.get(f"{API_BASE}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ 后端运行正常")
            print(f"   📊 版本: {data.get('version')}")
            print(f"   ⏱️  运行时长: {data.get('uptime_seconds', 0):.2f} 秒")
        else:
            print(f"   ❌ 健康检查失败: HTTP {response.status_code}")
            return False

        # 2. 检查根路径
        print("\n2️⃣  检查根路径...")
        response = requests.get(f"{API_BASE}/", timeout=5)
        if response.status_code == 200:
            print(f"   ✅ 根路径响应正常: {response.json()}")
        else:
            print(f"   ⚠️  根路径异常: HTTP {response.status_code}")

        # 3. 检查 API 文档
        print("\n3️⃣  检查 API 文档...")
        response = requests.get(f"{API_BASE}/docs", timeout=5)
        if response.status_code == 200:
            print(f"   ✅ API 文档可访问: {API_BASE}/docs")
        else:
            print(f"   ⚠️  API 文档不可访问")

        print("\n" + "=" * 80)
        print("✅ 健康检查完成 - 后端运行正常")
        print("=" * 80)
        return True

    except requests.exceptions.ConnectionError:
        print("\n❌ 连接失败：后端未启动或端口不正确")
        print(f"   请确认后端运行在 {API_BASE}")
        return False
    except requests.exceptions.Timeout:
        print("\n❌ 请求超时：后端响应过慢")
        return False
    except Exception as e:
        print(f"\n❌ 检查失败: {e}")
        return False

def check_autopilot_daemon():
    """检查自动驾驶守护进程状态"""
    print("\n4️⃣  检查自动驾驶守护进程...")
    print("   ℹ️  守护进程是独立进程，需单独启动")
    print("   💡 提示：查看日志文件确认守护进程是否运行")
    print("      - 日志位置: logs/plotpilot.log")
    print("      - 查找关键字: 'Autopilot Daemon Started'")

if __name__ == "__main__":
    success = check_health()
    check_autopilot_daemon()
    sys.exit(0 if success else 1)
