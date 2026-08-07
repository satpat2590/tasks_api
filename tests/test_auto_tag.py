import os, sys
os.environ.setdefault("SUPABASE_URL", "https://fake-project.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "aaa.bbb.ccc")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch, MagicMock
import utils.tags as tags_mod


def _mock_supabase_query(existing=None):
    """Return a mock supabase table chain. `existing` = list of tag rows returned by .execute()."""
    client = MagicMock()
    table = MagicMock()
    for m in ("select", "eq", "is_"):
        getattr(table, m).return_value = table
    table.execute.return_value = MagicMock(data=existing or [])
    client.table.return_value = table
    return client, table


# ---------- fallback order ----------

def _providers(p1, p2, p3):
    return [("p1", p1), ("p2", p2), ("p3", p3)]


@pytest.mark.asyncio
async def test_fallback_to_second_provider_when_first_raises():
    p2 = MagicMock(return_value='["A/B/C"]')
    p3 = MagicMock()
    with patch.object(tags_mod, "TAGGING_PROVIDERS",
                      _providers(MagicMock(side_effect=RuntimeError("down")), p2, p3)), \
         patch.object(tags_mod, "ensure_tag_exists", return_value=42), \
         patch.object(tags_mod.supabase, "table") as tbl:
        tbl.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        result = await tags_mod.auto_tag_task({"title": "t", "category": "mental", "description": ""})
    p2.assert_called_once()
    p3.assert_not_called()
    assert result == [42]


@pytest.mark.asyncio
async def test_fallback_to_third_when_first_two_raise():
    p3 = MagicMock(return_value='["X/Y"]')
    with patch.object(tags_mod, "TAGGING_PROVIDERS",
                      _providers(MagicMock(side_effect=RuntimeError),
                                 MagicMock(side_effect=RuntimeError), p3)), \
         patch.object(tags_mod, "ensure_tag_exists", return_value=7), \
         patch.object(tags_mod.supabase, "table") as tbl:
        tbl.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        result = await tags_mod.auto_tag_task({"title": "t", "category": "mental"})
    p3.assert_called_once()
    assert result == [7]


@pytest.mark.asyncio
async def test_fail_open_returns_empty_when_all_providers_raise():
    boom = MagicMock(side_effect=RuntimeError)
    with patch.object(tags_mod, "TAGGING_PROVIDERS", _providers(boom, boom, boom)), \
         patch.object(tags_mod.supabase, "table") as tbl:
        tbl.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])
        result = await tags_mod.auto_tag_task({"title": "t", "category": "mental"})
    assert result == []


# ---------- ensure_tag_exists ----------

def test_ensure_tag_exists_reuses_existing():
    client, table = _mock_supabase_query(existing=[{"id": 5, "name": "Health"}])
    with patch.object(tags_mod, "supabase", client):
        out = tags_mod.ensure_tag_exists("Health", "physical")
    assert out == 5
    table.insert.assert_not_called()


def test_ensure_tag_exists_creates_hierarchy():
    # nothing exists: every level must be created, parent chain respected
    client = MagicMock()
    table = MagicMock()
    created = []

    table.select.return_value = table
    table.eq.return_value = table
    table.is_.return_value = table
    # select never finds anything
    select_result = MagicMock()
    select_result.data = []
    table.execute.return_value = select_result

    next_id = [10]
    def insert_side_effect(row):
        rid = next_id[0]
        next_id[0] += 1
        created.append(row)
        result = MagicMock()
        result.data = [{"id": rid}]
        return result
    # production code calls supabase.table('tags').insert({...}).execute()
    table.insert.side_effect = lambda row: MagicMock(execute=lambda: insert_side_effect(row))
    client.table.return_value = table

    with patch.object(tags_mod, "supabase", client):
        out = tags_mod.ensure_tag_exists("Health/Exercise/Cardio", "physical")

    assert out == 12
    assert created[0]["parent_tag_id"] is None
    assert created[1]["parent_tag_id"] == 10
    assert created[2]["parent_tag_id"] == 11


# ---------- endpoint-level fail-open (R5 gap closure) ----------

def test_create_task_endpoint_survives_tagging_failure():
    """All tagging providers raising must not fail task creation (fail-open)."""
    from fastapi.testclient import TestClient
    import main as main_mod

    # fake supabase: tasks.insert works, task_tags insert irrelevant
    fake = MagicMock()
    table = MagicMock()
    full_row = {
        "id": 999, "title": "x", "category": "mental", "description": None,
        "priority": 3, "due_date": None, "is_recurring": False,
        "recurrence_pattern": None, "is_active": True,
        "created_at": "2026-07-24T00:00:00+00:00", "updated_at": "2026-07-24T00:00:00+00:00",
        "chain_group": None, "assigned_to": None, "created_by": None,
    }
    table.insert.return_value.execute.return_value = MagicMock(data=[full_row])
    fake.table.return_value = table

    # Public mutation routes now require a bearer token with write scope.
    os.environ["ATMA_HERMES_TOKEN"] = "test-token"
    from utils import auth as auth_mod
    auth_mod.load_agent_registry.cache_clear()

    boom = MagicMock(side_effect=RuntimeError("all providers down"))
    with patch.object(main_mod, "supabase", fake), \
         patch.object(tags_mod, "TAGGING_PROVIDERS", [("a", boom), ("b", boom), ("c", boom)]), \
         patch.object(main_mod, "_resolve_user_id", return_value=None), \
         patch.object(main_mod, "_resolve_user_name", return_value=None):
        client = TestClient(main_mod.app)
        r = client.post(
            "/api/tasks",
            json={"title": "fail-open check", "category": "mental"},
            headers={"Authorization": "Bearer test-token"},
        )
    assert r.status_code in (200, 201), f"endpoint failed: {r.status_code} {r.text[:200]}"
