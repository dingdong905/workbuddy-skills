#!/usr/bin/env python3
"""有状态菜单靶机动作序列工具——动作共享单连接按序执行，分段打印回显。

适用：compile→lint→probe 这类服务端有状态（lint 检查"最近一次编译"）的菜单题。
单命令无状态侦察用 recv_probe.py。

用法:
    python menu_seq.py <host> <port> <action> [action ...]

动作语法:
    compile:<file>  发 compile，随后发文件各行，再发单独一行 . 结束，收全量回显
                    （注意：文档自身含单独一行 . 会提前结束编译）
    line:<text>     发送一行 <text>（可含空格），收回显
    sleep:<sec>     等待秒数，不发送不接收

示例（律令窑题型）:
    python menu_seq.py host port compile:doc.txt lint "probe:dossier://slot-7"
"""
import socket
import sys
import time


def recv_all(s, first_timeout=10, idle_timeout=2.5):
    """收数据直到空闲 idle_timeout 秒；首包等 first_timeout 秒。"""
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
    return buf


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    host, port, actions = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
    s = socket.create_connection((host, port), timeout=20)
    print(recv_all(s, first_timeout=8).decode("utf-8", "replace"))
    for act in actions:
        kind, _, arg = act.partition(":")
        if kind == "compile":
            doc = open(arg, "rb").read().decode("utf-8")
            payload = b"compile\n" + doc.encode()
            if not payload.endswith(b"\n"):
                payload += b"\n"
            payload += b".\n"
            s.sendall(payload)
        elif kind == "line":
            s.sendall(arg.encode() + b"\n")
        elif kind == "sleep":
            time.sleep(float(arg))
            continue
        else:
            print(f"[menu_seq] 未知动作: {act}", file=sys.stderr)
            continue
        resp = recv_all(s, first_timeout=12)
        print(f"===== [{act}] =====")
        print(resp.decode("utf-8", "replace"))
    s.close()


if __name__ == "__main__":
    main()
