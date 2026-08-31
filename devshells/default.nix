{
  inputs,
  flake,
  pkgs,
  system,
  perSystem,
}:
let
  dependencies = [
    pkgs.nixfmt
    pkgs.shfmt
    pkgs.python3
    pkgs.python3Packages.invoke
    pkgs.python3Packages.pytest
    pkgs.uv
    pkgs.ruff
    # perSystem.llm-agents.claude-code
    # perSystem.llm-agents.opencode
    # perSystem.llm-agents.gemini-cli
    # perSystem.llm-agents.codex
    # perSystem.llm-agents.cursor-agent
    # perSystem.llm-agents.backlog-md
    # perSystem.llm-agents.ck
    # perSystem.llm-agents.rtk
    pkgs.findutils
    pkgs.ripgrep
    pkgs.nodejs_24
    pkgs.parquet-tools
    pkgs.gzip
    pkgs.zip
    pkgs.unzip
  ];

  unstablePkgs = import inputs.unstable {
    inherit system;
    config.allowUnfree = true;
  };

  ideExtensions =
    (with pkgs.vscode-extensions; [
      jnoortheen.nix-ide
      ms-python.python
      ms-python.debugpy
      charliermarsh.ruff
      anthropic.claude-code
      ms-toolsai.jupyter
    ])
    ++ pkgs.vscode-utils.extensionsFromVscodeMarketplace [
      {
        name = "quantconnect";
        publisher = "quantconnect";
        version = "0.1.2056";
        sha256 = "9QH5G3R8DgwXBMqgAdiaaYGRlh72G1NqCvCeaubm+F8=";
      }
    ];

  ide = inputs.toolbox.packages."${system}".sec-code.override {
    name = "ide";
    editor = unstablePkgs.code-cursor;
    extensions = ideExtensions;
    dependencies = dependencies;
  };
  jsh = inputs.toolbox.packages."${system}".jsh.override {
    extraPackages = dependencies;
    ide = unstablePkgs.code-cursor;
    ideExtensions = ideExtensions;
    ideExtraPackages = dependencies;
  };
in
inputs.toolbox.lib.mkDevShell {
  tmux = null;
  inherit pkgs;
  packages = dependencies ++ [
    ide
    jsh
    pkgs.stdenv.cc.cc.lib # Standard C++ library
    pkgs.zlib
    inputs.toolbox.packages."${system}".ibkr-gateway
    pkgs.meld
  ];
  env = {
    UV_PYTHON_DOWNLOADS = "never";
    # Ensures compiled wheels find system libraries on NixOS
    LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath [
      pkgs.stdenv.cc.cc.lib
      pkgs.zlib
    ];
    JAWTEST = "123";
  };
  # bash = pkgs.bashInteractive;
  # tmux = null;
  project = "trading";
  devshell_name = "default";
}
