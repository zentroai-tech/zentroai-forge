"""Browse forge_integrations library from frontend."""

from __future__ import annotations

from pathlib import Path
import io
import json
import zipfile

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/integrations/library", tags=["integrations"])


class IntegrationLibraryIndex(BaseModel):
    shared_files: list[str]
    docs_files: list[str]
    recipes: dict[str, list[str]]


class IntegrationLibraryFile(BaseModel):
    path: str
    content: str


RECIPE_TOOL_NAME_OVERRIDES: dict[str, str] = {
    "whatsapp_cloud": "whatsapp_send_message",
}


def _library_root() -> Path:
    # backend/src/agent_compiler/routers -> repo root is parents[4]
    return Path(__file__).resolve().parents[4] / "forge_integrations"


def _list_files(root: Path, *, base: Path | None = None) -> list[str]:
    if not root.exists():
        return []
    out: list[str] = []
    rel_base = (base or root).resolve()
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file():
            continue
        if "__pycache__" in file_path.parts:
            continue
        if file_path.suffix in {".pyc", ".pyo"}:
            continue
        out.append(file_path.resolve().relative_to(rel_base).as_posix())
    return out


def _resolve_safe(relative_path: str) -> Path:
    root = _library_root()
    candidate = (root / relative_path).resolve()
    root_resolved = root.resolve()
    if root_resolved not in candidate.parents and candidate != root_resolved:
        raise HTTPException(status_code=400, detail="invalid_path")
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="file_not_found")
    return candidate


def _recipe_tool_name(recipe_id: str) -> str:
    return RECIPE_TOOL_NAME_OVERRIDES.get(recipe_id, recipe_id)


def _build_recipe_zip_bytes(recipe_id: str) -> bytes:
    root = _library_root().resolve()
    recipe_dir = (root / "recipes" / recipe_id).resolve()
    if root not in recipe_dir.parents and recipe_dir != root:
        raise HTTPException(status_code=400, detail="invalid_recipe")
    if not recipe_dir.exists() or not recipe_dir.is_dir():
        raise HTTPException(status_code=404, detail="recipe_not_found")

    tool_name = _recipe_tool_name(recipe_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(recipe_dir.rglob("*")):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(recipe_dir).as_posix()
            data = file_path.read_bytes()

            if rel == "tool.py":
                out_path = f"tools/{tool_name}.py"
            elif rel.startswith("schemas/"):
                schema_file = Path(rel).name
                out_path = f"runtime/schemas/tools/{schema_file}"
            elif rel.startswith("tests/"):
                out_path = f"tests/{Path(rel).name}"
            elif rel == "queries/query_allowlist.json":
                out_path = "tools/queries/query_allowlist.json"
            elif rel == "inbound_gateway_fastapi.py":
                out_path = f"docs/examples/{recipe_id}/inbound_gateway_fastapi.py"
            elif rel == "README.md":
                out_path = f"docs/INTEGRATIONS_{recipe_id.upper()}.md"
            else:
                out_path = f"docs/forge_integrations/{recipe_id}/{rel}"

            zf.writestr(out_path, data)

        install_guide = {
            "recipe": recipe_id,
            "tool_name": tool_name,
            "copy_map": [
                {"from": "tool.py", "to": f"tools/{tool_name}.py"},
                {"from": "schemas/*.json", "to": "runtime/schemas/tools/"},
                {"from": "tests/*.py", "to": "tests/"},
            ],
            "register_in": "runtime/tools/registry.py",
            "allowlist_in": "settings.py FLOW_POLICIES['tool_allowlist']",
        }
        zf.writestr(
            "docs/INTEGRATION_INSTALL_MAP.json",
            json.dumps(install_guide, indent=2, ensure_ascii=False).encode("utf-8"),
        )
    buffer.seek(0)
    return buffer.getvalue()


def _build_library_zip_bytes() -> bytes:
    root = _library_root().resolve()
    if not root.exists():
        raise HTTPException(status_code=404, detail="library_not_found")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file():
                continue
            if "__pycache__" in file_path.parts:
                continue
            if file_path.suffix in {".pyc", ".pyo"}:
                continue
            zf.writestr(file_path.relative_to(root).as_posix(), file_path.read_bytes())
    buffer.seek(0)
    return buffer.getvalue()


@router.get("", response_model=IntegrationLibraryIndex)
async def list_integrations_library() -> IntegrationLibraryIndex:
    root = _library_root()
    if not root.exists():
        raise HTTPException(status_code=404, detail="library_not_found")

    recipes_dir = root / "recipes"
    recipes: dict[str, list[str]] = {}
    if recipes_dir.exists():
        for recipe_dir in sorted(recipes_dir.iterdir()):
            if not recipe_dir.is_dir():
                continue
            recipes[recipe_dir.name] = _list_files(recipe_dir, base=root)

    docs_files: list[str] = []
    for name in ("README.md",):
        p = root / name
        if p.exists() and p.is_file():
            docs_files.append(name)

    return IntegrationLibraryIndex(
        shared_files=_list_files(root / "shared", base=root),
        docs_files=docs_files,
        recipes=recipes,
    )


@router.get("/file", response_model=IntegrationLibraryFile)
async def get_integrations_library_file(
    path: str = Query(..., min_length=1, description="Path relative to forge_integrations root"),
) -> IntegrationLibraryFile:
    file_path = _resolve_safe(path)
    root = _library_root().resolve()
    return IntegrationLibraryFile(
        path=file_path.relative_to(root).as_posix(),
        content=file_path.read_text(encoding="utf-8"),
    )


@router.get("/export")
async def export_integrations_library_zip(
    recipe: str | None = Query(default=None, description="Optional recipe id for plug-and-play zip"),
) -> StreamingResponse:
    if recipe:
        payload = _build_recipe_zip_bytes(recipe)
        filename = f"forge_integration_{recipe}.zip"
    else:
        payload = _build_library_zip_bytes()
        filename = "forge_integrations_library.zip"

    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
