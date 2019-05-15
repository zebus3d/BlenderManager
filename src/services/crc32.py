import zlib
import os

def crc32_checker(fileName):
    if os.path.isfile(fileName):
        prev = 0
        for eachLine in open(fileName,"rb"):
            prev = zlib.crc32(eachLine, prev)
        return "%X"%(prev & 0xFFFFFFFF)
    else:
        print("No se encontro el archivo: " + str(fileName))


crc = crc32_checker('../../data/settings.cfg')
if crc:
    print(crc)