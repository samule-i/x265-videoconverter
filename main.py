#!/usr/bin/env python3
import os, sys
import getopt
import subprocess
import logging
import json
import glob

class VideoInformation():
    def __init__(self, fp):
        self.filepath = fp

    def analyze(self):
        self.command = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams", '"'+self.filepath+'"'
            ]
        try:
            self.ffprobe = json.loads(
                subprocess.check_output(' '.join(self.command))
                )
        except subprocess.CalledProcessError:
            print('Error running ffprobe')
            print(f'command {" ".join(self.command)}')
            return False

        self.streams = self.ffprobe["streams"]
        self.videoStreams = [ stream for stream in self.streams
                if stream["codec_type"] == "video"
                and not stream["disposition"]["attached_pic"]]
        self.audioStreams = [ stream for stream in self.streams
                if stream["codec_type"] == "audio"]
        self.subtitleStreams = [ stream for stream in self.streams
                if stream["codec_type"] == "subtitle"]
        self.attachmentStreams = [ stream for stream in self.streams
                if stream["codec_type"] == "attachment"]
        self.imageStreams = [ stream for stream in self.streams
                if stream["codec_type"] == "video"
                and stream["disposition"]["attached_pic"]]

    def isEncoded(self):
        for stream in self.videoStreams:
            if stream["codec_name"] != 'hevc':
                return False
            elif stream["profile"] != 'Main':
                return False
            else:
                return True

    def simpleEntry(self):
        self.entry = {}
        try:
            self.entry["video_codec"] = self.videoStreams[0]["codec_name"]
        except IndexError:
            print("No video streams")
            return False
        if self.entry["video_codec"] == 'hevc':
            self.entry["video_profile"] = self.videoStreams[0]["profile"]
        else:
            self.entry["video_profile"] = ''
        self.entry["file_size"] = self.ffprobe["format"]["size"]
        self.entry["duration"] = int(float(self.ffprobe["format"]["duration"]))
        return self.entry

class MediaLibrary():
    def __init__(self):
        self.libraryFilePath = os.path.abspath(os.path.dirname(sys.argv[0])) + '/library.json'
        self.videoFileTypes = [
            '.mkv', '.mp4', '.avi',
            '.wmv', '.flv', '.mov',
            '.ogm', '.ogv', '.mpg',
            '.vob', '.webm', '.3gp'
            ]

        if not os.path.isfile(self.libraryFilePath):
            logging.info(f' No medialibrary found, creating new library')
            self.library = {}
            self.library['paths'] = []
            self.library['incomplete_files'] = {}
            self.library['complete_files'] = {}
            self.library['failed_files'] = {}
            self.library['space_saved'] = 0
            #scanPathForMedia(jsonLibrary)
            self._libraryCommit()
        print('loading library')
        with open(self.libraryFilePath) as jsonFile:
            self.library = json.load(jsonFile)

    def scan(self, path):
        """Searching through files in path that are not in database.
           ffprobe them and add metadata to database."""
        logging.info(f' MediaLibrary scanning {path}')
        for root, dir, files in os.walk(path):
            for name in files:
                if (str.lower(os.path.splitext(name)[1])
                        not in self.videoFileTypes):
                    continue # not a video
                self.filepath = os.path.join(root, name)

                if (self.filepath in self.library["incomplete_files"] or
                    self.filepath in self.library["complete_files"] or
                    self.filepath in self.library["failed_files"]):
                    continue # file is already tracked

                # Windows path limit. Fatal
                if len(self.filepath) > 255:
                    continue
                print(self.filepath)

                self.info = VideoInformation(self.filepath)
                self.analyzeResult = self.info.analyze()
                if self.analyzeResult == False:
                    error = f'VideoInformation failed reading {self.filepath}'
                    logging.info(error)
                    failedEntry = {}
                    failedEntry['filepath'] = self.filepath
                    failedEntry['errorMessage'] = error
                    self.library['failed_files'][self.filepath] = failedEntry
                    continue
                try:
                    self.entry = self.info.simpleEntry()
                except KeyError as error:
                    self.markFailed(self.filepath, error)
                    continue
                if self.info.isEncoded():
                    self.library['complete_files'][self.filepath] = self.entry
                    self.library['complete_files'][self.filepath]['original_codec'] = 'hevc'
                    self.library['complete_files'][self.filepath]['space_saved'] = 0
                else:
                    self.library["incomplete_files"][self.filepath] = self.entry
        self._libraryCommit()
        print("Scan completed")

    def markComplete(self, filepath):
        logging.info(f' Completed transcoding {filepath}')
        self.filepath = filepath
        self.newFilepath = os.path.splitext(self.filepath)[0]+'.mkv'
        self.newEntry = self.library["incomplete_files"].pop(filepath)

        try:
            self.newSize = os.path.getsize(self.newFilepath)
        except FileNotFoundError:
            print('File not found, assuming filename character encoding error')
            self.newSize = self.newEntry["file_size"]

        self.spaceSaved = int(self.newEntry["file_size"]) - int(self.newSize)
        self.newEntry["original_video_codec"] = self.newEntry["video_codec"]
        self.newEntry["video_codec"] = 'hevc'
        self.newEntry["video_profile"] = 'Main'
        self.newEntry["space_saved"] = self.spaceSaved
        self.newEntry["file_size"] = self.newSize
        self.library["complete_files"][self.newFilepath] = self.newEntry
        self.library["space_saved"] += self.spaceSaved
        self._libraryCommit()

    def markFailed(self, filepath, errorMessage):
        """
            create entry in failed_files and
            remove file from incomplete_files if it exists
        """
        if filepath in self.library['incomplete_files']:
            entry = self.library['incomplete_files'].pop(filepath)
        else:
            entry = {}
            entry['filepath'] = filepath
        entry['error_message'] = str(errorMessage)
        self.library['failed_files'][filepath] = entry
        self._libraryCommit()
        logging.error(f' {filepath} failed to convert, moving to failed_files')

    def showFailed(self):
        """ print failed_files dictionary to stdout """
        for entry in self.library['failed_files']:
            item = self.library['failed_files'][entry]
            fp = entry
            errorMessage = item['error_message']
            print(f'path: {fp}\nerror message: {errorMessage}\n')


    def addNewPath(self, filepath):
        self.mediaDirectory = os.path.abspath(filepath)
        if not os.path.isdir(filepath):
            print("not valid directory")
            logging.error(f' invalid directory {filepath}')
            sys.exit(2)
        if self.mediaDirectory not in self.library["paths"]:
            logging.info(f' Adding new scan path {self.mediaDirectory}')
            self.library["paths"].append(self.mediaDirectory)
        self._libraryCommit()

    def listPaths(self):
        return self.library["paths"]

    def returnLibraryEntries(self, count):
        """Returns a list of filepaths from the top of the database"""
        self.dictionaryIterator = iter(self.library["incomplete_files"])
        self.entryList = []
        for i in range(count):
            try:
                self.entryList.append(next(self.dictionaryIterator))
            except StopIteration:
                logging.warning(' reached end of database')
                break
        if len(self.entryList) == 0:
            logging.error(' media conversion completed, scan may add new media')
            sys.exit(100)
        return self.entryList

    def returnDirectory(self, directory):
        """Returns all filepaths from directory in argument"""
        directory = os.path.abspath(directory)
        if not os.path.isdir(directory):
            print(f'{directory} is not a valid path, exiting')
            sys.exit()
        self.scan(directory)
        self.entryList = []
        for file in os.listdir(directory):
            fp = directory + '\\' + file
            if os.path.splitext(fp)[1] not in self.videoFileTypes:
                continue
            if fp in self.library['complete_files']:
                print(f'{fp} already completed')
                continue
            if fp in self.library['failed_files']:
                print(f'{fp} has already failed conversion')
                continue
            try:
                self.entryList.append(fp)
            except KeyError as errorMessage:
                logging.error(errorMessage)
                print(errorMessage)
                continue
        return self.entryList

    def _libraryCommit(self):
        with open(self.libraryFilePath, "w") as jsonFile:
            json.dump(self.library, jsonFile)

class X265Encoder():
    def __init__(self, filepath):
        self.filepath = filepath
        self.filepathBase = os.path.splitext(self.filepath)[0]
        self.backupFilepath = self.filepath+'.bk'
        self.outputFilepath = self.filepathBase+'.mkv'

    def _backup(self):
        if os.path.isfile(self.backupFilepath): os.remove(self.backupFilepath)
        os.rename(self.filepath, self.backupFilepath)
        if os.path.isfile(self.backupFilepath):
            return True
        else:
            return False

    def _restore(self):
        if os.path.exists(self.backupFilepath):
            if os.path.exists(self.outputFilepath):
                os.remove(self.outputFilepath)
            if os.path.exists(self.filepath):
                os.remove(self.filepath)
            os.rename(self.backupFilepath, self.filepath)
        if (os.path.exists(self.filepath)
                and not os.path.exists(self.backupFilepath)):
            return True
        else:
            return False

    def _checkValid(self):
        if os.path.exists(self.backupFilepath): self._restore()

        if not os.path.exists(self.filepath):
            logging.error(f' skipping: {self.filepath} not found')
            return False
        return True

    def _subtitlePaths(self):
        self.subtitleExtensions = ['.ass', '.ssa', '.sub', '.srt']
        self.subtitleFiles = []
        for extension in self.subtitleExtensions:
            # glob chokes on '[]', escape [ and ]
            self.pattern = f'{self.filepathBase}*{extension}'
            self.pattern = self.pattern.translate(
                {ord('['):'[[]', ord(']'):'[]]'}
            )
            self.subtitleFiles += glob.glob(self.pattern)
        return self.subtitleFiles

    def _mapVideoStreams(self):
        for stream in self.file.videoStreams:
            self.command += ["-map", f'0:{stream["index"]}']
        self.command += ["-c:v", "libx265", "-pix_fmt", "yuv420p"]

    def _mapAudioStreams(self):
        self.compatableAudioCodecs = [
            'mp3', 'wma', 'aac',
            'ac3', 'dts', 'pcm',
            'lpcm', 'mlp', 'dts-hd'] # flac alac not included to save space
        self.streamCounter = 0
        for stream in self.file.audioStreams:
            self.command += ["-map", f'0:{stream["index"]}']
            if stream["codec_name"] in self.compatableAudioCodecs:
                self.command += [f'-c:a:{self.streamCounter}', 'copy']
            else:
                self.command += [f'-c:a:{self.streamCounter}', 'aac']
            self.streamCounter += 1


    def _mapSubtitleStreams(self):
        self.compatableSubtitleCodecs = [
            'sami', 'srt', 'ass',
            'dvd_subtitle', 'ssa', 'sub',
            'usf',  'xsub', 'subrip']
        self.streamCounter = 0
        for stream in self.file.subtitleStreams:
            self.command += ["-map", f'0:{stream["index"]}']
            if stream["codec_name"] in self.compatableSubtitleCodecs:
                self.command += [f'-c:s:{self.streamCounter}', 'copy']
            else:
                self.command += [f'-c:s:{self.streamCounter}', 'ass']
            self.streamCounter += 1
        for subtitle in self.externalSubtitles:
            self.subtitleFile = VideoInformation(subtitle)
            self.subtitleFile.analyze()
            self.subtitleInformation = self.subtitleFile.subtitleStreams
            self.streamCounter = 0
            for stream in self.subtitleInformation:
                self.command += [
                    "-map",
                    f'{self.externalSubtitles.index(subtitle)+1}:{stream["index"]}']
                if stream['codec_name'] in self.compatableSubtitleCodecs:
                    self.command += [f'-c:s:{self.streamCounter}', 'copy']
                else:
                    self.command += [f'-c:s:{self.streamCounter}', 'srt']
                self.streamCounter += 1


    def _mapAttachments(self):
        for stream in self.file.attachmentStreams:
            self.command += ["-map", f'0:{stream["index"]}']

    def _mapImages(self):
        """
            ffmpeg 4.1 -disposition:v:s attached_pic outputs a
            file with disposition attached_pic = 0
            I have tried this with the
            ffmpeg example cover_art.mkv and
            several different commands to try to achieve an
            attached_pic disposition
            return False and skip the file
        """
        # obo gives current stream number
        self.streamCounter = len(self.file.videoStreams)
        for stream in self.file.imageStreams:
            return False
            self.command += [
                "-map",
                f'0:{stream["index"]}']
            self.command += [
                f'-c:v:{self.streamCounter}',
                'copy']
            self.command += [
                f'-disposition:v:{self.streamCounter}',
                'attached_pic']
            self.streamCounter += 1
        return True

    def encode(self):

        if not self._checkValid():
            print('invalid file')
            return False

        self.file = VideoInformation(self.filepath)
        self.file.analyze()

        if self.file.isEncoded():
            logging.error(f' skipping: {self.filepath} is already encoded')
            library.markComplete(self.filepath)
            return False

        self._backup()

        self.command = ["ffmpeg", "-n", "-hide_banner"]
        self.command += ["-i", f'"{self.backupFilepath}"']

        self.externalSubtitles = self._subtitlePaths()
        for subtitle in self.externalSubtitles:
            self.command += ["-i", f'"{subtitle}"']

        self.command += ["-map_chapters", "0", "-map_metadata", "0"]

        self._mapVideoStreams()
        self._mapAudioStreams()
        self._mapSubtitleStreams()
        self._mapAttachments()
        if not self._mapImages():
            logging.warning(
                f' {self.filepath} contains images, not handling'
            )
            failedFilepaths.append(self.filepath)
            self._restore()
            return False

        self.command += [f'"{self.outputFilepath}"']

        print(' '.join(self.command)+'\n')
        self.result = subprocess.call(' '.join(self.command) )
        if self.result == 0:
            os.remove(self.backupFilepath)
            library.markComplete(self.filepath)
        else:
            logging.error(
                f' failed encoding {self.filepath}, restoring original file'
            )
            failedFilepaths.append(self.filepath)
            self._restore()
        return self.result

scriptdir = os.path.dirname(os.path.abspath(sys.argv[0]))
logging.basicConfig(filename=scriptdir + '/log.txt', level=logging.DEBUG)
logging.info("_"*80)

library = MediaLibrary()

try:
    opts, args = getopt.getopt(
        sys.argv[1:],
        "hn:p:sle",
        ["number=", "path=", "scan=", "listpaths=", "focus_directory="]
    )
except getopt.GetoptError as err:
    print(str(err))
    sys.exit(2)

for opt, arg in opts:
    if opt == '-h':
        print(
            "h265encode.py -p 'path' -n 'number' -s 'scan media' -l 'list paths' -e 'list errors'"
        )
        sys.exit()
    elif opt in ("-n", "--number"):
        convertFilepaths = library.returnLibraryEntries(int(arg))
    elif opt in ("--focus_directory"):
        print(f'Focusing {arg}')
        convertFilepaths = library.returnDirectory(arg)
    elif opt in ("-p", "--path"):
        library.addNewPath(os.path.abspath(arg))
        sys.exit()
    elif opt in ("-s", "--scan"):
        for fp in library.listPaths():
            library.scan(fp)
        sys.exit()
    elif opt in ("-l", "--listpaths"):
        print(library.library['paths'])
        sys.exit()
    elif opt in ("-e"):
        library.showFailed()
        sys.exit()

failedFilepaths = []
spaceSaved = 0

#Can't be changes whilst iterating dicts
for filepath in convertFilepaths:

    print(filepath)
    libraryEntry = library.library['incomplete_files'][filepath]

    #check json db if encoded before running encoder
    try:
        if (libraryEntry["video_codec"] == 'hevc'
            and libraryEntry["video_profile"] == 'Main'):
            continue
    except KeyError:
        continue

    encoder = X265Encoder(filepath)
    encodeResult = encoder.encode()
    if encodeResult == 0:
        fileSpaceSaved = library.library["complete_files"][os.path.splitext(filepath)[0]+'.mkv']["space_saved"]
        spaceSaved += fileSpaceSaved
        logging.info(f'     space saved {fileSpaceSaved/1_000_000}')
    else:
        errorMessage = f'ffmpeg failed with error: {encodeResult}'
        library.markFailed(filepath, encodeResult)

if len(failedFilepaths) > 0:
    print(" Some files failed, recommended manual conversion")
    for filename in failedFilepaths:
        print(f' failed: {filename}')
logging.info(' completed')
logging.info(f' space saved this run: {int(spaceSaved/1000000)}mb')
