#!/usr/bin/env python3
import glob
import logging
import sys
import subprocess
import os

from library import mediaTracker
from library import logger

class X265Encoder:
    def __init__(self, filepath):
        self.filepath = filepath
        self.filepathBase = os.path.splitext(self.filepath)[0]
        self.backupFilepath = self.filepath + ".bk"
        self.outputFilepath = self.filepathBase + ".mkv"
        self.low_profile = False
        self.log = logger.setup_logging()

    def _backup(self):
        if os.path.isfile(self.backupFilepath):
            os.remove(self.backupFilepath)
        os.rename(self.filepath, self.backupFilepath)
        if os.path.isfile(self.backupFilepath):
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

    def _commandString(self):
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
        return self.command

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
            self.subtitleFile = mediaTracker.VideoInformation(subtitle)
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

    def _subtitlePaths(self):
        self.subtitleExtensions = [".ass", ".ssa", ".sub", ".srt"]
        self.subtitleFiles = []
        for extension in self.subtitleExtensions:
            # glob chokes on '[]', escape [ and ]
            self.pattern = f"{self.filepathBase}*{extension}"
            self.pattern = self.pattern.translate({ord("["): "[[]", ord("]"): "[]]"})
            self.subtitleFiles += glob.glob(self.pattern)
        return self.subtitleFiles

    def _validateNewFile(self, filepath):
        """ Perform some checks on output file to check whether the transcode worked
            returns False if there is a problem, true otherwise"""
        if not os.path.exists(filepath):
            return False
        if os.path.getsize(filepath) == 0:
            return False
        return True

    def encode(self):

        if not self._checkValid():
            return "invalid file"

        self.file = mediaTracker.VideoInformation(self.filepath)
        if self.low_profile is True:
            self.file.low_profile = True
        self.file.analyze()

        if self.file.isEncoded():
            alreadyX265 = (f'{self.filepath} already encoded,'
                           'moved to completed without doing anything')
            self.log.error(alreadyX265)
            return "already encoded"

        self._backup()

        self.command = self._commandString()
        print(" ".join(self.command) + "\n")
        try:
            self.result = subprocess.call(self.command)
        except KeyboardInterrupt:
            self.log.info("cleaning up")
            self.log.error("Keyboard interrupt")
            self._restore()
            sys.exit()

        if self.result != 0:
            ffmpegError = (f"failed encoding {self.filepath}, FFMPEG error {self.result}")
            self.log.error(ffmpegError)
            self._restore()
            return ffmpegError
        elif not self._validateNewFile(self.outputFilepath):
            ffmpegError = (f"failed {self.outputFilepath}, validateNewFile failed")
            self.log.error(ffmpegError)
            self._restore()
            return "failed"
        else:
            os.remove(self.backupFilepath)
            return "success"
