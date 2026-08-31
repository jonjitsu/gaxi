{
  description = "gaxi developer shells built on the private toolbox flake";

  # Deliberately a separate flake. The toolbox lives at a local path that only
  # exists on a machine that has it checked out, so keeping it here means the
  # released flake stays fetchable by everyone: `nix build`, `nix flake check`
  # and `nix flake show` at the repository root never reach this file.
  inputs = {
    toolbox.url = "git+file:///home/user/nix/toolbox";
    nixpkgs.follows = "toolbox/nixpkgs";
  };

  outputs =
    {
      toolbox,
      nixpkgs,
      ...
    }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-darwin"
      ];
    in
    {
      devShells = nixpkgs.lib.genAttrs systems (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            config.allowUnfree = true;
          };
          # gaxi's toolchain, kept in step with ../devshells/default.nix. A
          # flake may not read files above its own root, so this list is
          # duplicated rather than imported.
          dependencies = [
            pkgs.python313
            pkgs.uv
            pkgs.ruff
            pkgs.nixfmt
            pkgs.nodejs_24
            pkgs.git
          ];

          ideExtensions = with pkgs.vscode-extensions; [
            jnoortheen.nix-ide
            ms-python.python
            ms-python.debugpy
            charliermarsh.ruff
            anthropic.claude-code
          ];

          jsh = toolbox.packages.${system}.jsh.override {
            extraPackages = dependencies;
            inherit ideExtensions;
            ideExtraPackages = dependencies;
          };
        in
        {
          default = toolbox.lib.mkDevShell {
            inherit pkgs;
            tmux = null;
            packages = dependencies ++ [
              jsh
              pkgs.stdenv.cc.cc.lib
              pkgs.zlib
            ];
            env = {
              UV_PYTHON_DOWNLOADS = "never";
              # Compiled wheels in the dev group need the loader's libraries.
              LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
                pkgs.stdenv.cc.cc.lib
                pkgs.zlib
              ];
            };
            project = "gaxi";
            devshell_name = "default";
          };
        }
      );
    };
}
