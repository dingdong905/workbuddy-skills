#!/usr/bin/env python3
"""通用 CTF 靶场 TCP 侦察脚本。

用法:
    python recv_probe.py <host> <port> [cmd1 cmd2 ...]

无 cmd 参数时只收 banner。有 cmd 时逐条发送并分段打印响应。
适用于菜单式 nc 题目：先跑一遍把 help/policy/source/pairs 等信息项全拉下来。
"""
import socket
import sys


def recv_all(s, first_timeout=6, idle_timeout=2):
    """收数据直到空闲 idle_timeout 秒。首包等 first_timeout 秒。"""
    s.settimeout(first_timeout)
    buf = b""
    try:
        while True:
            data = s.recv(4096)
            if not data:
                break
            buf += data
            s.settimeout(idle_timeout)
    except socket.timeout:
        pass
    except ConnectionResetError:
        # RST 时 recv 抛异常，保留已收到的 buf（否则崩溃前输出丢失）。
        # 教训（2026-09-17 ToyLM-3000）：> HELP 触发服务器 RST，未捕获时
        # 崩溃前输出被丢弃，误判为"无响应"。
        pass
    return buf


def emit(s):
    """统一文本输出并立即 flush。

    教训（2026-09-17 Echo Vault）：print（块缓冲）与 sys.stdout.buffer.write
    （直写底层）混用会导致响应段落乱序——所有命令输出挤进 BANNER 段、
    CMD 段显示为空，极易误判靶机行为。所有输出必须走同一文本通道并逐段 flush。
    """
    sys.stdout.write(s)
    sys.stdout.flush()


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    host, port = sys.argv[1], int(sys.argv[2])
    cmds = sys.argv[3:]

    s = socket.create_connection((host, port), timeout=15)
    banner = recv_all(s, first_timeout=8)
    emit("===== BANNER =====\n")
    emit(banner.decode("utf-8", "replace"))
    emit("\n===== BANNER END =====\n")

    for cmd in cmds:
        s.sendall(cmd.encode() + b"\n")
        resp = recv_all(s, first_timeout=8)
        emit("===== CMD [%s] =====\n" % cmd)
        emit(resp.decode("utf-8", "replace"))
        emit("\n===== END =====\n")
    s.close()


if __name__ == "__main__":
    main()
