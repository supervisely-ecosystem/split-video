
from moviepy.video.io.VideoFileClip import VideoFileClip
import os
import supervisely_lib as sly
from supervisely_lib.video_annotation.key_id_map import KeyIdMap
from copy import deepcopy
from supervisely_lib.video_annotation.video_tag_collection import VideoTagCollection


my_app = sly.AppService()

TEAM_ID = int(os.environ['context.teamId'])
WORKSPACE_ID = int(os.environ['context.workspaceId'])
PROJECT_ID = int(os.environ['modal.state.slyProjectId'])
#SPLIT_SEC = int(os.environ['modal.state.split_sec'])
TASK_ID = int(os.environ["TASK_ID"])

RESULT_DIR_NAME = 'split_videos'
new_project_suffix = '_splitted'
logger = sly.logger
time_split = 'time'

video_splitter = os.environ['modal.state.videoSplitter']

if video_splitter == time_split:
   SPLIT_SEC = os.environ['modal.state.timeStep']

else:
    SPLIT_FRAMES = os.environ['modal.state.framesStep']

logger.warn('SPLIT_SEC {}'.format(SPLIT_SEC))
logger.warn('SPLIT_FRAMES {}'.format(SPLIT_FRAMES))
a = 5 / 0


def get_splitter(split_sec, video_length):
    splitter = []
    for split_step in range(0, int(video_length) + 1, split_sec):
        if split_step + split_sec > video_length:
            splitter.append([split_step, video_length])
            break
        splitter.append([split_step, split_step + split_sec])

    return splitter


def get_new_frames(old_frames):
    new_frames = []
    for index, frame in enumerate(old_frames):
        new_figures = []
        for figure in frame.figures:
            new_figure = figure.clone(frame_index=index)
            new_figures.append(new_figure)
        new_frame = frame.clone(index=index, figures=new_figures)
        new_frames.append(new_frame)
    split_frames = sly.FrameCollection(new_frames)

    return split_frames


def get_frame_range_tags(frame_range_tags, curr_frame_range, curr_frames_count):
    result_tags = []
    for tag in frame_range_tags:
        fr_range = tag.frame_range
        if fr_range[1] < curr_frame_range[0] or fr_range[0] > curr_frame_range[1]:
            continue
        if fr_range[0] <= curr_frame_range[0] and fr_range[1] >= curr_frame_range[1]:
            result_tags.append(tag.clone(frame_range=[0, curr_frames_count], key=tag.key()))
        elif fr_range[0] >= curr_frame_range[0] and fr_range[1] <= curr_frame_range[1]:
            result_tags.append(tag.clone(frame_range=[tag.frame_range[0] - curr_frame_range[0], tag.frame_range[1] - curr_frame_range[0]], key=tag.key()))
        elif fr_range[0] <= curr_frame_range[0] and fr_range[1] <= curr_frame_range[1]:
            result_tags.append(tag.clone(frame_range=[0, tag.frame_range[1] - curr_frame_range[0]], key=tag.key()))
        elif fr_range[0] >= curr_frame_range[0] and fr_range[1] >= curr_frame_range[1]:
            result_tags.append(tag.clone(frame_range=[tag.frame_range[0] - curr_frame_range[0], curr_frames_count], key=tag.key()))

    return result_tags


@my_app.callback("split_video")
@sly.timeit
def split_video(api: sly.Api, task_id, context, state, app_logger):

    project = api.project.get_info_by_id(PROJECT_ID)
    meta_json = api.project.get_meta(PROJECT_ID)
    meta = sly.ProjectMeta.from_json(meta_json)
    if project is None:
        raise RuntimeError("Project with ID {!r} not found".format(PROJECT_ID))
    if project.type != str(sly.ProjectType.VIDEOS):
        raise TypeError("Project type is {!r}, but have to be {!r}".format(project.type, sly.ProjectType.VIDEOS))

    project_name = project.name
    splitted_project_name = project_name + new_project_suffix
    new_project = api.project.create(WORKSPACE_ID, splitted_project_name, type=sly.ProjectType.VIDEOS, change_name_if_conflict=True)
    api.project.update_meta(new_project.id, meta.to_json())
    meta_json = api.project.get_meta(PROJECT_ID)
    meta = sly.ProjectMeta.from_json(meta_json)

    RESULT_DIR = os.path.join(my_app.data_dir, RESULT_DIR_NAME)
    key_id_map = KeyIdMap()
    for dataset in api.dataset.get_list(PROJECT_ID):
        ds = api.dataset.create(new_project.id, dataset.name, change_name_if_conflict=True)
        videos = api.video.get_list(dataset.id)
        for batch in sly.batched(videos, batch_size=10):
            for video_info in batch:
                progress = sly.Progress('Video being splitted', len(batch))
                ann_info = api.video.annotation.download(video_info.id)
                ann = sly.VideoAnnotation.from_json(ann_info, meta, key_id_map)

                video_tags = []
                frame_range_tags = []
                for tag in ann.tags:
                    if tag.frame_range is None:
                        video_tags.append(tag)
                    else:
                        frame_range_tags.append(tag)

                ann_frames = [frame for frame in ann.frames]
                video_length = video_info.frames_to_timecodes[-1]
                if SPLIT_SEC >= video_length:
                    logger.warn('SPLIT_SEC is more then video {} length'.format(video_info.name))
                    new_video_info = api.video.upload_hash(ds.id, video_info.name, video_info.hash)
                    api.video.annotation.append(new_video_info.id, ann, key_id_map)
                    continue

                splitter = get_splitter(SPLIT_SEC, video_length)

                input_video_path = os.path.join(RESULT_DIR, video_info.name)
                api.video.download_path(video_info.id, input_video_path)
                curr_video_paths = []
                curr_video_names = []
                for curr_split in splitter:
                    with VideoFileClip(input_video_path) as video:
                        new = video.subclip(curr_split[0], curr_split[1])
                        split_video_name = sly.fs.get_file_name(video_info.name) + '_' + str(curr_split[1]) + sly.fs.get_file_ext(video_info.name)
                        output_video_path = os.path.join(RESULT_DIR, split_video_name)
                        curr_video_names.append(split_video_name)
                        curr_video_paths.append(output_video_path)
                        new.write_videofile(output_video_path, audio_codec='aac')
                new_video_infos = api.video.upload_paths(ds.id, curr_video_names, curr_video_paths)
                start_frames_count = new_video_infos[0].frames_count
                for idx in range(len(new_video_infos)):
                    curr_frames_count = new_video_infos[idx].frames_count

                    curr_frame_range = [start_frames_count * idx, start_frames_count * (idx + 1)]
                    split_ann_tags = deepcopy(video_tags)

                    if start_frames_count * (idx + 1) > len(ann.frames):
                        old_frames = ann_frames[start_frames_count * idx: len(ann.frames)]
                        split_frames_coll = get_new_frames(old_frames)
                        range_tags = get_frame_range_tags(frame_range_tags, curr_frame_range, curr_frames_count)
                    else:
                        old_frames = ann_frames[start_frames_count * idx: curr_frames_count * (idx + 1)]
                        split_frames_coll = get_new_frames(old_frames)
                        range_tags = get_frame_range_tags(frame_range_tags, curr_frame_range, curr_frames_count)

                    split_ann_tags.extend(range_tags)
                    split_ann = ann.clone(frames_count=curr_frames_count, frames=split_frames_coll, tags=VideoTagCollection(split_ann_tags))
                    api.video.annotation.append(new_video_infos[idx].id, split_ann, key_id_map)
                progress.iter_done_report()

    my_app.stop()


def main():
    sly.logger.info("Script arguments", extra={
        "TEAM_ID": TEAM_ID,
        "WORKSPACE_ID": WORKSPACE_ID,
        "modal.state.slyProjectId": PROJECT_ID
    })
    my_app.run(initial_events=[{"command": "split_video"}])


if __name__ == '__main__':
    sly.main_wrapper("main", main)