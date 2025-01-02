import shutil
from pathlib import Path

import pytest
import tomlkit

import convert_poetry2uv


@pytest.mark.parametrize(
    "key, value",
    [
        ("^3.6", ">=3.6"),
        ("*", ""),
        ("^1.2.3", ">=1.2.3"),
    ],
)
def test_version_conversion(key, value):
    assert convert_poetry2uv.version_conversion(key) == value


@pytest.mark.parametrize(
    "key, name, email",
    [
        (["authors", "firstname lastname", "name@domain.nl"]),
        (["authors", "another one", "just@checking.com"]),
        (["maintainers", "firstname lastname", "name@domain.nl"]),
        (["maintainers", "another one", "just@checking.com"]),
    ],
)
def test_authors_maintainers(key, name, email):
    authors = [f"{name} <{email}>"]
    in_dict = {"project": {key: authors}}
    expected = {"project": {key: [{"name": name, "email": email}]}}
    convert_poetry2uv.authors_maintainers(in_dict)
    assert in_dict == expected


@pytest.mark.parametrize(
    "authors, author_string",
    [
        (
            ["First Last <first@domain2.nl>", "another <email@domain.nl>"],
            [
                {"name": "First Last", "email": "first@domain2.nl"},
                {"name": "another", "email": "email@domain.nl"},
            ],
        ),
        (
            ["First Last", "<email@domain.nl>"],
            [{"name": "First Last"}, {"email": "email@domain.nl"}],
        ),
        (
            ["First Last <first@domain2.nl>", "<email@domain.nl>", "First Last"],
            [
                {"name": "First Last", "email": "first@domain2.nl"},
                {"email": "email@domain.nl"},
                {"name": "First Last"},
            ],
        ),
    ],
)
def test_multiple_authors(authors, author_string):
    in_dict = {"project": {"authors": authors}}
    expected = {"project": {"authors": author_string}}
    convert_poetry2uv.authors_maintainers(in_dict)
    assert in_dict == expected


def test_no_python_in_deps(org_toml):
    deps = org_toml["tool"]["poetry"]["dependencies"]
    uv_deps = []
    uv_deps, _, _ = convert_poetry2uv.parse_packages(deps)
    assert "python" not in uv_deps


def test_dependencies(pyproject_empty_base, org_toml):
    expected = {"project": {"dependencies": ["pytest", "pytest-cov", "jira>=3.8.0"]}}
    convert_poetry2uv.dependencies(pyproject_empty_base, org_toml)
    assert pyproject_empty_base == expected


def test_optional_dependencies(pyproject_empty_base, org_toml_optional):
    expected = {
        "project": {
            "dependencies": ["pytest", "pytest-cov"],
            "optional-dependencies": {"JIRA": ["jira>=3.8.0"]},
        }
    }
    convert_poetry2uv.dependencies(pyproject_empty_base, org_toml_optional)
    assert pyproject_empty_base == expected


def test_extras_dependencies():
    in_txt = """
    [tool.poetry.dependencies]
    python = "^3.12"
    pytest = "*"
    pandas = {version="^2.2.1", extras=["computation", "performance"]}
    fastapi = {version="^0.92.0", extras=["all"]}
    """
    in_dict = tomlkit.loads(in_txt)
    deps = in_dict["tool"]["poetry"]["dependencies"]
    expected = [
        "pytest",
        "pandas[computation]>=2.2.1",
        "pandas[performance]>=2.2.1",
        "fastapi[all]>=0.92.0",
    ]
    uv_deps, _, _ = convert_poetry2uv.parse_packages(deps)
    assert uv_deps == expected


def test_dev_dependencies(pyproject_empty_base, org_toml):
    expected = {
        "project": {},
        "dependency-groups": {"dev": ["mypy>=1.0.1"]},
    }
    convert_poetry2uv.group_dependencies(pyproject_empty_base, org_toml)
    assert pyproject_empty_base == expected


def test_dev_dependencies_optional(pyproject_empty_base):
    in_dict = {
        "tool": {
            "poetry": {
                "group": {
                    "dev": {
                        "dependencies": {
                            "mypy": "^1.0.1",
                            "jira": {"version": "^3.8.0", "optional": True},
                        }
                    }
                },
                "extras": {"JIRA": ["jira"]},
            }
        }
    }
    convert_poetry2uv.group_dependencies(pyproject_empty_base, in_dict)
    expected = {
        "project": {"optional-dependencies": {"JIRA": ["jira>=3.8.0"]}},
        "dependency-groups": {"dev": ["mypy>=1.0.1"]},
    }
    assert pyproject_empty_base == expected


def test_dev_extras_dependencies(pyproject_empty_base):
    in_txt = """
    [tool.poetry.dependencies]
    python = "^3.12"
    pytest = "*"

    [tool.poetry.group.dev.dependencies]
    fastapi = {version="^0.92.0", extras=["all"]}
    """
    in_dict = tomlkit.loads(in_txt)
    convert_poetry2uv.group_dependencies(pyproject_empty_base, in_dict)
    expected = {"project": {}, "dependency-groups": {"dev": ["fastapi[all]>=0.92.0"]}}
    assert pyproject_empty_base == expected


def test_tools_remain_the_same(toml_obj):
    org_toml = toml_obj("tests/files/tools_org.toml")
    new_toml = toml_obj("tests/files/tools_new.toml")
    convert_poetry2uv.tools(new_toml, org_toml)
    del org_toml["tool"]["poetry"]
    assert new_toml == org_toml


def test_doc_dependencies(pyproject_empty_base, org_toml):
    org_toml["tool"]["poetry"]["group"]["doc"] = {"dependencies": {"mkdocs": "*"}}
    expected = {
        "project": {},
        "dependency-groups": {"dev": ["mypy>=1.0.1"], "doc": ["mkdocs"]},
    }
    convert_poetry2uv.group_dependencies(pyproject_empty_base, org_toml)
    assert pyproject_empty_base == expected


def test_project_license(tmp_path):
    in_dict = {"project": {"license": "MIT"}}
    expected = {"project": {"license": {"text": "MIT"}}}
    convert_poetry2uv.project_license(in_dict, tmp_path)
    assert in_dict == expected


def test_project_license_file(tmp_path):
    license_name = "license_file_name"
    in_dict = {"project": {"license": license_name}}
    tmp_path.joinpath(license_name).touch()
    expected = {"project": {"license": {"file": license_name}}}
    convert_poetry2uv.project_license(in_dict, tmp_path)
    assert in_dict == expected


def test_build_system():
    in_dict = {
        "build-system": {
            "requires": ["poetry-core>=1.0.0"],
            "build-backend": "poetry.core.masonry.api",
        }
    }
    expected = {
        "build-system": {
            "requires": ["hatchling"],
            "build-backend": "hatchling.build",
        }
    }
    convert_poetry2uv.build_system(in_dict, in_dict)
    assert in_dict == expected


def test_poetry_sources(pyproject_empty_base):
    in_txt = """
    [tool.poetry.dependencies]
    python = "^3.12"
    requests = { version = "^2.13.0", source = "private" }

    [[tool.poetry.source]]
    name = "private"
    url = "http://example.com/simple"
    """
    in_dict = tomlkit.loads(in_txt)
    convert_poetry2uv.dependencies(pyproject_empty_base, in_dict)
    expected = {
        "project": {"dependencies": ["requests>=2.13.0"]},
        "tool": {"uv": {"sources": {"requests": {"git": "http://example.com/simple"}}}},
    }
    assert pyproject_empty_base == expected


def test_normal_and_dev_poetry_sources(pyproject_empty_base):
    in_txt = """
    [tool.poetry.group.dev.dependencies]
    requests = { version = "^2.13.0", source = "private" }

    [tool.poetry.group.doc.dependencies]
    httpx = { version = "^1.13.0", source = "other" }

    [[tool.poetry.source]]
    name = "private"
    url = "http://example.com/simple"

    [[tool.poetry.source]]
    name = "other"
    url = "http://other.com/simple"
    """
    in_dict = tomlkit.loads(in_txt)
    convert_poetry2uv.group_dependencies(pyproject_empty_base, in_dict)
    expected = {
        "project": {},
        "dependency-groups": {"dev": ["requests>=2.13.0"], "doc": ["httpx>=1.13.0"]},
        "tool": {
            "uv": {
                "sources": {
                    "requests": {"git": "http://example.com/simple"},
                    "httpx": {"git": "http://other.com/simple"},
                }
            }
        },
    }
    assert pyproject_empty_base == expected


def test_project_base(toml_obj, pyproject_empty_base):
    org_toml = toml_obj("tests/files/poetry_pyproject.toml")
    new_toml = pyproject_empty_base
    convert_poetry2uv.project_base(new_toml, org_toml)
    expected = {
        "project": {
            "name": "name of the project",
            "version": "0.1.0",
            "description": "A description",
            "authors": ["another <email@domain.nl>", "<some@email.nl>", "user"],
            "maintainers": ["another <email@domain.nl>", "<some@email.nl>", "user"],
            "license": "LICENSE",
            "readme": "README.md",
            "requires-python": ">=3.12",
            "scripts": {"script_name": "dir.file:app"},
            "dependencies": {
                "python": "^3.12",
                "pytest": "*",
                "pytest-cov": "*",
                "pytest-mock": "*",
                "ruff": "*",
                "jira": "^3.8.0",
            },
        }
    }
    assert new_toml == expected


def test_project_base(toml_obj, pyproject_empty_base, expected_project_base):
    org_toml = toml_obj("tests/files/poetry_pyproject.toml")
    new_toml = pyproject_empty_base
    convert_poetry2uv.project_base(new_toml, org_toml)
    assert new_toml == expected_project_base


def test_project_base_require_python(
    toml_obj, pyproject_empty_base, expected_project_base
):
    org_toml = toml_obj("tests/files/poetry_pyproject.toml")
    org_toml["tool"]["poetry"]["requires-python"] = "^3.10"
    expected_project_base["project"]["requires-python"] = ">=3.10"
    new_toml = pyproject_empty_base
    convert_poetry2uv.project_base(new_toml, org_toml)
    assert new_toml == expected_project_base


def test_empty_group_dependencies(org_toml, pyproject_empty_base):
    del org_toml["tool"]["poetry"]["group"]
    convert_poetry2uv.group_dependencies(pyproject_empty_base, org_toml)
    assert pyproject_empty_base == {"project": {}}


def test_argparser(mocker):
    mocker.patch(
        "sys.argv",
        ["convert_poetry2uv.py", "tests/files/poetry_pyproject.toml", "-n"],
    )
    sys_argv = convert_poetry2uv.argparser()
    assert sys_argv.filename == "tests/files/poetry_pyproject.toml"
    assert sys_argv.n is True


def test_plugins(pyproject_empty_base):
    in_txt = """
    [tool.poetry.plugins."spam.magical"]
    tomatoes = "spam:main_tomatoes"
    """
    exp_txt = """
    [project.entry-points."spam.magical"]
    tomatoes = "spam:main_tomatoes"
    """
    in_dict = tomlkit.loads(in_txt)
    expected = tomlkit.loads(exp_txt)
    convert_poetry2uv.poetry_plugins(pyproject_empty_base, in_dict)
    assert pyproject_empty_base == expected


def test_main_dry_run(mocker, tmp_path):
    src = "tests/files/poetry_pyproject.toml"
    filename = tmp_path.joinpath("pyproject.toml")
    shutil.copy(src, filename)
    mocker.patch(
        "sys.argv",
        ["convert_poetry2uv.py", str(filename), "-n"],
    )
    convert_poetry2uv.main()
    should_match = Path("tests/files/uv_pyproject.toml").read_text()
    generated_toml_txt = filename.parent.joinpath("pyproject_temp_uv.toml").read_text()
    assert generated_toml_txt == should_match


def test_main(mocker, tmp_path):
    src = "tests/files/poetry_pyproject.toml"
    filename = tmp_path.joinpath("pyproject.toml")
    shutil.copy(src, filename)
    mocker.patch(
        "sys.argv",
        ["convert_poetry2uv.py", str(filename)],
    )
    convert_poetry2uv.main()
    should_match = Path("tests/files/uv_pyproject.toml").read_text()
    generated_toml_txt = filename.read_text()
    assert generated_toml_txt == should_match