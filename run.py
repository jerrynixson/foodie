import subprocess
import sys
import os
import time
import socket

def find_free_port(preferred: int) -> int:
    """Return preferred port if free, otherwise find a random free one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", preferred)) != 0:
            return preferred  # preferred port is free
    # preferred is taken — let the OS pick one
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

def main():
    # Get the project root directory (where this script is)
    project_root = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.join(project_root, "src")

    # Prepare environment with src in PYTHONPATH
    env = os.environ.copy()
    if "PYTHONPATH" in env:
        env["PYTHONPATH"] = src_path + os.pathsep + env["PYTHONPATH"]
    else:
        env["PYTHONPATH"] = src_path

    # Render (and other hosts) inject $PORT — Streamlit must bind to it so the
    # reverse-proxy can route traffic to the UI.  FastAPI runs on a fixed internal
    # port (8000) that is never directly exposed.
    streamlit_port = os.environ.get("PORT", "8501")
    api_port = str(find_free_port(8000))

    print(f"Starting Foodie Services...")
    print(f"Project Root: {project_root}")
    print(f"Source Path: {src_path}")
    print(f"Streamlit -> port {streamlit_port}  |  FastAPI -> port {api_port} (internal)")

    processes = []

    try:
        # 1. Start FastAPI (Uvicorn) on a fixed internal port
        print(f"Starting FastAPI server on port {api_port}...")
        api_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "foodie.api:app",
             "--host", "0.0.0.0", "--port", api_port],
            cwd=project_root,
            env=env
        )
        processes.append(api_process)

        # Wait a moment for API to start
        time.sleep(2)

        # 2. Start Streamlit bound to $PORT (what Render exposes to the internet)
        print(f"Starting Streamlit app on port {streamlit_port}...")
        streamlit_process = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run",
             "src/foodie/pages/streamlit_app.py",
             "--server.port", streamlit_port,
             "--server.headless", "true"],
            cwd=project_root,
            env=env
        )
        processes.append(streamlit_process)

        print("Services are running. Press Ctrl+C to stop.")
        
        # Monitor processes
        while True:
            time.sleep(1)
            if api_process.poll() is not None:
                print("FastAPI process exited unexpectedly.")
                break
            if streamlit_process.poll() is not None:
                print("Streamlit process exited unexpectedly.")
                break

    except KeyboardInterrupt:
        print("\nStopping services...")
    finally:
        for p in processes:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    p.kill()
        print("Services stopped.")

if __name__ == "__main__":
    main()
