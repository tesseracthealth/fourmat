import fnmatch
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from subprocess import PIPE, CalledProcessError

import click

from . import ASSETS_DIR, cli

# -----------------------------------------------------------------------------

CONFIG_FILE = Path(".fourmat")

SNAPSHOT_GLOB = "*/snapshots/snap_*.py"
SNAPSHOT_REGEX = r".*\/snapshots\/snap_.*\.py"
CONFIGURATION_FILES = (".flake8", ".isort.cfg", "pyproject.toml")

# -----------------------------------------------------------------------------


def get_project_paths():
    return CONFIG_FILE.read_text().split()


def get_dirty_filenames(paths, *, staged=False):
    filenames = subprocess.run(
        (
            "git",
            "diff-index",
            "--name-only",
            "--diff-filter",
            "ACM",
            *(("--cached",) if staged else ()),
            "HEAD",
            "--",
            *paths,
        ),
        check=True,
        stdout=PIPE,
        encoding=sys.getdefaultencoding(),
    ).stdout.split()

    return tuple(
        filename
        for filename in filenames
        if Path(filename).suffix == ".py"
        and not fnmatch.fnmatch(filename, SNAPSHOT_GLOB)
    )


# -----------------------------------------------------------------------------


def copy_configuration(override=False):
    for name in CONFIGURATION_FILES:
        if override is True or not Path(name).exists():
            # This will always be in project root because we implicitly assert
            # in get_project_paths().
            shutil.copy(ASSETS_DIR / name, ".")


def black(paths, *, check=False):
    subprocess.run(
        (
            "black",
            *(("--check", "--diff") if check else ()),
            "--exclude",
            SNAPSHOT_REGEX,
            "--quiet",
            "--",
            *paths,
        ),
        check=True,
    )


def isort(paths, *, project_paths, check=False):
    subprocess.run(
        (
            "isort",
            *(("--check", "--diff") if check else ("--apply",)),
            *(arg for path in project_paths for arg in ("--project", path)),
            "--skip-glob",
            SNAPSHOT_GLOB,
            "--atomic",
            "--quiet",
            "--recursive",
            "--",
            *paths,
        ),
        check=True,
    )


def flake8(paths, *, check=True):
    assert check is True, "Flake8 has no fix mode"

    subprocess.run(("flake8", "--", *paths), check=True)


# -----------------------------------------------------------------------------


@cli.command(
    help=f"check code style. If no file is specified, it will run on all the files specified in {CONFIG_FILE}"
)
@click.option("-c", "--override-config", is_flag=True)
@click.argument("files", nargs=-1)
def check(override_config, files):
    try:
        project_paths = get_project_paths()
        files = files or project_paths
        copy_configuration(override=override_config)
        status = 0

        @contextmanager
        def record_failure():
            try:
                yield
            except CalledProcessError:
                nonlocal status
                status = 1

        # When linting, continue running linters even after failures, to
        # display all lint errors.
        with record_failure():
            isort(files, project_paths=project_paths, check=True)
        with record_failure():
            black(files, check=True)
        with record_failure():
            flake8(files, check=True)

        if status:
            sys.exit(status)
    except KeyboardInterrupt:
        pass


@cli.command(
    "fix",
    help=f"automatically fix code. If no file is specified, it will run on all the files specified in {CONFIG_FILE}",
)
@click.option(
    "-c",
    "--override-config",
    is_flag=True,
    help=f"specify this flag to override the config files ({', '.join(CONFIGURATION_FILES)})",
)
@click.argument("files", nargs=-1)
def fix(*, override_config, files):
    try:
        project_paths = get_project_paths()
        copy_configuration(override=override_config)

        files = files or project_paths

        isort(files, project_paths=project_paths)
        black(files)
        flake8(files)

    except CalledProcessError as e:
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        pass