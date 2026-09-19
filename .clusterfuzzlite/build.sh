#!/bin/sh
set -eu

# The official ClusterFuzzLite Python builder provides Atheris, libFuzzer, and
# PyInstaller. Its interpreter can lag the application's supported Python
# floor, so fuzzing imports the bounded parser modules directly from src rather
# than weakening package metadata or resolving/installing project dependencies.

for fuzzer in fuzz/*_fuzzer.py; do
    name=$(basename "$fuzzer" .py)
    package="${name}.pkg"
    pyinstaller --paths src --distpath "$OUT" --onefile --name "$package" "$fuzzer"
    cat > "$OUT/$name" <<EOF
#!/bin/sh
# LLVMFuzzerTestOneInput marker used by ClusterFuzzLite target detection.
this_dir=\$(CDPATH= cd -- "\$(dirname -- "\$0")" && pwd)
exec "\$this_dir/$package" "\$@"
EOF
    chmod +x "$OUT/$name"
    if test -d "fuzz/corpus/$name"; then
        zip -q -j "$OUT/${name}_seed_corpus.zip" "fuzz/corpus/$name"/*
    fi
done
