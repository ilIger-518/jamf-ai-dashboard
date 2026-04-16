from __future__ import annotations

import importlib.util
import socket
from pathlib import Path


def _load_updater_module():
    module_path = Path(__file__).resolve().parents[1] / "updater.py"
    spec = importlib.util.spec_from_file_location("updater_module", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_is_host_port_in_use_detects_bound_socket() -> None:
    updater = _load_updater_module()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        port = sock.getsockname()[1]
        assert updater._is_host_port_in_use(port) is True


def test_find_free_port_skips_non_docker_host_conflict() -> None:
    updater = _load_updater_module()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        taken_port = sock.getsockname()[1]
        free_port = updater._find_free_port(taken_port, allocated=set(), end=taken_port + 20)
        assert free_port is not None
        assert free_port != taken_port
