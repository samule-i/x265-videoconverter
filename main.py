#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import time
import sys

from library import mediaTracker
from library import videoEncoder
from library import logger

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
    parser.add_argument("--database", action="store", help="name of database to be used")
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
        log = logger.setup_logging(logDirectory, "DEBUG")
    elif args.quiet:
        log = logger.setup_logging(logDirectory, "CRITICAL")
    else:
        log = logger.setup_logging(logDirectory)

    databaseDir = os.path.abspath(os.path.dirname(sys.argv[0])) + "/database"
    if args.database:
        databasePath = databaseDir + "/" + args.database + ".json"
    else:
        databasePath = databaseDir + "/library.json"

    library = mediaTracker.MediaLibrary(databasePath)

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

        encoder = videoEncoder.X265Encoder(filepath)
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
