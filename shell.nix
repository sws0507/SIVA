let
  name = "ChiselAIA";
  # pin nixpkgs to latest nixos-24.05
  pkgs = import (fetchTarball {
    url = "https://github.com/NixOS/nixpkgs/archive/ecbc1ca8ffd6aea8372ad16be9ebbb39889e55b6.tar.gz";
    sha256 = "0yfaybsa30zx4bm900hgn3hz92javlf4d47ahdaxj9fai00ddc1x";
  }) {};
  circtPkgsBase = import (pkgs.fetchFromGitHub {
    owner = "NixOS";
    repo = "nixpkgs";
    rev = "771b079bb84ac2395f3a24a5663ac8d1495c98d3";
    sha256 = "0l1l9ms78xd41xg768pkb6xym200zpf4zjbv4kbqbj3z7rzvhpb7";
  }) {};
  circtLLVMNoCheck = circtPkgsBase.circt.passthru.llvm.overrideAttrs (_: {
    doCheck = false;
    doInstallCheck = false;
    dontCheck = true;
    checkTarget = "";
    checkInputs = [];
    nativeCheckInputs = [];
    checkPhase = "true";
    installCheckPhase = "true";
  });
  circtNoCheck = circtPkgsBase.circt.overrideAttrs (old: {
    doCheck = false;
    doInstallCheck = false;
    dontCheck = true;
    checkTarget = "";
    checkInputs = [];
    nativeCheckInputs = [];
    checkPhase = "true";
    installCheckPhase = "true";
    buildInputs = builtins.map (input:
      if (input.pname or "") == "circt-llvm" then circtLLVMNoCheck else input
    ) old.buildInputs;
    cmakeFlags = builtins.map (flag:
      if pkgs.lib.hasPrefix "-DMLIR_DIR=" flag
      then "-DMLIR_DIR=${circtLLVMNoCheck.dev}/lib/cmake/mlir"
      else flag
    ) old.cmakeFlags;
    passthru = old.passthru // {
      llvm = circtLLVMNoCheck;
    };
  });
  my-python3 = pkgs.python3.withPackages (python-pkgs: let
    ghdl-stub = pkgs.writeShellScriptBin "ghdl" ''
      echo "ghdl is not available in this shell" >&2
      exit 1
    '';
    cocotb-no-ghdl-checks = (python-pkgs.cocotb.override {
      ghdl = ghdl-stub;
    }).overridePythonAttrs (_: {
      doCheck = false;
      doInstallCheck = false;
      nativeCheckInputs = [];
      checkPhase = "true";
      installCheckPhase = "true";
    });
  in [ cocotb-no-ghdl-checks ]);
in pkgs.mkShell {
  inherit name;

  buildInputs = [
    pkgs.mill
    pkgs.verilator
    circtNoCheck
    my-python3
    # for generating gtkwave's fst waveform
    pkgs.zlib
  ];

  shellHook = ''
    export CHISEL_FIRTOOL_PATH=${circtNoCheck}/bin/
    export PYTHONPATH+=:${my-python3}/lib/${my-python3.libPrefix}/site-packages
    export PYTHONPATH+=:$(realpath ./test)
    export LIBGL_ALWAYS_SOFTWARE=1
    # To enable pdb when cocotb test failed
    export COCOTB_PDB_ON_EXCEPTION=1
    echo "SIVA shell ready. Run: scripts/verify-basic.sh"
  '';
}
