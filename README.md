# convert-poetry2uv

The convert_poetry2uv.py script is meant to easily convert the pyproject.toml to be consumed by `uv` instead of `poetry`.

> It is specifically meant for the poetry syntax prior to version 2.0. The 2.0 release is compliant to the [PEP 621](https://peps.python.org/pep-0621/) specification. The script will not work for the 2.0 release!

It has a dry-run flag, to have a temporary file to validate the output. When not running the dry-run the original file is saved with a .org extension.

    uv run convert_poetry2uv.py <path to file> [-n]

You may need to make some manual changes.
The layout might not be exactly to your liking. I would recommend using [Even better toml](https://marketplace.visualstudio.com/items?itemName=tamasfe.even-better-toml) in VSCode. Just open the newly generated toml file and save. It will format the file according to the toml specification.

## Caveats
* If you were using the poetry build-system, it will be replaced by hatchling.
* if you had optional dev groups, the dev group libraries will be used, the optional flag is removed

# Using as a tool
The script can be run as a tool using [`uvx`](https://docs.astral.sh/uv/guides/tools/)

    uvx --from git+https://github.com/bartdorlandt/convert_poetry2uv convert-poetry2uv --help

## uv instructions
Once the pyproject.toml is converted, you can use `uv` to manage your project. To start fresh, the .venv directory is removed followed by the creation and sync of the .venv directory.

    rm -rf .venv
    uv venv   # or 'uv venv -p 3.12' to specify a python version
    uv sync

With this you are good to go and are able to validate the migration was a success.

## Pypi
The script is also available on pypi as [convert-poetry2uv](https://pypi.org/project/convert-poetry2uv/)

    pip install convert-poetry2uv

# Contribute
Though I've tried to make it as complete as possible, it is not guaranteed to work for all cases. Feel free to contribute to the code or create an issue with the toml file that is not converted correctly.

# Links
* [Writing pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/)
* [uv pyproject.toml](https://docs.astral.sh/uv/concepts/projects/layout/)
* [Poetry pyproject.toml](https://python-poetry.org/docs/pyproject/)
* [Real python blog: Python and toml](https://realpython.com/python-toml/#write-toml-documents-with-tomli_w)
* [tomlkit docs](https://tomlkit.readthedocs.io/en/latest/quickstart/#)
* [Taskfile installation](https://taskfile.dev/installation/)
* [uv installation](https://docs.astral.sh/uv/getting-started/installation/)

