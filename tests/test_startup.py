from unittest.mock import Mock, patch

import main


def test_default_startup_does_not_start_simulator():
    with patch.object(main, "_launch_desktop", return_value=0) as launch, patch.object(main, "threading") as threading:
        assert main.main([]) == 0
    launch.assert_called_once()
    threading.Thread.assert_not_called()


def test_development_simulator_requires_explicit_switch():
    with patch.object(main, "_launch_desktop", return_value=0), patch.object(main, "threading") as threading:
        assert main.main(["--dev-simulator"]) == 0
    threading.Thread.assert_called_once_with(target=main._start_kme_server, daemon=True, name="qumail-dev-simulator")
    threading.Thread.return_value.start.assert_called_once()


def test_simulator_status_does_not_claim_real_qkd():
    from kme.virtual_node import app
    response = app.test_client().get("/api/v1/status")
    assert response.json["provenance"] == "simulated-csprng"
    assert response.json["production_ready"] is False
    assert "simulator" in response.json["node"].lower()
