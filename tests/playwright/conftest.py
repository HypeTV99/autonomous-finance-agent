import os
import subprocess
import sys
import time
import pytest
import requests
import socket

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0

@pytest.fixture(scope="session")
def http_server():
    """
    Session-scoped deterministic local test server running FastAPI via uvicorn.
    Starts on 127.0.0.1:4173, performs healthcheck polling, and shuts down cleanly on teardown.
    """
    host = "127.0.0.1"
    port = int(os.getenv("TEST_PORT", "4173"))
    base_url = f"http://{host}:{port}"

    server_process = None
    if not is_port_in_use(port, host):
        # Start uvicorn server
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["GOOGLE_CLOUD_PROJECT"] = "test-sandbox-project"
        server_process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app", "--host", host, "--port", str(port)],
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env
        )

        # Polling readiness check
        max_retries = 30
        ready = False
        for _ in range(max_retries):
            try:
                resp = requests.get(f"{base_url}/docs", timeout=1)
                if resp.status_code == 200:
                    ready = True
                    break
            except Exception:
                time.sleep(0.4)

        if not ready:
            if server_process:
                server_process.terminate()
            raise RuntimeError(f"Local test server failed to start on {base_url} within 12 seconds")

    yield base_url

    if server_process:
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()

@pytest.fixture
def ui_base_url(http_server):
    return http_server

@pytest.fixture
def desktop_context(browser, ui_base_url):
    context = browser.new_context(viewport={"width": 1280, "height": 800}, base_url=ui_base_url)
    yield context
    context.close()

@pytest.fixture
def tablet_context(browser, ui_base_url):
    context = browser.new_context(viewport={"width": 768, "height": 1024}, base_url=ui_base_url)
    yield context
    context.close()

@pytest.fixture
def mobile_context(browser, ui_base_url):
    context = browser.new_context(viewport={"width": 375, "height": 667}, base_url=ui_base_url)
    yield context
    context.close()

@pytest.fixture
def maker_context(browser, ui_base_url):
    """
    Isolated authenticated browser context representing the AP Clerk (Maker).
    """
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        base_url=ui_base_url,
        extra_http_headers={"X-User-Role": "ROLE_AP_CLERK"}
    )
    context.add_init_script("localStorage.setItem('YIRE_ROLE', 'ROLE_AP_CLERK'); localStorage.setItem('PAY_SMOOTH_ROLE', 'ROLE_AP_CLERK');")
    yield context
    context.close()

@pytest.fixture
def checker_context(browser, ui_base_url):
    """
    Isolated authenticated browser context representing the Treasury Controller (Checker).
    """
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        base_url=ui_base_url,
        extra_http_headers={"X-User-Role": "ROLE_CONTROLLER"}
    )
    context.add_init_script("localStorage.setItem('YIRE_ROLE', 'ROLE_CONTROLLER'); localStorage.setItem('PAY_SMOOTH_ROLE', 'ROLE_CONTROLLER');")
    yield context
    context.close()

