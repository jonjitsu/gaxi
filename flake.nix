{
  description = "gaxi - an AXI bridge for Gitea-compatible instances";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    blueprint.url = "github:numtide/blueprint";
    blueprint.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = inputs: inputs.blueprint { inherit inputs; };
}
