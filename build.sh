#!/bin/bash
curl https://sh.rustup.rs -sSf | sh -s -- -y
export PATH="$HOME/.cargo/bin:$PATH"
pip install --upgrade pip setuptools
pip install -r requirements.txt
apt-get update && apt-get install -y libgl1
pip install --upgrade pip setuptools
pip install -r requirements.txt