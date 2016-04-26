#!/usr/bin/env bash
docker build -t dngroup/vhg-adaptation-worker:t-nova .
docker push  dngroup/vhg-adaptation-worker:t-nova
docker build -t dngroup/vhg-adaptation-worker .
docker push  dngroup/vhg-adaptation-worker

