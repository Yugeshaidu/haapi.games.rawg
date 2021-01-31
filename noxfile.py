"""Nox sessions."""
import shutil
import sys
from pathlib import Path
from textwrap import dedent

import nox
import nox_poetry.patch
from nox.sessions import Session


package = "haapi.games.rawg"
latest_python_version = "3.9"
python_versions = ["3.9", "3.8", "3.7", "3.6"]
pytest_deps = [
    "pytest",
    "pygments",
    "aioresponses",
    "pytest-mock",
    "pytest-datadir",
    "pytest-asyncio",
]

nox.options.sessions = (
    "pre-commit",
    "safety",
    "mypy",
    "tests",
    "typeguard",
    "xdoctest",
    "docs-build",
)

base_docs_path = "docs"
docs_build_path = f"{base_docs_path}/_build"


def activate_virtualenv_in_precommit_hooks(session: Session) -> None:
    """Activate virtualenv in hooks installed by pre-commit.

    This function patches git hooks installed by pre-commit to activate the
    session's virtual environment. This allows pre-commit to locate hooks in
    that environment when invoked from git.

    Args:
        session: The Session object.
    """
    if session.bin is None:
        return

    virtualenv = session.env.get("VIRTUAL_ENV")
    if virtualenv is None:
        return

    hookdir = Path(".git") / "hooks"
    if not hookdir.is_dir():
        return

    for hook in hookdir.iterdir():
        if hook.name.endswith(".sample") or not hook.is_file():
            continue

        text = hook.read_text()
        bindir = repr(session.bin)[1:-1]  # strip quotes
        if not (
            Path("A") == Path("a") and bindir.lower() in text.lower() or bindir in text
        ):
            continue

        lines = text.splitlines()
        if not (lines[0].startswith("#!") and "python" in lines[0].lower()):
            continue

        header = dedent(
            f"""\
            import os
            os.environ["VIRTUAL_ENV"] = {virtualenv!r}
            os.environ["PATH"] = os.pathsep.join((
                {session.bin!r},
                os.environ.get("PATH", ""),
            ))
            """
        )

        lines.insert(1, header)
        hook.write_text("\n".join(lines))


@nox.session(name="pre-commit", python=latest_python_version)
def precommit(session: Session) -> None:
    """Lint using pre-commit.

    Args:
        session: The Session object.
    """
    args = session.posargs or ["run", "--all-files", "--show-diff-on-failure"]
    session.install(
        "black",
        "darglint",
        "flake8",
        "flake8-bandit",
        "flake8-bugbear",
        "flake8-docstrings",
        "flake8-rst-docstrings",
        "pep8-naming",
        "pre-commit",
        "pre-commit-hooks",
        "reorder-python-imports",
    )
    session.run("pre-commit", *args)
    if args and args[0] == "install":
        activate_virtualenv_in_precommit_hooks(session)


@nox.session(python=latest_python_version)
def safety(session: Session) -> None:
    """Scan dependencies for insecure packages.

    Args:
        session: The Session object.
    """
    requirements = nox_poetry.export_requirements(session)
    session.install("safety")
    session.run("safety", "check", f"--file={requirements}", "--bare")


@nox.session(python=latest_python_version)
def mypy(session: Session) -> None:
    """Type-check using mypy.

    Args:
        session: The Session object.
    """
    args = session.posargs or [
        "--explicit-package-bases",
        "src/haapi/games",
        "tests",
        "docs/conf.py",
    ]
    session.install(".")
    session.install("mypy", "pytest", "pytest-mock")
    session.run("mypy", *args)
    if not session.posargs:
        session.run("mypy", f"--python-executable={sys.executable}", "noxfile.py")


@nox.session(python=python_versions)
def tests(session: Session) -> None:
    """Run the test suite.

    Args:
        session: The Session object.
    """
    session.install(".")
    session.install("coverage[toml]")
    session.install(*pytest_deps)
    try:
        session.run("coverage", "run", "--parallel", "-m", "pytest", *session.posargs)
    finally:
        if session.interactive:
            session.notify("coverage")


@nox.session
def coverage(session: Session) -> None:
    """Produce the coverage report.

    Args:
        session: The Session object.
    """
    # Do not use session.posargs unless this is the only session.
    has_args = session.posargs and len(session._runner.manifest) == 1
    args = session.posargs if has_args else ["report"]

    session.install("coverage[toml]")

    if not has_args and any(Path().glob(".coverage.*")):
        session.run("coverage", "combine")

    session.run("coverage", *args)


@nox.session(python=python_versions)
def typeguard(session: Session) -> None:
    """Runtime type checking using Typeguard.

    Args:
        session: The Session object.
    """
    session.install(".")
    session.install("typeguard")
    session.install(*pytest_deps)
    session.run("pytest", f"--typeguard-packages={package}", *session.posargs)


@nox.session(python=python_versions)
def xdoctest(session: Session) -> None:
    """Run examples with xdoctest.

    Args:
        session: The Session object.
    """
    args = session.posargs or ["all"]
    session.install(".")
    session.install("xdoctest[colors]")
    # I cannot get this to run correctly with the installed package even with checking
    # the package installation multiple times
    # session.run("python", "-m", "xdoctest", package, *args)
    session.run("python", "-m", "xdoctest", f"src/{package.replace('.', '/')}", *args)


@nox.session(name="docs-build", python=latest_python_version)
def docs_build(session: Session) -> None:
    """Build the documentation.

    Args:
        session: The Session object.
    """
    args = session.posargs or [base_docs_path, docs_build_path]
    session.install(".")
    session.install("sphinx", "sphinx-rtd-theme")

    build_dir = Path(docs_build_path)
    if build_dir.exists():
        shutil.rmtree(build_dir)

    session.run(
        "sphinx-apidoc",
        "-o",
        base_docs_path,
        "-fTPM",
        "--implicit-namespaces",
        "src/haapi",
    )
    session.run("sphinx-build", *args)


@nox.session(python=latest_python_version)
def docs(session: Session) -> None:
    """Build and serve the documentation with live reloading on file changes.

    Args:
        session: The Session object.
    """
    args = session.posargs or [
        "--open-browser",
        base_docs_path,
        f"{docs_build_path}",
    ]
    session.install(".")
    session.install("sphinx", "sphinx-autobuild", "sphinx-rtd-theme")

    build_dir = Path(docs_build_path)
    if build_dir.exists():
        shutil.rmtree(build_dir)

    session.run("sphinx-autobuild", *args)