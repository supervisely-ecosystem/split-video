
import os, shutil
import supervisely as sly
from supervisely.video_annotation.key_id_map import KeyIdMap


my_app = sly.AppService()
api: sly.Api = my_app.public_api

shutil.rmtree(my_app.data_dir, ignore_errors=True)

TASK_ID = int(os.environ["TASK_ID"])
TEAM_ID = int(os.environ['context.teamId'])
WORKSPACE_ID = int(os.environ['context.workspaceId'])
PROJECT_ID = int(os.environ['modal.state.slyProjectId'])

result_dir_name = 'split_videos'
new_project_suffix = '_splitted'
logger = sly.logger
time_split = 'time'
last_frame_ms = 0.001
key_id_map = KeyIdMap()

video_splitter = os.environ['modal.state.videoSplitter']

if video_splitter == time_split:
   split_sec = int(os.environ['modal.state.timeStep'])
   split_frames = None
else:
   split_frames = int(os.environ['modal.state.framesStep'])
   split_sec = None