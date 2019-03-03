#!/usr/bin/env python3
import os, sys
import getopt
import subprocess
import logging
import json

def videoCodecName(file):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", file]
    output = subprocess.check_output( cmd )
    return output.strip().decode('ascii')

def hevcProfile(file):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=profile", "-of", "default=noprint_wrappers=1:nokey=1", file]
    output = subprocess.check_output( cmd )
    return output.strip().decode('ascii')

def scanPathForMedia(library):
    videoFiletypes = ['.mkv', '.mp4', '.avi', '.wmv', '.flv', '.mov', '.ogm', '.mpg', '.vob']
    for path in library['paths']:
        for root, dir, files in os.walk(path):
            for name in files:
                if os.path.splitext(name)[1] not in videoFiletypes:
                    continue

                filePath = os.path.join(root, name)

                #Windows path length limit. fatal.
                if len(filePath) > 255:
                    continue

                libraryItem = {}
                libraryItem['filename'] = name
                libraryItem['original_codec'] = videoCodecName(filePath)
                libraryItem['original_mode'] = hevcProfile(filePath)
                libraryItem['original_filesize'] = os.path.getsize(filePath)
                libraryItem['hevc_fileSize'] = os.path.getsize(filePath)
                if libraryItem['original_codec'] == 'hevc' and libraryItem['original_mode'] == 'Main':
                    libraryItem['encoded'] = True
                else:
                    libraryItem['encoded'] = False
                library['files'][filePath] = libraryItem

def backup(fullpath):
    newFilePath = fullpath + '.bk'
    os.rename(fullpath, newFilePath)
    return newFilePath

def restoreBackup(filepath):
    # If the program was stopped during a transcode, mkv or bk files may be left and cause ffmpeg to fail.
    trueFile = os.path.splitext(filepath)[0]
    logging.info('FAILED: %s', os.path.basename(filepath))
    if os.path.exists(trueFile):
        os.remove(trueFile)
    failedTranscodeFile = os.path.splitext(trueFile)[0]+'.mkv'
    if os.path.exists(failedTranscodeFile):
        os.remove(failedTranscodeFile)
    os.rename(filepath, trueFile)
    return trueFile

def convertLibx265(input, output):
    cmd = ["ffmpeg", "-i", input, "-n", "-hide_banner",
    "-map", "0", "-map_metadata", "0", "-map_chapters", "0",
    "-c:v", "libx265", "-pix_fmt", "yuv420p",
    "-c:a", "aac",  "-ac", "2",
    "-c:s", "copy", output]
    result = subprocess.call(cmd)
    return result

scriptdir = os.path.dirname(os.path.abspath(sys.argv[0]))
logging.basicConfig(filename=scriptdir + '/log.txt', level=logging.DEBUG)
logging.info("Begin search and convert")

jsonFilePath = os.path.abspath(scriptdir + '/library.json')
if not os.path.isfile(jsonFilePath):
    print('No library found, initialising new library')
    jsonLibrary = {}
    jsonLibrary['paths'] = []
    jsonLibrary['files'] = {}
    scanPathForMedia(jsonLibrary)
    with open(jsonFilePath, 'w') as jsonFile:
        json.dump(jsonLibrary, jsonFile)
print('loading library')
with open(jsonFilePath) as jsonFile:
    jsonLibrary = json.load(jsonFile)
rescan = False

try:
    opts, args = getopt.getopt(sys.argv[1:],"hc:p:s", ["count=", "path=", "scan="])
except getopt.GetoptError:
    print("h265encode.py -p 'path' -c 'count'")
    sys.exit(2)

for opt, arg in opts:
    if opt == '-h':
        print("h265encode.py -p 'path' -c 'count'")
        sys.exit()
    elif opt in ("-c", "--count"):
        fileConvertCount = int(arg)
    elif opt in ("-p", "--path"):
        appendPath = os.path.abspath(arg)
        if not os.path.isdir(appendPath):
            print('invalid path')
            sys.exit(2)
        print(appendPath)
        if appendPath not in jsonLibrary['paths']:
            logging.info('adding %s to paths', appendPath)
            jsonLibrary['paths'].append(appendPath)
    elif opt in ("-s", "--scan"):
        scanPathForMedia(jsonLibrary)

spaceSaved = 0
i = 0

for file in jsonLibrary['files']:
    if(i >= fileConvertCount):
        break

    if not os.path.exists(file):
        logging.info("error reading %s, file not found.", file)
        continue

    if os.path.isfile(file + '.bk'):
        restoreBackup(file + '.bk')

    try:
        if jsonLibrary['files'][file]['encoded']:
            continue
    except KeyError:
        continue

    if videoCodecName(file) == 'hevc' and hevcProfile(file) == 'Main':
        logging.info('ERROR: GOT 265 FILE, %s', file)

    i += 1
    input = backup(file)
    output = os.path.splitext(file)[0]+'.mkv'
    result = convertLibx265(input, output)
    if result == 0:
        jsonLibrary['files'][output] = jsonLibrary['files'].pop(file)
        jsonLibrary['files'][output]['filename'] = os.path.basename(output)
        jsonLibrary['files'][output]['hevc_fileSize'] = os.path.getsize(output)
        jsonLibrary['files'][output]['encoded'] = True
        with open(jsonFilePath, 'w') as jsonFile:
            json.dump(jsonLibrary, jsonFile)
        fileSpaceSaved = jsonLibrary['files'][output]['original_filesize'] - jsonLibrary['files'][output]['hevc_fileSize']
        spaceSaved += fileSpaceSaved
        logging.info('%s/%s delete: %s, space saved: %smb', i, fileConvertCount, os.path.basename(input), fileSpaceSaved/1000000)
        os.remove(input)
    else:
        restoreBackup(input)

logging.info('completed')
logging.info('SAVED: %smb', int(spaceSaved/1000000))
