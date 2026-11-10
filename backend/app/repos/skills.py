"""Skills: persistence + import from skills.sh (via official API or GitHub)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Skill, utcnow
from app.repos.errors import UnknownRefs
from app.runtime.models import (
    SLUG_RE,
    SkillCreate,
    SkillDetail,
    SkillLocalFile,
    SkillLocalImportResult,
    SkillLocalImportSkipped,
    SkillOut,
    SkillUpdate,
)
from app.runtime.slugs import slugify
from app.settings import get_settings

GITHUB_API = "https://api.github.com"
SKILL_FILE = "SKILL.md"
MAX_FILES = 25
MAX_FILE_BYTES = 64 * 1024
MAX_TOTAL_BYTES = 512 * 1024
MAX_LOCAL_SKILLS = 50
MAX_LOCAL_DEPTH = 5


def _client() -> httpx.AsyncClient:
    settings = get_settings()
    headers = {"User-Agent": "ai-agents/0.1", "Accept": "application/vnd.github+json"}
    token = (settings.github_token or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers)


def parse_source(value: str) -> tuple[str, str, str]:
    """Accept `https://skills.sh/owner/repo/skill`, `https://www.skills.sh/...`, `owner/repo/skill`.

    Returns (source, slug, source_id). Only GitHub-backed sources are supported for import.
    """
    raw = value.strip()
    if not raw:
        raise ValueError("url is required")
    if "://" in raw:
        parsed = urlparse(raw)
        if parsed.hostname not in {"skills.sh", "www.skills.sh"}:
            raise ValueError("only skills.sh URLs are supported")
        parts = [part for part in parsed.path.split("/") if part]
    else:
        parts = [part for part in raw.split("/") if part]
    if len(parts) < 3:
        raise ValueError(
            "expected https://skills.sh/<owner>/<repo>/<skill> (well-known sources are not supported)"
        )
    source = f"{parts[0]}/{parts[1]}"
    slug = parts[2]
    return source, slug, f"{source}/{slug}"


def _frontmatter(content: str) -> dict[str, str]:
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end < 0:
        return {}
    block = content[3:end]
    data: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition(":")
            data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _guess_description(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "---", "<!--", "|")):
            continue
        if re.match(r"^[a-zA-Z_-]+:\s", stripped):
            continue
        return stripped[:300]
    return ""


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    return slug[:60] or "skill"


async def _github_skill(
    source: str, slug: str
) -> tuple[str, str, str, list[dict[str, str]], str]:
    """Fetch SKILL.md + sibling files for `owner/repo` skill folder."""
    async with _client() as client:
        repo = await client.get(f"{GITHUB_API}/repos/{source}")
        if repo.status_code == 404:
            raise ValueError(f"repository not found: {source}")
        repo.raise_for_status()
        branch = repo.json().get("default_branch") or "main"

        tree_response = await client.get(
            f"{GITHUB_API}/repos/{source}/git/trees/{branch}",
            params={"recursive": "1"},
        )
        tree_response.raise_for_status()
        tree = tree_response.json().get("tree") or []

        candidates = [
            item["path"]
            for item in tree
            if item.get("type") == "blob"
            and item["path"].endswith(f"/{SKILL_FILE}")
            and item["path"].split("/")[-2] == slug
        ]
        if not candidates:
            raise ValueError(f"skill {slug!r} not found in {source}")
        skill_path = sorted(candidates, key=len)[0]
        folder = skill_path.rsplit("/", 1)[0]

        blobs = [
            item
            for item in tree
            if item.get("type") == "blob" and item["path"].startswith(folder + "/")
        ]
        blobs.sort(key=lambda item: (item["path"] != skill_path, len(item["path"])))
        files: list[dict[str, str]] = []
        total = 0
        for item in blobs[:MAX_FILES]:
            if item.get("size", 0) > MAX_FILE_BYTES or total >= MAX_TOTAL_BYTES:
                continue
            raw = await client.get(
                f"https://raw.githubusercontent.com/{source}/{branch}/{item['path']}"
            )
            if raw.status_code != 200:
                continue
            text = raw.text
            total += len(text.encode("utf-8"))
            files.append(
                {"path": item["path"][len(folder) + 1 :], "contents": text}
            )

    skill_md = next((item["contents"] for item in files if item["path"] == SKILL_FILE), "")
    if not skill_md:
        raise ValueError(f"{SKILL_FILE} is empty for {source}/{slug}")
    meta = _frontmatter(skill_md)
    name = meta.get("name") or slug
    description = meta.get("description") or _guess_description(skill_md)
    return name, description, skill_md, files, branch


async def _official_skill(
    source_id: str,
) -> tuple[str, str, str, list[dict[str, str]]] | None:
    """Use the skills.sh API when a Vercel OIDC token is configured."""
    token = (get_settings().skills_sh_token or "").strip()
    if not token:
        return None
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(
            f"https://skills.sh/api/v1/skills/{source_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code != 200:
            return None
        data = response.json()
    files = [
        {"path": item["path"], "contents": item["contents"]}
        for item in (data.get("files") or [])
        if isinstance(item.get("contents"), str)
    ]
    skill_md = next(
        (item["contents"] for item in files if item["path"].endswith(SKILL_FILE)), ""
    )
    if not skill_md:
        return None
    meta = _frontmatter(skill_md)
    return (
        meta.get("name") or data.get("slug") or "skill",
        meta.get("description") or _guess_description(skill_md),
        skill_md,
        files,
    )


def _normalize_skill_files(raw: list[Any] | None) -> list[dict[str, str]]:
    """Привести файлы к канону `{path, contents}` (старые local-импорты писали `content`)."""
    files: list[dict[str, str]] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        text = item.get("contents")
        if not isinstance(text, str):
            text = item.get("content")
        if not isinstance(text, str):
            text = ""
        files.append({"path": path, "contents": text})
    return files


def to_out(skill: Skill, *, detail: bool = False) -> SkillOut | SkillDetail:
    payload = dict(
        id=skill.id,
        slug=skill.slug,
        name=skill.name,
        description=skill.description or "",
        source=skill.source,
        source_id=skill.source_id,
        source_url=skill.source_url,
        hash=skill.hash,
        created_at=skill.created_at,
        updated_at=skill.updated_at,
    )
    if detail:
        return SkillDetail(
            **payload,
            content=skill.content or "",
            files=_normalize_skill_files(list(skill.files or [])),
        )
    return SkillOut(**payload)


async def list_skills(session: AsyncSession, *, q: str | None = None) -> list[Skill]:
    stmt = select(Skill)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(Skill.name.ilike(pattern) | Skill.slug.ilike(pattern))
    stmt = stmt.order_by(Skill.updated_at.desc())
    return list((await session.execute(stmt)).scalars())


async def get_skill(session: AsyncSession, ref: str) -> Skill | None:
    stmt = select(Skill).where((Skill.id == ref) | (Skill.slug == ref))
    return (await session.execute(stmt)).scalars().first()


def _content_hash(content: str) -> str:
    return hashlib.sha256((content or "").encode("utf-8")).hexdigest()


def _resolve_slug(requested: str | None, name: str) -> str:
    candidate = (requested or "").strip().lower() or slugify(name) or _slugify(name)
    if not SLUG_RE.match(candidate):
        raise ValueError("slug must match ^[a-z0-9][a-z0-9-]{1,62}$")
    return candidate


async def create_manual(
    session: AsyncSession, *, data: SkillCreate, created_by: str
) -> Skill:
    """Свой навык (source=manual): тот же формат SKILL.md, что и у skills.sh."""
    slug = _resolve_slug(data.slug, data.name)
    existing = (
        await session.execute(select(Skill.id).where(Skill.slug == slug))
    ).first()
    if existing is not None:
        raise ValueError(f"навык со slug {slug!r} уже существует")
    skill = Skill(
        slug=slug,
        name=data.name.strip(),
        description=data.description.strip(),
        source="manual",
        content=data.content,
        files=[],
        hash=_content_hash(data.content),
        created_by=created_by,
    )
    session.add(skill)
    await session.commit()
    await session.refresh(skill)
    return skill


async def update_manual(
    session: AsyncSession, skill: Skill, data: SkillUpdate
) -> Skill:
    if skill.source != "manual":
        raise PermissionError("импортированный навык редактируется только повторным импортом")
    if data.name is not None:
        skill.name = data.name.strip()
    if data.description is not None:
        skill.description = data.description.strip()
    if data.content is not None:
        skill.content = data.content
        skill.hash = _content_hash(data.content)
    skill.updated_at = utcnow()
    await session.commit()
    await session.refresh(skill)
    return skill


async def delete_skill(session: AsyncSession, skill: Skill) -> None:
    await session.delete(skill)
    await session.commit()


async def import_skill(
    session: AsyncSession, *, url: str, created_by: str
) -> tuple[Skill, bool]:
    """Import (or refresh) a skill. Returns (skill, created)."""
    source, slug, source_id = parse_source(url)
    official = await _official_skill(source_id)
    if official is not None:
        name, description, content, files = official
    else:
        name, description, content, files, _branch = await _github_skill(source, slug)

    digest = hashlib.sha256(
        json.dumps(files, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

    existing = (
        await session.execute(select(Skill).where(Skill.source_id == source_id))
    ).scalars().first()
    if existing is not None:
        existing.name = name
        existing.description = description
        existing.content = content
        existing.files = files
        existing.hash = digest
        existing.source_url = f"https://skills.sh/{source_id}"
        existing.updated_at = utcnow()
        await session.commit()
        await session.refresh(existing)
        return existing, False

    local_slug = _slugify(slug)
    taken = (await session.execute(select(Skill.id).where(Skill.slug == local_slug))).first()
    if taken is not None:
        local_slug = f"{local_slug[:54]}-{digest[:6]}"

    skill = Skill(
        slug=local_slug,
        name=name,
        description=description,
        source="skills.sh",
        source_id=source_id,
        source_url=f"https://skills.sh/{source_id}",
        hash=digest,
        content=content,
        files=files,
        created_by=created_by,
    )
    session.add(skill)
    await session.commit()
    await session.refresh(skill)
    return skill, True


async def resolve_skill_refs(session: AsyncSession, names: list[str]) -> list[Skill]:
    if not names:
        return []
    stmt = select(Skill).where(Skill.slug.in_(names))
    rows = {row.slug: row for row in (await session.execute(stmt)).scalars()}
    missing = [name for name in names if name not in rows]
    if missing:
        raise UnknownRefs(f"unknown skills: {', '.join(sorted(missing))}")
    return [rows[name] for name in names]


def skill_definition(skill: Skill) -> dict[str, Any]:
    return {
        "slug": skill.slug,
        "name": skill.name,
        "description": skill.description or "",
        "content": skill.content or "",
    }


async def search_remote(q: str, limit: int = 20) -> list[dict[str, Any]] | None:
    """skills.sh search requires a Vercel OIDC token (SKILLS_SH_TOKEN)."""
    token = (get_settings().skills_sh_token or "").strip()
    if not token:
        return None
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        response = await client.get(
            "https://skills.sh/api/v1/skills/search",
            params={"q": q, "limit": max(1, min(limit, 50))},
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code != 200:
            return None
        return list(response.json().get("data") or [])


def _assert_import_path(raw: str) -> Path:
    """Resolve path and ensure it stays under configured import roots."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("path is required")
    target = Path(text).expanduser().resolve()
    roots = get_settings().skills_import_root_list
    if not roots:
        raise ValueError("SKILLS_IMPORT_ROOTS / STORAGE_PATH is not configured")
    allowed = False
    for root_raw in roots:
        root = Path(root_raw).expanduser().resolve()
        try:
            if target == root or target.is_relative_to(root):
                allowed = True
                break
        except (OSError, ValueError):
            continue
    if not allowed:
        raise ValueError(
            "path is outside allowed import roots "
            f"({', '.join(roots)}); mount the folder into STORAGE_PATH or set SKILLS_IMPORT_ROOTS"
        )
    if not target.exists():
        raise ValueError(f"path not found: {target}")
    return target


def _read_text_file(path: Path) -> str:
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"file too large (>{MAX_FILE_BYTES} bytes): {path.name}")
    return data.decode("utf-8")


def _discover_skill_mds(root: Path) -> list[Path]:
    """Find SKILL.md under a folder (or the file itself if it is a markdown skill)."""
    if root.is_file():
        if root.name.upper() == SKILL_FILE.upper() or root.suffix.lower() == ".md":
            return [root]
        raise ValueError("expected a SKILL.md / .md file or a directory with skills")
    found: list[Path] = []
    for path in sorted(root.rglob(SKILL_FILE)):
        if not path.is_file():
            continue
        try:
            depth = len(path.relative_to(root).parts)
        except ValueError:
            continue
        if depth > MAX_LOCAL_DEPTH:
            continue
        found.append(path)
        if len(found) >= MAX_LOCAL_SKILLS:
            break
    if not found:
        # Single-level: any *.md directly in folder (or one level of subfolders).
        for path in sorted(root.glob("*.md")):
            if path.is_file():
                found.append(path)
        for path in sorted(root.glob("*/*.md")):
            if path.is_file() and path.name.upper() == SKILL_FILE.upper():
                found.append(path)
        found = found[:MAX_LOCAL_SKILLS]
    if not found:
        raise ValueError(f"no SKILL.md found under {root}")
    return found


def _sibling_files(skill_md: Path) -> list[dict[str, str]]:
    folder = skill_md.parent
    files: list[dict[str, str]] = []
    total = 0
    for child in sorted(folder.iterdir()):
        if not child.is_file() or child.name == skill_md.name:
            continue
        if child.suffix.lower() not in {".md", ".txt", ".json", ".yaml", ".yml", ".toml"}:
            continue
        try:
            raw = child.read_bytes()
        except OSError:
            continue
        if len(raw) > MAX_FILE_BYTES or total + len(raw) > MAX_TOTAL_BYTES:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        files.append({"path": child.name, "contents": text})
        total += len(raw)
        if len(files) >= MAX_FILES:
            break
    return files


def _meta_from_content(content: str, *, fallback_slug: str) -> tuple[str, str, str]:
    meta = _frontmatter(content)
    name = (meta.get("name") or fallback_slug).strip() or fallback_slug
    description = (meta.get("description") or "").strip() or _guess_description(content)
    slug_src = meta.get("slug") or fallback_slug
    return name, description, _slugify(slug_src)


def _entries_to_skill_groups(
    entries: list[SkillLocalFile],
) -> list[tuple[str, str, list[dict[str, str]]]]:
    """Group uploaded files by skill folder; primary file is SKILL.md or sole .md."""
    by_dir: dict[str, list[SkillLocalFile]] = {}
    for entry in entries:
        rel = entry.path.replace("\\", "/").lstrip("/")
        if ".." in Path(rel).parts:
            raise ValueError(f"invalid relative path: {entry.path}")
        parent = str(Path(rel).parent).replace("\\", "/")
        if parent == ".":
            parent = ""
        by_dir.setdefault(parent, []).append(
            SkillLocalFile(path=rel, content=entry.content)
        )

    groups: list[tuple[str, str, list[dict[str, str]]]] = []
    for parent, files in sorted(by_dir.items()):
        skill_file = next(
            (f for f in files if Path(f.path).name.upper() == SKILL_FILE.upper()),
            None,
        )
        if skill_file is None:
            md_files = [f for f in files if Path(f.path).suffix.lower() == ".md"]
            if len(md_files) == 1:
                skill_file = md_files[0]
            else:
                continue
        siblings = [
            {"path": Path(f.path).name, "contents": f.content}
            for f in files
            if f.path != skill_file.path
        ][:MAX_FILES]
        folder_slug = Path(parent).name if parent else Path(skill_file.path).stem
        groups.append((folder_slug or "skill", skill_file.content, siblings))
        if len(groups) >= MAX_LOCAL_SKILLS:
            break
    if not groups:
        raise ValueError("no SKILL.md / markdown skill files in upload")
    return groups


async def _upsert_local_skill(
    session: AsyncSession,
    *,
    source_id: str,
    fallback_slug: str,
    content: str,
    files: list[dict[str, str]],
    created_by: str,
) -> tuple[Skill, bool]:
    name, description, slug = _meta_from_content(content, fallback_slug=fallback_slug)
    digest = hashlib.sha256(
        json.dumps(
            {"content": content, "files": files},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    existing = (
        await session.execute(select(Skill).where(Skill.source_id == source_id))
    ).scalars().first()
    if existing is not None:
        existing.name = name
        existing.description = description
        existing.content = content
        existing.files = files
        existing.hash = digest
        existing.source = "local"
        existing.source_url = source_id
        existing.updated_at = utcnow()
        await session.commit()
        await session.refresh(existing)
        return existing, False

    local_slug = slug
    taken = (await session.execute(select(Skill.id).where(Skill.slug == local_slug))).first()
    if taken is not None:
        local_slug = f"{local_slug[:54]}-{digest[:6]}"

    skill = Skill(
        slug=local_slug,
        name=name,
        description=description,
        source="local",
        source_id=source_id,
        source_url=source_id,
        hash=digest,
        content=content,
        files=files,
        created_by=created_by,
    )
    session.add(skill)
    await session.commit()
    await session.refresh(skill)
    return skill, True


async def import_from_local(
    session: AsyncSession,
    *,
    path: str | None,
    entries: list[SkillLocalFile] | None,
    created_by: str,
) -> SkillLocalImportResult:
    """Import skills from a server path or browser-uploaded entries."""
    if bool(path and path.strip()) == bool(entries):
        raise ValueError("provide either path or entries")

    groups: list[tuple[str, str, str, list[dict[str, str]]]] = []
    # (source_id, fallback_slug, content, files)
    if entries is not None:
        for folder_slug, content, files in _entries_to_skill_groups(entries):
            source_id = f"local:upload/{folder_slug}"
            groups.append((source_id, folder_slug, content, files))
    else:
        root = _assert_import_path(path or "")
        for skill_md in _discover_skill_mds(root):
            try:
                content = _read_text_file(skill_md)
                files = _sibling_files(skill_md) if skill_md.name.upper() == SKILL_FILE.upper() else []
            except ValueError as exc:
                # Collected after loop via skipped — re-raise empty content differently
                raise ValueError(f"{skill_md}: {exc}") from exc
            rel = (
                str(skill_md.relative_to(root)).replace("\\", "/")
                if skill_md != root and root.is_dir()
                else skill_md.name
            )
            folder_slug = (
                skill_md.parent.name
                if skill_md.name.upper() == SKILL_FILE.upper()
                else skill_md.stem
            )
            source_id = f"local:{root.as_posix().rstrip('/')}/{rel}"
            groups.append((source_id, folder_slug or "skill", content, files))

    created = 0
    updated = 0
    items: list[SkillOut] = []
    skipped: list[SkillLocalImportSkipped] = []
    for source_id, folder_slug, content, files in groups:
        try:
            skill, was_created = await _upsert_local_skill(
                session,
                source_id=source_id,
                fallback_slug=folder_slug,
                content=content,
                files=files,
                created_by=created_by,
            )
        except Exception as exc:  # noqa: BLE001 — one bad skill should not abort the batch
            skipped.append(SkillLocalImportSkipped(path=source_id, reason=str(exc)))
            continue
        items.append(to_out(skill))  # type: ignore[arg-type]
        if was_created:
            created += 1
        else:
            updated += 1

    if not items and skipped:
        raise ValueError(skipped[0].reason)
    if not items:
        raise ValueError("nothing imported")
    return SkillLocalImportResult(
        items=items, created=created, updated=updated, skipped=skipped
    )
