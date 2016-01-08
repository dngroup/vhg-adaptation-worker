#!/bin/bash

echo "stop container"
cd soft
QUEUE=soft docker-compose kill
cd ../hard
QUEUE=hard docker-compose kill
QUEUE=hard docker-compose up -d
echo "start container"
wget --tries=0 http://localhost:25672/cli/rabbitmqadmin -O rabbitmqadmin
chmod +x rabbitmqadmin

echo ---------------------------------------------
#./rabbitmqadmin --port=25672 -f long -d 3 list queues
sleep 3
echo send request
./rabbitmqadmin --port=25672 publish exchange=amq.default routing_key=hard properties='{"content_encoding":"utf-8", "content_type":"application/json"}'  payload='{"id":"testhard","task":"adaptation.commons.encode_workflow_hard","args":[],"kwargs":{"url":"http://nginx/1.mp4","qualities":{"quality":[{"name":"h264_gpu","bitrate":500,"codec":"h264_gpu","height":320},{"name":"h265_gpu","bitrate":250,"codec":"h265_gpu","height":320}]}},"retries":1,"eta":"2015-12-09T07:54:42+01:00"}'
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

    if [[ "$result" == "a3b9f93268cc8b5e4a09bda51d19f85e" ]]; then
        echo "ok"
        result=$(./rabbitmqadmin --port=25672 get queue=transcode-result requeue=false | grep transcode-result |  sed "s/.* | \({.*} \).*|/\1/g"|python -m json.tool|grep md5|sed "s/.*md5\": \"\([0-9a-fA-F]*\)\".*/\1/g")
        echo $result

        if [[ "$result" == "a3b9f93268cc8b5e4a09bda51d19f85e" ]]; then
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
