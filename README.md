# Changes in this fork
Variable Bit Rate added to allow for controlling the quality of NVENC  
Threshold and Ceiling for scanning for both Bit Rate and Height of the video, allow to selectively pick which files to add to the encode list  
Add commands for clearing the different lists of files  
Skipped file list of files which did not meet the thresholds or ceilings, to allow to be easily purged when ready to change parameters

# x265-converter
A database focused media conversion utility that converts video files to the
HEVC video codec with a focus on reducing disk usage in media libraries. This
script attempts to be as safe as possible, however encoding to HEVC is a lossy
operation. though it should be unnoticable it is recommended to test first.
Backups are encouraged.

# requirements:
x265-videoconverter needs python3 and ffmpeg
The latest version of ffmpeg is 4.1.4 when testing, download from [ffmpeg](https://ffmpeg.org/download.html).

# typical usage:
    main.py -t /path/to/media -s
    main.py -n 10

# usage for compression
Both of these examples are utilizing the NVENC option, which will speed up the encoding process drastically

Here we can use it to compress a video library to a smaller frame size, ensuring only to compress files which are not already low bitrate

    main.py -t /path/to/media -s --height-threshold 1080 --rate-threshold 1000 --force-encode
    main.py -n 10 --height 720 --nvenc --vbr 1000k --minrate 400k --maxrate 1600k

Or use it to compress files with low resolution, making sure to only add files below SDTV

    main.py -t /path/to/media -s --height-ceiling 480 --force-encode
    main.py -n 10 --nvenc --vbr 300k --minrate 100k --maxrate 800k

# comparison
Original:
![original](https://github.com/formcore/x265-videoconverter/blob/master/video_examples_output/x264%20to%20x265%20original.png?raw=true)

Transcoded:
![transcoded](https://github.com/formcore/x265-videoconverter/blob/master/video_examples_output/x264%20to%20x265%20output.png?raw=true)


# example usage:

    usage: main.py [-h] [--crf int] [--errors] [--database DATABASE] [--focus PATH] [--list-paths] [--list-blacklist-paths] [--low-profile] [--number NUMBER]  
                [--nvenc] [--height HEIGHT] [--preset PRESET] [--track PATH] [--blacklist PATH] [--saved-space] [--scan] [--quiet] [--verbose] [--vbr VBR]  
                [--minrate MINRATE] [--maxrate MAXRATE] [--rate-threshold RATE_THRESHOLD] [--rate-ceiling RATE_CEILING] [--height-threshold HEIGHT_THRESHOLD]  
                [--height-ceiling HEIGHT_CEILING] [--force-encode] [--clear-all] [--clear-skipped] [--clear-incomplete] [--clear-complete] [--clear-failed]  

    A database focused media conversion utility that converts video files to the HEVC video codec with a focus on reducing disk usage in media libraries. This  
    script attempts to be as safe as possible, however encoding to HEVC is a lossy operation. though it should be unnoticeable it is recommended to test first.  
    Backups are encouraged.  

    optional arguments:
    -h, --help            show this help message and exit  
    --crf int             CRF parameter to be passed through to ffmpeg, determines quality and speed with lower values being slower but higher quality (not  
                            for NVENC)  
    --errors, -e          list errors  
    --database DATABASE   name of database to be used  
    --focus PATH, -f PATH  
                            immediately begin conversion on target directory  
    --list-paths, -lp     list tracked paths  
    --list-blacklist-paths, -lbp  
                            list blacklisted paths  
    --low-profile         for weaker devices, convert to 4-bit HEVC including downgrading 10-bit hevc  
    --number NUMBER, -n NUMBER  
                            transcode from tracked paths limit number of files to be converted  
    --nvenc               transcode using NVENC compatible GPU  
    --height HEIGHT       Height of the output resolution to be used for conversion  
    --preset PRESET       string for ffmpeg paramater, accepts ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow and placebo,  
                            slower speeds have a higher filesize and better quality  
    --track PATH, -t PATH  
                            add a new path to be tracked  
    --blacklist PATH, -b PATH  
                            add a blacklist path to be excluded from scans  
    --saved-space         display HDD space saved by transcoding into x265  
    --scan, -s            scan tracked directories for new files  
    --quiet, -q           only produce minimal output  
    --verbose, -v         produce as much output as possible  
    --vbr VBR             Set the Variable Bitrate for the encoding pass, this will adjust NVENC quality  
    --minrate MINRATE     Set the minimum rate for Variable Bitrate mode  
    --maxrate MAXRATE     Set the maximum rate for Variable Bitrate mode  
    --rate-threshold RATE_THRESHOLD  
                            Set the minimum kbps files must have in order to add to processing list during scan  
    --rate-ceiling RATE_CEILING  
                            Set the maximum kbps files can have in order to add to processing list during scan  
    --height-threshold HEIGHT_THRESHOLD  
                            Set the minimum height files must have in order to add to processing list during scan  
    --height-ceiling HEIGHT_CEILING  
                            Set the maximum height files can have in order to add to processing list during scan  
    --force-encode        force HEVC re-encode  
    --clear-all           clear the library of all files  
    --clear-skipped       clear the library of skipped files  
    --clear-incomplete    clear the library of incomplete files  
    --clear-complete      clear the library of complete files  
    --clear-failed        clear the library of failed files  