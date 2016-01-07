#!/bin/bash

cd soft
docker-compose kill
docker-compose up -d
wget --tries=0 http://localhost:25672/cli/rabbitmqadmin -O rabbitmqadmin
chmod +x rabbitmqadmin

echo ---------------------------------------------
#./rabbitmqadmin --port=25672 -f long -d 3 list queues
echo send request
./rabbitmqadmin --port=25672 publish exchange=amq.default routing_key=soft properties='{"content_encoding":"utf-8", "content_type":"application/json"}'  payload='{"id":"testsoft","task":"adaptation.commons.encode_workflow","args":[],"kwargs":{"url":"http://nginx/1.mp4","qualities":{"quality":[{"name":"lowx264","bitrate":500,"codec":"libx264","height":320},{"name":"lowx265","bitrate":250,"codec":"libx265","height":320}]}},"retries":1,"eta":"2015-12-09T07:54:42+01:00"}'
echo $?
echo ---------------------------------------------
echo ---------------------------------------------
echo ---------------------------------------------
echo ---------------------------------------------
#./rabbitmqadmin --port=25672 get queue=transcode-result
sleep 15
result=$(./rabbitmqadmin --port=25672 get queue=transcode-result requeue=false | grep transcode-result |  sed "s/.* | \({.*} \).*|/\1/g"|python -m json.tool|grep md5|sed "s/.*md5\": \"\([0-9a-fA-F]*\)\".*/\1/g")
echo $result

if [[ "$result" == "a3b9f93268cc8b5e4a09bda51d19f85e" ]]; then
    echo "ok"
    result=$(./rabbitmqadmin --port=25672 get queue=transcode-result requeue=false | grep transcode-result |  sed "s/.* | \({.*} \).*|/\1/g"|python -m json.tool|grep md5|sed "s/.*md5\": \"\([0-9a-fA-F]*\)\".*/\1/g")
    echo $result

    if [[ "$result" == "e46f43484d4bbc2b21b1900e930143ee" ]]; then
        echo "ok"
        result=$(./rabbitmqadmin --port=25672 get queue=transcode-result requeue=false | grep transcode-result |  sed "s/.* | \({.*} \).*|/\1/g"|python -m json.tool|grep md5|sed "s/.*md5\": \"\([0-9a-fA-F]*\)\".*/\1/g")
        echo $result

        if [[ "$result" == "56da1b97b62c53f5d50e369b2b0c7462" ]]; then
            echo "ok"
        else
            echo "not ok";
            exit -1
        fi
        exit 0
    else
        echo "not ok";
        exit -1
    fi
    exit 0
else
    echo "not ok";
    exit -1
fi

# sed "s/.* | \({.*} \).*|/\1/g"|python -m json.tool|grep md5|sed "s/.*md5\": \"\([0-9a-fA-F]*\)\".*/\1/g"
#docker-compose rm -f