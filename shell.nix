let
  pkgs = import <nixpkgs>{};
in
pkgs.mkShellNoCC rec {
  name = "unnamed";
  venvDir = "./.venv";
  buildInputs = with pkgs; [
    python3Packages.python
    python3Packages.venvShellHook
    python3Packages.ruff
    python3Packages.python-lsp-server
  ];
  packages = with pkgs; [
    uv
  ];
}
