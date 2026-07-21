{
  description = "NixOS Steam Patcher GUI";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
  let
    system = "x86_64-linux";
    pkgs = nixpkgs.legacyPackages.${system};


    pythonEnv = pkgs.python3.withPackages (ps: with ps; [
      pygobject3
      vdf
      pillow
    ]);

    desktopItem = pkgs.makeDesktopItem {
      name = "steam-patcher";
      desktopName = "Steam Patcher";
      exec = "steam-patcher";
      icon = "steam";
      comment = "NixOS Steam shortcut and icon fixer";
      categories = [ "Utility" "System" ];
    };

  in {
    packages.${system}.default = pkgs.stdenv.mkDerivation {
      pname = "steam-patcher";
      version = "1.0.0";

      src = ./.;

      nativeBuildInputs = [
        pkgs.wrapGAppsHook4
        pkgs.gobject-introspection
        pkgs.copyDesktopItems
      ];


      buildInputs = [
        pkgs.gtk4
        pkgs.libadwaita
        pythonEnv
        pkgs.adwaita-icon-theme
      ];

      desktopItems = [ desktopItem ];

      installPhase = ''
        mkdir -p $out/bin
        cp steam_patcher_gtk.py $out/bin/steam-patcher
        chmod +x $out/bin/steam-patcher
      '';
    };

    apps.${system}.default = {
      type = "app";
      program = "${self.packages.${system}.default}/bin/steam-patcher";
    };
  };
}
