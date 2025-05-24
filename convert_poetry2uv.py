#!/usr/bin/env python
"""convert_poetry2uv.py: Convert Poetry pyproject.toml to Uv pyproject.toml."""

import argparse
import re
import sys
from pathlib import Path

import tomlkit as tk

POETRYV2 = False
__version__ = "0.3.0"


def argparser() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="convert_poetry2uv",
        description="Poetry to Uv pyproject conversion",
        epilog="It will move the original pyproject.toml to pyproject.toml.org",
    )
    parser.add_argument("filename")
    parser.add_argument(
        "-n",
        action="store_true",
        help="Do not modify pyproject.toml, instead create pyproject_temp_uv.toml",
    )
    return parser.parse_args()


def version_conversion(version: str) -> str:
    """Convert version to uv format."""
    gt_tilde_version = re.compile(r"[\^~](\d.*)")
    tilde_with_digits_and_star = re.compile(r"^~([\d\.]+)\.\*")
    multi_ver_restrictions = re.compile(r"([<>=!]+)[\s,]*([\d\.\*]+),?")

    if version == "*":
        return ""
    elif (found := tilde_with_digits_and_star.match(version)) or (
        found := gt_tilde_version.match(version)
    ):
        return f">={found[1]}"
    elif (found := multi_ver_restrictions.findall(version)) and len(found) >= 1:
        bundle = ["".join(g) for g in found]
        return ",".join(bundle)
    else:
        print(f"Well, this is an unexpected version\nVersion = {version}\n")
        print("Skipping this version, add it manually.")
    return ""


def authors_maintainers(new_toml: tk.TOMLDocument) -> None:
    """Parse authors and maintainers."""
    project = new_toml["project"]
    user_email = re.compile(r"^(.*) <(.*)>$")
    only_email = re.compile(r"^<(.*)>$")

    if POETRYV2:
        return

    for key in ("authors", "maintainers"):
        if (authors := project.get(key)) and isinstance(authors, list):
            new_authors = tk.array()
            for author in authors:
                if not isinstance(author, str):
                    print(f"Expected string in the list of '{key}', got {type(author)}")
                    continue
                elif found := user_email.match(author):
                    name, email = found.groups()
                    tb = tk.inline_table().add("name", name).add("email", email)
                    new_authors.add_line(tb)
                elif found := only_email.match(author):
                    email = found[1]
                    new_authors.add_line(tk.inline_table().add("email", email))
                elif author:
                    new_authors.add_line(tk.inline_table().add("name", author))

            if new_authors:
                new_authors.add_line(indent="")
                project[key] = new_authors
            else:
                del project[key]


def parse_packages(deps: dict) -> tuple[list[str], dict[str, str], dict[str, str]]:
    """Parse packages."""
    uv_deps: list[str] = []
    uv_deps_optional: dict[str, str] = {}
    uv_deps_source: dict[str, str] = {}
    for name, version in deps.items():
        if name == "python":
            continue

        if isinstance(version, dict):
            if extras := version.get("extras"):
                v = version["version"]
                for i in extras:
                    extra = f"[{i}]"
                    uv_deps.append(f"{name}{extra}{version_conversion(v)}")
            elif version.get("optional"):
                uv_deps_optional[name] = version_conversion(version["version"])
            elif source := version.get("source"):
                uv_deps_source[name] = source
                uv_deps.append(f"{name}{version_conversion(version['version'])}")
            continue

        uv_deps.append(f"{name}{version_conversion(version)}")
    return uv_deps, uv_deps_optional, uv_deps_source


def group_dependencies(new_toml: tk.TOMLDocument, org_toml: tk.TOMLDocument) -> None:
    """Parse group dependencies."""
    if not (groups := org_toml["tool"]["poetry"].get("group")):
        return
    for group, data in groups.items():
        uv_deps, uv_deps_optional, uv_deps_source = parse_packages(data.get("dependencies", {}))
        new_toml["dependency-groups"] = new_toml.get("dependency-groups", tk.table())
        new_toml["dependency-groups"].add(group, uv_deps)

        parse_uv_deps_optional(new_toml, org_toml, uv_deps_optional)
        parse_uv_deps_sources(new_toml, org_toml, uv_deps_source)


def dependencies(new_toml: tk.TOMLDocument, org_toml: tk.TOMLDocument) -> None:
    """Parse dependencies."""
    if not (deps := org_toml["tool"]["poetry"].get("dependencies", {})):
        return

    uv_deps, uv_deps_optional, uv_deps_source = parse_packages(deps)
    new_toml["project"]["dependencies"] = tk.array()
    if uv_deps:
        for x in uv_deps:
            new_toml["project"]["dependencies"].add_line(x)
        new_toml["project"]["dependencies"].add_line(indent="")

    parse_uv_deps_optional(new_toml, org_toml, uv_deps_optional)
    parse_uv_deps_sources(new_toml, org_toml, uv_deps_source)


def parse_uv_deps_sources(new_toml, org_toml, uv_deps_source) -> None:
    """Parse uv dependencies sources."""
    if uv_deps_source:
        if not new_toml.get("tool", {}).get("uv", {}).get("sources"):
            new_toml["tool"] = {"uv": {"sources": tk.table()}}
        for lib, source in uv_deps_source.items():
            for entry in org_toml["tool"]["poetry"]["source"]:
                if entry.get("name") == source:
                    url = entry.get("url")
                    break
            new_toml["tool"]["uv"]["sources"].add(lib, tk.inline_table().add("git", url))


def parse_uv_deps_optional(
    new_toml: tk.TOMLDocument,
    org_toml: tk.TOMLDocument,
    uv_deps_optional: dict[str, str],
) -> None:
    """Parse optional dependencies."""
    if uv_deps_optional:
        optional_deps = {
            extra: [f"{x}{uv_deps_optional[x]}" for x in deps]
            for extra, deps in org_toml["tool"]["poetry"].pop("extras", {}).items()
        }
        new_toml["project"]["optional-dependencies"] = new_toml["project"].get(
            "optional-dependencies", {}
        )
        new_toml["project"]["optional-dependencies"].update(optional_deps)


def tools(new_toml: tk.TOMLDocument, org_toml: tk.TOMLDocument) -> None:
    """Updates the 'tool' section in the given TOML document."""
    if org_toml["tool"]:
        new_toml["tool"] = new_toml.get("tool", tk.table())
        for tool, data in org_toml["tool"].items():
            if tool == "poetry":
                continue
            new_toml["tool"][tool] = data
    if "tool" in new_toml and not new_toml["tool"]:
        del new_toml["tool"]


def poetry_plugins(new_toml: tk.TOMLDocument, org_toml: tk.TOMLDocument) -> None:
    """Updates the 'plugins' section in the given TOML document."""
    if plugins := org_toml["tool"]["poetry"].get("plugins"):
        new_toml["project"]["entry-points"] = new_toml["project"].get("entry-points", tk.table())
        for plugin, data in plugins.items():
            new_toml["project"]["entry-points"][plugin] = data


def build_system(new_toml: tk.TOMLDocument, org_toml: tk.TOMLDocument) -> None:
    """Updates the 'build-system' section in the given TOML document."""
    if build := org_toml.get("build-system"):
        if "poetry" in build.get("build-backend"):
            print("Poetry build system detected. It will be removed.")
        else:
            new_toml["build-system"] = org_toml["build-system"]


def is_poetry_v2(org_toml: tk.TOMLDocument) -> bool:
    """Check if the project is using Poetry v2 or v1."""
    global POETRYV2
    # Poetry v2 has a [project] section
    if org_toml.get("project", {}).get("name"):
        POETRYV2 = True
        return True
    # Poetry v1 has a [tool.poetry] section
    elif org_toml.get("tool", {}).get("poetry").get("name"):
        POETRYV2 = False
        return False
    else:
        print("Poetry version not found. Name field not found in tool.poetry or project section")
        sys.exit(1)


def project_base(new_toml: tk.TOMLDocument, org_toml: tk.TOMLDocument) -> None:  # noqa: C901
    """Updates the 'project' section in the given TOML document."""
    project_base = org_toml["project"] if POETRYV2 else org_toml["tool"]["poetry"]

    project = new_toml["project"]

    project.add("name", project_base["name"])
    project.add("version", project_base["version"])
    if description := project_base.get("description"):
        project.add("description", description)
    if authors := project_base.get("authors"):
        project.add("authors", authors)
    if maintainers := project_base.get("maintainers"):
        project.add("maintainers", maintainers)
    if license := project_base.get("license"):
        project.add("license", license)
    if readme := project_base.get("readme"):
        project.add("readme", readme)
    if (requirespython := project_base.get("requires-python")) or (
        requirespython := project_base.get("dependencies", {}).get("python")
    ):
        project.add("requires-python", version_conversion(requirespython))
    if keywords := project_base.get("keywords"):
        project.add("keywords", keywords)
    if classifiers := project_base.get("classifiers"):
        project.add("classifiers", classifiers)
    if urls := project_base.get("urls"):
        project.add("urls", urls)

    if scripts := project_base.get("scripts"):
        project.add("scripts", scripts)

    if dependencies := project_base.get("dependencies"):
        project.add("dependencies", dependencies)


def project_license(new_toml: tk.TOMLDocument, project_dir: Path) -> None:
    """Updates the 'license' field in the given TOML document's 'project' section."""
    project = new_toml["project"]
    if (license := project.get("license")) and isinstance(license, str):
        if project_dir.joinpath(license).exists():
            project["license"] = tk.inline_table().add("file", license)
        else:
            project["license"] = tk.inline_table().add("text", license)


def poetry_section_specific(
    new_toml: tk.TOMLDocument, org_toml: tk.TOMLDocument, dir: Path
) -> None:
    """Convert poetry section specific data."""
    project_base(new_toml, org_toml)
    project_license(new_toml, dir)
    authors_maintainers(new_toml)
    group_dependencies(new_toml, org_toml)
    dependencies(new_toml, org_toml)
    poetry_plugins(new_toml, org_toml)


def main() -> None:
    """Main."""
    args = argparser()
    project_file = Path(args.filename)
    if not project_file.exists():
        print(f"File {project_file} not found")
        return
    org_toml = tk.loads(project_file.read_text())
    if not org_toml.get("tool", {}).get("poetry"):
        print("Poetry section not found, are you certain this is a poetry project?")
        return

    dry_run = args.n
    project_dir = project_file.parent
    backup_file = project_dir / f"{project_file.name}.org"
    if dry_run:
        output_file = Path(project_dir / "pyproject_temp_uv.toml")
        print(f"Dry_run enabled. Output file: {output_file}")
    else:
        print(f"Replacing {project_file}\nBackup file : {backup_file}")
        output_file = project_file

    new_toml = tk.document()
    new_toml["project"] = tk.table()

    global POETRYV2
    POETRYV2 = is_poetry_v2(org_toml)
    poetry_section_specific(new_toml, org_toml, dir=project_dir)
    build_system(new_toml, org_toml)
    tools(new_toml, org_toml)

    if not dry_run:
        project_file.rename(backup_file)

    output_file.write_text(tk.dumps(new_toml))


if __name__ == "__main__":
    main()
