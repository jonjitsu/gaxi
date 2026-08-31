# Blueprint maps this file to `packages.default`, so `nix build` and `nix run`
# with no attribute reach gaxi. The definition itself lives in packages/gaxi.
{ perSystem }:
perSystem.self.gaxi
