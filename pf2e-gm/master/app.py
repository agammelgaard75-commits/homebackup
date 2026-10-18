"""FastAPI entry point for the local master dashboard."""

from contextlib import asynccontextmanager
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from master.pages import dashboard, placeholder
from master.registry import discover_tools
from shared.database.storage import initialize_database


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app(db_path: Path | None = None, tool_root: Path | None = None) -> FastAPI:
    database_path = Path(db_path) if db_path is not None else PROJECT_ROOT / "data" / "pf2e.sqlite3"
    tools = discover_tools(Path(tool_root) if tool_root is not None else PROJECT_ROOT / "tools")
    tools_by_slug = {tool.slug: tool for tool in tools}
    tool_modules = []
    for tool in tools:
        if tool.implemented:
            spec = spec_from_file_location(f"pf2e_tool_{tool.slug.replace('-', '_')}", tool.folder / "tool.py")
            if spec is None or spec.loader is None:
                raise RuntimeError(f"Could not load {tool.folder / 'tool.py'}")
            module = module_from_spec(spec)
            spec.loader.exec_module(module)
            tool_modules.append(module)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize_database(database_path)
        for module in tool_modules:
            module.initialize(database_path)
        yield

    app = FastAPI(title="PF2e GM Toolkit", lifespan=lifespan)
    app.state.database_path = database_path
    app.mount("/static", StaticFiles(directory=PROJECT_ROOT / "shared" / "ui"), name="static")
    for module in tool_modules:
        module.register(app, database_path)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return dashboard(tools)

    @app.get("/tools/{slug}", response_class=HTMLResponse)
    def tool_page(slug: str) -> str:
        tool = tools_by_slug.get(slug)
        if tool is None:
            raise HTTPException(status_code=404, detail="Tool not found")
        return placeholder(tool)

    return app


app = create_app()
