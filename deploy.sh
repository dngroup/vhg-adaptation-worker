#!/bin/bash
#Script for Ubuntu 14.04

#Install RabbitMQ for Celery, Then Celery and MediaInfo wrapper for python
apt-get -y install rabbitmq-server python-pip mediainfo python-lxml python-dev wget yasm
pip install celery pymediainfo
#Compile Manually MP4Box from GPAC project
./compile_MP4Box.sh

#Compile FFmpeg
./compile_ffmpeg.sh
