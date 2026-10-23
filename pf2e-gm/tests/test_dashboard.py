from pathlib import Path
from html import unescape

from fastapi.testclient import TestClient

from master.app import PROJECT_ROOT, create_app
from master.registry import discover_tools


def test_dashboard_and_every_tool_page(tmp_path: Path) -> None:
    tools = discover_tools(PROJECT_ROOT / "tools")
    assert len(tools) == 10

    with TestClient(create_app(db_path=tmp_path / "test.sqlite3")) as client:
        dashboard = client.get("/")
        assert dashboard.status_code == 200
        dashboard_html = unescape(dashboard.text)
        assert 'id="dashboard-xp"' in dashboard_html
        for tool in tools:
            assert tool.name in dashboard_html
            assert f'/tools/{tool.slug}' in dashboard_html
            page = client.get(f"/tools/{tool.slug}")
            assert page.status_code == 200
            assert tool.name in unescape(page.text)
            assert tool.purpose in unescape(page.text)
            if tool.slug in {"rules-reference", "dc-helper", "encounter-builder", "monster-reference", "combat-tracker", "conditions", "healing-death", "exploration", "treasure-xp", "adventure-planner"}:
                marker = {"rules-reference": "Search rules", "dc-helper": "Final DC", "encounter-builder": "Total creature XP", "monster-reference": "Quick Add", "combat-tracker": "Next Turn", "conditions": "Apply condition", "healing-death": "Recovery check", "exploration": "Travel calculator", "treasure-xp": "Treasure overview", "adventure-planner": "Adventure Planner"}[tool.slug]
                assert marker in page.text
                assert "Not implemented yet" not in page.text
            else:
                assert "Not implemented yet" in page.text

        assert client.get("/tools/unknown").status_code == 404
        assert client.get("/static/style.css").status_code == 200
        assert client.get("/static/app.js").status_code == 200


def test_new_manifest_is_discovered_without_master_changes(tmp_path: Path) -> None:
    folder = tmp_path / "new-tool"
    folder.mkdir()
    (folder / "tool.json").write_text(
        '{"slug":"new-tool","name":"New Tool","purpose":"A future tool."}',
        encoding="utf-8",
    )
    with TestClient(create_app(db_path=tmp_path / "data.sqlite3", tool_root=tmp_path)) as client:
        assert "New Tool" in client.get("/").text
        assert client.get("/tools/new-tool").status_code == 200
