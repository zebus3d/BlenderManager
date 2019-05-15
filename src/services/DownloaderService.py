from bs4 import BeautifulSoup
from urllib.request import urlopen

import re

import os
print(os.getcwd())

# from src.model.BlenderFile import BlenderFile

import sys
sys.path.insert(0, 'src/model/')
from BlenderFile import BlenderFile

class DownloaderService:

    def __init__(self):
        pass

    def getAvaibleVersions(self):

        url = "https://download.blender.org/release/"
        blendObj = []

        html_page = urlopen(url)
        soup = BeautifulSoup(html_page)

        regexRule = '(Blender[0-9].[0-9]*).*( [0-9]*-[a-zA-Z]*-[0-9]* [0-9]*:[0-9]*)'

        data = re.findall(regexRule, str(soup))
        print(data)


        # for link in soup.findAll('a'):

        #     blendName = link.get('href')[:-1]

        #     print(blendName)

        #     if blendName.startswith('Blender'):
        #         if not "Benchmark" in blendName:
        #             bf = BlenderFile(blendName)
        #             bf.version = blendName[7:11]
        #             blendObj.append(bf)

        # for item in blendObj:
        #     print(str(item.name) + "  " + str(item.version) + " " + str(item.builds))


if __name__ == "__main__":    
    test = DownloaderService()
    test.getAvaibleVersions()