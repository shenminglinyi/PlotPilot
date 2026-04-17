"""CLI 入口点"""
import sys
import argparse


def main(args=None):
    """主入口函数"""
    if args is None:
        args = sys.argv[1:]

    parser = argparse.ArgumentParser(description='aitext CLI')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # serve 命令
    serve_parser = subparsers.add_parser('serve', help='启动 API 服务器')
    serve_parser.add_argument('--host', default='127.0.0.1', help='监听地址')
    serve_parser.add_argument('--port', type=int, default=8005, help='监听端口')
    serve_parser.add_argument('--reload', action='store_true', help='开启热重载')

    parsed_args = parser.parse_args(args)

    if parsed_args.command == 'serve':
        import uvicorn
        from .interfaces.main import app

        _port = parsed_args.port
        _host = parsed_args.host

        # 端口被占用时自动杀掉占用进程
        import socket as _socket
        def _port_in_use(p):
            with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                return s.connect_ex(("127.0.0.1", p)) == 0

        if _port_in_use(_port):
            import subprocess as _sp, platform as _pl, time as _t
            _system = _pl.system()
            _pid = None
            try:
                if _system == "Windows":
                    r = _sp.run(["netstat", "-ano"], capture_output=True, text=True, timeout=10)
                    for line in r.stdout.splitlines():
                        parts = line.split()
                        if len(parts) >= 5 and f":{_port}" in parts[1] and parts[3] == "LISTENING":
                            try:
                                _pid = int(parts[4]); break
                            except ValueError:
                                pass
                    if _pid:
                        print(f"[aitext] 端口 {_port} 被占用 (PID={_pid})，正在释放...")
                        _sp.run(["taskkill", "/PID", str(_pid), "/T", "/F"], capture_output=True)
                else:
                    r = _sp.run(["lsof", "-ti", f"TCP:{_port}", "-sTCP:LISTEN"],
                                capture_output=True, text=True, timeout=10)
                    _pid_str = r.stdout.strip().split("\n")[0]
                    if _pid_str:
                        _pid = int(_pid_str)
                        print(f"[aitext] 端口 {_port} 被占用 (PID={_pid})，正在释放...")
                        import os as _os, signal as _sig
                        _os.kill(_pid, _sig.SIGTERM)
            except Exception as _e:
                print(f"[aitext] 释放端口失败: {_e}")
            # 等待端口释放
            for _ in range(15):
                if not _port_in_use(_port):
                    print(f"[aitext] 端口 {_port} 已释放")
                    break
                _t.sleep(0.3)
            else:
                print(f"[aitext] 警告：端口 {_port} 仍被占用，启动可能失败")

        uvicorn.run(
            app,
            host=_host,
            port=_port,
            reload=parsed_args.reload
        )
    else:
        parser.print_help()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
