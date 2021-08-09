
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

result_dir_name = 'split_videos'
new_project_suffix = '_splitted'
logger = sly.logger
time_split = 'time'
last_frame_ms = 0.001

video_splitter = os.environ['modal.state.videoSplitter']

if video_splitter == time_split:
   split_sec = int(os.environ['modal.state.timeStep'])
   split_frames = None
else:
   split_frames = int(os.environ['modal.state.framesStep'])
   split_sec = None


def get_time_splitter(split_sec, video_length):
    splitter = []
    full_parts = int(video_length // split_sec)
    start_time = 0
    for i in range(full_parts):
        end_time = split_sec * (i+1)
        splitter.append([start_time, end_time])
        start_time = end_time

    if end_time < video_length:
        splitter.append([end_time, video_length + last_frame_ms])

    return splitter


def get_frames_splitter(split_frames, frames_to_timecodes):
    splitter = []
    start_time = 0
    if type(len(frames_to_timecodes) // split_frames) == int:
        full_parts = int(len(frames_to_timecodes) // (split_frames + 1))
    else:
        full_parts = int(len(frames_to_timecodes) // split_frames)

    for i in range(full_parts):
        end_time = frames_to_timecodes[split_frames * (i+1)] - last_frame_ms
        splitter.append([start_time, end_time])
        start_time = frames_to_timecodes[split_frames * (i+1)]

    if end_time < frames_to_timecodes[-1]:
        splitter.append([end_time + last_frame_ms, frames_to_timecodes[-1] + last_frame_ms])

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
            result_tags.append(tag.clone(
                frame_range=[tag.frame_range[0] - curr_frame_range[0], tag.frame_range[1] - curr_frame_range[0]],
                key=tag.key()))
        elif fr_range[0] <= curr_frame_range[0] and fr_range[1] <= curr_frame_range[1]:
            result_tags.append(tag.clone(frame_range=[0, tag.frame_range[1] - curr_frame_range[0]], key=tag.key()))
        elif fr_range[0] >= curr_frame_range[0] and fr_range[1] >= curr_frame_range[1]:
            result_tags.append(
                tag.clone(frame_range=[tag.frame_range[0] - curr_frame_range[0], curr_frames_count], key=tag.key()))

    return result_tags


@my_app.callback("split_video")
@sly.timeit
def split_video(api: sly.Api, task_id, context, state, app_logger):
    global split_sec

    project = api.project.get_info_by_id(PROJECT_ID)
    meta_json = api.project.get_meta(PROJECT_ID)
    meta = sly.ProjectMeta.from_json(meta_json)
    project_name = project.name
    splitted_project_name = project_name + new_project_suffix
    new_project = api.project.create(WORKSPACE_ID, splitted_project_name, type=sly.ProjectType.VIDEOS,
                                     change_name_if_conflict=True)
    api.project.update_meta(new_project.id, meta.to_json())
    meta_json = api.project.get_meta(PROJECT_ID)
    meta = sly.ProjectMeta.from_json(meta_json)

    result_dir = os.path.join(my_app.data_dir, result_dir_name)
    key_id_map = KeyIdMap()
    for dataset in api.dataset.get_list(PROJECT_ID):
        ds = api.dataset.create(new_project.id, dataset.name, change_name_if_conflict=True)
        videos = api.video.get_list(dataset.id)
        progress = sly.Progress('Video being splitted', len(videos))
        for batch in sly.batched(videos, batch_size=10):
            for video_info in batch:
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

                if split_frames:
                    if split_frames > len(video_info.frames_to_timecodes):
                        logger.warn('Frames count, set for splitting, is more then video {} length'.format(video_info.name))
                        new_video_info = api.video.upload_hash(ds.id, video_info.name, video_info.hash)
                        api.video.annotation.append(new_video_info.id, ann, key_id_map)
                        continue
                    splitter = get_frames_splitter(split_frames, video_info.frames_to_timecodes)

                if split_sec:
                    if split_sec >= video_length:
                        logger.warn('Time, set for splitting, is more then video {} length'.format(video_info.name))
                        new_video_info = api.video.upload_hash(ds.id, video_info.name, video_info.hash)
                        api.video.annotation.append(new_video_info.id, ann, key_id_map)
                        continue
                    splitter = get_time_splitter(split_sec, video_length)

                input_video_path = os.path.join(result_dir, video_info.name)
                api.video.download_path(video_info.id, input_video_path)
                curr_video_paths = []
                curr_video_names = []
                for idx, curr_split in enumerate(splitter):
                    with VideoFileClip(input_video_path) as video:
                        new = video.subclip(curr_split[0], curr_split[1])
                        split_video_name = sly.fs.get_file_name(video_info.name) + '_' + str(
                            idx + 1) + sly.fs.get_file_ext(video_info.name)
                        output_video_path = os.path.join(result_dir, split_video_name)
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
                    split_ann = ann.clone(frames_count=curr_frames_count, frames=split_frames_coll,
                                          tags=VideoTagCollection(split_ann_tags))
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