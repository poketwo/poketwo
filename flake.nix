{
  description = "A small Pokécord clone";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, flake-utils, poetry2nix }: flake-utils.lib.eachDefaultSystem (system:
    let
      pkgs = import nixpkgs {
        inherit system;
        overlays = [ poetry2nix.overlays.default ];
      };

      # Python version to use. Should match the version in pyproject.toml.
      python = pkgs.python310;

      # Since some dependencies require additional build inputs, we need to
      # specify them here.
      extra-build-requirements = {
        discord-ext-menus-views = [ "poetry" ];
        discord-ext-menus = [ "setuptools" ];
        discord-flags = [ "setuptools" ];
        jishaku = [ "setuptools" ];
      };

      # This uses the above to build a poetry2nix overrides set that adds the
      # build inputs to the Python packages.
      overrides = pkgs.poetry2nix.defaultPoetryOverrides.extend (final: prev:
        builtins.mapAttrs
          (package: reqs:
            let
              reqs-pkgs = builtins.map (pkg: if builtins.isString pkg then prev.${pkg} else pkg) reqs;
            in
            prev.${package}.overridePythonAttrs (old: {
              buildInputs = (old.buildInputs or [ ]) ++ reqs-pkgs;
              nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ reqs-pkgs;
            })
          )
          extra-build-requirements
      );

      # This is the actual package definition. It uses poetry2nix to build a
      # Python package from the poetry.lock file in the current directory.
      env = pkgs.poetry2nix.mkPoetryEnv {
        inherit python overrides;
        projectDir = self;
        groups = [ "dev" ];
        preferWheels = true;
      };
    in
    {
      devShells.default = pkgs.mkShell {
        buildInputs = [
          pkgs.poetry
          env
        ];
      };
    }
  );
}
