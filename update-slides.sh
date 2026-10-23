#!/bin/bash
set -x
mkdir -p slides
pushd ../cs4457-slides; make
cp _dist/*.pdf ../cs4457-website/slides
popd
if false; then
    pushd ../cs4457-slides/f2024;
    for i in 2024*; do
        pushd $i
        make copy-public
        popd
    done
    popd
fi
