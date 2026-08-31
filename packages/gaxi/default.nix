{ pkgs, ... }:
let
  inherit (pkgs) lib python3Packages;
  root = ../..;
  sources = lib.fileset.fileFilter (file: !lib.hasSuffix ".pyc" file.name);
  pyproject = lib.importTOML (root + "/pyproject.toml");
in
python3Packages.buildPythonApplication {
  pname = pyproject.project.name;
  inherit (pyproject.project) version;
  pyproject = true;

  # Only the files that define the package and its tests, so editing docs or
  # CI does not invalidate the build. Compiled bytecode left behind by a local
  # run is not part of the source either.
  src = lib.fileset.toSource {
    inherit root;
    fileset = lib.fileset.unions [
      (root + "/pyproject.toml")
      (root + "/LICENSE") # `license-files` makes this a build input
      (sources (root + "/src"))
      (sources (root + "/tests"))
    ];
  };

  build-system = [ python3Packages.setuptools ];

  # gaxi speaks HTTP through the standard library, so the runtime closure is
  # the interpreter alone. The dev group (python-codeforge) is a quality gate,
  # not a dependency of the released package.
  dependencies = [ ];

  nativeCheckInputs = [
    python3Packages.pytestCheckHook
    python3Packages.hypothesis
  ];

  # The integration suite drives a live instance (GAXI_TEST_SERVER) and the
  # sandbox has no network, so the build gates on the offline suites.
  enabledTestPaths = [
    "tests/gaxi/unit"
    "tests/gaxi/properties"
  ];

  pythonImportsCheck = [ "gaxi" ];

  meta = {
    inherit (pyproject.project) description;
    license = lib.licenses.mit;
    mainProgram = "gaxi";
    platforms = lib.platforms.unix;
  };
}
