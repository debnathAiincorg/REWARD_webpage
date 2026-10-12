# Test-wide safety net: no test may ever talk to Microsoft Graph (the app is
# connected to the live production workbook). Any request that reaches
# graph_client's transport fails loudly instead of silently reading or writing
# real data — a test that needs sheet data must use a fake.

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(autouse=True)
def _no_live_graph(monkeypatch):
    import graph_client

    def blocked(*args, **kwargs):
        raise RuntimeError("Live Microsoft Graph call attempted from a test — use a fake instead.")

    monkeypatch.setattr(graph_client, "_request", blocked)
    monkeypatch.setattr(graph_client, "get_access_token", blocked)
