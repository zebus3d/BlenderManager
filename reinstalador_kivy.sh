#!/bin/bash

sudo apt-get remove --purge python3-kivy
sudo pip3 uninstall cython kivy
sudo apt autoremove
sudo apt-get install python3.7 build-essential

sudo pip3 install Cython==0.28.6
sudo pip3 install kivy==1.10.1