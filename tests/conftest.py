from __future__ import annotations

import pytest

from sori_with.api.routes.practice import clear_coaching_policies
from sori_with.config import get_settings, get_thresholds
from sori_with.engines.sessionist import clear_sessionist_controllers
from sori_with.storage.demo_stage import demo_stage_store
from sori_with.storage.memory import store
from sori_with.storage.rooms import room_store


@pytest.fixture(autouse=True)
def _reset_global_state(tmp_path):
    """Isolate tests that share process-global in-memory stores."""
    store.clear()
    room_store.clear()
    clear_coaching_policies()
    clear_sessionist_controllers()
    get_settings.cache_clear()
    get_thresholds.cache_clear()
    demo_stage_store.reset(tmp_path / "demo_stage_default")
    yield
    store.clear()
    room_store.clear()
    clear_coaching_policies()
    clear_sessionist_controllers()
    get_settings.cache_clear()
    get_thresholds.cache_clear()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from sori_with.api.main import app

    with TestClient(app) as c:
        yield c
