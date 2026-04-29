import json
from pathlib import Path
from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel, Field

from app.core.response import err, ok
from app.services.workspace_context import (
    get_workspace_mappings,
    get_workspace_root,
    switch_workspace_by_project_name,
)
from app.agent.s_full import SkillLoader, SKILLS_DIR
import app.agent.s_full as s_full

router = APIRouter()


class WorkspaceSwitchRequest(BaseModel):
    project_name: str = Field(..., description="前端目录选择器返回的根目录名")
    top_level_entries: list[str] = Field(default_factory=list, description="前端目录根层级的子项名")


@router.get("/ide/workspace/current")
def current_workspace() -> dict:
    return ok(
        {
            "workspace_root": str(get_workspace_root()),
            "mappings": get_workspace_mappings(),
        }
    )


@router.post("/ide/workspace/switch")
def switch_workspace(req: WorkspaceSwitchRequest) -> dict:
    try:
        data = switch_workspace_by_project_name(
            req.project_name,
            top_level_entries=req.top_level_entries,
        )
        return ok(data)
    except ValueError as exc:
        return err(code=30001, message=str(exc), status=400)


@router.get("/ide/skills")
def list_skills() -> dict:
    skills_dir = s_full.SKILLS_DIR
    loader = SkillLoader(skills_dir)
    result = []
    for name, skill_data in loader.skills.items():
        meta = skill_data.get("meta", {})
        result.append({
            "name": name,
            "description": meta.get("description", ""),
            "path": skill_data.get("path", "")
        })
    return ok({"skills": result})


@router.post("/ide/skills")
async def create_skill(
    name: str = Form(...),
    description: str = Form(...),
    file: UploadFile = File(...)
) -> dict:
    skills_dir = s_full.SKILLS_DIR
    
    skill_folder = skills_dir / name
    if skill_folder.exists():
        return err(code=40001, message=f"Skill '{name}' already exists.", status=400)
    
    skill_folder.mkdir(parents=True, exist_ok=True)
    
    content = await file.read()
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        text_content = content.decode("latin-1", errors="ignore")
        
    md_content = f"---\nname: {name}\ndescription: {description}\n---\n{text_content}"
    skill_md_path = skill_folder / "SKILL.md"
    skill_md_path.write_text(md_content, encoding="utf-8")
    
    # Reload global skills for the agent
    s_full.SKILLS = SkillLoader(s_full.SKILLS_DIR)
    
    return ok({"message": "Skill created successfully", "path": str(skill_md_path)})


@router.get("/ide/tasks")
def list_project_tasks() -> dict:
    # Use relative resolution from this file to find the project root dynamically
    project_root = Path(__file__).resolve().parents[4]
    tasks_dir = project_root / ".tasks"
    
    tasks = []
    if tasks_dir.exists():
        for f in sorted(tasks_dir.glob("task_*.json")):
            try:
                task_data = json.loads(f.read_text(encoding="utf-8"))
                tasks.append(task_data)
            except Exception:
                continue
                
    for t in tasks:
        # Calculate who this task blocks (tasks whose blockedBy includes this task's id)
        t["blocks"] = [other["id"] for other in tasks if t.get("id") in other.get("blockedBy", [])]
        
    return ok({"tasks": tasks})
