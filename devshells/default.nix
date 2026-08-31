{ pkgs, ... }:
pkgs.mkShell {
  packages = [
    # `uv sync` installs the dev group (python-codeforge and the gates it
    # drives) from PyPI; the shell supplies the interpreter it binds to.
    pkgs.python313
    pkgs.uv
    # Editor-facing copies of two gates uv also installs, so a formatter or
    # `nix fmt` works before the first sync.
    pkgs.ruff
    pkgs.nixfmt
    # pyright ships a Node language server and would otherwise fetch its own.
    pkgs.nodejs_24
    pkgs.git
  ];

  env = {
    UV_PYTHON_DOWNLOADS = "never";
    # The dev group installs binary wheels (mypy, semgrep, complexipy), which
    # need the loader's libraries on NixOS.
    LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
      pkgs.stdenv.cc.cc.lib
      pkgs.zlib
    ];
  };
}
