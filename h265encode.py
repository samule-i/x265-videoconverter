#!/usr/bin/env python3
import os
import subprocess
import logging

def videoCodecName(file):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", file]
    output = subprocess.check_output( cmd )
    return output.strip().decode('ascii')

def hevcProfile(file):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=profile", "-of", "default=noprint_wrappers=1:nokey=1", file]
    output = subprocess.check_output( cmd )
    return output.strip().decode('ascii')

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
            if filename.endswith('.bk'):
                recover = restoreBackup(filepath)
                videoList.append(recover)
            if not (filename.endswith('.mkv') or filename.endswith('.mp4')):
                continue
            encoding = videoCodecName(filepath)
            profile = hevcProfile(filepath)
            if not encoding == 'hevc' or not profile == 'Main':
                logging.info('adding file: %s - %s', filepath, encoding)
                videoList.append(filepath)
            if len(videoList) >= 15:
                return videoList
    return videoList

def backup(fullpath):
    newFilePath = fullpath + '.bk'
    os.rename(fullpath, newFilePath)
    return newFilePath

def restoreBackup(filepath):
    trueFile = os.path.splitext(filepath)[0]
    logging.info('RM %s MV %s', filepath, trueFile)
    if os.path.exists(trueFile):
        os.remove(trueFile)
    os.rename(filepath, trueFile)
    return trueFile

def convertLibx265(input, output):
    cmd = ["ffmpeg", "-i", input, "-n", "-hide_banner", "-loglevel", "panic",
    "-map", "0", "-map_metadata", "0", "-map_chapters", "0",
    "-c:v", "libx265", "-pix_fmt", "yuv420p",
    "-x265-params", "--profile=main",
    "-c:a", "aac",  "-ac", "2",
    "-c:s", "ass", output]
    result = subprocess.call(cmd)
    return result

def sizeCompare(input, output):
    inputSize = os.path.getsize(input)
    outputSize = os.path.getsize(output)
    return inputSize - outputSize


logging.basicConfig(filename='h265encode.py.log', level=logging.DEBUG)
logging.info("------------------------------------------------------")
logging.info("Begin search and convert")
spaceSaved = 0
i = 0
media = mediaList()
for file in media:
    i += 1
    logging.info('%s/%s converting file %s', i, len(media), os.path.basename(file))
    input = backup(file)
    output = os.path.splitext(file)[0]+'.mkv'
    result = convertLibx265(input, output)
    if result == 0:
        fileSpaceSaved = sizeCompare(input, output)
        spaceSaved += fileSpaceSaved
        logging.info('%s/%s delete: %s, space saved: %smb', i, len(media), os.path.basename(input), fileSpaceSaved/1000000)
        os.remove(input)
    else:
        restoreBackup(input)
logging.info('completed')
logging.info('SAVED: %smb', spaceSaved/1000000)
