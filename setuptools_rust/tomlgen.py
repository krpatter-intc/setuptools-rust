# coding: utf-8
from __future__ import unicode_literals

import glob
import os
import string

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

import setuptools

from distutils import log
from distutils.command.build import build

from .extension import RustExtension


__all__ = ["tomlgen"]


class tomlgen_rust(setuptools.Command):

    description = "Generate `Cargo.toml` for rust extensions"

    user_options = [
        ("create-workspace", 'w',
         "create a workspace file at the root of the project"),
        ("force", 'f',
         "overwrite existing files if any")
    ]

    boolean_options = ['create_workspace', 'force']

    def initialize_options(self):

        self.dependencies = None
        self.authors = None
        self.create_workspace = None
        self.force = None

        # parse config files
        self.cfg = configparser.ConfigParser()
        self.cfg.read(self.distribution.find_config_files())

    def finalize_options(self):

        # Finalize previous commands
        self.distribution.finalize_options()

        # Shortcuts
        self.extensions = self.distribution.rust_extensions
        self.workspace = os.path.abspath(os.path.dirname(self.distribution.script_name) or '.')

        # Build list of authors
        if self.authors is not None:
            self.authors = "[{}]".format(
                ", ".join(author.strip() for author in self.authors.split('\n')))
        else:
            self.authors = '["{} <{}>"]'.format(
                self.distribution.get_author(),
                self.distribution.get_author_email().strip('"\''))

    def run(self):

        # Create a `Cargo.toml` for each extension
        for ext in self.extensions:
            toml = self.build_cargo_toml(ext)
            if not os.path.exists(ext.path) or self.force:
                log.info("creating 'Cargo.toml' for '%s'", ext.name)
                with open(ext.path, 'w') as manifest:
                    toml.write(manifest)
            else:
                log.warn("skipping 'Cargo.toml' for '%s' -- already exists", ext.name)

        # Create a `Cargo.toml` for the project workspace
        if self.create_workspace and self.extensions:
            toml = self.build_workspace_toml()
            if not os.path.exists(ext.path) or self.force:
                log.info("creating 'Cargo.toml' for workspace")
                toml_path = os.path.join(self.workspace, "Cargo.toml")
                with open(toml_path, 'w') as manifest:
                    toml.write(manifest)
            else:
                log.warn("skipping 'Cargo.toml' for workspace -- already exists")

    def build_cargo_toml(self, ext):

        # Shortcuts
        quote = '"{}"'.format
        dist = self.distribution

        # Use a ConfigParser object to build a TOML file (hackish)
        toml = configparser.ConfigParser()

        # The directory where the extension's manifest is located
        tomldir = os.path.dirname(ext.path)

        # Create a small package section
        toml.add_section("package")
        toml.set("package", "name", quote(ext.name))
        toml.set("package", "version", quote(dist.get_version()))
        toml.set("package", "authors", self.authors)
        toml.set("package", "publish", "false")

        # Add the relative path to the workspace if any
        if self.create_workspace:
            path_to_workspace = os.path.relpath(self.workspace, tomldir)
            toml.set("package", "workspace", quote(path_to_workspace))

        # Create a small lib section
        toml.add_section("lib")
        toml.set("lib", "crate-type", '["cdylib"]')
        toml.set("lib", "name", quote(_slugify(ext.name)))
        toml.set("lib", "path", quote(os.path.relpath(ext.libfile, tomldir)))

        # Find dependencies within the `setup.cfg` file of the project
        toml.add_section("dependencies")
        for dep, options in self.iter_dependencies(ext):
            toml.set("dependencies", dep, options)

        return toml

    def build_workspace_toml(self):

        # Find all members of the workspace
        members = [os.path.dirname(os.path.relpath(ext.path)) for ext in self.extensions]
        members = ['"{}"'.format(m) for m in members]

        # Create the `Cargo.toml` content using a ConfigParser
        toml = configparser.ConfigParser()
        toml.add_section('workspace')
        toml.set('workspace', 'members', '[{}]'.format(', '.join(members)))

        return toml

    def iter_dependencies(self, ext=None):

        command = self.get_command_name()
        sections = ['{}.dependencies'.format(command)]

        if ext is not None:
            sections.append('{}.dependencies.{}'.format(command, ext.name))

        for section in sections:
            if self.cfg.has_section(section):
                for dep, options in self.cfg.items(section):
                    yield dep, options


def _slugify(name):
    allowed = set(string.ascii_letters + string.digits + '_')
    slug = [char if char in allowed else '_' for char in name]
    return ''.join(slug)

def find_rust_extensions(*directories, libfile="lib.rs", **kwargs):
    """Attempt to find Rust extensions in given directories.

    This function will recurse through the directories in the given
    directories, to find a name whose name is ``libfile``. When such
    a file is found, an extension is created, expecting the cargo
    manifest file (``Cargo.toml``) to be next to that file. The
    extension destination will be deduced from the name of the
    directory where that ``libfile`` is contained.

    Arguments:
        directories (list, *optional*): a list of directories to walk
            through recursively to find extensions. If none are given,
            then the current directory will be used instead.

    Keyword Arguments:
        libfile (str): the name of the file to look for when searching
            for Rust extensions. Defaults to ``lib.rs``, but might be
            changed to allow defining more *Pythonic* filenames
            (like ``__init__.rs``)!

    Note:
        All other keyword arguments will be directly passed to the
        `RustExtension` instance created when an extension is found.
        One may be interested in passing ``bindings`` and ``strip``
        options.

    Example:

        Consider the following project::

            lib/
             └ mylib/
                 └ rustext/
                     ├ lib.rs
                     ├  ...
                     └  Cargo.toml
            setup.py

        The only extension can be found in the ``lib`` module:

        .. code-block:: python

            >>> import setuptools_rust as rust
            >>> for ext in rust.find_rust_extensions("lib"):
            ...     print(ext.name, "=>", ext.path)
            lib.mylib.rustext => lib/mylib/rustext/Cargo.toml
    """

    directories = directories or [os.getcwd()]
    extensions = []

    for directory in directories:
        for base, dirs, files in os.walk(directory):
            if libfile in files:
                dotpath = os.path.relpath(base).replace(os.path.sep, '.')
                tomlpath = os.path.join(base, "Cargo.toml")
                ext = RustExtension(dotpath, tomlpath, **kwargs)
                ext.libfile = os.path.join(base, libfile)
                extensions.append(ext)

    return extensions
