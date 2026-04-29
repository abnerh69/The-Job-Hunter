import os
import subprocess
import sys


def run_tests():
    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = "dummy"
    env["DASHBOARD_PASSWORD"] = "secret123"
    env["PYTHONPATH"] = "src"

    print("Installing Playwright chromium...")
    subprocess.run(["uv", "run", "playwright", "install", "chromium"], env=env, check=True)

    print("Running tests with coverage...")
    result = subprocess.run(["uv", "run", "pytest", "-v", "--cov"], env=env)

    if result.returncode != 0:
        print(f"Tests failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    else:
        print("Tests passed!")


if __name__ == "__main__":
    run_tests()
