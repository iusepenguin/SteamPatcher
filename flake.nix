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

  in {
    packages.${system}.default = pkgs.stdenv.mkDerivation {
      pname = "steam-patcher";
      version = "1.0.0";

      src = ./.;

      nativeBuildInputs = [
        pkgs.wrapGAppsHook4
        pkgs.gobject-introspection
      ];

      buildInputs = [
        pkgs.gtk4
        pkgs.libadwaita
        pythonEnv
        pkgs.adwaita-icon-theme
      ];

      installPhase = ''
        mkdir -p $out/bin $out/share/applications
        cp steam_patcher_gtk.py $out/bin/steam-patcher
        chmod +x $out/bin/steam-patcher

        cat << EOF > $out/share/applications/steam-patcher.desktop
[Desktop Entry]
Type=Application
Name=Steam Patcher
Exec=steam-patcher
Icon=steam
Comment=NixOS Steam shortcut and icon fixer
Categories=Utility;System;
EOF
      '';
    };

    apps.${system}.default = {
      type = "app";
      program = "${self.packages.${system}.default}/bin/steam-patcher";
    };
  };
}
