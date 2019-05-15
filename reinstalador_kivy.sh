#!/bin/bash

# Estoy usando Python 3.6.7
# Estoy usando kyvy 1.10.1

sudo apt-get remove --purge python3-kivy
sudo pip3 uninstall cython kivy
sudo apt autoremove
sudo apt-get install python3.7 build-essential

pip install --upgrade pip --user
pip3 install Cython==0.28.6
pip3 install kivy==1.10.1