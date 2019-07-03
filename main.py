#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
x265-converter
python3 script to track and convert media to HEVC format
https://github.com/formcore/x265-videoconverter

A file conversion utility that will attempt to convert files in media
directories to HEVC content with the priority of saving disk space.

HEVC is known for having much smaller file sizes than h264 and much smaller than
older codecs such as AVC.

Some devices can not play HEVC as it is a reasonably new codec, so make sure
your player can handle HEVC before converting a library.

It should be reasonably safe to use ctrl+c to cancel during a conversion, the
script manages to abort the conversion and restore a backup.
"""

import argparse
import glob
import json
import logging
import os
import subprocess
import sys

from pprint import pprint


class VideoInformation:
    def __init__(self, fp):
        self.filepath = fp

    def analyze(self):
        self.command = [
            "ffprobe.exe",
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
            # logging.debug(self.ffprobe)
        except subprocess.CalledProcessError as error:
            logging.error(error)
            logging.error(f'Error running ffprobe: {" ".join(self.command)}')
            return False
        except FileNotFoundError as error:
            logging.error("ffprobe.exe:" + str(error))
            sys.exit(1)

        self.streams = self.ffprobe["streams"]
        self.videoStreams = [
            stream
            for stream in self.streams
            if stream["codec_type"] == "video" and not stream["disposition"]["attached_pic"]
        ]
        self.audioStreams = [stream for stream in self.streams if stream["codec_type"] == "audio"]
        self.subtitleStreams = [stream for stream in self.streams if stream["codec_type"] == "subtitle"]
        self.attachmentStreams = [stream for stream in self.streams if stream["codec_type"] == "attachment"]
        self.imageStreams = [
            stream
            for stream in self.streams
            if stream["codec_type"] == "video" and stream["disposition"]["attached_pic"]
        ]
        return True

    def isEncoded(self, low_profile=True):
        for stream in self.videoStreams:
            if stream["codec_name"] != "hevc":
                return False
            elif stream["profile"] != "Main" and low_profile is True:
                return False
            else:
                return True

    def simpleEntry(self):
        self.entry = {}
        try:
            self.entry["video_codec"] = self.videoStreams[0]["codec_name"]
        except IndexError:
            logging.error("No video streams")
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
        self.libraryFilePath = os.path.abspath(os.path.dirname(sys.argv[0])) + "/library.json"
        self.videoFileTypes = [
            ".mkv",
            ".mp4",
            ".avi",
            ".wmv",
            ".flv",
            ".mov",
            ".ogm",
            ".ogv",
            ".mpg",
            ".vob",
            ".webm",
            ".3gp",
        ]

        if not os.path.isfile(self.libraryFilePath):
            logging.info(f"No media library found, creating new library")
            self.library = {}
            self.library["paths"] = []
            self.library["incomplete_files"] = {}
            self.library["complete_files"] = {}
            self.library["failed_files"] = {}
            self.library["space_saved"] = 0
            # scanPathForMedia(jsonLibrary)
            self._libraryCommit()
        logging.debug("loading library")
        with open(self.libraryFilePath) as jsonFile:
            self.library = json.load(jsonFile)

    def scan(self, path):
        """Searching through files in path that are not in database.
           ffprobe them and add metadata to database."""
        logging.info(f"Media library scanning {path}")
        for root, _, files in os.walk(path):  # _ == directory
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
                logging.info(self.filepath)

                self.info = VideoInformation(self.filepath)
                self.analyzeResult = self.info.analyze()
                if not self.analyzeResult:
                    error = f"VideoInformation failed reading {self.filepath}"
                    logging.error(error)
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
                    self.library["complete_files"][self.filepath]["original_codec"] = "hevc"
                    self.library["complete_files"][self.filepath]["space_saved"] = 0
                else:
                    self.library["incomplete_files"][self.filepath] = self.entry
        self._libraryCommit()
        logging.info("Scan completed")

    def markComplete(self, filepath):
        logging.info(f"Completed transcoding {filepath}")
        self.filepath = filepath
        self.newFilepath = os.path.splitext(self.filepath)[0] + ".mkv"
        self.newEntry = self.library["incomplete_files"].pop(filepath)

        try:
            self.newSize = os.path.getsize(self.newFilepath)
        except FileNotFoundError:
            logging.warning("File not found, assuming filename character encoding error")
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
            remove file from incomplete_files if it exists
        """
        if filepath in self.library["incomplete_files"]:
            entry = self.library["incomplete_files"].pop(filepath)
        else:
            entry = {}
            entry["filepath"] = filepath
        entry["error_message"] = str(errorMessage)
        self.library["failed_files"][filepath] = entry
        self._libraryCommit()
        logging.error(f"{filepath} failed to convert, moving to failed_files")

    def showFailed(self):
        """print failed_files dictionary to stdout"""
        for entry in self.library["failed_files"]:
            item = self.library["failed_files"][entry]
            fp = entry
            try:
                errorMessage = item["error_message"]
            except KeyError:
                errorMessage = "unknown error"
            logging.error(f"path: {fp} error message: {errorMessage}")

    def addNewPath(self, filepath):
        self.mediaDirectory = os.path.abspath(filepath)
        if not os.path.isdir(filepath):
            logging.error(f"invalid directory {filepath}")
            sys.exit(2)
        if self.mediaDirectory not in self.library["paths"]:
            logging.info(f"{self.mediaDirectory}: new path, adding to library")
            self.library["paths"].append(self.mediaDirectory)
        else:
            logging.debug(f"{self.mediaDirectory} path exists in library, skipping")
        self._libraryCommit()

    def listPaths(self):
        return self.library["paths"]

    def returnLibraryEntries(self, count):
        """Returns a list of filepaths from the top of the database"""
        self.dictionaryIterator = iter(self.library["incomplete_files"])
        self.entryList = []
        for _ in range(count):
            try:
                self.entryList.append(next(self.dictionaryIterator))
            except StopIteration:
                logging.warning("reached end of database")
                break
        if len(self.entryList) == 0:
            logging.error("media conversion completed, scan may add new media")
            sys.exit(100)
        return self.entryList

    def returnDirectory(self, directory):
        """Returns all filepaths from directory in argument"""
        directory = os.path.abspath(directory)
        if not os.path.isdir(directory):
            logging.error(f"{directory} is not a valid path, exiting")
            sys.exit()
        self.scan(directory)
        self.entryList = []
        for file in os.listdir(directory):
            fp = directory + "\\" + file
            if os.path.splitext(fp)[1] not in self.videoFileTypes:
                continue
            if fp in self.library["complete_files"]:
                logging.debug(f"{fp} already completed")
                continue
            if fp in self.library["failed_files"]:
                logging.warning(f"{fp} has already failed conversion")
                continue
            try:
                self.entryList.append(fp)
            except KeyError as errorMessage:
                logging.error(errorMessage)
                continue
        return self.entryList

    def _libraryCommit(self):
        with open(self.libraryFilePath, "w") as jsonFile:
            json.dump(self.library, jsonFile)


class X265Encoder:
    def __init__(self, filepath):
        self.filepath = filepath
        self.filepathBase = os.path.splitext(self.filepath)[0]
        self.backupFilepath = self.filepath + ".bk"
        self.outputFilepath = self.filepathBase + ".mkv"

    def _backup(self):
        if os.path.isfile(self.backupFilepath):
            os.remove(self.backupFilepath)
        os.rename(self.filepath, self.backupFilepath)
        if os.path.isfile(self.backupFilepath):
            return True
        else:
            return False

    def _restore(self):
        """restore converted file from backup"""
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
        """restore from backup if it exists; if file exists, then True"""
        if os.path.exists(self.backupFilepath):
            self._restore()

        if not os.path.exists(self.filepath):
            logging.error(f"Skipping: {self.filepath} not found")
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

    def _mapVideoStreams(self, low_profile=True):
        for stream in self.file.videoStreams:
            self.command += ["-map", f'0:{stream["index"]}']
        self.command += ["-c:v", "libx265"]
        if low_profile is True:
            self.command += ["-pix_fmt", "yuv420p"]

    def _mapAudioStreams(self):
        self.compatableAudioCodecs = [
            "mp3",
            "wma",
            "aac",
            "ac3",
            "dts",
            "pcm",
            "lpcm",
            "mlp",
            "dts-hd",
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
        self.compatableSubtitleCodecs = ["sami", "srt", "ass", "dvd_subtitle", "ssa", "sub", "usf", "xsub", "subrip"]
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
                self.command += ["-map", f'{self.externalSubtitles.index(subtitle)+1}:{stream["index"]}']
                if stream["codec_name"] in self.compatableSubtitleCodecs:
                    self.command += [f"-c:s:{self.streamCounter}", "copy"]
                else:
                    self.command += [f"-c:s:{self.streamCounter}", "srt"]
                self.streamCounter += 1

    def _mapAttachments(self):
        for stream in self.file.attachmentStreams:
            self.command += ["-map", f'0:{stream["index"]}']

    def _build_command(self):
        """build the ffmpeg command arguments"""
        self.command = ["ffmpeg.exe", "-n", "-hide_banner", "-i", self.backupFilepath]
        self.externalSubtitles = self._subtitlePaths()
        for subtitle in self.externalSubtitles:
            self.command += ["-i", f'"{subtitle}"']
        self.command += ["-map_chapters", "0", "-map_metadata", "0"]
        self._mapVideoStreams()
        self._mapAudioStreams()
        self._mapSubtitleStreams()
        self._mapAttachments()
        self.command += [self.outputFilepath]
        logging.debug(" ".join(self.command))

    def encode(self):
        """encode file"""
        if not self._checkValid():
            self.result = 1
            return f"{self.filepath}: invalid file"

        self.file = VideoInformation(self.filepath)
        self.file.analyze()

        if self.file.isEncoded():
            self.result = 0
            return f"{self.filepath}: already encoded, skipping"

        self._backup()
        self._build_command()

        if self.file.imageStreams:
            logging.warning(f"{self.filepath}: contains images, not handling")
            self.result = 1
            self._restore()
            return f"{self.filepath}: imageStream found"
        # encode file
        try:
            self.result = subprocess.call(self.command)
        except KeyboardInterrupt as kbd:
            logging.error(kbd)
            self._restore()
            sys.exit()
        except FileNotFoundError as error:
            logging.critical("ffmpeg.exe:" + str(error))
            self._restore()
            sys.exit(1)
        if self.result == 0:
            os.remove(self.backupFilepath)
        else:
            logging.error(f"{self.filepath}: failed encoding")
            # failedFilepaths.append(self.filepath)
            self._restore()
        return self.result


def convert_files(convertFilepaths, library):
    failedFilepaths = []
    spaceSaved = 0
    exitcode = 0
    # Can't be changes whilst iterating dicts
    for filepath in convertFilepaths:

        logging.debug(filepath)
        libraryEntry = library.library["incomplete_files"][filepath]

        # check json db if encoded before running encoder
        try:
            if libraryEntry["video_codec"] == "hevc" and libraryEntry["video_profile"] == "Main":
                continue
        except KeyError:
            continue

        encoder = X265Encoder(filepath)
        encodeResult = encoder.encode()
        if encodeResult == 0:
            library.markComplete(filepath)
            fileSpaceSaved = library.library["complete_files"][os.path.splitext(filepath)[0] + ".mkv"]["space_saved"]
            spaceSaved += fileSpaceSaved
            logging.info(f"Space saved: {fileSpaceSaved // 1024**2}MB")
        else:
            logging.error(f"ffmpeg failed with error: {encodeResult}")
            library.markFailed(filepath, encodeResult)
            failedFilepaths.append(filepath)

    if len(failedFilepaths) > 0:
        exitcode = 1
        logging.warning("Some files failed, recommended manual conversion")
        for filename in failedFilepaths:
            logging.warning(f"failed: {filename}")
    logging.info(f"completed. space saved this run: {spaceSaved // 1024**2}MB")
    sys.exit(exitcode)


def main():
    """main loop to reduce globals"""
    # argparse
    parser = argparse.ArgumentParser(
        description="""
A file conversion utility that will attempt to convert files in
media directories to HEVC content with the priority of saving disk space.
"""
    )
    parser.add_argument("--path", "-p", action="append", help="add new path(s) to library")
    parser.add_argument("--number", "-n", action="store", help="number of files", type=int)
    parser.add_argument("--scan", "-s", action="store_true", help="scan media")
    parser.add_argument("--list", "-l", "--listpaths", action="store_true", help="list paths")
    parser.add_argument("--list-errors", "-le", action="store_true", dest="list_errors", help="list errors")
    parser.add_argument("--focus", "-f", action="append", help="convert a specific directory/directories now")
    parser.add_argument("--low-profile", action="store_true", dest="low_profile", help="low profile processing")
    parser.add_argument("--verbose", "-v", action="count", help="increase output verbosity")
    parser.add_argument("--quiet", "-q", action="store_true", help="quiet mode (stdout)")
    parser.add_argument(
        "--logfile", action="store", help="specify log filename, default is log.txt", type=str, default="log.txt"
    )

    args = parser.parse_args()
    scriptdir = os.path.dirname(os.path.abspath(sys.argv[0]))
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    # NOTE: low_profile does nothing yet
    # low_profile = args.low_profile

    if args.verbose is None:
        logginglevel = logging.WARNING
    elif args.verbose == 1:
        logginglevel = logging.INFO
        console.setLevel(logging.INFO)
    elif args.verbose >= 2:
        logginglevel = logging.DEBUG
        console.setLevel(logging.DEBUG)
    else:
        logginglevel = logging.WARNING

    if args.quiet is True:
        logginglevel = logging.CRITICAL
        console.setLevel(logging.CRITICAL)

    logging.basicConfig(
        filename=scriptdir + "/" + args.logfile,
        level=logginglevel,
        format="%(asctime)s %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
    )

    formatter = logging.Formatter("%(name)-12s: %(levelname)-8s %(message)s")
    # tell the handler to use this format
    console.setFormatter(formatter)
    # add the handler to the root logger
    logging.getLogger("").addHandler(console)

    library = MediaLibrary()
    convertFilepaths = []

    if args.number:
        convertFilepaths = library.returnLibraryEntries(args.number)
        convert_files(convertFilepaths, library)
    elif args.focus:
        for directory in args.focus:
            convertFilepaths = library.returnDirectory(directory)
            convert_files(convertFilepaths, library)
    elif args.path:
        for path in args.path:
            library.addNewPath(os.path.abspath(path))
    elif args.scan:
        for fp in library.listPaths():
            library.scan(fp)
    elif args.list:
        pprint(library.library["paths"])
    elif args.list_errors:
        library.showFailed()


if __name__ == "__main__":
    main()
