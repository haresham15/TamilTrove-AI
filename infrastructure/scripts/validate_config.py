"""Validate checked-in delivery configuration without contacting external services."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
ACTION_REF = re.compile(r"^[-A-Za-z0-9_.]+/[-A-Za-z0-9_./]+@([0-9a-f]{40})$")
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
REQUIRED_ENV_KEYS = {
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "TAMILTROVE_SECRET_KEY",
    "ALLOWED_ORIGINS",
    "NEXT_PUBLIC_API_URL",
    "TAMILTROVE_MODEL_NAME",
    "TAMILTROVE_MODEL_VERSION",
    "TAMILTROVE_RANKING_VERSION",
}


class ValidationError(RuntimeError):
    """Raised when a repository delivery invariant is not satisfied."""


def require(condition: Any, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValidationError(f"{relative(path)} is not valid YAML: {error}") from error


def validate_structured_files() -> tuple[int, int]:
    yaml_files = sorted(
        {
            *ROOT.joinpath(".github").rglob("*.yml"),
            *ROOT.joinpath(".github").rglob("*.yaml"),
            *ROOT.joinpath("infrastructure").rglob("*.yml"),
            *ROOT.joinpath("infrastructure").rglob("*.yaml"),
        }
    )
    json_files = sorted(
        {
            *ROOT.joinpath("infrastructure").rglob("*.json"),
            *ROOT.joinpath("evaluation", "datasets").rglob("*.json"),
            *ROOT.joinpath("evaluation", "reports").glob("baseline-*.json"),
        }
    )
    for path in yaml_files:
        require(load_yaml(path) is not None, f"{relative(path)} is empty")
    for path in json_files:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValidationError(f"{relative(path)} is not valid JSON: {error}") from error
    return len(yaml_files), len(json_files)


def validate_workflows() -> int:
    workflow_dir = ROOT / ".github" / "workflows"
    expected = {"ci.yml", "release.yml", "deploy.yml", "rollback.yml"}
    require(
        expected <= {path.name for path in workflow_dir.glob("*.yml")},
        "delivery workflows are missing",
    )

    workflows = sorted(workflow_dir.glob("*.yml"))
    for path in workflows:
        text = path.read_text(encoding="utf-8")
        document = load_yaml(path)
        require(isinstance(document, dict), f"{relative(path)} must contain a mapping")
        # PyYAML follows YAML 1.1 and may parse the unquoted GitHub key `on` as True.
        require("on" in document or True in document, f"{relative(path)} has no event trigger")
        require(isinstance(document.get("jobs"), dict), f"{relative(path)} has no jobs")
        require(
            "permissions" in document,
            f"{relative(path)} must declare least-privilege permissions",
        )
        require(
            "pull_request_target:" not in text,
            f"{relative(path)} must not execute privileged fork code",
        )

        for match in re.finditer(r"^\s*uses:\s*([^\s#]+)", text, flags=re.MULTILINE):
            reference = match.group(1)
            if reference.startswith(("./", "docker://")):
                continue
            require(
                ACTION_REF.fullmatch(reference),
                f"{relative(path)} uses an action that is not pinned to a full commit: {reference}",
            )

    for name in ("deploy.yml", "rollback.yml"):
        text = (workflow_dir / name).read_text(encoding="utf-8")
        require(
            "environment: ${{ inputs.environment }}" in text,
            f"{name} must use a protected environment selected by the operator",
        )
        require("confirmation:" in text, f"{name} must require explicit operator confirmation")
    return len(workflows)


def validate_compose() -> int:
    path = ROOT / "infrastructure" / "compose.yml"
    document = load_yaml(path)
    require(isinstance(document, dict), "Compose configuration must be a mapping")
    services = document.get("services")
    require(isinstance(services, dict), "Compose configuration has no services")
    required = {
        "database",
        "backend",
        "frontend",
        "redis",
        "prometheus",
        "grafana",
        "otel-collector",
    }
    require(required <= set(services), "Compose is missing a required V2 service")

    for service_name, service in services.items():
        require(isinstance(service, dict), f"Compose service {service_name} must be a mapping")
        image = service.get("image")
        if image:
            require(
                "@sha256:" in image or (":" in image and not image.endswith(":latest")),
                f"Compose service {service_name} must use an explicit image version",
            )
        for port in service.get("ports", []):
            value = port if isinstance(port, str) else str(port.get("published", ""))
            require(
                value.startswith("127.0.0.1:"),
                f"Compose service {service_name} publishes a port beyond loopback: {value}",
            )

    backend_environment = services["backend"].get("environment", {})
    require(
        str(backend_environment.get("DATABASE_URL", "")).startswith("postgresql://"),
        "Compose backend DATABASE_URL must be a psycopg-compatible PostgreSQL DSN",
    )
    require(services["redis"].get("profiles") == ["cache"], "Redis must remain optional")
    for service_name in ("prometheus", "grafana", "otel-collector"):
        require(
            services[service_name].get("profiles") == ["observability"],
            f"{service_name} must remain in the optional observability profile",
        )
    return len(services)


def validate_environment_example() -> int:
    values: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, value = stripped.split("=", 1)
            values[key] = value
    missing = REQUIRED_ENV_KEYS - values.keys()
    require(not missing, f".env.example is missing keys: {', '.join(sorted(missing))}")
    require(
        values["TAMILTROVE_ENV"] == "development",
        ".env.example must remain explicitly development-only",
    )
    return len(values)


def validate_markdown_links() -> int:
    markdown_files = sorted(
        {
            ROOT / "README.md",
            ROOT / "DEPLOYMENT.md",
            *ROOT.joinpath("docs").rglob("*.md"),
            *ROOT.joinpath("infrastructure").rglob("*.md"),
            *ROOT.joinpath("evaluation").rglob("*.md"),
            *ROOT.joinpath("backend", "migrations").rglob("*.md"),
        }
    )
    for path in markdown_files:
        text = path.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip().strip("<>").split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            # A link title follows a quoted or parenthesized path; this repository does not
            # use titles, but splitting keeps the validator conservative.
            target = target.split(' "', 1)[0].split(" '", 1)[0]
            destination = (path.parent / target).resolve()
            try:
                destination.relative_to(ROOT.resolve())
            except ValueError as error:
                raise ValidationError(
                    f"{relative(path)} links outside the repository: {raw_target}"
                ) from error
            require(destination.exists(), f"{relative(path)} has a broken link: {raw_target}")
    return len(markdown_files)


def main() -> int:
    try:
        yaml_count, json_count = validate_structured_files()
        workflow_count = validate_workflows()
        service_count = validate_compose()
        env_count = validate_environment_example()
        markdown_count = validate_markdown_links()
    except (OSError, ValidationError) as error:
        print(f"Configuration validation failed: {error}", file=sys.stderr)
        return 1
    print(
        "Configuration validation passed: "
        f"{yaml_count} YAML, {json_count} JSON, {workflow_count} workflows, "
        f"{service_count} Compose services, {env_count} environment keys, "
        f"and {markdown_count} Markdown files"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
