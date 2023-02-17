"""Build the Svelte site with a static adapter.
This is intended to be vendor-independent, so it should work on any CI system and locally too.

Requirements:
- node 18.x
- python >=3.10
- Some way to install Python dependencies (pip, pip-tools)

This should install the required Node package manager, if corepack cannot find it. 
"""
import os
import getpass
import json
import platform
import shutil
import subprocess
import sys
from io import UnsupportedOperation
from pathlib import Path

import pygit2


class Config:
    def build(self) -> bool:
        self.build.enabled = True
        return self.build.enabled

    def deploy(self) -> bool:
        self.deploy.enabled = True
        return self.deploy.enabled

    def deploy_token(self) -> str:
        token = os.getenv("SVELTE_GIT_TOKEN")
        if token is None:
            print("Warning: Could not find environment variable, please enter a token with push permissions:")
            token = getpass.getpass("Token: ")
        return token


built = False

# i don't think this is even running on python < 3.10
if platform.python_version() < "3.10":
    raise UnsupportedOperation("Python 3.10 or greater is required")


def check_node_packagemanager() -> str:
    """Check the package.json (and, if needed, the lock file) to find the Node package manager being used.
    If you have multiple lockfiles *and* you don't have the `packageManager` field in package.json with a package manager,
    Yarn will take priority, then pnpm, then npm. If none are found, raises an OSError - if package.json is not found, raises a FileNotFoundError.

    Returns:
      str: The package manager. One of `npm`, `pnpm` or `yarn`.
    """
    try:
        package_json = json.load(open(Path("package.json")))
    except OSError:
        print("No package.json found. Try running from the project root?")
        raise FileNotFoundError(
            "Could not find package.json - are you running from the project root?"
        )
    try:
        package_json["packageManager"]
    except KeyError:
        package_manager = check_lockfiles()
        if package_manager is None:
            raise FileNotFoundError("No lockfile found.")
        return package_manager

    if package_json["packageManager"].startswith("yarn"):
        print("Package manager detected using package.json: yarn.")
        package_manager = "yarn"
    elif package_json["packageManager"].startswith("pnpm"):
        print("Package manager detected using package.json: pnpm.")
        package_manager = "pnpm"
    else:
        print("Package manager detected using package.json: npm.")
        package_manager = "npm"

    return package_manager


def check_lockfiles() -> str | None:
    print("Package manager not detectable using package.json. Checking lockfiles.")
    if Path("yarn.lock").exists():
        print("Package manager detected using lockfile: yarn.")
        package_manager = "yarn"
    elif Path("pnpm-lock.yaml").exists():
        print("Package manager detected using lockfile: pnpm.")
        package_manager = "pnpm"
    elif Path("package-lock.json").exists():
        print("Package manager detected using lockfile: npm.")
        package_manager = "npm"
    else:
        package_manager = None

    return package_manager


def get_version() -> str:
    """Get the version of the Node package manager needed."""
    try:
        package_json = json.load(open(Path("package.json")))
    except OSError:
        print("No package.json found. Try running from the project root?")
        raise FileNotFoundError(
            "Could not find package.json - are you running from the project root?"
        )
    try:
        version = package_json["packageManager"]
        return version
    except KeyError:
        raise UnsupportedOperation(
            "The `packageManager` field is not defined in `package.json`."
        )


def check_node() -> bool:
    try:
        subprocess.run("node --version", check=True, stdout=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False


def build():
    if check_node() is False:
        raise UnsupportedOperation(
            "You don't have node installed! Please [re]install from https://nodejs.org and then run this script again."
        )
    print("Starting build process.")
    print("Detecting package manager...")
    package_manager = check_node_packagemanager()
    print("Enabling the given package manager...")
    subprocess.run("corepack enable", check=True, shell=True)
    try:
        package_manager_version = get_version()
        subprocess.run(
            f"corepack prepare {package_manager_version} --activate",
            check=True,
            shell=True,
        )
    except UnsupportedOperation:
        # here we have to assume this is NPM, which is installed with node
        pass
    print("Installing dependencies; the package manager will output below.")
    subprocess.run(f"{package_manager} install", check=True, shell=True)
    print("Building...")
    subprocess.run(f"{package_manager} run build", check=True, shell=True)
    global built
    built = True


def deploy(repository: str, branch: str | None = None):
    """Deploy a Svelte site to a Git repository utilizing libgit via pygit2.
    This *only works with the static adapter* (`@sveltejs/adapter-static`), and you are expected to have
    the needed configuration at the Git repository level to deploy this static site. If you don't, check out https://codeberg.page.

    Usually, this will require a personal access token, which will be read from the environment variable `BUILD_SVELTE_TOKEN` (will fall back to `GITHUB_TOKEN` if the repository given) so that it isn't in plaintext.
    In the case of GitHub, this will need the [insert_scopes] scopes.

    This also assumes you are running from the root directory of the project - which should have caused a package manager failure above anyway.

    Building will automatically happen if it hasn't already; obviously you can't deploy if there was no build to deploy haha.
    """
    if built is False:
        build()
    print("Cloning repository. This could take a while...")
    if branch is not None:
        try:
            pygit2.clone_repository(
                repository, ".tmp/push_repo", checkout_branch=branch
            )
            repo = pygit2.Repository(repository)
        except ValueError:
            repo = pygit2.Repository(repository)
    else:
        try:
            pygit2.clone_repository(repository, ".tmp/push_repo")
            repo = pygit2.Repository(repository)
        except ValueError:
            repo = pygit2.Repository(repository)
    shutil.copy("build", ".tmp/push_repo")
    repo.add_worktree("", ".tmp/push_repo")


if __name__ == "__main__":
    if Config.build is False:
        print("Nothing to do.")
        sys.exit(1)
    if Config.build is True:
        build()
    if Config.deploy is True:
        deploy("https://codeberg.org/osfanbuff63/pages.git")
