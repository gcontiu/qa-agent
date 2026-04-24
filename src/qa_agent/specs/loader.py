"""
Loads a spec directory into a SpecBundle.
Supports: .feature (Gherkin) and config.yaml.
"""
from pathlib import Path

import yaml

from .schema import Requirement, SpecBundle, SpecConfig

_STEP_KEYWORDS = ("Given", "When", "Then", "And", "But")


# ---------------------------------------------------------------------------
# Gherkin parser (minimal, no Scenario Outline support yet)
# ---------------------------------------------------------------------------

def _classify_steps(steps: list[str]) -> dict:
    """Split a flat list of Gherkin steps into given/when/then strings."""
    given, when, then = [], [], []
    bucket = None

    for step in steps:
        kw = step.split()[0]
        if kw == "Given":
            bucket = given
        elif kw == "When":
            bucket = when
        elif kw == "Then":
            bucket = then
        # And / But → current bucket
        if bucket is not None:
            bucket.append(step.split(None, 1)[1] if " " in step else "")

    join = " AND ".join
    return {
        "given": join(given) if given else "",
        "when": join(when) if when else None,
        "then": join(then) if then else "",
    }


def _parse_tags(tag_tokens: list[str]) -> dict:
    result: dict = {"id": None, "priority": "medium", "fixture": None, "extra": []}
    for tok in tag_tokens:
        tag = tok.lstrip("@")
        if tag.startswith("id:"):
            result["id"] = tag[3:]
        elif tag.startswith("priority:"):
            result["priority"] = tag[9:]
        elif tag.startswith("fixture:"):
            result["fixture"] = tag[8:]
        else:
            result["extra"].append(tag)
    return result


def _parse_feature_file(path: Path) -> list[Requirement]:
    lines = path.read_text("utf-8").splitlines()

    requirements: list[Requirement] = []
    background_steps: list[str] = []
    pending_tags: list[str] = []
    current: dict | None = None
    state = "TOP"  # TOP | BACKGROUND | SCENARIO

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("Feature:"):
            continue

        if line.startswith("Background:"):
            state = "BACKGROUND"
            current = None
            continue

        if line.startswith("@"):
            if current is not None:
                requirements.append(_build_requirement(current, background_steps))
                current = None
            pending_tags = line.split()
            state = "TOP"
            continue

        if line.startswith("Scenario:"):
            if current is not None:
                requirements.append(_build_requirement(current, background_steps))
            title = line[len("Scenario:"):].strip()
            current = {"title": title, "tags": pending_tags[:], "steps": []}
            pending_tags = []
            state = "SCENARIO"
            continue

        if any(line.startswith(kw) for kw in _STEP_KEYWORDS):
            if state == "BACKGROUND":
                background_steps.append(line)
            elif state == "SCENARIO" and current is not None:
                current["steps"].append(line)

    if current is not None:
        requirements.append(_build_requirement(current, background_steps))

    return requirements


def _build_requirement(raw: dict, background_steps: list[str]) -> Requirement:
    tag_info = _parse_tags(raw["tags"])
    all_steps = background_steps + raw["steps"]
    step_parts = _classify_steps(all_steps)

    req_id = tag_info["id"] or raw["title"].upper().replace(" ", "-")[:20]

    return Requirement(
        id=req_id,
        title=raw["title"],
        priority=tag_info["priority"],
        given=step_parts["given"],
        when=step_parts["when"],
        then=step_parts["then"],
        tags=tag_info["extra"],
        fixture=tag_info["fixture"],
    )


# ---------------------------------------------------------------------------
# YAML config loader
# ---------------------------------------------------------------------------

def _parse_config(path: Path) -> SpecConfig:
    data = yaml.safe_load(path.read_text("utf-8"))
    meta = data.get("meta", {})
    target = meta.get("target", {})
    envs_raw = target.get("environments", {})

    environments = {
        name: (env["url"] if isinstance(env, dict) else env)
        for name, env in envs_raw.items()
    }

    return SpecConfig(
        name=meta.get("name", path.parent.name),
        version=str(meta.get("version", "1.0")),
        target_type=target.get("type", "web"),
        environments=environments,
        default_environment=target.get("default_environment", "prod"),
        context=data.get("context", ""),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_spec(spec_dir: Path) -> SpecBundle:
    """Load a spec directory into a SpecBundle."""
    spec_dir = Path(spec_dir)
    if not spec_dir.is_dir():
        raise FileNotFoundError(f"Spec directory not found: {spec_dir}")

    config_path = spec_dir / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing config.yaml in {spec_dir}")

    config = _parse_config(config_path)

    requirements: list[Requirement] = []
    for feature_file in sorted(spec_dir.glob("*.feature")):
        requirements.extend(_parse_feature_file(feature_file))

    return SpecBundle(
        config=config,
        requirements=requirements,
        source_dir=str(spec_dir),
    )
