"""Exercise persona validation with only the worker files shipped in the portal image."""
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_portal_image_persona_validation_needs_no_worker_runtime(tmp_path):
    recipe = (ROOT / "docker/tenant-portal-api.Dockerfile").read_text()
    assert "COPY worker/providers/ worker/providers/" in recipe
    (tmp_path / "worker").mkdir()
    shutil.copy(ROOT / "worker/__init__.py", tmp_path / "worker/__init__.py")
    shutil.copytree(ROOT / "worker/providers", tmp_path / "worker/providers", ignore=shutil.ignore_patterns("__pycache__"))
    (tmp_path / "tenant_portal_api").mkdir()
    for name in ("__init__.py", "provider_validation.py"):
        shutil.copy(ROOT / "tenant_portal_api" / name, tmp_path / "tenant_portal_api" / name)
    script = r'''
import sys
sys.path.insert(0, sys.argv[1])
from types import SimpleNamespace
from tenant_portal_api.provider_validation import resolve_agent_provider_fields, ProviderValidationError
conn = SimpleNamespace(execute=lambda *a: SimpleNamespace(fetchone=lambda: ("cartesia", "en", "enabled", True)))
kwargs = dict(agent_language="en", stt_provider="gladia", stt_model="default", stt_options={},
              llm_provider="gemini", llm_model="gemini-3.6-flash", llm_options={"humanization": {"enabled": True}},
              tts_provider="cartesia", tts_voice_id="fixture", tts_options={}, voice_id="fixture")
assert resolve_agent_provider_fields(conn, **kwargs)["llm_options"]["humanization"]["enabled"] is True
try:
    resolve_agent_provider_fields(conn, **{**kwargs, "llm_options": {"humanization": {"enabled": "invalid"}}})
except ProviderValidationError as exc:
    assert exc.code == "invalid_llm_options" and exc.status == 422
else:
    raise AssertionError("invalid persona was accepted")
assert not any(name == "livekit" or name.startswith("livekit.") for name in sys.modules)
assert "worker.humanization" not in sys.modules
'''
    result = subprocess.run([sys.executable, "-B", "-I", "-c", script, str(tmp_path)],
                            capture_output=True, text=True, cwd=tmp_path,
                            env={**os.environ, "CI_UNIT_FORCE_OFFLINE": "1"}, timeout=30)
    assert result.returncode == 0, result.stderr
