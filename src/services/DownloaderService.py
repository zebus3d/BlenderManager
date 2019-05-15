from bs4 import BeautifulSoup
from urllib.request import urlopen
from src.model.BlenderFile import BlenderFile


class DownloaderService:

    def __init__(self):
        pass

    def getAvaibleVersions(self):

        url = "https://download.blender.org/release/"
        tmpResult = []

        html_page = urlopen(url)
        soup = BeautifulSoup(html_page)
        for link in soup.findAll('a'):

            blendName = link.get('href')[:-1]

            if str.startswith(blendName, 'Blender'):
                bf = BlenderFile(blendName)
                bf.version = blendName[7:11]
                tmpResult.append(bf)

        for item in tmpResult:

            print(str(item.name) + "  " + str(item.version) + " " + str(item.builds))
