{
  description = "Simple flake with a devshell";

  inputs = {
    # nixpkgs.url = "github:NixOS/nixpkgs?ref=nixos-25.11";
    blueprint.url = "github:numtide/blueprint";
    blueprint.inputs.nixpkgs.follows = "nixpkgs";
    toolbox.url = "git+file:///home/user/nix/toolbox";
    nixpkgs.follows = "toolbox/nixpkgs";
    # jsys.url = "path:/home/user/nix/system";
    # nixpkgs.follows = "jsys/nixpkgs";
    unstable.url = "github:nixos/nixpkgs/nixos-unstable";
    #llm-agents.url = "github:numtide/llm-agents.nix";
    #llm-agents.inputs.nixpkgs.follows = "nixpkgs";

    # pyproject-nix = {
    #   url = "github:pyproject-nix/pyproject.nix";
    #   inputs.nixpkgs.follows = "nixpkgs";
    # };

    # uv2nix = {
    #   url = "github:pyproject-nix/uv2nix";
    #   inputs.pyproject-nix.follows = "pyproject-nix";
    #   inputs.nixpkgs.follows = "nixpkgs";
    # };

    # pyproject-build-systems = {
    #   url = "github:pyproject-nix/build-system-pkgs";
    #   inputs.pyproject-nix.follows = "pyproject-nix";
    #   inputs.uv2nix.follows = "uv2nix";
    #   inputs.nixpkgs.follows = "nixpkgs";
    # };

    # Do not follow this repo's nixpkgs: nix2container patches skopeo's vendor
    # tree; following toolbox/unstable nixpkgs often breaks that patch (missing
    # vendor/go.podman.io/image/v5). Use nix2container's locked nixpkgs instead.
    # nix2container.url = "github:nlewo/nix2container";
  };

  outputs =
    inputs:
    inputs.blueprint {
      inherit inputs;
      nixpkgs.config.allowUnfree = true;
    };
}
