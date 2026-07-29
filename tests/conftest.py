from __future__ import annotations

import pytest

from sori_with.api.routes.practice import clear_coaching_policies
from sori_with.config import get_settings, get_thresholds
from sori_with.engines.sessionist import clear_sessionist_controllers
from sori_with.storage.memory import store
from sori_with.storage.rooms import room_store


@pytest.fixture(autouse=True)
def _reset_global_state():
    """Isolate tests that share process-global in-memory stores."""
    store.clear()
    room_store.clear()
    clear_coaching_policies()
    clear_sessionist_controllers()
    get_settings.cache_clear()
    get_thresholds.cache_clear()
    yield
    store.clear()
    room_store.clear()
    clear_coaching_policies()
    clear_sessionist_controllers()
    get_settings.cache_clear()
    get_thresholds.cache_clear()
