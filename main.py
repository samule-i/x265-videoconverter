#!/usr/bin/env python3
import argparse
import glob
import json
import logging
import os
import subprocess
import time

import sys


class VideoInformation:
    def __init__(self, fp):
        self.filepath = fp
        self.low_profile = False
        self.log = setup_logging()

    def analyze(self):
        self.command = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            self.filepath,
        ]
        try:
            self.ffprobe = json.loads(subprocess.check_output(self.command))
        except subprocess.CalledProcessError as error:
            self.log.error(f'{error}\ncommand {" ".join(self.command)}')
            return False

        self.streams = self.ffprobe["streams"]
        self.videoStreams = [
            stream
            for stream in self.streams
            if stream["codec_type"] == "video"
            and not stream["disposition"]["attached_pic"]
        ]
        self.audioStreams = [
            stream for stream in self.streams if stream["codec_type"] == "audio"
        ]
        self.subtitleStreams = [
            stream for stream in self.streams if stream["codec_type"] == "subtitle"
        ]
        self.attachmentStreams = [
            stream for stream in self.streams if stream["codec_type"] == "attachment"
        ]
        self.imageStreams = [
            stream
            for stream in self.streams
            if stream["codec_type"] == "video" and stream["disposition"]["attached_pic"]
        ]

    def isEncoded(self):
        for stream in self.videoStreams:
            if stream["codec_name"] != "hevc":
                return False
            elif stream["profile"] != "Main" and self.low_profile is True:
                return False
            else:
                return True

    def simpleEntry(self):
        self.entry = {}
        try:
            self.entry["video_codec"] = self.videoStreams[0]["codec_name"]
        except IndexError:
            self.log.error("No video streams")
            return False
        if self.entry["video_codec"] == "hevc":
            self.entry["video_profile"] = self.videoStreams[0]["profile"]
        else:
            self.entry["video_profile"] = ""
        self.entry["file_size"] = self.ffprobe["format"]["size"]
        self.entry["duration"] = int(float(self.ffprobe["format"]["duration"]))
        return self.entry


class MediaLibrary:
    def __init__(self):
        self.log = setup_logging()
        self.libraryFilePath = (
            os.path.abspath(os.path.dirname(sys.argv[0])) + "/library.json"
        )
        self.videoFileTypes = [
            ".3gp",
            ".avi",
            ".flv",
            ".mkv",
            ".mov",
            ".mp4",
            ".mpg",
            ".ogm",
            ".ogv",
            ".vob",
            ".webm",
            ".wmv",
        ]

        if not os.path.isfile(self.libraryFilePath):
            self.log.info(f" No medialibrary found, creating new library")
            self.library = {}
            self.library["paths"] = []
            self.library["incomplete_files"] = {}
            self.library["complete_files"] = {}
            self.library["failed_files"] = {}
            self.library["space_saved"] = 0
            self._libraryCommit()
        print("loading library")
        with open(self.libraryFilePath) as jsonFile:
            self.library = json.load(jsonFile)

    def scan(self, path):
        """Searching through files in path that are not in database.
           ffprobe them and add metadata to database."""
        self.log.info(f" MediaLibrary scanning {path}")
        for root, dir, files in os.walk(path):
            for name in files:
                if str.lower(os.path.splitext(name)[1]) not in self.videoFileTypes:
                    continue  # not a video
                self.filepath = os.path.join(root, name)

                if (
                    self.filepath in self.library["incomplete_files"]
                    or self.filepath in self.library["complete_files"]
                    or self.filepath in self.library["failed_files"]
                ):
                    continue  # file is already tracked

                # Windows path limit. Fatal
                if len(self.filepath) > 255:
                    continue
                print(self.filepath)

                self.info = VideoInformation(self.filepath)
                self.analyzeResult = self.info.analyze()
                if self.analyzeResult is False:
                    error = f"VideoInformation failed reading {self.filepath}"
                    self.log.info(error)
                    failedEntry = {}
                    failedEntry["filepath"] = self.filepath
                    failedEntry["errorMessage"] = error
                    self.library["failed_files"][self.filepath] = failedEntry
                    continue
                try:
                    self.entry = self.info.simpleEntry()
                except KeyError as error:
                    self.markFailed(self.filepath, error)
                    continue
                if self.info.isEncoded():
                    self.library["complete_files"][self.filepath] = self.entry
                    self.library["complete_files"][self.filepath][
                        "original_codec"
                    ] = "hevc"
                    self.library["complete_files"][self.filepath]["space_saved"] = 0
                else:
                    self.library["incomplete_files"][self.filepath] = self.entry
        self._libraryCommit()
        self.log.info("Scan completed")

    def markComplete(self, filepath):
        """Move entry from incomplete_files to complete_files."""
        self.log.info(f"Completed transcoding {filepath}")
        self.filepath = filepath
        self.newFilepath = os.path.splitext(self.filepath)[0] + ".mkv"
        self.newEntry = self.library["incomplete_files"].pop(filepath)

        try:
            self.newSize = os.path.getsize(self.newFilepath)
        except FileNotFoundError:
            self.log.error("File not found, assuming filename character encoding error")
            self.newSize = self.newEntry["file_size"]

        self.spaceSaved = int(self.newEntry["file_size"]) - int(self.newSize)
        self.newEntry["original_video_codec"] = self.newEntry["video_codec"]
        self.newEntry["video_codec"] = "hevc"
        self.newEntry["video_profile"] = "Main"
        self.newEntry["space_saved"] = self.spaceSaved
        self.newEntry["file_size"] = self.newSize
        self.library["complete_files"][self.newFilepath] = self.newEntry
        self.library["space_saved"] += self.spaceSaved
        self._libraryCommit()

    def markFailed(self, filepath, errorMessage):
        """
            create entry in failed_files and
            remove file from incomplete_files if it exists.
        """
        if filepath in self.library["incomplete_files"]:
            entry = self.library["incomplete_files"].pop(filepath)
        else:
            entry = {}
            entry["filepath"] = filepath
        entry["error_message"] = str(errorMessage)
        self.library["failed_files"][filepath] = entry
        self._libraryCommit()
        self.log.error(f"{filepath} failed to convert, moving to failed_files")

    def showFailed(self):
        """print failed_files dictionary to stdout."""
        for entry in self.library["failed_files"]:
            item = self.library["failed_files"][entry]
            fp = entry
            try:
                errorMessage = item["error_message"]
            except KeyError:
                errorMessage = "unkown error"
            print(f"path: {fp}\nerror message: {errorMessage}\n")

    def addNewPath(self, filepath):
        """Create a new path entry in library."""
        self.mediaDirectory = os.path.abspath(filepath)
        if not os.path.isdir(filepath):
            self.log.error(f"invalid directory {filepath}")
            sys.exit(2)
        if self.mediaDirectory not in self.library["paths"]:
            self.log.info(f" Adding new scan path {self.mediaDirectory}")
            self.library["paths"].append(self.mediaDirectory)
        self._libraryCommit()

    def listPaths(self):
        """List tracked paths stored in library."""
        return self.library["paths"]

    def returnLibraryEntries(self, count):
        """Return a list of filepaths from the top of the database."""
        self.dictionaryIterator = iter(self.library["incomplete_files"])
        self.entryList = []
        for i in range(count):
            try:
                self.entryList.append(next(self.dictionaryIterator))
            except StopIteration:
                self.log.warning("reached end of database")
                break
        if len(self.entryList) == 0:
            self.log.error("media conversion completed, scan may add new media")
            sys.exit(100)
        return self.entryList

    def returnDirectory(self, directory):
        """Return all filepaths from directory in argument."""
        directory = os.path.abspath(directory)
        if not os.path.isdir(directory):
            print(f"{directory} is not a valid path, exiting")
            sys.exit()
        self.scan(directory)
        self.entryList = []
        for file in os.listdir(directory):
            fp = os.path.join(directory, file)
            if os.path.splitext(fp)[1] not in self.videoFileTypes:
                continue
            if fp in self.library["complete_files"]:
                self.log.debug(f"{fp} already completed")
                continue
            if fp in self.library["failed_files"]:
                self.log.debug(f"{fp} has already failed conversion")
                continue
            try:
                self.entryList.append(fp)
            except KeyError as errorMessage:
                self.log.error(errorMessage)
                print(errorMessage)
                continue
        return self.entryList

    def returnTotalSaved(self):
        return self.library["space_saved"]

    def _libraryCommit(self):
        with open(self.libraryFilePath, "w") as jsonFile:
            json.dump(self.library, jsonFile)


class X265Encoder:
    def __init__(self, filepath):
        self.filepath = filepath
        self.filepathBase = os.path.splitext(self.filepath)[0]
        self.backupFilepath = self.filepath + ".bk"
        self.outputFilepath = self.filepathBase + ".mkv"
        self.low_profile = False
        self.log = setup_logging()

    def _backup(self):
        if os.path.isfile(self.backupFilepath):
            os.remove(self.backupFilepath)
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
        if os.path.exists(self.filepath) and not os.path.exists(self.backupFilepath):
            return True
        else:
            return False

    def _checkValid(self):
        if os.path.exists(self.backupFilepath):
            self._restore()

        if not os.path.exists(self.filepath):
            self.log.error(f"skipping: {self.filepath} not found")
            return False
        return True

    def _validateNewFile(self, filepath):
        """ Perform some checks on output file to check whether the transcode worked
            returns False if there is a problem, true otherwise"""
        if not os.path.isfile(filepath):
            return False
        if os.path.getsize(filepath) == 0:
            return False
        return True

    def _subtitlePaths(self):
        self.subtitleExtensions = [".ass", ".ssa", ".sub", ".srt"]
        self.subtitleFiles = []
        for extension in self.subtitleExtensions:
            # glob chokes on '[]', escape [ and ]
            self.pattern = f"{self.filepathBase}*{extension}"
            self.pattern = self.pattern.translate({ord("["): "[[]", ord("]"): "[]]"})
            self.subtitleFiles += glob.glob(self.pattern)
        return self.subtitleFiles

    def _mapVideoStreams(self):
        for stream in self.file.videoStreams:
            self.command += ["-map", f'0:{stream["index"]}']
        self.command += ["-c:v", "libx265"]
        if self.low_profile is True:
            self.log.debug("Setting pixel format to 4-bit depth")
            self.command += ["-pix_fmt", "yuv420p"]
        else:
            self.log.debug("Setting pixel format to 10-bit depth")
            self.command += ["-pix_fmt", "yuv420p10le"]

    def _mapAudioStreams(self):
        self.compatableAudioCodecs = [
            "aac",
            "ac3",
            "dts",
            "dts-hd",
            "lpcm",
            "mlp",
            "mp3",
            "pcm",
            "wma",
        ]  # flac alac not included to save space
        self.streamCounter = 0
        for stream in self.file.audioStreams:
            self.command += ["-map", f'0:{stream["index"]}']
            if stream["codec_name"] in self.compatableAudioCodecs:
                self.command += [f"-c:a:{self.streamCounter}", "copy"]
            else:
                self.command += [f"-c:a:{self.streamCounter}", "aac"]
            self.streamCounter += 1

    def _mapSubtitleStreams(self):
        self.compatableSubtitleCodecs = [
            "ass",
            "dvd_subtitle",
            "hdmv_pgs_subtitle",
            "sami",
            "srt",
            "ssa",
            "sub",
            "subrip",
            "usf",
            "xsub",
        ]
        self.streamCounter = 0
        for stream in self.file.subtitleStreams:
            self.command += ["-map", f'0:{stream["index"]}']
            if stream["codec_name"] in self.compatableSubtitleCodecs:
                self.command += [f"-c:s:{self.streamCounter}", "copy"]
            else:
                self.command += [f"-c:s:{self.streamCounter}", "ass"]
            self.streamCounter += 1
        for subtitle in self.externalSubtitles:
            self.subtitleFile = VideoInformation(subtitle)
            self.subtitleFile.analyze()
            self.subtitleInformation = self.subtitleFile.subtitleStreams
            self.streamCounter = 0
            for stream in self.subtitleInformation:
                self.command += [
                    "-map",
                    f'{self.externalSubtitles.index(subtitle)+1}:{stream["index"]}',
                ]
                if stream["codec_name"] in self.compatableSubtitleCodecs:
                    self.command += [f"-c:s:{self.streamCounter}", "copy"]
                else:
                    self.command += [f"-c:s:{self.streamCounter}", "srt"]
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
            self.command += ["-map", f'0:{stream["index"]}']
            self.command += [f"-c:v:{self.streamCounter}", "copy"]
            self.command += [f"-disposition:v:{self.streamCounter}", "attached_pic"]
            self.streamCounter += 1
        return True

    def encode(self):

        if not self._checkValid():
            return "invalid file"

        self.file = VideoInformation(self.filepath)
        if self.low_profile is True:
            self.file.low_profile = True
        self.file.analyze()

        if self.file.isEncoded():
            alreadyX265 = (f'{self.filepath} already encoded,'
                           'moved to completed without doing anything')
            self.log.error(alreadyX265)
            return "already encoded"

        self._backup()

        self.command = ["ffmpeg", "-n", "-hide_banner"]
        self.command += ["-i", self.backupFilepath]

        self.externalSubtitles = self._subtitlePaths()
        for subtitle in self.externalSubtitles:
            self.command += ["-i", f'"{subtitle}"']

        self.command += ["-map_chapters", "0", "-map_metadata", "0"]

        self._mapVideoStreams()
        self._mapAudioStreams()
        self._mapSubtitleStreams()
        self._mapAttachments()
        if not self._mapImages():
            imageStreamError = (f'filepath had an imageStream'
                                'ignoring file')
            self.log.error(imageStreamError)
            self._restore()
            return "failed"

        self.command += [self.outputFilepath]

        print(" ".join(self.command) + "\n")
        try:
            self.result = subprocess.call(self.command)
        except KeyboardInterrupt:
            self.log.info("cleaning up")
            self.log.error("Keyboard interrupt")
            self._restore()
            sys.exit()
        if self.result == 0 and self._validateNewFile(self.filepath):
            os.remove(self.backupFilepath)
            return "success"
        else:
            ffmpegError = (f"failed encoding {self.filepath},"
                           "restoring original file")
            self.log.error(ffmpegError)
            self._restore()
            return "failed"


def setup_logging(logDirectory=None, loggingLevel=None):
    """Initialise the logger and stdout"""
    # set root
    rootLogger = logging.getLogger()
    format = '%(asctime)s %(name)s.%(funcName)s +%(lineno)s: %(levelname)-8s [%(process)d] %(message)s'
    dateFormat = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter(format, dateFormat)
    if loggingLevel is not None:
        rootLogger.setLevel(loggingLevel)
    # logger set level
    logger = logging.getLogger(__name__)
    # file
    if logDirectory is None:
        scriptDirectory = os.path.dirname(os.path.abspath(sys.argv[0]))
        logDirectory = os.path.join(scriptDirectory, 'logs')
    if not os.path.exists(logDirectory):
        os.makedirs(logDirectory)
    logFile = os.path.join(logDirectory, '265encoder.log')
    if not len(logger.handlers):
        fileHandler = logging.FileHandler(logFile)
        fileHandler.setFormatter(formatter)
        logger.addHandler(fileHandler)
        # console
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(formatter)
        logger.addHandler(consoleHandler)
    return logger


def main():
    scriptDescription = ("""
    A database focused media conversion utility that converts video files to
    the HEVC video codec with a focus on reducing disk usage in media libraries.
    This script attempts to be as safe as possible, however encoding to HEVC is
    a lossy operation. though it should be unnoticable it is recommended to test
    first. Backups are encouraged.
    """)
    parser = argparse.ArgumentParser(description=scriptDescription, allow_abbrev=False)

    parser.add_argument("--errors", "-e", action="store_true", help="list errors")
    parser.add_argument("--focus", "-f", action="append", metavar="PATH", help="immediately begin conversion on target directory")
    parser.add_argument("--list-paths", "-lp", action="store_true", help="list tracked paths")
    parser.add_argument("--low-profile", action="store_true", help="for weaker devices, convert to 4-bit HEVC including downgrading 10-bit hevc", default=False)
    parser.add_argument("--number", "-n", action="store", help="transcode from tracked paths limit number of files to be converted", type=int)
    parser.add_argument("--track", "-t", action="append", metavar="PATH", help="add a new path to be tracked")
    parser.add_argument("--saved-space", action="store_true", help="display HDD space saved by transcoding into x265")
    parser.add_argument("--scan", "-s", action="store_true", help="scan tracked directories for new files")
    parser.add_argument("--quiet", "-q", action="store_true", help="only produce minimal output")
    parser.add_argument("--verbose", "-v", action="store_true", help="produce as much output as possible")

    args = parser.parse_args()

    logDirectory = None
    if args.verbose:
        log = setup_logging(logDirectory, logging.DEBUG)
    elif args.quiet:
        log = setup_logging(logDirectory, logging.CRITICAL)
    else:
        log = setup_logging(logDirectory, logging.INFO)

    library = MediaLibrary()

    if args.errors:
        library.showFailed()
        sys.exit()

    if args.list_paths:
        print(library.listPaths())
        sys.exit()

    if args.track:
        for path in args.track:
            library.addNewPath(os.path.abspath(path))

    if args.saved_space:
        totalSavedMB = int(library.returnTotalSaved() / 1_000_000)
        totalSavedGB = (totalSavedMB / 1_000)
        totalSavedTB = (totalSavedGB / 1_000)
        if totalSavedTB > 1:
            print(f"{totalSavedTB}tb")
        elif totalSavedGB > 1:
            print(f"{totalSavedGB}gb")
        else:
            print(f"{totalSavedMB}mb")
        sys.exit()

    if args.scan:
        for fp in library.listPaths():
            library.scan(fp)

    if args.focus:
        for dir in args.focus:
            convertFilepaths = library.returnDirectory(dir)
    elif args.number:
        convertFilepaths = library.returnLibraryEntries(args.number)
    else:
        sys.exit()

    failedFilepaths = []
    spaceSaved = 0
    totalElapsedTime = 0

    # Can't be changes whilst iterating dicts
    for filepath in convertFilepaths:

        print(filepath)
        beginTime = time.time()
        libraryEntry = library.library["incomplete_files"][filepath]

        # check json db if encoded before running encoder
        try:
            if libraryEntry["video_codec"] == "hevc" and args.low_profile is False:
                library.markComplete(filepath)
                continue
            elif (
                libraryEntry["video_codec"] == "hevc"
                and libraryEntry["video_profile"] == "Main"
                and args.low_profile is True
            ):
                library.markComplete(filepath)
                continue
        except KeyError:
            continue

        encoder = X265Encoder(filepath)
        if args.low_profile is True:
            encoder.low_profile = True
        encodeResult = encoder.encode()

        if encodeResult == "success":
            library.markComplete(filepath)
            fileSpaceSaved = library.library["complete_files"][
                os.path.splitext(filepath)[0] + ".mkv"
            ]["space_saved"]
            spaceSaved += fileSpaceSaved
            elapsedTime = time.time() - beginTime
            totalElapsedTime = totalElapsedTime + elapsedTime
            elapsedTimeString = time.strftime("%H:%M:%S", time.localtime(elapsedTime))
            log.info(f"space saved {fileSpaceSaved/1_000_000} : time taken {elapsedTimeString}.")
        elif encodeResult == "already encoded":
            library.markComplete(filepath)
        else:
            failedFilepaths.append(filepath)
            errorMessage = f"x265 convert failed with error: {encodeResult}"
            library.markFailed(filepath, errorMessage)

    if len(failedFilepaths) > 0:
        log.warning("Some files failed, recommended manual conversion")
        for filename in failedFilepaths:
            log.warning(f" failed: {filename}")
    totalElapsedTimeString = time.strftime("%H:%M:%S", time.localtime(totalElapsedTime))
    log.info(f"time taken {totalElapsedTimeString}")
    log.info(f"space saved this run: {int(spaceSaved/1_000_000)}mb")


if __name__ == "__main__":
    main()
