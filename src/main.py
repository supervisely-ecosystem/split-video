
from moviepy.video.io.VideoFileClip import VideoFileClip
import os
import supervisely as sly
from copy import deepcopy
from supervisely.video_annotation.video_tag_collection import VideoTagCollection
import sly_globals as g


def get_time_splitter(split_sec, video_length):
    splitter = []
    full_parts = int(video_length // split_sec)
    for i in range(full_parts):
        splitter.append([split_sec * i, split_sec * (i+1)])

    splitter.append([split_sec * (i+1), video_length + g.last_frame_ms])

    return splitter


def get_frames_splitter(split_frames, fr_to_timecodes):
    splitter = []
    full_parts = int(len(fr_to_timecodes) // split_frames)
    if full_parts == len(fr_to_timecodes):                 # check the case of splitting into 1 frame
        full_parts -= 1

    for i in range(full_parts):
        splitter.append([fr_to_timecodes[split_frames * i], fr_to_timecodes[split_frames * (i+1)] - g.last_frame_ms])

    splitter.append([fr_to_timecodes[split_frames * (i+1)] - g.last_frame_ms, fr_to_timecodes[-1] + g.last_frame_ms])

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


def get_frame_range_tags(frame_range_tags, curr_frame_range):
    result_tags = []
    curr_fr_range = list(range(curr_frame_range[0], curr_frame_range[1]))
    for tag in frame_range_tags:
        fr_range = list(range(tag.frame_range[0], tag.frame_range[1] + 1))
        res = list(set(fr_range) & set(curr_fr_range))
        if len(res) == 0:
            continue

        result_tags.append(tag.clone(frame_range=[min(res) - curr_frame_range[0], max(res) - curr_frame_range[0]], key=tag.key()))

    return result_tags


def upload_full_video(api, ds_id, video_info, ann, progress):
    new_video_info = api.video.upload_hash(ds_id, video_info.name, video_info.hash)
    api.video.annotation.append(new_video_info.id, ann, g.key_id_map)
    progress.iter_done_report()


def write_videos(api, splitter, result_dir, video_info):
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

    return curr_video_paths, curr_video_names


def get_ann_tags(ann):
    video_tags = []
    frame_range_tags = []
    for tag in ann.tags:
        if tag.frame_range is None:
            video_tags.append(tag)
        else:
            frame_range_tags.append(tag)

    return video_tags, frame_range_tags

def upload_new_anns(api, new_video_infos, ann):

    video_tags, frame_range_tags = get_ann_tags(ann)
    ann_frames = ann.frames.items()
    start_frames_count = new_video_infos[0].frames_count
    for idx in range(len(new_video_infos)):
        curr_frames_count = new_video_infos[idx].frames_count

        curr_frame_range = [start_frames_count * idx, start_frames_count * (idx + 1)]
        split_ann_tags = deepcopy(video_tags)

        if start_frames_count * (idx + 1) > len(ann.frames):
            old_frames = ann_frames[start_frames_count * idx: len(ann.frames)]
        else:
            old_frames = ann_frames[start_frames_count * idx: curr_frames_count * (idx + 1)]

        split_frames_coll = get_new_frames(old_frames)
        range_tags = get_frame_range_tags(frame_range_tags, curr_frame_range)

        split_ann_tags.extend(range_tags)
        split_ann = ann.clone(frames_count=curr_frames_count, frames=split_frames_coll,
                              tags=VideoTagCollection(split_ann_tags))
        api.video.annotation.append(new_video_infos[idx].id, split_ann, g.key_id_map)


@g.my_app.callback("split_video")
@sly.timeit
def split_video(api: sly.Api, task_id, context, state, app_logger):

    project = api.project.get_info_by_id(g.PROJECT_ID)
    meta_json = api.project.get_meta(g.PROJECT_ID)
    meta = sly.ProjectMeta.from_json(meta_json)
    splitted_project_name = project.name + g.new_project_suffix
    new_project = api.project.create(g.WORKSPACE_ID, splitted_project_name, type=sly.ProjectType.VIDEOS,
                                      change_name_if_conflict=True)
    api.project.update_meta(new_project.id, meta.to_json())
    meta_json = api.project.get_meta(g.PROJECT_ID)
    meta = sly.ProjectMeta.from_json(meta_json)

    result_dir = os.path.join(g.my_app.data_dir, g.result_dir_name)
    for dataset in api.dataset.get_list(g.PROJECT_ID):
        ds = api.dataset.create(new_project.id, dataset.name, change_name_if_conflict=True)
        videos = api.video.get_list(dataset.id)
        progress = sly.Progress('Video being splitted', len(videos))
        for video_info in videos:
            ann_info = api.video.annotation.download(video_info.id)
            ann = sly.VideoAnnotation.from_json(ann_info, meta, g.key_id_map)
            video_length = video_info.frames_to_timecodes[-1]

            if g.split_frames:
                if g.split_frames >= len(video_info.frames_to_timecodes):
                    g.logger.warn('Frames count, set for splitting, is more then video {} length'.format(video_info.name))
                    upload_full_video(api, ds.id, video_info, ann, progress)
                    continue
                splitter = get_frames_splitter(g.split_frames, video_info.frames_to_timecodes)

            if g.split_sec:
                if g.split_sec >= round(video_length):
                    g.logger.warn('Time, set for splitting, is more then video {} length'.format(video_info.name))
                    upload_full_video(api, ds.id, video_info, ann, progress)
                    continue
                splitter = get_time_splitter(g.split_sec, video_length)

            curr_video_paths, curr_video_names = write_videos(api, splitter, result_dir, video_info)
            new_video_infos = api.video.upload_paths(ds.id, curr_video_names, curr_video_paths)
            upload_new_anns(api, new_video_infos, ann)
            progress.iter_done_report()

    g.my_app.stop()


def main():
    sly.logger.info("Script arguments", extra={
        "TEAM_ID": g.TEAM_ID,
        "WORKSPACE_ID": g.WORKSPACE_ID,
        "modal.state.slyProjectId": g.PROJECT_ID
    })
    g.my_app.run(initial_events=[{"command": "split_video"}])


if __name__ == '__main__':
    sly.main_wrapper("main", main)