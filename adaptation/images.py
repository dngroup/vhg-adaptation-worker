__author__ = 'nherbaut'
import subprocess
import uuid
import os


# config import
from settings import config

# celery import
from celery import Celery, chord

# main app for celery, configuration is in separate settings.ini file
app = Celery('tasks')

# inject settings into celery
app.config_from_object('adaptation.settings')

def run_background(*args):
    try: 
        code = subprocess.check_call(*args, shell=True)
    except subprocess.CalledProcessError:
        print "Error"


@app.task()
def ddo(src, dest):
    print "(------------"
    random_uuid = uuid.uuid4().hex
    context={"original_file": src, "folder_out": config["folder_out"] + dest, "id": random_uuid}
    
    if not os.path.exists(context['folder_out']):
        os.makedirs(context['folder_out'])

    ffargs = "ffmpeg -i " + src + " -vf scale=iw/2:ih/2 " + context["folder_out"] + dest
    print ffargs
    run_background(ffargs)