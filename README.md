

<div align="center" markdown>
<img src="https://i.imgur.com/vYGZLho.png"/>





# Split videos

<p align="center">
  <a href="#Overview">Overview</a> •
  <a href="#How-To-Run">How To Run</a> •
  <a href="#How-To-Use">How To Use</a>
</p>
  

[![](https://img.shields.io/badge/slack-chat-green.svg?logo=slack)](https://supervise.ly/slack)
![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/supervisely-ecosystem/split_video)
[![views](https://app.supervise.ly/img/badges/views/supervisely-ecosystem/split-video.png)](https://supervise.ly)
[![runs](https://app.supervise.ly/img/badges/runs/supervisely-ecosystem/split-video.png)](https://supervise.ly)

</div>

## Overview

Application splits `videos` in [Supervisely](https://app.supervise.ly) project or dataset by specified `time` in seconds or specified number of `frames`. Result videos will have names like original videos with `_index` suffix, where `index`  - the sequence number of the video received in the process of splitting. If video length is less, then specified splitter(`time` or `frames` number), it will be add to result project without changes.



## How To Run 
**Step 1**: Add app to your team from [Ecosystem](https://ecosystem.supervise.ly/apps/split_video) if it is not there.

**Step 2**: Open context menu of project -> `Run App` -> `Split videos` 

<img src="https://i.imgur.com/CnlKoDX.png"/>

**Step 3**: Сhoose a way to split the video - by `time` in seconds or number of `frames`.

Split videos by `time` in seconds.

<img src="https://i.imgur.com/t6tCy2Z.png" width="600px"/>

Split videos by number of `frames`.

<img src="https://i.imgur.com/bgjbjhJ.png" width="600px"/>

Press `RUN`button.



## How to use

Result project will be saved in your current `Workspace` with `_splitted` suffix.

<img src="https://i.imgur.com/LhBStdT.png"/>