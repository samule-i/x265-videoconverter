#!/usr/bin/env python3
import os
import json
import sys
import subprocess

from library import logger

class VideoInformation:
    def __init__(self, fp, args):
        self.filepath = fp
        self.low_profile = False
        self.height = False
        if args.verbose:
            self.log = logger.setup_logging(None, "DEBUG")
        elif args.quiet:
            self.log = logger.setup_logging(None, "CRITICAL")
        else:
            self.log = logger.setup_logging(None)        

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
            elif self.height and stream["height"] != self.height:
                return False
            elif stream["profile"] != "Main" and self.low_profile is True:
                return False
            else:
                return True

    def simpleEntry(self):
        self.entry = {}
        try:
            self.entry["video_codec"] = self.videoStreams[0]["codec_name"]
            self.entry["height"] = self.videoStreams[0]["height"]
            self.entry["width"] = self.videoStreams[0]["width"]
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

    def advEntry(self):
        try:
            self.entry["bit_rate"] = int(self.ffprobe["format"]["bit_rate"]) / 1000
        except IndexError:
            self.entry["bit_rate"] = None
            return False


class MediaLibrary:
    def __init__(self, databasePath, args):
        self.low_profile = False
        self.height = False
        self.rate_threshold = False
        self.rate_ceiling = False
        self.height_threshold = False
        self.height_ceiling = False
        self.force_encode = False
        if args.verbose:
            self.log = logger.setup_logging(None, "DEBUG")
        elif args.quiet:
            self.log = logger.setup_logging(None, "CRITICAL")
        else:
            self.log = logger.setup_logging(None)        
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
            ".m4v"
        ]
        if not os.path.exists(os.path.dirname(self.libraryFilePath)):
            os.makedirs(os.path.dirname(self.libraryFilePath), exist_ok=True)
        if not os.path.isfile(self.libraryFilePath):
            self.log.info(f" No medialibrary found, creating new library")
            self.library = {}
            self.library["paths"] = []
            self.library["blacklist"] = []
            self.library["incomplete_files"] = {}
            self.library["skipped_files"] = {}
            self.library["complete_files"] = {}
            self.library["failed_files"] = {}
            self.library["space_saved"] = 0
            self._libraryCommit()
        print("loading library")
        with open(self.libraryFilePath) as jsonFile:
            self.library = json.load(jsonFile)

    def scan(self, path, args):
        """Searching through files in path that are not in database.
           ffprobe them and add metadata to database."""
        self.log.info(f" MediaLibrary scanning {path}")
        for root, _, files in os.walk(path):
            root_valid = True
            for blacklist_entry in self.library["blacklist"]:
                if blacklist_entry in root:
                    self.log.debug( f'{root} is within blacklisted folder {blacklist_entry}')
                    root_valid = False
                    break
            if not root_valid:
                continue 
            for name in files:
                if str.lower(os.path.splitext(name)[1]) not in self.videoFileTypes:
                    self.log.debug(f'{name} is not a video')
                    continue
                self.filepath = os.path.join(root, name)

                if (
                    self.filepath in self.library["incomplete_files"]
                    or self.filepath in self.library["complete_files"]
                    or self.filepath in self.library["failed_files"]
                ):
                    self.log.debug(f'{name} is already tracked')
                    continue
                if ( self.filepath in self.library["skipped_files"] ):
                    self.log.debug(f'{name} is already skipped')
                    continue

                # Windows path limit. Fatal
                if len(self.filepath) > 255:
                    continue
                print(self.filepath)

                self.info = VideoInformation(self.filepath,args)
                self.info.low_profile = self.low_profile
                self.info.height = self.height
                self.analyzeResult = self.info.analyze()
                if self.analyzeResult is False:
                    error = f"VideoInformation failed reading {self.filepath}"
                    self.log.critical(error)
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
                try:
                    self.info.advEntry()
                except KeyError as error:
                    print(json.dumps(self.info.ffprobe, indent=2))
                    return

                if (self.rate_threshold and self.entry["bit_rate"] < self.rate_threshold ):
                    self.library["skipped_files"][self.filepath] = self.entry
                    self.log.info(f'{self.entry["width"]}x{self.entry["height"]} @ {self.entry["bit_rate"]}kbps -- Skipping File, below the bit rate threshold')
                elif (self.rate_ceiling and self.entry["bit_rate"] > self.rate_ceiling ):
                    self.library["skipped_files"][self.filepath] = self.entry
                    self.log.info(f'{self.entry["width"]}x{self.entry["height"]} @ {self.entry["bit_rate"]}kbps -- Skipping File, above the bit rate ceiling')
                elif (self.height_threshold and self.entry["height"] < self.height_threshold ):
                    self.library["skipped_files"][self.filepath] = self.entry
                    self.log.info(f'{self.entry["width"]}x{self.entry["height"]} @ {self.entry["bit_rate"]}kbps -- Skipping File, below the height threshold')
                elif (self.height_ceiling and self.entry["height"] > self.height_ceiling ):
                    self.library["skipped_files"][self.filepath] = self.entry
                    self.log.info(f'{self.entry["width"]}x{self.entry["height"]} @ {self.entry["bit_rate"]}kbps -- Skipping File, above the height ceiling')
                elif (self.info.isEncoded() and not self.force_encode):
                    self.library["complete_files"][self.filepath] = self.entry
                    self.library["complete_files"][self.filepath]["original_codec"] = "hevc"
                    self.library["complete_files"][self.filepath]["space_saved"] = 0
                    self.log.debug(f'{self.entry["width"]}x{self.entry["height"]} @ {self.entry["bit_rate"]}kbps -- File is already encoded in HEVC')
                elif (self.force_encode):
                    self.library["incomplete_files"][self.filepath] = self.entry
                    self.log.info(f'{self.entry["width"]}x{self.entry["height"]} @ {self.entry["bit_rate"]}kbps -- Adding to tracked list as forced HEVC re-encode')
                else:
                    self.library["incomplete_files"][self.filepath] = self.entry
                    self.log.info(f'{self.entry["width"]}x{self.entry["height"]} @ {self.entry["bit_rate"]}kbps -- Adding to tracked list')
                
        self._libraryCommit()
        self.log.info("Scan completed")

    def markComplete(self, inputfp, outputfp=None):
        """Move entry from incomplete_files to complete_files."""
        if outputfp is None:
            outputfp = inputfp
        self.log.info(f"Completed transcoding {outputfp}")
        self.newEntry = self.library["incomplete_files"].pop(inputfp)

        try:
            self.newSize = os.path.getsize(outputfp)
        except FileNotFoundError:
            self.log.error("File not found, assuming filename character encoding error")
            self.newSize = self.newEntry["file_size"]

        self.spaceSaved = int(self.newEntry["file_size"]) - int(self.newSize)
        self.newEntry["original_video_codec"] = self.newEntry["video_codec"]
        self.newEntry["video_codec"] = "hevc"
        self.newEntry["video_profile"] = "Main"
        self.newEntry["space_saved"] = self.spaceSaved
        self.newEntry["file_size"] = self.newSize
        self.library["complete_files"][outputfp] = self.newEntry
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

    def clearAll(self):
        """Clear all file lists."""
        self.library["skipped_files"] = {}
        self.library["incomplete_files"] = {}
        self.library["complete_files"] = {}
        self.library["failed_files"] = {}
        self._libraryCommit()

    def clearSkipped(self):
        """Clear the skipped file list."""
        self.library["skipped_files"] = {}
        self._libraryCommit()

    def clearIncomplete(self):
        """Clear the incomplete file list."""
        self.library["incomplete_files"] = {}
        self._libraryCommit()

    def clearComplete(self):
        """Clear the complete file list."""
        self.library["complete_files"] = {}
        self._libraryCommit()

    def clearFailed(self):
        """Clear the failed file list."""
        self.library["failed_files"] = {}
        self._libraryCommit()

    def addBlacklistPath(self, filepath):
        """Create a new blacklist path entry in library."""
        self.mediaDirectory = os.path.abspath(filepath)
        if not os.path.isdir(filepath):
            self.log.error(f"invalid directory {filepath}")
            sys.exit(2)
        if self.mediaDirectory not in self.library["blacklist"]:
            self.log.info(f" Adding new blacklist path {self.mediaDirectory}")
            self.library["blacklist"].append(self.mediaDirectory)
        self._libraryCommit()

    def listPaths(self):
        """List tracked paths stored in library."""
        return self.library["paths"]

    def listBlacklistPaths(self):
        """List blacklist paths stored in library."""
        return self.library["blacklist"]

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
            jsonFile.write(json.dumps(self.library,indent=2))
