#!/bin/bash
curl https://sh.rustup.rs -sSf | sh -s -- -y
export PATH="$HOME/.cargo/bin:$PATH"
pip install --upgrade pip setuptools
pip install -r requirements.txt