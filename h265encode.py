#!/usr/bin/env python3
import os
import json
import subprocess

def videoCodecName(file):
    cmd = ["ffprobe","-show_format", "-show_streams", "-loglevel", "quiet", "-print_format", "json", file]
    output = json.loads(subprocess.check_output( cmd ))
    return output["streams"][0]["codec_name"]

def mediaList():
    videoList = []
    directoryList = []
    for directory in os.listdir(os.getcwd()):
        if os.path.isdir(directory) and not directory.endswith('.old'):
            directoryList.append(os.path.abspath(directory))

    for directory in directoryList:
        for file in os.listdir(directory):
            filepath = os.path.join(directory, file)
            filename = file.lower()
            if not (filename.endswith('.mkv') or filename.endswith('.mp4')):
                continue
            encoding = videoCodecName(filepath)
            if not encoding == 'hevc':
                videoList.append(filepath)
    return videoList

def backup(fullpath):
    backupDirectory = os.path.dirname(fullpath)+'.old'
    if not os.path.exists(backupDirectory):
        os.makedirs(backupDirectory)
    newFilePath = os.path.join(backupDirectory, os.path.basename(fullpath))
    os.rename(fullpath, newFilePath)
    return newFilePath

def convertLibx265(input, output):
    cmd = ["ffmpeg", "-i", input, "-n", "-map", "0", "-c:v", "libx265", "-c:a", "copy", "-c:s", "copy", output]
    result = subprocess.call(cmd)
    return result

for file in mediaList():
    print(file)
    input = backup(file)
    print(input)
    output = os.path.splitext(file)[0]+'.mkv'
    result = convertLibx265(input, output)
    if result == 0:
        print("delete: "+input)
        os.remove(input)
    print(result)
