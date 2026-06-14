"""field-stack tooling tests - gen-certs.sh idempotence + stop-field.sh usage.

shell-only; no fieldhub app surface. openssl-dependent cases self-skip when
openssl is absent (mirrors test_media_return_e2e's reachability skip).
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "field-hub"
GEN_CERTS = SCRIPTS_DIR / "gen-certs.sh"
STOP_FIELD = SCRIPTS_DIR / "stop-field.sh"

HAS_BASH = shutil.which("bash") is not None
HAS_OPENSSL = shutil.which("openssl") is not None
HAS_SHELLCHECK = shutil.which("shellcheck") is not None

requires_bash = pytest.mark.skipif(not HAS_BASH, reason="bash not on PATH")
requires_openssl = pytest.mark.skipif(not HAS_OPENSSL, reason="openssl not on PATH")


def _run(args, **kwargs):
    """run a subprocess capturing text stdout/stderr, no implicit raise."""
    return subprocess.run(args, capture_output=True, text=True, **kwargs)


# ---------------------------------------------------------------------------
# static checks - syntax always, shellcheck when present
# ---------------------------------------------------------------------------
@requires_bash
@pytest.mark.parametrize("script", [GEN_CERTS, STOP_FIELD])
def test_script_syntax_ok(script):
    """bash -n parses both field scripts."""
    result = _run(["bash", "-n", str(script)])
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(not HAS_SHELLCHECK, reason="shellcheck not on PATH")
@pytest.mark.parametrize("script", [GEN_CERTS, STOP_FIELD])
def test_script_shellcheck_clean(script):
    """shellcheck finds no errors in the field scripts."""
    result = _run(["shellcheck", "--severity=error", str(script)])
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# gen-certs.sh - idempotent CA reuse, service certs, failure paths
# ---------------------------------------------------------------------------
@requires_bash
@requires_openssl
def test_gen_certs_reuses_ca_and_writes_service_certs(tmp_path):
    """second run reuses the CA byte-for-byte and re-emits all service certs."""
    env = {"PATH": os.environ["PATH"], "CERTS_DIR": str(tmp_path)}

    first = _run(["bash", str(GEN_CERTS), "192.168.8.100"], env=env)
    assert first.returncode == 0, first.stderr

    ca_crt = tmp_path / "ca" / "ca.crt"
    ca_key = tmp_path / "ca" / "ca.key"
    crt_bytes, key_bytes = ca_crt.read_bytes(), ca_key.read_bytes()

    second = _run(["bash", str(GEN_CERTS), "192.168.8.100"], env=env)
    assert second.returncode == 0, second.stderr
    assert "Reusing existing CA" in second.stdout

    # CA must be untouched - regenerating would invalidate provisioned RCs
    assert ca_crt.read_bytes() == crt_bytes
    assert ca_key.read_bytes() == key_bytes

    # every service cert present after both runs
    for rel in ("fieldhub/server.crt", "emqx/server.crt", "minio/public.crt"):
        assert (tmp_path / rel).is_file(), f"missing {rel}"


@requires_bash
@requires_openssl
def test_gen_certs_rejects_bad_hub_ip(tmp_path):
    """non-IPv4 HUB_IP exits nonzero with a clear stderr message."""
    env = {"PATH": os.environ["PATH"], "CERTS_DIR": str(tmp_path)}
    result = _run(["bash", str(GEN_CERTS), "not-an-ip"], env=env)
    assert result.returncode != 0
    assert "IPv4 address" in result.stderr


# ---------------------------------------------------------------------------
# stop-field.sh - usage + arg validation (docker not exercised in ci)
# ---------------------------------------------------------------------------
@requires_bash
def test_stop_field_help_exits_zero():
    """--help prints usage and exits 0."""
    result = _run(["bash", str(STOP_FIELD), "--help"])
    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "--wipe" in result.stdout


@requires_bash
def test_stop_field_rejects_unknown_flag():
    """an unknown argument exits nonzero before touching docker."""
    result = _run(["bash", str(STOP_FIELD), "--bogus"])
    assert result.returncode != 0
    assert "unknown argument" in result.stderr
