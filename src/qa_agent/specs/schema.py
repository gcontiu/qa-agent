from pydantic import BaseModel, Field


class Requirement(BaseModel):
    id: str
    title: str
    priority: str = "medium"
    given: str
    when_: str | None = Field(None, alias="when")
    then: str
    tags: list[str] = []
    fixture: str | None = None

    model_config = {"populate_by_name": True}

    def to_executor_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority,
            "given": self.given,
            "when": self.when_ or "",
            "then": self.then,
        }


class SpecConfig(BaseModel):
    name: str
    version: str = "1.0"
    target_type: str = "web"
    environments: dict[str, str] = {}
    default_environment: str = "prod"
    context: str = ""

    def get_url(self, env: str | None = None) -> str:
        key = env or self.default_environment
        if key not in self.environments:
            raise ValueError(
                f"Environment '{key}' not found. Available: {list(self.environments)}"
            )
        return self.environments[key]


class SpecBundle(BaseModel):
    config: SpecConfig
    requirements: list[Requirement]
    source_dir: str = ""
