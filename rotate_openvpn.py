#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, subprocess, time, random, sys

CONF_DIR = "/opt/pia_rotate/configs"
CRED_FILE = "/opt/pia_rotate/creds.txt"
EXIT_LOG = "/opt/pia_rotate/exit_log.txt"
ROTATE_INTERVAL = 3600  # 秒
TARGET_CMD = ["curl", "--interface", "tun0", "-s", "https://api.ipify.org"]

def run(cmd, check=False, capture=False):
    return subprocess.run(
        cmd, shell=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        text=True
    )

def list_confs():
    return [os.path.join(CONF_DIR, f)
            for f in os.listdir(CONF_DIR)
            if f.endswith(".ovpn") or f.endswith(".conf")]

def ensure_creds(user=None, passwd=None):
    os.makedirs(os.path.dirname(CRED_FILE), exist_ok=True)
    # 如果 creds 已存在且非空，则直接使用
    if os.path.exists(CRED_FILE) and os.path.getsize(CRED_FILE) > 0:
        print(f"🔑 使用已存在的凭证文件: {CRED_FILE}")
        return
    # 否则写入新的凭证
    if not user or not passwd:
        print("❌ 缺少用户名或密码且未检测到凭证文件。")
        sys.exit(1)
    with open(CRED_FILE, "w") as f:
        f.write(user + "\n" + passwd + "\n")
    os.chmod(CRED_FILE, 0o600)
    print(f"✅ 凭证文件已生成: {CRED_FILE}")

def connect_openvpn(conf):
    print(f"🔌 启动 OpenVPN 节点: {os.path.basename(conf)}")
    run("pkill openvpn || true")
    cmd = (
        f"openvpn --config '{conf}' --auth-user-pass '{CRED_FILE}' "
        f"--route-nopull --persist-tun --daemon "
        f"--writepid /var/run/openvpn.pid --dev tun0"
    )
    run(cmd)
    # 等待 tun0 出现
    for i in range(20):
        r = run("ip link show tun0", capture=True)
        if "tun0" in r.stdout:
            print("✅ 检测到 tun0 已创建")
            return True
        time.sleep(1)
    print("❌ tun0 未出现，连接失败")
    return False

def disconnect_openvpn():
    if os.path.exists("/var/run/openvpn.pid"):
        with open("/var/run/openvpn.pid") as f:
            pid = f.read().strip()
        run(f"kill {pid}")
        os.remove("/var/run/openvpn.pid")
    run("pkill openvpn || true")

def get_exit_ip():
    r = run("curl -s --interface tun0 https://api.ipify.org", capture=True)
    return r.stdout.strip() if r.returncode == 0 else None

def rotate_loop(user=None, passwd=None):
    ensure_creds(user, passwd)
    while True:
        confs = list_confs()
        if not confs:
            print("⚠️ 没有配置文件，等待...")
            time.sleep(5)
            continue
        conf = random.choice(confs)
        disconnect_openvpn()
        ok = connect_openvpn(conf)
        if not ok:
            time.sleep(5)
            continue

        # 检查出口 IP
        time.sleep(4)
        ip = get_exit_ip()
        print("🌍 出口 IP:", ip or "检测失败")
        with open(EXIT_LOG, "a") as f:
            f.write(f"{time.strftime('%F %T')} {os.path.basename(conf)} exit:{ip}\n")

        # 执行目标命令
        print("🚀 执行命令:", " ".join(TARGET_CMD))
        run(" ".join(TARGET_CMD))

        # 轮换间隔
        time.sleep(ROTATE_INTERVAL)

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("请用 root 运行。")
        sys.exit(1)

    user = sys.argv[1] if len(sys.argv) > 1 else None
    passwd = sys.argv[2] if len(sys.argv) > 2 else None
    rotate_loop(user, passwd)
