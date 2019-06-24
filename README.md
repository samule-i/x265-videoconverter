# x265-converter
A python3 script to track and convert media to HEVC format

#example usage:

`main.py -p /path/to/media` adds a new path for scanning
`main.py -s` scans and adds to db
`main.py -n 10` converts 10 files to x265
`main.py -e` shows errors that have occurred
`main.py -l` lists tracked directories
`main.py --focus-directory /path/to/media` converts a directory now if you don't want to wait until it's gotten there in the queue
`main.py -n 4 --focus-directory /path/to/media` should behave as expected.
