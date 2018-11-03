#!/usr/bin/env python3
import os
import subprocess
import logging

def videoCodecName(file):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", file]
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
            if not (filename.endswith('.mkv') or filename.endswith('.mp4')):
                continue
            encoding = videoCodecName(filepath)
            if not encoding == 'hevc':
                logging.info('adding file: %s - %s', filepath, encoding)
                videoList.append(filepath)
            if len(videoList) >= 10:
                return videoList
    return videoList

def backup(fullpath):
    newFilePath = fullpath + '.bk'
    os.rename(fullpath, newFilePath)
    return newFilePath

def convertLibx265(input, output):
    cmd = ["ffmpeg", "-i", input, "-n", "-ac", "2", "-map", "0", "-c:v", "libx265", "-c:a", "aac", "-c:s", "copy", output]
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

for file in mediaList():
    logging.info('converting file %s', file)
    input = backup(file)
    output = os.path.splitext(file)[0]+'.mkv'
    result = convertLibx265(input, output)
    if result == 0:
        spaceSaved += sizeCompare(input, output)
        logging.info('delete: %s', input)
        os.remove(input)
    else:
        logging.warning('failed to convert %s \n error code: %s', input, result)
        logging.warning('Delete %s', output)
        logging.warning('replace %s', file)
        os.remove(output)
        os.rename(input, file)
logging.info('completed')
logging.info('SAVED: %smb', spaceSaved/1000000)
