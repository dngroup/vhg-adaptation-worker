import os

config = {"folder_out": "/var/www/out",
          "folder_in": "/var/www/in",
          "bitrates_size_tuple_list": [(100, 100, "low"), (200, 200, "medium"), (500, 300, "high")]}

# CELERY_RESULT_BACKEND = BROKER_URL
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']

SERVER_VTU = '10.17.53.11'
SSH_PORT_VTU = '22'
HTTP_PORT_VTU = '80'
STATIC_WAIT_TIME = 10
COEF_WAIT_TIME = 1.5
# TODO: remove this if not necessary
CELERYD_CONCURRENCY = 1
CELERYD_PREFETCH_MULTIPLIER = 1