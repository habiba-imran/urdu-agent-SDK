"""Start an isolated local browser voice test stack; never overwrite env files.

--check validates the setup without starting processes or contacting providers.
--start registers a distinct LiveKit worker; provider usage begins with your calls.
Ctrl+C stops only the child processes started by this launcher.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def port_open(port):
    with socket.socket() as connection:
        connection.settimeout(.3)
        return connection.connect_ex(('127.0.0.1', port)) == 0


def settings(agent_name):
    from dotenv import dotenv_values
    from worker.development import configure, validate_installed
    env = {**os.environ}
    for key, value in dotenv_values(ROOT / '.env.local').items():
        if value is not None:
            env.setdefault(key, value)
    backend = {key: value for key, value in dotenv_values(ROOT / 'client-integration-test/backend/.env').items() if value is not None}
    frontend = {key: value for key, value in dotenv_values(ROOT / 'client-integration-test/frontend/.env').items() if value is not None}
    for name in ['UVA_TENANT_ID', 'UVA_HMAC_SECRET', 'UVA_PUBLISHABLE_KEY', 'UVA_API_BASE_URL']:
        if not backend.get(name):
            raise ValueError(f'Configure {name} in the existing demo backend .env first.')
    for name in ['LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET', 'SUPABASE_DB_URL', 'ANTHROPIC_API_KEY']:
        if not env.get(name):
            raise ValueError(f'Configure {name} in the existing root .env.local first.')
    configure(agent_name, environ=env)
    validate_installed()
    env.update(UVA_ENV='development', PYTHONUNBUFFERED='1',
               CP_ALLOWED_ORIGINS='http://localhost:5174,http://127.0.0.1:5174',
               CP_TENANT_SECRETS=json.dumps({backend['UVA_TENANT_ID']: backend['UVA_HMAC_SECRET']}),
               UVA_WORKER_HEALTH_PORT='0')
    backend_env = {**env, **backend, 'PORT': '13100', 'UVA_CONTROL_PLANE_URL': 'http://127.0.0.1:18100',
                   'HOST_PUBLIC_BASE_URL': 'http://localhost:13100',
                   'HOST_ALLOWED_ORIGINS': 'http://localhost:5174,http://127.0.0.1:5174'}
    frontend_env = {**env, **frontend, 'VITE_UVA_PUBLISHABLE_KEY': backend['UVA_PUBLISHABLE_KEY'],
                    'VITE_UVA_SESSION_ENDPOINT': 'http://localhost:13100/api/voice/session',
                    'VITE_UVA_REFRESH_ENDPOINT': 'http://localhost:13100/api/voice/session/refresh'}
    return env, backend_env, frontend_env


def is_demo_ui():
    try:
        with urlopen('http://localhost:5174', timeout=2) as response:
            demo = 'AwaazLabs UVA' in response.read(10000).decode('utf-8', errors='replace')
        with urlopen('http://localhost:5174/src/main.ts', timeout=2) as response:
            source = response.read(100000).decode('utf-8', errors='replace')
        return demo and 'voiceTest' in source and '13100' in source
    except Exception:
        return False


def main(args):
    env, backend_env, frontend_env = settings(args.agent_name)
    node = shutil.which('node')
    vite = ROOT / 'client-integration-test/frontend/node_modules/vite/bin/vite.js'
    if not node or not vite.is_file():
        raise ValueError('Install the demo Node dependencies first (npm.cmd run install:all).')
    if any(port_open(port) for port in [13100, 18100]):
        raise ValueError('Test port 13100 or 18100 is in use. Stop the previous owned test launcher before starting another.')
    reuse_ui = port_open(5174)
    if reuse_ui and not is_demo_ui():
        raise ValueError('Port 5174 belongs to another app. Free that port; this launcher will not stop it.')
    print(json.dumps({'setup': 'ready', 'dispatch': args.agent_name,
                      'url': 'http://localhost:5174/?voiceTest=local', 'reuse_existing_demo_ui': reuse_ui,
                      'control_plane': 'http://127.0.0.1:18100', 'backend': 'http://localhost:13100',
                      'env_files_modified': False}, indent=2), flush=True)
    if not args.start:
        return
    directory = ROOT / 'tmp' / 'voice-experience-test' / time.strftime('%Y%m%d-%H%M%S')
    directory.mkdir(parents=True, exist_ok=True)
    processes, logs = [], []
    commands = [
        ('control-plane', [sys.executable, '-m', 'worker.development', 'control-plane', '--agent-name', args.agent_name, '--port', '18100'], ROOT, env),
        ('worker', [sys.executable, '-m', 'worker.development', 'worker', '--agent-name', args.agent_name], ROOT, env),
        ('backend', [node, 'src/server.js'], ROOT / 'client-integration-test/backend', backend_env),
    ]
    if not reuse_ui:
        commands.append(('frontend', [node, str(vite), '--host', '127.0.0.1', '--port', '5174'], ROOT / 'client-integration-test/frontend', frontend_env))
    try:
        for label, command, cwd, child_env in commands:
            log = (directory / (label+'.log')).open('w', encoding='utf-8')
            logs.append(log)
            child = subprocess.Popen(command, cwd=cwd, env=child_env, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                start_new_session=os.name != 'nt')
            processes.append((label, child))
        print(f'Owned test processes started. Logs: {directory}', flush=True)
        print('Open the URL above, choose Claude and enable Humanized speech on your test agent. Ctrl+C stops this stack.', flush=True)
        while True:
            for label, child in processes:
                if child.poll() is not None:
                    raise RuntimeError(f'{label} exited; inspect its local log in {directory}')
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for _, child in reversed(processes):
            if child.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    import signal
                    os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
        for log in logs:
            log.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent-name', default='uva-humanization-dev-habiba-final')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--check', action='store_true')
    action.add_argument('--start', action='store_true')
    args = parser.parse_args()
    try:
        main(args)
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
