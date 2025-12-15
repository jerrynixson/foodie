import subprocess
import sys
import os
import time
import signal

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

    print(f"Starting Foodie Services...")
    print(f"Project Root: {project_root}")
    print(f"Source Path: {src_path}")

    processes = []

    try:
        # 1. Start FastAPI (Uvicorn)
        # We run it as a module 'uvicorn' to ensure we use the same python interpreter
        print("Starting FastAPI server on port 8000...")
        api_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "foodie.api:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
            cwd=project_root, # Run from root so .env files are found
            env=env
        )
        processes.append(api_process)

        # Wait a moment for API to start
        time.sleep(2)

        # 2. Start Streamlit
        print("Starting Streamlit app...")
        streamlit_process = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "src/foodie/pages/streamlit_app.py"],
            cwd=project_root, # Run from root
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
