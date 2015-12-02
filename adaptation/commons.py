import urllib

__author__ = 'nherbaut'
import subprocess
import math
import shutil
import json
import copy
import mimetypes
import pika
import swiftclient
from celery.utils.log import get_task_logger
# config import
from .settings import *
# celery import
from celery import Celery
# media info wrapper import
from pymediainfo import MediaInfo
# lxml import to edit dash playlist
from lxml import etree as LXML
# context helpers
from .context import get_transcoded_folder, get_transcoded_file, get_hls_transcoded_playlist, get_hls_transcoded_folder, \
    get_dash_folder, get_hls_folder, get_hls_global_playlist, get_dash_mpd_file_path

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

logger.info("connecting to swift")

try:
    swift_authurl, swift_username, swift_password = (os.environ["ST_AUTH"], os.environ["ST_USER"], os.environ["ST_KEY"])
    swift_connection = swiftclient.Connection(authurl=swift_authurl, user=swift_username, key=swift_password)
    # verifying swift connectivity
    swift_connection.head_account()

except KeyError as key:
    # no swift => no data will be sent to streamer
    logger.warning("swift is NOT configured, nothing will be sent to streamer")
    # swift_authurl,swift_username, swift_password = (None,None,None)
    swift_connection = None
except swiftclient.ClientException as ce:
    logger.warning("swift credentials are did NOT pass, nothing will be sent to streamer")
    # swift_authurl,swift_username, swift_password = (None,None,None)
    swift_connection = None


def run_background(*args):
    try:
        code = subprocess.check_call(*args, shell=True)
    except subprocess.CalledProcessError:
        print("Error")


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

@app.task(bind=True)
def publish_output(*args, **kwargs):
    self = args[0]
    context = args[1]
    name = context["name"]
    output_folder = context["folder_out"]
    if swift_connection is None:
        logger.warn("swift connection is not active, skipping streamer upload")

    else:
        headers = {}
        container = os.path.basename(output_folder)
        headers["X-Container-Read"] = " .r:*"
        headers["X-Container-Meta-Access-Control-Allow-Origin"] = "*"
        headers["X-Container-Meta-Access-Control-Allow-Method"] = "GET"

        swift_connection.put_container(container, headers)
        # for object in os.walk(output_folder):
        encoding_folder = get_transcoded_folder(context)
        # paths = object[2]
        root =encoding_folder
        # for path in paths:
        path = name + ".mp4"
        filepath = os.path.abspath(os.path.join(root, path))
        with open(filepath) as f:
            content_type, encoding = mimetypes.guess_type(filepath)
            swift_connection.put_object(container, os.path.join(root, path)[len(output_folder) + 1:], f,
                                        content_type=content_type)

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


@app.task()
def deploy_original_file(*args, **kwargs):
    context = args[0]
    encoding_folder = get_transcoded_folder(context)
    if not os.path.exists(encoding_folder):
        os.makedirs(encoding_folder)
    shutil.copyfile(context["original_file"], os.path.join(encoding_folder, "original.mp4"))
    return context


@app.task()
def ddo(url):
    encode_workflow.delay(url)


@app.task(bind=True)
def encode_workflow(self, url):
    main_task_id = self.request.id
    print("(------------")

    context = download_file(
        context={"url": url, "folder_out": os.path.join(config["folder_out"], main_task_id), "id": main_task_id,
                 "folder_in": config["folder_in"]})
    context = get_video_size(context)
    context = add_playlist_header(context)
    for target_height, bitrate, name in config["bitrates_size_tuple_list"]:
        context_loop = copy.deepcopy(context)
        context_loop["name"] = name
        context_loop = compute_target_size(context_loop, target_height=target_height)
        context_loop = transcode(context_loop, bitrate=bitrate, segtime=4, name=name)
        context_loop = publish_output(context_loop)
        context_loop = notify(context_loop, main_task_id=main_task_id, quality=name)
        context_loop = chunk_hls(context_loop, segtime=4)
        context_loop = add_playlist_info(context_loop)

    context = add_playlist_footer(context)
    context = chunk_dash(context, segtime=4, )
    context = edit_dash_playlist(context)

   # context = notify(context, complete=True, main_task_id=main_task_id)


@app.task()
def download_file(*args, **kwargs):
    print((args, kwargs))
    context = kwargs["context"]
    folder_in = context["folder_in"]
    print(("downloading %s", context["url"]))
    context["original_file"] = os.path.join(folder_in, context["id"])
    print(("downloading in %s", context["original_file"]))
    opener = urllib.URLopener()
    opener.retrieve(context["url"], context["original_file"])
    print(("downloaded in %s", context["original_file"]))
    return context


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
    dimsp = str(context["target_width"]) + ":" + str(context["target_height"])
    if not os.path.exists(get_transcoded_folder(context)):
        try:
            os.makedirs(get_transcoded_folder(context))
        except OSError as e:
            pass

    command_line = "ffmpeg -i " + context[
        "original_file"] + " -c:v libx264 -profile:v main -level 3.1 -b:v " + str(context[
                                                                                      "bitrate"]) + "k -vf scale=" + dimsp + " -c:a aac -strict -2 -force_key_frames expr:gte\(t,n_forced*" + str(
        context["segtime"]) + "\) " + get_transcoded_file(
        context)
    print(("transcoding commandline %s" % command_line))
    subprocess.call(command_line,
                    shell=True)
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
