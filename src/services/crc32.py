import zlib


def crc32_checker(fileName):
    prev = 0
    for eachLine in open(fileName,"rb"):
        prev = zlib.crc32(eachLine, prev)
    return "%X"%(prev & 0xFFFFFFFF)


crc = crc32_checker('../data/settings.cfg')
print(crc)