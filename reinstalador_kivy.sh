#!/bin/bash

# Estoy usando Python 3.6.7
# Estoy usando kyvy 1.10.1
# Estoy usando Cython 0.28.6

sudo apt-get remove --purge python3-kivy
#pip install --upgrade pip --user
sudo pip3 uninstall cython kivy
sudo apt autoremove

sudo add-apt-repository ppa:kivy-team/kivy
sudo apt-get update
sudo apt-get install python3.7 python3-pip build-essential python3-kivy python3-sdl2