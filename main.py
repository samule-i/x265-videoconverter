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
    a lossy operation. though it should be unnoticeable it is recommended to test
    first. Backups are encouraged.
    """)
    parser = argparse.ArgumentParser(description=scriptDescription, allow_abbrev=False)

    parser.add_argument("--crf", action="store", metavar="int", type=int,
        help="CRF parameter to be passed through to ffmpeg, determines quality and speed with lower values being slower but higher quality (not for NVENC)")
    parser.add_argument("--errors", "-e", action="store_true", help="list errors")
    parser.add_argument("--database", action="store", help="name of database to be used")
    parser.add_argument("--focus", "-f", action="append", metavar="PATH", help="immediately begin conversion on target directory")
    parser.add_argument("--list-paths", "-lp", action="store_true", help="list tracked paths")
    parser.add_argument("--list-blacklist-paths", "-lbp", action="store_true", help="list blacklisted paths")
    parser.add_argument("--low-profile", action="store_true", help="for weaker devices, convert to 4-bit HEVC including downgrading 10-bit hevc", default=False)
    parser.add_argument("--number", "-n", action="store", help="transcode from tracked paths limit number of files to be converted", type=int)
    parser.add_argument("--nvenc", action="store_true", help="transcode using NVENC compatible GPU")
    parser.add_argument("--height", action="store", type=int, help="Height of the output resolution to be used for conversion")
    parser.add_argument("--preset", action="store", type=str,
        help="string for ffmpeg paramater, accepts ultrafast, superfast, veryfast, faster, fast, medium, slow, slower,\
             veryslow and placebo, slower speeds have a higher filesize and better quality")
    parser.add_argument("--track", "-t", action="append", metavar="PATH", help="add a new path to be tracked")
    parser.add_argument("--blacklist", "-b", action="append", metavar="PATH", help="add a blacklist path to be excluded from scans")
    parser.add_argument("--saved-space", action="store_true", help="display HDD space saved by transcoding into x265")
    parser.add_argument("--scan", "-s", action="store_true", help="scan tracked directories for new files")
    parser.add_argument("--quiet", "-q", action="store_true", help="only produce minimal output")
    parser.add_argument("--verbose", "-v", action="store_true", help="produce as much output as possible")
    parser.add_argument("--vbr", action="store", type=str, help="Set the Variable Bitrate for the encoding pass, this will adjust NVENC quality")
    parser.add_argument("--minrate", action="store", type=str, help="Set the minimum rate for Variable Bitrate mode")
    parser.add_argument("--maxrate", action="store", type=str, help="Set the maximum rate for Variable Bitrate mode")
    parser.add_argument("--rate-threshold", action="store", type=int, help="Set the minimum kbps files must have in order to add to processing list during scan")
    parser.add_argument("--rate-ceiling", action="store", type=int, help="Set the maximum kbps files can have in order to add to processing list during scan")
    parser.add_argument("--height-threshold", action="store", type=int, help="Set the minimum height files must have in order to add to processing list during scan")
    parser.add_argument("--height-ceiling", action="store", type=int, help="Set the maximum height files can have in order to add to processing list during scan")
    parser.add_argument("--force-encode", action="store_true", help="force HEVC re-encode")
    parser.add_argument("--clear-all", action="store_true", help="clear the library of all files")
    parser.add_argument("--clear-skipped", action="store_true", help="clear the library of skipped files")
    parser.add_argument("--clear-incomplete", action="store_true", help="clear the library of incomplete files")
    parser.add_argument("--clear-complete", action="store_true", help="clear the library of complete files")
    parser.add_argument("--clear-failed", action="store_true", help="clear the library of failed files")

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

    library = mediaTracker.MediaLibrary(databasePath, args)

    if args.force_encode:
        library.force_encode = True

    if args.rate_threshold:
        library.rate_threshold = args.rate_threshold

    if args.rate_ceiling:
        library.rate_ceiling = args.rate_ceiling

    if args.height_threshold:
        library.height_threshold = args.height_threshold

    if args.height_ceiling:
        library.height_ceiling = args.height_ceiling

    if args.low_profile:
        library.low_profile = True

    if args.height:
        library.height = args.height

    if args.errors:
        library.showFailed()
        sys.exit()

    if args.list_paths:
        print(library.listPaths())
        sys.exit()

    if args.list_blacklist_paths:
        print(library.listBlacklistPaths())
        sys.exit()

    if args.clear_all:
        library.clearAll()
        print('All file lists have been cleared')
        sys.exit()

    if args.clear_skipped:
        library.clearSkipped()
        print('Skipped file list has been cleared')
        sys.exit()

    if args.clear_incomplete:
        library.clearIncomplete()
        print('Incomplete file list has been cleared')
        sys.exit()

    if args.clear_complete:
        library.clearComplete()
        print('Complete file list has been cleared')
        sys.exit()

    if args.clear_failed:
        library.clearFailed()
        print('Failed file list has been cleared')
        sys.exit()

    if args.track:
        for path in args.track:
            library.addNewPath(os.path.abspath(path))

    if args.blacklist:
        for path in args.blacklist:
            library.addBlacklistPath(os.path.abspath(path))

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
            library.scan(fp, args)

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
            matchLow = args.low_profile and libraryEntry["video_profile"] == "Main"
            matchHigh = not args.low_profile
            if libraryEntry["video_codec"] == "hevc" and (matchLow or matchHigh) and (not args.height or args.height == libraryEntry["height"]):
                library.markComplete(filepath)
                continue
        except KeyError:
            continue

        encoder = videoEncoder.X265Encoder(filepath)
        if args.low_profile:
            encoder.low_profile = True
        if args.nvenc:
            encoder.nvenc = True
        if args.height:
            encoder.height = args.height
        if args.crf:
            if 0 < args.crf < 51:
                encoder.crf = args.crf
            else:
                raise ValueError("CRF value unacceptable, must be between 0 and 51")
        if args.preset:
            validPresets = ["ultrafast", "superfast", "veryfast",
                            "faster", "fast", "medium", "slow",
                            "slower", "veryslow", "placebo"]
            nvencPresets = ["fast", "medium", "slow"]
            preset = args.preset.lower()
            if preset in validPresets:
                if args.nvenc and args.preset.lower() not in nvencPresets:
                    log.error("invalid nvenc preset passed with nvenc selected, please use fast, medium, or slow")
                    sys.exit()
                encoder.preset = preset
            else:
                raise ValueError("preset not a valid argument, please use ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow or placebo")
        if args.height:
            encoder.height = args.height
        if args.vbr:
            encoder.vbr = args.vbr
            if args.minrate:
                encoder.minrate = args.minrate
            if args.maxrate:
                encoder.maxrate = args.maxrate
            
        try:
            encodeResult = encoder.encode()
        except videoEncoder.AlreadyEncodedError:
            library.markComplete(filepath)
            continue
        except (videoEncoder.InvalidFileError, videoEncoder.EncoderFailedError) as e:
            failedFilepaths.append(filepath)
            errorMessage = f"x265 convert failed with error: {e}"
            library.markFailed(filepath, errorMessage)
            continue

        library.markComplete(filepath, encodeResult)
        fileSpaceSaved = library.library["complete_files"][encodeResult]["space_saved"]
        spaceSaved += fileSpaceSaved
        elapsedTime = time.time() - beginTime
        totalElapsedTime = totalElapsedTime + elapsedTime
        elapsedTimeString = time.strftime("%H:%M:%S", time.localtime(elapsedTime))
        log.info(f"space saved {fileSpaceSaved/1_000_000} : time taken {elapsedTimeString}.")

    if len(failedFilepaths) > 0:
        log.warning("Some files failed, recommended manual conversion")
        for filename in failedFilepaths:
            log.warning(f" failed: {filename}")
    totalElapsedTimeString = time.strftime("%H:%M:%S", time.localtime(totalElapsedTime))
    log.info(f"time taken {totalElapsedTimeString}")
    log.info(f"space saved this run: {int(spaceSaved/1_000_000)}mb")


if __name__ == "__main__":
    main()
