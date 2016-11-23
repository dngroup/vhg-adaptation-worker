__author__ = 'nherbaut dbourasseau'
# coding: utf-8
import copy
import json
import math
import mimetypes
import shutil
import subprocess
import urllib

import pika
# import swiftclient
import time
from celery.utils.log import get_task_logger
from lxml import etree
# config import
from .settings import *
# for md5
import hashlib
import uuid
# for post  transcoding result
import requests
# celery import
from celery import Celery
# media info wrapper import
from pymediainfo import MediaInfo
# lxml import to edit dash playlist
from lxml import etree as LXML
# use to get home directory
from os.path import expanduser
# context helpers
from .context import get_transcoded_folder, get_transcoded_file, get_hls_transcoded_playlist, get_hls_transcoded_folder, \
    get_dash_folder, get_hls_folder, get_hls_global_playlist, get_dash_mpd_file_path
# Encoding profil
from adaptation.EncodingProfil import EncodingProfile

# main app for celery, configuration is in separate settings.ini file
app = Celery('tasks')

# logger FROM CELERY, not native python
logger = get_task_logger(__name__)

# inject settings into celery
app.config_from_object('adaptation.settings')

pika_con_params = pika.URLParameters(os.environ["CELERY_BROKER_URL"])

pika_con_params.credentials.password = "guest"
# connection randomly failing in the cloud
pika_con_params.socket_timeout = 300

connection = pika.BlockingConnection(pika_con_params)
channel_pika = connection.channel()
channel_pika.queue_declare(queue='transcode-result', durable=True, exclusive=False, auto_delete=False)


# logger.info("connecting to swift")
#
# try:
#     swift_authurl, swift_username, swift_password = (os.environ["ST_AUTH"], os.environ["ST_USER"], os.environ["ST_KEY"])
#     swift_connection = swiftclient.Connection(authurl=swift_authurl, user=swift_username, key=swift_password)
#     # verifying swift connectivity
#     swift_connection.head_account()
#
# except KeyError as key:
#     # no swift => no data will be sent to streamer
#     logger.warning("swift is NOT configured, nothing will be sent to streamer")
#     # swift_authurl,swift_username, swift_password = (None,None,None)
#     swift_connection = None
# except swiftclient.ClientException as ce:
#     logger.warning("swift credentials are did NOT pass, nothing will be sent to streamer")
#     # swift_authurl,swift_username, swift_password = (None,None,None)
#     swift_connection = None


def run_background(*args):
    try:
        code = subprocess.check_call(*args, shell=True)
    except subprocess.CalledProcessError:
        print("Error")


# commented since publication occurs atomically before notification of a new video format.
# this one use to push everything from the output folder
# @app.task(bind=True)
# def publish_output(*args, **kwargs):
#     self = args[0]
#     context = args[1]
#     output_folder = context["folder_out"]
#     if swift_connection is None:
#         logger.warn("swift connection is not active, skipping streamer upload")
#
#     else:
#         headers = {}
#         container = os.path.basename(output_folder)
#         headers["X-Container-Read"] = " .r:*"
#         headers["X-Container-Meta-Access-Control-Allow-Origin"] = "*"
#         headers["X-Container-Meta-Access-Control-Allow-Method"] = "GET"
#
#         swift_connection.put_container(container, headers)
#         for object in os.walk(output_folder):
#             paths = object[2]
#             root = object[0]
#             for path in paths:
#                 filepath = os.path.abspath(os.path.join(root, path))
#                 with open(filepath) as f:
#                     content_type, encoding = mimetypes.guess_type(filepath)
#                     swift_connection.put_object(container, os.path.join(root, path)[len(output_folder) + 1:], f,
#                                                 content_type=content_type)
#
#     return context

# @app.task(bind=True)
# def publish_output(*args, **kwargs):
#     self = args[0]
#     context = args[1]
#     name = context["name"]
#     output_folder = context["folder_out"]
#     context["md5"] = md5(context["absolute_name"])
#     if swift_connection is None:
#         logger.warn("swift connection is not active, skipping streamer upload")
#
#     else:
#         headers = {}
#         container = os.path.basename(output_folder)
#         headers["X-Container-Read"] = " .r:*"
#         headers["X-Container-Meta-Access-Control-Allow-Origin"] = "*"
#         headers["X-Container-Meta-Access-Control-Allow-Method"] = "GET"
#
#         swift_connection.put_container(container, headers)
#         # for object in os.walk(output_folder):
#         encoding_folder = get_transcoded_folder(context)
#         # paths = object[2]
#         root = encoding_folder
#
#         path = name  # + ".mp4"
#         # for path in paths:
#         filepath = context["absolute_name"]  # os.path.abspath(os.path.join(root, path))
#         with open(filepath) as f:
#             content_type, encoding = mimetypes.guess_type(filepath)
#             swift_connection.put_object(container, context["absolute_name"][len(output_folder) + 1:], f,
#                                         content_type=content_type)
#
#     return context

@app.task(bind=True)
def publish_output(*args, **kwargs):
    self = args[0]
    context = args[1];
    name = context["name"];
    returnURL = kwargs["returnURL"];

    output_folder = context["folder_out"]
    context["md5"] = md5(context["absolute_name"])

    print(("PUT " + context["absolute_name"] + " to " + returnURL))
    content_type, encoding = mimetypes.guess_type(context["absolute_name"])
    if content_type is None:
        content_type = "video/mp4"
    # files = {'upload_file': open(context["absolute_name"],'rb')}
    data = open(context["absolute_name"], 'rb').read()
    #         headers["X-Container-Read"] = " .r:*"
    #         headers["X-Container-Meta-Access-Control-Allow-Origin"] = "*"
    #         headers["X-Container-Meta-Access-Control-Allow-Method"] = "GET"

    r = requests.put(returnURL, data, headers={'Content-Type': content_type, "X-Container-Read": ".r:*","X-Container-Meta-Access-Control-Allow-Origin": "*","X-Container-Meta-Access-Control-Allow-Method": "GET"})

    print("PUT")

    # print(r.content)

    return context


@app.task(bind=True)
def notify(*args, **kwargs):
    self = args[0]
    context = args[1]
    main_task_id = kwargs["main_task_id"]
    logger.debug("sending %s to result queue" % json.dumps(kwargs))
    try:
        channel_pika.basic_publish(exchange='',
                                   routing_key='transcode-result',
                                   body=json.dumps(kwargs))
    except:
        logger.error("failed to connect to pika, trying again one more time")
        connection = pika.BlockingConnection(pika_con_params)

        channel_pika = connection.channel()
        channel_pika.queue_declare(queue='transcode-result', durable=True, exclusive=False, auto_delete=False)
        channel_pika.basic_publish(exchange='',
                                   routing_key='transcode-result',
                                   body=json.dumps(kwargs))

    return context


# @app.task()
# def deploy_original_file(*args, **kwargs):
#     context = args[0]
#     encoding_folder = get_transcoded_folder(context)
#     if not os.path.exists(encoding_folder):
#         os.makedirs(encoding_folder)
#     shutil.copyfile(context["original_file"], os.path.join(encoding_folder, "original.mp4"))
#     return context


@app.task()
def ddo(url):
    encode_workflow.delay(url=url)


@app.task()
def md5(file):
    hash = hashlib.md5()
    with open(file, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash.update(chunk)
    return hash.hexdigest()


# docker run -ite FRONTAL_HOSTNAME="192.168.236.81" -e FRONTAL_PORT="8080" -p 8080:8080 nherbaut/adapted-video-osgi-bundle
# Exchange	(AMQP default)
# Routing Key	celery
# Properties
# priority:	0
# delivery_mode:	2
# headers:
# content_encoding:	utf-8
# content_type:	application/json
# Payload
# 213 bytes
# Encoding: string
# {"id": "20e56aa73ca741a29bb24fb02072a1b2", "task": "adaptation.commons.encode_workflow", "args": ["http://clips.vorwaerts-gmbh.de/big_buck_bunny.mp4?13"], "kwargs": {}, "retries": 0, "eta": "2015-11-26T09:23:33Z"}
# {
#    "id":"20e56aa73ca741a29bb24fb02072a1b2",
#    "task":"adaptation.commons.encode_workflow",
#    "args":[
#
#    ],
#    "kwargs":{
#       "url":"http://clips.vorwaerts-gmbh.de/big_buck_bunny.mp4?13",
#       "qualities":{
#          "quality":[
#             {
#                "name":"lowx264",
#                "bitrate":500,
#                "codec":"libx264",
#                "height":320
#             },
#             {
#                "name":"lowx265",
#                "bitrate":250,
#                "codec":"libx265",
#                "height":320
#             }
#          ]
#       }
#    },
#    "retries":1,
#    "eta":"2015-12-09T07:54:42+01:00"
# }

@app.task(bind=True)
def encode_workflow(*args, **kwargs):
    timestart = time.time()
    self = args[0]
    main_task_id = self.request.id
    url = kwargs["url"]
    qualities = kwargs["qualities"]
    returnURL = self.request.returnURL
    encodingprofils = [];
    for quality in qualities["quality"]:
        print(quality)
        profil = EncodingProfile(quality)
        encodingprofils.insert(0, profil)

        # encodingprofils = [EncodingProfile('lowx264',500,"libx264",320),EncodingProfile('lowx265',250,"libx265",320)]

    print("(------------")

    context = download_file(
        context={"url": url, "returnURL": returnURL, "folder_out": os.path.join(config["folder_out"], main_task_id),
                 "id": main_task_id,
                 "folder_in": config["folder_in"]})
    context = get_video_size(context)
    for encodingprofil in encodingprofils:
        print(encodingprofil.name)

        #  for target_height, bitrate, name in config["bitrates_size_tuple_list"]:
        context_loop = copy.deepcopy(context)
        context_loop["name"] = encodingprofil.name
        context_loop = compute_target_size(context_loop, target_height=encodingprofil.target_height)
        context_loop = transcode(context_loop, bitrate=encodingprofil.bitrate, segtime=4, name=encodingprofil.name,
                                 codec=encodingprofil.codec)
        context_loop = publish_output(context_loop, returnURL=encodingprofil.returnURL)
        context_loop = notify(context_loop, main_task_id=main_task_id, quality=encodingprofil.name,
                              md5=context_loop["md5"], timestart=timestart, timeend=time.time())
        context_loop = remove_video(context_loop)
    context = remove_video(context)


@app.task
def send_file_SSH(*args, **kwargs):
    context = kwargs["context"]

    file = kwargs["file"]
    path = kwargs["path"]
    serverVTU = os.environ.get("SERVER_VTU", SERVER_VTU)
    sshPortVTU = os.environ.get("SSH_PORT_VTU", SSH_PORT_VTU)
    sshkey = os.environ.get("SSH_KEY", "sshkey")

    command_line = 'scp -P ' + sshPortVTU + " -i " + sshkey + "  -o \"StrictHostKeyChecking no\" " + file + ' herbaut@' + serverVTU + ':' + path
    print("send file over ssh ", command_line)
    resp = subprocess.call(command_line, shell=True)
    if (resp == 0):
        print("Success send file")
    else:
        print("Fail send file")
    return context


@app.task()
def createXML(*args, **kwargs):
    encodingprofils = kwargs["encodingprofils"]
    context = kwargs["context"]

    # Create the root element
    page = etree.Element('vTU')

    # Make a new document tree
    doc = etree.ElementTree(page)

    # Add the subelements
    inxml = etree.SubElement(page, 'in')
    local = etree.SubElement(inxml, 'local')
    stream = etree.SubElement(local, 'stream')
    stream.text = context["nameid"]
    for encodingprofil in encodingprofils:
        print(encodingprofil.name)
        #    context_loop = copy.deepcopy(context)
        #    context_loop["name"] = encodingprofil.name
        #    context_loop = compute_target_size(context_loop, target_height=encodingprofil.target_height)


        outxml = etree.SubElement(page, 'out')

        context_loop = copy.deepcopy(context)
        context_loop = compute_target_size(context_loop, target_height=encodingprofil.target_height)

        outlocal = etree.SubElement(outxml, 'local')
        overwrite = etree.SubElement(outlocal, 'overwrite')
        overwrite.text = "y"
        outstream = etree.SubElement(outlocal, 'stream')
        outstream.text = context["id"] + encodingprofil.name + ".mp4"
        codec = etree.SubElement(outxml, 'codec')
        vcodec = etree.SubElement(codec, 'vcodec')
        vcodec.text = encodingprofil.codec
        acodec = etree.SubElement(codec, 'acodec')
        acodec.text = "aac"
        vbitrate = etree.SubElement(codec, 'vbitrate')
        vbitrate.text = str(encodingprofil.bitrate) + "k"
        abitrate = etree.SubElement(codec, 'abitrate')
        abitrate.text = "128k"
        vsizewidth = etree.SubElement(codec, 'vsizewidth')
        vsizewidth.text = str(context_loop["target_width"])
        vsizeheight = etree.SubElement(codec, 'vsizeheight')
        vsizeheight.text = str(context_loop["target_height"])

    # <vsize></vsize>
    #   <vframerate></vframerate>
    #   <asamplerate></asamplerate>
    #   <achannels></achannels>

    # For multiple multiple attributes, use as shown above

    # Save to XML file
    home = expanduser("~")
    try:
        os.makedirs(home + "/worker/")
        # os.makedirs("/usr/share/nginx/html/vTU/output/" + time.strftime("%Y.%m.%d"))
    except OSError as e:
        print("folder already exist")
        pass
    outFile = open(home + "/worker/" + context["nameid"] + '.xml', 'w')
    doc.write(outFile, xml_declaration=True, encoding='utf-8', pretty_print=True)
    context["xml_file"] = home + "/worker/" + context["nameid"] + '.xml'
    return context


#
# {
#    "id":"20e56aa73ca741a29bb24fb02072a1b2",
#    "task":"adaptation.commons.encode_workflow_hard",
#    "args":[
#
#    ],
#    "kwargs":{
#       "url":"http://clips.vorwaerts-gmbh.de/big_buck_bunny.mp4?13",
#       "qualities":{
#          "quality":[
#             {
#                "name":"lowx264",
#                "bitrate":500,
#                "codec":"h264-gpu",
#                "height":320
#             },
#             {
#                "name":"lowx265",
#                "bitrate":250,
#                "codec":"h265-gpu",
#                "height":320
#             }
#          ]
#       }
#    },
#    "retries":1,
#    "eta":"2015-12-09T07:54:42+01:00"
# }
@app.task(bind=True)
def encode_workflow_hard(*args, **kwargs):
    timestart = time.time()
    self = args[0]
    main_task_id = self.request.id
    url = kwargs["url"]
    qualities = kwargs["qualities"]
    returnURL = self.request.returnURL

    serverVTU = os.environ.get("SERVER_VTU", SERVER_VTU)
    # sshPortVTU = os.environ.get("SSH_PORT_VTU", SSH_PORT_VTU)
    httpPortVTU = os.environ.get("HTTP_PORT_VTU", HTTP_PORT_VTU)

    encodingprofils = [];
    for quality in qualities["quality"]:
        print(quality)
        profil = EncodingProfile(quality)
        encodingprofils.insert(0, profil)

    print("------------")

    context = download_file(
        context={"url": url, "returnURL": returnURL, "folder_out": os.path.join(config["folder_out"], main_task_id),
                 "id": main_task_id,
                 "folder_in": config["folder_in"]})
    context = get_video_size(context)
    context = send_file_SSH(context=context, path="/vTU/vTU/input/", file=context["original_file"])
    context = createXML(encodingprofils=encodingprofils, context=context)
    context = send_file_SSH(context=context, path="/vTU/vTU/spool/", file=context["xml_file"])

    try:
        os.makedirs(context['folder_out'])
    except OSError, e:
        # be happy if someone already created the path
        if (e.strerror != "File exists"):
            raise
            # pass
    start = time.time();
    while ((start + COEF_WAIT_TIME * context["track_duration"] / 1000 + STATIC_WAIT_TIME) - time.time() > 0 and len(
            encodingprofils) > 0):
        for encodingprofil in encodingprofils:
            print(encodingprofil.name)
            context_loop = copy.deepcopy(context)
            context_loop["name"] = encodingprofil.name
            context_loop["folder_in"] = context_loop["folder_out"]
            # context_loop["id"]=context["id"]+context_loop["name"]
            context_loop["url"] = "http://" + serverVTU + ":" + httpPortVTU + "/vTU/output/" + time.strftime(
                "%Y.%m.%d") + "/" + context_loop["id"] + context_loop["name"] + ".mp4"
            context_loop["id"] = context["id"] + context_loop["name"]

            try:
                context_loop = download_file(context=context_loop)

                context_loop = publish_output(context_loop, returnURL=encodingprofil.returnURL)
                context_loop = notify(context_loop, main_task_id=main_task_id, quality=encodingprofil.name,
                                      md5=context_loop["md5"], timestart=timestart, timeend=time.time())
                context_loop = remove_video(context_loop)
                encodingprofils.remove(encodingprofil)
            except IOError as e:
                if (e.args[1] == 404):
                    print str(e.args[1]) + " retry download"
                else:
                    break
                time.sleep(0.5)
                # context_loop = chunk_hls(context_loop, segtime=4)
                # context_loop = add_playlist_info(context_loop)


@app.task()
def remove_video(context):
    os.remove(context["absolute_name"])
    return context


@app.task(bind=True)
def staging_and_admission_workflow(*args, **kwargs):
    timestart = time.time()
    self = args[0]
    main_task_id = self.request.id
    url = kwargs["url"]
    qualities = kwargs["qualities"]
    print("------------")
    context = {"url": url, "folder_out": os.path.join(config["folder_out"], main_task_id), "id": main_task_id,
               "folder_in": config["folder_in"]}

    context = download_file(
        context={"url": url, "folder_out": os.path.join(config["folder_out"], main_task_id), "id": main_task_id,
                 "folder_in": config["folder_in"]})
    context_original = copy.deepcopy(context)
    context_original["name"] = "original"
    context_original = publish_output(context_original, returnURL=kwargs["returnURL"])

    context_original = notify(context_original, main_task_id=main_task_id, quality="Original",
                              md5=context_original["md5"], timestart=timestart, timeend=time.time())
    context_original = get_video_size(context);
    context_original = remove_video(context)
    url = kwargs["cacheURL"]
    context["url"] = kwargs["cacheURL"]
    qualitiesNoSpe = {"quality": []}  # notgood

    for quality in qualities:

        print(quality)
        if (quality["height"] > context_original["track_height"]):
            print ('remove this quality ', quality["height"])
            continue

        if (quality["codec"].find("SOFT") != -1):
            context["task_name"] = "adaptation.commons.encode_workflow"
            context["queue"] = "soft"
            if quality["codec"].find("264") != -1:
                quality["codec"] = "libx264"
            elif quality["codec"].find("265") != -1:
                quality["codec"] = "libx265"
            else:
                print "no encoder specified"
                quality["codec"] = "libx264"
            push_message(context, id=main_task_id, task=context["task_name"],
                         kwargs={"url": url, "qualities": {"quality": [quality]}}, retries=self.request.retries,
                         eta=self.request.eta, returnURL=quality["return_url"])
        elif (quality["codec"].find("HARD") != -1):

            context["task_name"] = "adaptation.commons.encode_workflow_hard"
            context["queue"] = "hard"
            if quality["codec"].find("264") != -1:
                quality["codec"] = "h264-gpu"
            elif quality["codec"].find("265") != -1:
                quality["codec"] = "h265-gpu"
            else:
                print "no encoder specified"
                quality["codec"] = "h264-gpu"
            # qualities["quality"].remove(quality)
            push_message(context, id=main_task_id, task=context["task_name"],
                         kwargs={"url": url, "qualities": {"quality": [quality]}}, retries=self.request.retries,
                         eta=self.request.eta, returnURL=quality["return_url"])

        else:
            print "Encoder is not specified "
            qualitiesNoSpe["quality"].insert(0, quality)

    if len(qualitiesNoSpe["quality"]) == 0:
        return 0

    # q_hard = channel_pika.queue_declare(queue='hard', durable=True, exclusive=False, auto_delete=False)
    # q_hard_leng = q_hard.method.message_count
    # encoder = "hard"
    # context["task_name"]="adaptation.commons.encode_workflow_hard"
    # if (q_hard_leng > 0):
    #
    #     # To equilibrated soft and hard
    #     # q_soft = channel_pika.queue_declare(queue='soft', durable=True, exclusive=False, auto_delete=False)
    #     # q_soft_leng= q_soft.method.message_count
    #     # if (q_soft_leng < q_hard_leng):
    #     #   encoder = "soft"
    #     #   context["task_name"]="adaptation.commons.encode_workflow"

    encoder = "soft"
    context["task_name"] = "adaptation.commons.encode_workflow"

    for quality in qualitiesNoSpe["quality"]:
        print(quality)
        if (quality["codec"].find("264") != -1):
            if encoder == "soft":
                quality["codec"] = "libx264"
            elif encoder == "hard":
                quality["codec"] = "h264-gpu"
            else:
                print "no encoder set"
        elif (quality["codec"].find("265") != -1):
            if encoder == "soft":
                quality["codec"] = "libx265"
            elif encoder == "hard":
                quality["codec"] = "h265-gpu"
            else:
                print "no encoder set"
        else:
            print "codec is not equal at h264 or h265 (set h264 by default)"
            if encoder == "soft":
                quality["codec"] = "libx264"
            elif encoder == "hard":
                quality["codec"] = "h264-gpu"
            else:
                print "no encoder set"
        # quality["return_url"]
        context["queue"] = encoder
        push_message(context, id=main_task_id, task=context["task_name"],
                     kwargs={"url": url, "qualities": {"quality": [quality]}}, retries=self.request.retries,
                     eta=self.request.eta, returnURL=quality["returnURL"])
        # push_message(context,id=main_task_id,task=context["task_name"] , kwargs={"url": url, "qualities":qualitiesNoSpe},retries=self.request.retries,eta=self.request.eta,returnURL=self.request.returnURL)

    print encoder


@app.task(bind=True)
def push_message(*args, **kwargs):
    self = args[0]
    context = args[1]
    logger.debug("sending %s to result queue" % json.dumps(kwargs))
    try:
        channel_pika.basic_publish(exchange='',
                                   routing_key=context["queue"],
                                   body=json.dumps(kwargs))
    except:
        logger.error("failed to connect to pika, trying again one more time")
        connection = pika.BlockingConnection(pika_con_params)

        channel_pika = connection.channel()
        channel_pika.queue_declare(queue=context["queue"], durable=True, exclusive=False, auto_delete=False)
        properties = pika.BasicProperties(content_encoding='utf-8',
                                          content_type='application/json')
        channel_pika.basic_publish(exchange='',
                                   routing_key=context["queue"],
                                   body=json.dumps(kwargs),
                                   properties=properties)

    return context


@app.task()
def download_file(*args, **kwargs):
    print((args, kwargs))
    context = kwargs["context"]
    folder_in = context["folder_in"]
    print(("downloading %s", context["url"]))
    # split =context["url"].split("/")
    # filname=split[len(split)-1]
    # context["original_folder"] = os.path.join(folder_in, context["id"])
    # os.mkdir(context["original_folder"])
    # temp =uuid.uuid4()

    # new UUID set here for not conflic name when post on vTU server
    context["nameid"] = context["id"] + str(uuid.uuid4().hex)

    context["original_file"] = os.path.join(folder_in, context["nameid"])

    print(("downloading in " + context["original_file"] + " from " + context["url"]))
    opener = urllib.URLopener()
    opener.retrieve(context["url"], context["original_file"])
    print(("downloaded in %s", context["original_file"]))
    context["absolute_name"] = context["original_file"]
    return context  # @app.task()


@app.task
# def get_video_size(input_file):
def get_video_size(*args, **kwargs):
    '''
    use mediainfo to compute the video size
    '''
    print((args, kwargs))
    context = args[0]
    media_info = MediaInfo.parse(context["original_file"])
    for track in media_info.tracks:
        if track.track_type == 'Video':
            print(("video is %d, %d" % (track.height, track.width)))
            context["track_width"] = track.width
            context["track_height"] = track.height
            context["track_duration"] = track.duration
            return context
    raise AssertionError("failed to read video info from " + context["original_file"])


@app.task
# def get_video_thumbnail(input_file):
def get_video_thumbnail(*args, **kwargs):
    '''
    create image from video
    '''
    # print args, kwargs
    context = args[0]

    if not os.path.exists(context['folder_out']):
        os.makedirs(context['folder_out'])

    ffargs = "ffmpeg -i " + context["original_file"] + " -vcodec mjpeg -vframes 1 -an -f rawvideo -s 426x240 -ss 10 " + \
             context["folder_out"] + "/folder.jpg"
    print(ffargs)
    run_background(ffargs)
    return context


@app.task
# def compute_target_size(original_height, original_width, target_height):
def compute_target_size(*args, **kwargs):
    '''
    compute the new size for the video
    '''
    context = args[0]
    context["target_height"] = kwargs['target_height']

    print((args, kwargs))
    context["target_width"] = math.trunc(
        float(context["target_height"]) / context["track_height"] * context["track_width"] / 2) * 2
    return context


@app.task
# def transcode(file_in, folder_out, dimensions, bitrate):
def transcode(*args, **kwargs):
    '''
    transcode the video to mp4 format
    '''
    # print args, kwargs
    context = args[0]
    context["bitrate"] = kwargs['bitrate']
    context["segtime"] = kwargs['segtime']
    context["codec"] = kwargs['codec']
    dimsp = str(context["target_width"]) + ":" + str(context["target_height"])
    if not os.path.exists(get_transcoded_folder(context)):
        try:
            os.makedirs(get_transcoded_folder(context))
        except OSError as e:
            pass
            # ffmpeg -i " FILE " -c:v libx264 -profile:v main -level 3.1 -b:v "BITRATE"k -vf scale=640:480 -c:a aac -strict -2 -force_key_frames expr:gte\(t,n_forced*4\) OUPUT.mp4
    command_line = "ffmpeg -y -i " + context[
        "original_file"] + " -vcodec " + context["codec"] + " -b:v " + str(context[
                                                                               "bitrate"]) + "k -vf scale=" + dimsp + " -c:a aac -strict -2 -force_key_frames expr:gte\(t,n_forced*" + str(
        context["segtime"]) + "\) " + get_transcoded_file(
        context)
    print(("transcoding commandline %s" % command_line))
    start = time.time();
    subprocess.call(command_line,
                    shell=True)
    elpased = time.time() - start
    print("time to encode the video: " + str(elpased) + "s")
    context["absolute_name"] = get_transcoded_file(context)
    return context


@app.task
# def chunk_hls(file_in, folder_out, dimensions, segtime=4):
def chunk_hls(*args, **kwargs):
    '''
    create hls chunks and the version specific playlist
    '''
    # print args, kwargs
    context = args[0]
    context["segtime"] = kwargs['segtime']

    if not os.path.exists(get_hls_transcoded_folder(context)):
        os.makedirs(get_hls_transcoded_folder(context))

    ffargs = "ffmpeg -i " + get_transcoded_file(
        context) + " -map 0 -flags +global_header -vcodec copy -vbsf h264_mp4toannexb -acodec copy -f segment -segment_format mpegts -segment_time " + str(
        context["segtime"]) + " -segment_wrap 0 -segment_list " + get_hls_transcoded_playlist(
        context) + " " + get_hls_transcoded_folder(context) + "/chunks_name%03d.ts"
    print(ffargs)
    subprocess.call(ffargs, shell=True)
    return context


@app.task
# def chunk_dash(files_in, folder_out):
def chunk_dash(*args, **kwargs):
    '''
    create dash chunks for every video in the transcoded folder
    '''
    logger.info("chunking dash")
    logger.info(args)
    logger.info(kwargs)
    context = args[0]
    segtime = kwargs['segtime']
    if not os.path.exists(get_dash_folder(context)):
        os.makedirs(get_dash_folder(context))

    args = "MP4Box -dash " + str(segtime) + "000 -profile onDemand "
    files_in = [os.path.join(get_transcoded_folder(context), f) for f in os.listdir(get_transcoded_folder(context))]
    for i in range(0, len(files_in)):
        args += files_in[i] + "#video:id=v" + str(i) + " "

    args += files_in[0] + "#audio:id=a0 "
    args += " -out " + get_dash_mpd_file_path(context)
    print(args)
    subprocess.call(args, shell=True)
    return context


@app.task
def edit_dash_playlist(*args, **kwards):
    '''
    create dash chunks for every video in the transcoded folder
    '''
    # print args, kwargs
    context = args[0]

    tree = LXML.parse(get_dash_mpd_file_path(context))
    root = tree.getroot()
    # Namespace map
    nsmap = root.nsmap.get(None)

    # Function to find all the BaseURL
    find_baseurl = LXML.ETXPath("//{%s}BaseURL" % nsmap)
    results = find_baseurl(root)
    audio_file = results[-1].text
    results[-1].text = "audio/" + results[
        -1].text  # Warning : This is quite dirty ! We suppose the last element is the only audio element
    tree.write(get_dash_mpd_file_path(context))

    # Move audio files into audio directory
    os.makedirs(os.path.join(get_dash_folder(context), "audio"))
    shutil.move(os.path.join(get_dash_folder(context), audio_file),
                os.path.join(get_dash_folder(context), "audio", audio_file))

    # Create .htaccess for apache
    f = open(os.path.join(get_dash_folder(context), "audio", ".htaccess"), "w")
    f.write("AddType audio/mp4 .mp4 \n")
    f.close()
    return context


@app.task
# def add_playlist_info(main_playlist_folder, version_playlist_file, bitrate):
def add_playlist_info(*args, **kwargs):
    '''
    add this hls palylist info into the global hls playlist
    '''
    # print args, kwargs
    context = args[0]
    dimsp = str(context["target_width"]) + "x" + str(context["target_height"])
    with open(get_hls_global_playlist(context), "a") as f:
        f.write("#EXT-X-STREAM-INF:PROGRAM-ID=1,BANDWIDTH=" + str(
            context["bitrate"] * 1000) + ",RESOLUTION=" + dimsp + "\n" + "/".join(
            get_hls_transcoded_playlist(context).split("/")[-2:]) + "\n")
    return context


@app.task
# def add_playlist_header(playlist_folder):
def add_playlist_header(*args, **kwargs):
    '''
    add the header to the global playlist, possibly remove existing hls folder and recreate it
    '''
    # print args, kwargs
    context = args[0]
    if os.path.exists(get_hls_folder(context)):
        shutil.rmtree(get_hls_folder(context))
    os.makedirs(get_hls_folder(context))

    with open(get_hls_global_playlist(context), "a") as f:
        f.write("#EXTM3U\n")
    return context


@app.task
# def add_playlist_footer(playlist_folder):
def add_playlist_footer(*args, **kwargs):
    '''
    add global hls playlist folder
    '''
    # print args, kwargs
    context = args[0]  # take the first context["on"] the list, since we receive more than one
    with open(get_hls_global_playlist(context), "a") as f:
        f.write("##EXT-X-ENDLIST")
    return context
