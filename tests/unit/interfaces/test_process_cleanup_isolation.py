from unittest.mock import Mock

from interfaces.daemon_manager import cleanup_orphan_python_processes


def test_startup_never_enumerates_or_kills_unowned_system_processes(monkeypatch):
    run = Mock(side_effect=RuntimeError('Global process enumeration must not run'))
    monkeypatch.setattr('interfaces.daemon_manager.subprocess.run', run)
    cleanup_orphan_python_processes()
    run.assert_not_called()
