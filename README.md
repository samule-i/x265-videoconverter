# x265-converter
A python3 script to track and convert media to HEVC format

# big warning!

This script converts to hevc 4-bit mode by default, because that is what my player can handle at the moment, I will be changing to 10-bit or just letting defaults take over, but if you want to change to 10-bit you need to edit the source where it specifies `pix_fmt yuv420` and `stream["profile"] != Main`.  
Also, possibly where `libraryEntry["video_profile"] == 'Main'` comes up.

# example usage:

`main.py -p /path/to/media` adds a new path for scanning  
`main.py -s` scans and adds to db  
`main.py -n 10` converts 10 files to x265  
`main.py -e` shows errors that have occurred  
`main.py -l` lists tracked directories  
`main.py --focus-directory /path/to/media` converts a directory now if you don't want to wait until it's gotten there in the queue  
`main.py -n 4 --focus-directory /path/to/media` should behave as expected.  
