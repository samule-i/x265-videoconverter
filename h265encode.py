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

def audioCodecName(file):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", file]
    output = subprocess.check_output( cmd )
    return output.strip().decode('ascii')

def subtitleCodecName(file):
    cmd = ["ffprobe", "-v", "error", "-select_streams", "s", "-show_entries", "stream=codec_name", "-of", "default=noprint_wrappers=1:nokey=1", file]
    output = subprocess.check_output( cmd )
    return output.strip().decode('ascii')

def scanPathForMedia(library):
    videoFiletypes = ['.mkv', '.mp4', '.avi', '.wmv', '.flv', '.mov', '.ogm', 'ogv', '.mpg', '.vob', 'webm', 'webp']
    print('Scanning paths for media')
    print(library['paths'])
    for path in library['paths']:
        print(path)
        for root, dir, files in os.walk(path):
            print(root)
            for name in files:
                if str.lower(os.path.splitext(name)[1]) not in videoFiletypes:
                    continue

                filePath = os.path.join(root, name)

                if filePath in library['files']:
                    print("%s already in db", filePath)
                    continue

                #Windows path length limit. fatal.
                if len(filePath) > 255:
                    continue

                logging.info("adding %s to db", name)
                print("adding %s to db", name)
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
    return library

def markCompleted(filePath):
    #pass through the original name
    newKey = os.path.splitext(filePath)[0] + '.mkv'
    jsonLibrary['files'][newKey] = jsonLibrary['files'].pop(filePath)
    jsonLibrary['files'][newKey]['filename'] = os.path.basename(newKey)
    jsonLibrary['files'][newKey]['hevc_fileSize'] = os.path.getsize(newKey)
    jsonLibrary['files'][newKey]['encoded'] = True
    with open(jsonFilePath, 'w') as jsonFile:
        json.dump(jsonLibrary, jsonFile)

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
    mkvCompatableAudioCodecs = ['mp3', 'wma', 'aac', 'ac3', 'dts', 'pcm', 'lpcm', 'mlp', 'dts-hd'] # flac alac
    mkvCompatableSubtitleCodecs = ['sami', 'srt', 'ass', 'dvd_subtitle', 'ssa', 'sub', 'usf',  'xsub']
    command = ["ffmpeg", "-n", "-hide_banner", "-i", input]

    videoOptions = ["-map", "0", "-map_chapters", "0", "-map_metadata", "0",
                    "-c:v", "libx265", "-pix_fmt", "yuv420p"]

    VC = videoCodecName(input)
    AudioFormats = audioCodecName(input).split('\r\n')
    SubFormats = subtitleCodecName(input).split('\r\n')

    print(VC)
    print(AudioFormats)
    print(SubFormats)

    if AudioFormats[0] in mkvCompatableAudioCodecs:
        audioCodec = "copy"
    else:
        audioCodec = "aac"

    if SubFormats[0] in mkvCompatableSubtitleCodecs:
        subtitleCodec = "copy"
    else:
        subtitleCodec = "ass"

    audioOptions = ["-c:a", audioCodec]
    subtitleOptions = ["-c:s", subtitleCodec]

    command = command + videoOptions + audioOptions + subtitleOptions
    command.append(output)

    logging.info('Video: libx265, Audio: %s, Subtitle: %s', audioCodec, subtitleCodec)
    result = subprocess.call(command)
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
    opts, args = getopt.getopt(sys.argv[1:],"hn:p:sl", ["number=", "path=", "scan=", "listpaths="])
except getopt.GetoptError:
    print("h265encode.py -p 'path' -n 'number'")
    sys.exit(2)

for opt, arg in opts:
    if opt == '-h':
        print("h265encode.py -p 'path' -n 'number' -s 'scan media' -l 'list paths'")
        sys.exit()
    elif opt in ("-n", "--number"):
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
            with open(jsonFilePath, 'w') as jsonFile:
                json.dump(jsonLibrary, jsonFile)
    elif opt in ("-s", "--scan"):
        scanResult = scanPathForMedia(jsonLibrary)
        with open(jsonFilePath, 'w') as jsonFile:
            json.dump(scanResult, jsonFile)
    elif opt in ("-l", "--listpaths"):
        print(jsonLibrary['paths'])
        sys.exit()


spaceSaved = 0
i = 0
failureList = []

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
        logging.error('file passed through is already encoded hevc L4, %s', file)
        markCompleted(file)
        continue

    i += 1
    input = backup(file)
    output = os.path.splitext(file)[0]+'.mkv'
    result = convertLibx265(input, output)
    if result == 0:
        markCompleted(file)
        fileSpaceSaved = jsonLibrary['files'][output]['original_filesize'] - jsonLibrary['files'][output]['hevc_fileSize']
        spaceSaved += fileSpaceSaved
        logging.info('%s/%s delete: %s, space saved: %smb', i, fileConvertCount, os.path.basename(input), fileSpaceSaved/1000000)
        os.remove(input)
    else:
        restoreBackup(input)
        failureList.append(file)

if len(failureList) > 0:
    print("Some files failed, recommended manual conversion")
for filename in failureList:
    print("failed: %s", filename)

logging.info('completed')
logging.info('SAVED: %smb', int(spaceSaved/1000000))
