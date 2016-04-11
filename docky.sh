#!/usr/bin/env bash
./build_egg.sh
cp ./dist/*.egg ./docker
sudo docker build ./docker
