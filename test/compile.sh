#!/bin/bash
cd hard
docker-compose pull
cd ../..
docker build -t dngroup/vhg-adaptation-worker:t-nova . 
