#!/usr/bin/env python3
import os
import json
import sys
import subprocess

from library import logger

class VideoInformation:
    def __init__(self, fp):
        self.filepath = fp
        self.low_profile = False
        self.log = logger.setup_logging()

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
    def __init__(self, databasePath):
        self.log = logger.setup_logging()
        self.libraryFilePath = (os.path.abspath(databasePath))
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
        if not os.path.exists(os.path.dirname(self.libraryFilePath)):
            os.makedirs(os.path.dirname(self.libraryFilePath), exist_ok=True)
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
        for root, _, files in os.walk(path):
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
        for _ in range(count):
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