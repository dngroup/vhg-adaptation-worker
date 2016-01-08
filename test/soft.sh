#!/bin/bash

echo "stop container"
cd hard
QUEUE=hard docker-compose kill
cd ../soft
QUEUE=soft docker-compose kill
echo "start container"
QUEUE=soft docker-compose up -d
wget --tries=0 http://localhost:25672/cli/rabbitmqadmin -O rabbitmqadmin
chmod +x rabbitmqadmin

echo ---------------------------------------------
#./rabbitmqadmin --port=25672 -f long -d 3 list queues
echo send request
sleep 3
./rabbitmqadmin --port=25672 publish exchange=amq.default routing_key=soft properties='{"content_encoding":"utf-8", "content_type":"application/json"}'  payload='{"id":"testsoft","task":"adaptation.commons.encode_workflow","args":[],"kwargs":{"url":"http://nginx/1.mp4","qualities":{"quality":[{"name":"lowx264","bitrate":500,"codec":"libx264","height":320},{"name":"lowx265","bitrate":250,"codec":"libx265","height":320}]}},"retries":1,"eta":"2015-12-09T07:54:42+01:00"}'
echo $?
echo ---------------------------------------------
echo ---------------------------------------------
echo ---------------------------------------------
echo ---------------------------------------------
#./rabbitmqadmin --port=25672 get queue=transcode-result
sleep 10
result=$(./rabbitmqadmin --port=25672 get queue=transcode-result requeue=false | grep transcode-result |  sed "s/.* | \({.*} \).*|/\1/g"|python -m json.tool|grep md5|sed "s/.*md5\": \"\([0-9a-fA-F]*\)\".*/\1/g")
echo $result

if [[ "$result" == "63e0f7021b3fc6d55d4d6fd9a8b745ac" ]]; then
    echo "ok"
    echo "test transcode result maybe not equal but if you get a md5 is maybe ok"
    sleep 20
    result=$(./rabbitmqadmin --port=25672 get queue=transcode-result requeue=false | grep transcode-result |  sed "s/.* | \({.*} \).*|/\1/g"|python -m json.tool|grep md5|sed "s/.*md5\": \"\([0-9a-fA-F]*\)\".*/\1/g")
    echo $result

    if [[ "$result" == "2c7309b9e6eae4a9fb43d34e88f71c57" ]]; then
        echo "ok"
        sleep 10
        result=$(./rabbitmqadmin --port=25672 get queue=transcode-result requeue=false | grep transcode-result |  sed "s/.* | \({.*} \).*|/\1/g"|python -m json.tool|grep md5|sed "s/.*md5\": \"\([0-9a-fA-F]*\)\".*/\1/g")
        echo $result

        if [[ "$result" == "2f7bdabf7b917bf0c4be51e0f887ab4a" ]]; then
            echo "ok"
        else
            echo "not ok";
            exit -1
        fi

    else
        echo "not ok";
        exit -1
    fi
    docker-compose stop
    exit 0
else
    echo "not ok";
    exit -1
fi

# sed "s/.* | \({.*} \).*|/\1/g"|python -m json.tool|grep md5|sed "s/.*md5\": \"\([0-9a-fA-F]*\)\".*/\1/g"
#docker-compose rm -f
