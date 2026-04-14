"""View ALL LLM generation logs in real-time"""
import subprocess
import sys

def main():
    # Run uvicorn and show ALL logs (no filtering)
    cmd = [
        sys.executable, "-m", "uvicorn",
        "interfaces.main:app",
        "--host", "127.0.0.1",
        "--port", "8005",
        "--reload",
        "--log-level", "debug"
    ]
    
    print("=" * 80)
    print("Starting backend with FULL LOG OUTPUT...")
    print("All LLM-related logs will be displayed")
    print("=" * 80)
    print()
    
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        encoding='utf-8',
        errors='replace'
    )
    
    try:
        for line in process.stdout:
            line = line.rstrip()
            # Print all lines
            print(line)
    except KeyboardInterrupt:
        print("\n\nStopping...")
        process.terminate()
        process.wait()

if __name__ == "__main__":
    main()
