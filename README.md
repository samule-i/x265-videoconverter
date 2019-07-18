# x265-converter
A database focused media conversion utility that converts video files to the
HEVC video codec with a focus on reducing disk usage in media libraries. This
script attempts to be as safe as possible, however encoding to HEVC is a lossy
operation. though it should be unnoticable it is recommended to test first.
Backups are encouraged.

# typical usage:
    main.py -t /path/to/media -s
    main.py -n 10

# example usage:

    main.py [-h] [--errors] [--focus PATH] [--list-paths] [--low-profile]
                   [--number NUMBER] [--track PATH] [--scan]
                   
    optional arguments:
      -h, --help            show this help message and exit
      --errors, -e          list errors
      --focus PATH, -f PATH
                            immediately begin conversion on target directory
      --list-paths, -lp     list tracked paths
      --low-profile         for weaker devices, convert to 4-bit HEVC including
                            downgrading 10-bit hevc
      --number NUMBER, -n NUMBER
                            transcode from tracked paths limit number of files to
                            be converted
      --track PATH, -t PATH
                            add a new path to be tracked
      --scan, -s            scan tracked directories for new files
