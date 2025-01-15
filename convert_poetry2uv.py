#!/usr/bin/env python
import argparse
import re
from pathlib import Path

import tomlkit as tk


def argparser() -> argparse.Namespace:
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
    gt_tilde_version = re.compile(r"[\^~](\d.*)")
    tilde_with_digits_and_star = re.compile(r"^~([\d\.]+)\.\*")
    multi_ver_restrictions = re.compile(r"([<>=!]+)[\s,]*([\d\.\*]+),?")

    if version == "*":
        return ""
    elif found := tilde_with_digits_and_star.match(version):
        return f">={found[1]}"
    elif found := gt_tilde_version.match(version):
        return f">={found[1]}"
    elif (found := multi_ver_restrictions.findall(version)) and len(found) > 1:
        bundle = ["".join(g) for g in found]
        return ",".join(bundle)
    else:
        print(f"Well, this is an unexpected version\nVersion = {version}\n")
        print("Skipping this version, add it manually.")


def authors_maintainers(new_toml: tk.TOMLDocument) -> None:
    project = new_toml["project"]
    user_email = re.compile(r"^([\w ]+) <([\w@.]+)>$")
    only_email = re.compile(r"^<([\w@.]+)>$")
    only_user = re.compile(r"^([\w ]+)$")

    for key in ("authors", "maintainers"):
        if authors := project.get(key):
            if isinstance(authors, list):
                new_authors = tk.array()
                for author in authors:
                    if found := user_email.match(author):
                        name, email = found.groups()
                        tb = tk.inline_table().add("name", name).add("email", email)
                        new_authors.add_line(tb)
                    elif found := only_email.match(author):
                        email = found[1]
                        new_authors.add_line(tk.inline_table().add("email", email))
                    elif found := only_user.match(author):
                        name = found[1]
                        new_authors.add_line(tk.inline_table().add("name", name))
                    else:
                        print(f"Unknown author {key} format: {author}")

                new_authors.add_line(indent="")
                project[key] = new_authors


def parse_packages(deps: dict) -> tuple[list[str], dict[str, str], dict[str, str]]:
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
    if not (groups := org_toml["tool"]["poetry"].get("group")):
        return
    for group, data in groups.items():
        uv_deps, uv_deps_optional, uv_deps_source = parse_packages(
            data.get("dependencies", {})
        )
        new_toml["dependency-groups"] = new_toml.get("dependency-groups", tk.table())
        new_toml["dependency-groups"].add(group, uv_deps)

        parse_uv_deps_optional(new_toml, org_toml, uv_deps_optional)
        parse_uv_deps_sources(new_toml, org_toml, uv_deps_source)


def dependencies(new_toml: tk.TOMLDocument, org_toml: tk.TOMLDocument) -> None:
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
    if uv_deps_source:
        if not new_toml.get("tool", {}).get("uv", {}).get("sources"):
            new_toml["tool"] = {"uv": {"sources": tk.table()}}
        for lib, source in uv_deps_source.items():
            for entry in org_toml["tool"]["poetry"]["source"]:
                if entry.get("name") == source:
                    url = entry.get("url")
                    break
            new_toml["tool"]["uv"]["sources"].add(
                lib, tk.inline_table().add("git", url)
            )


def parse_uv_deps_optional(
    new_toml: tk.TOMLDocument,
    org_toml: tk.TOMLDocument,
    uv_deps_optional: dict[str, str],
) -> None:
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
    if org_toml["tool"]:
        new_toml["tool"] = new_toml.get("tool", tk.table())
        for tool, data in org_toml["tool"].items():
            if tool == "poetry":
                continue
            new_toml["tool"][tool] = data


def poetry_plugins(new_toml: tk.TOMLDocument, org_toml: tk.TOMLDocument) -> None:
    if plugins := org_toml["tool"]["poetry"].get("plugins"):
        new_toml["project"]["entry-points"] = new_toml["project"].get(
            "entry-points", tk.table()
        )
        for plugin, data in plugins.items():
            new_toml["project"]["entry-points"][plugin] = data


def build_system(new_toml: tk.TOMLDocument, org_toml: tk.TOMLDocument) -> None:
    if build := org_toml.get("build-system"):
        new_toml["build-system"] = org_toml["build-system"]
        if "poetry" in build.get("build-backend"):
            print("Poetry build system detected. Replaced with hatchling")
            new_toml["build-system"]["requires"] = ["hatchling"]
            new_toml["build-system"]["build-backend"] = "hatchling.build"


def project_base(new_toml: tk.TOMLDocument, org_toml: tk.TOMLDocument) -> None:
    project = new_toml["project"]

    project.add("name", org_toml["tool"]["poetry"]["name"])
    project.add("version", org_toml["tool"]["poetry"]["version"])
    if description := org_toml["tool"]["poetry"].get("description"):
        project.add("description", description)
    if authors := org_toml["tool"]["poetry"].get("authors"):
        project.add("authors", authors)
    if maintainers := org_toml["tool"]["poetry"].get("maintainers"):
        project.add("maintainers", maintainers)
    if license := org_toml["tool"]["poetry"].get("license"):
        project.add("license", license)
    if readme := org_toml["tool"]["poetry"].get("readme"):
        project.add("readme", readme)
    if requirespython := org_toml["tool"]["poetry"].get("requires-python"):
        project.add("requires-python", version_conversion(requirespython))
    elif (
        requirespython := org_toml["tool"]["poetry"]
        .get("dependencies", {})
        .get("python")
    ):
        project.add("requires-python", version_conversion(requirespython))
    if keywords := org_toml["tool"]["poetry"].get("keywords"):
        project.add("keywords", keywords)
    if classifiers := org_toml["tool"]["poetry"].get("classifiers"):
        project.add("classifiers", classifiers)
    if urls := org_toml["tool"]["poetry"].get("urls"):
        project.add("urls", urls)

    if scripts := org_toml["tool"]["poetry"].get("scripts"):
        project.add("scripts", scripts)

    if dependencies := org_toml["tool"]["poetry"].get("dependencies"):
        project.add("dependencies", dependencies)


def project_license(new_toml: tk.TOMLDocument, project_dir: Path) -> None:
    project = new_toml["project"]
    if license := project.get("license"):
        if project_dir.joinpath(license).exists():
            project["license"] = tk.inline_table().add("file", license)
        else:
            project["license"] = tk.inline_table().add("text", license)


def poetry_section_specific(
    new_toml: tk.TOMLDocument, org_toml: tk.TOMLDocument, dir: Path
) -> None:
    project_base(new_toml, org_toml)
    project_license(new_toml, dir)
    authors_maintainers(new_toml)
    group_dependencies(new_toml, org_toml)
    dependencies(new_toml, org_toml)
    poetry_plugins(new_toml, org_toml)


def main() -> None:
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

    poetry_section_specific(new_toml, org_toml, dir=project_dir)
    build_system(new_toml, org_toml)
    tools(new_toml, org_toml)

    if not dry_run:
        project_file.rename(backup_file)

    output_file.write_text(tk.dumps(new_toml))


if __name__ == "__main__":
    main()
